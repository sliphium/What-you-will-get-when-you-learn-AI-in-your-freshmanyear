import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
import json
import re
import hashlib
import urllib.parse
import urllib.request
import chromadb
import ast
import logging
import operator
logging.basicConfig(level=logging.INFO,format='%(asctime)s - %(levelname)s - %(message)s')
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from duckduckgo_search import DDGS


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger = logging.getLogger("agent")
logger.setLevel(logging.INFO)
_handler = logging.FileHandler(os.path.join(LOG_DIR, "app.log"), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(_handler)

MAX_HISTORY=int(os.getenv("MAX_HISTORY","40"))
MAX_HISTORY_CHARS=int(os.getenv("MAX_HISTORY_CHARS","40000"))

def _drop_oldest_turn(body):
    if len(body)<=1:
        return []
    i=1
    while i<len(body) and body[i].get("role")!="user":
        i+=1
    return body[i:] if i<len(body) else []
    
def  trim_history(messages,MAX_MESSAGES=MAX_HISTORY,MAX_CHARS=MAX_HISTORY_CHARS):
    if not messages:
        return messages
    system=messages[0] if messages[0].get("role")=="system" else None
    body=messages[1:] if system else list(messages)
    
    while len(body)>MAX_MESSAGES:
        body=_drop_oldest_turn(body)
        
    def  total_size(items):
        return sum(len(str(m.get("content")or" "))for m in items)

    while len(body)>1 and total_size(body)> MAX_CHARS:
        body=_drop_oldest_turn(body)
    return ([system]if system else[])+body

OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv,ast.FloorDiv:operator.floordiv,
    ast.Pow: operator.pow,ast.Mod:operator.mod
}
def safe_eval(node):
    if isinstance(node,ast.Constant):
        if not isinstance(node.value,(int,float)) or isinstance(node.value,bool):
            raise ValueError("只支持数字")
        return node.value
        
    if isinstance(node,ast.UnaryOp):
        value=safe_eval(node.operand)
        if isinstance(node.op,ast.UAdd): return +value
        if isinstance(node.op,ast.USub): return -value
        raise ValueError("不支持的一元运算")
    
    if isinstance(node,ast.BinOp) and type(node.op) in OPERATORS:
        left=safe_eval(node.left)
        right=safe_eval(node.right)
        if isinstance(node.op,ast.Pow) and abs(right) >100:
            raise ValueError("指数过大")
        return OPERATORS [type(node.op)](left,right)
    raise ValueError("不支持的运算") 
def calculator(expression):
    try:
        return str(safe_eval(ast.parse(expression,mode="eval").body))
    except Exception:
        return "算不出来呜，表达式写错了或包含非法字符！"

def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _format_results(results, limit):
    import html as _html

    lines = []
    for r in results[:limit]:
        title = _html.unescape((r.get("title") or "").strip())
        body = _html.unescape((r.get("body") or "").strip().replace("\n", " "))
        href = (r.get("href") or "").strip()
        lines.append(f"- {title}: {body}（{href}）")
    return "\n".join(lines)

def _bing_search(query, max_results=3):
    url="https://cn.bing.com/search?" + urllib.parse.urlencode({"q": query})
    req=urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    html=urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
    print(f"📏 [爬虫测试] 抓到的网页长度: {len(html)}")
    print(f"🔍 [爬虫测试] 前100个字符: {html[:100]}") 
    items=re.findall(r'<li class="b_algo".*?</li>', html, re.S)
    print(f"📦 [爬虫测试] 正则匹配到的条目数: {len(items)}")
    items= re.findall(r'<li class="b_algo".*?</li>', html, re.S)
    out = []
    for it in items:
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', it, re.S)
        if not m:
            continue
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        p = re.search(r"<p[^>]*>(.*?)</p>", it, re.S)
        body = re.sub(r"<[^>]+>", "", p.group(1)).strip() if p else ""
        if title:
            out.append({"title": title, "body": body, "href": m.group(1)})
        if len(out) >= max_results:
            break
    return out


def search_web(query, max_results=3):
    """联网搜索：用 Bing 失败再退 DuckDuckGo。"""
    errors = []
            
    try:
        results = _bing_search(query, max_results)
        if results:
            return _format_results(results, max_results)
        errors.append("Bing 无结果")
    except Exception as e:
        errors.append(f"Bing {type(e).__name__}: {e}")

    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            results = list(DDGS().text(query, max_results=max_results) or [])
        if results:
            return _format_results(results, max_results)
        errors.append("DuckDuckGo 无结果")
    except Exception as e:
        errors.append(f"DuckDuckGo {type(e).__name__}")

    return "联网搜索失败：" + "；".join(errors)



available_tools = {"calculator": calculator, "get_current_time": get_current_time,"search_web":search_web}
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "用于计算数学表达式，例如 '23 * 45' 或 '100 / 4'",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要计算的数学公式，比如 '3 + 5 * 2'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "用于读取当前时间",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "联网搜索实时信息。凡是涉及最近/实时的事实（天气、新闻、价格、比分、"
                "版本更新、人物近况、你不确定的知识）都必须先调用它，不要凭记忆回答。"
                "传参前必须提取关键词，避免直接传原话"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，尽量简洁具体，例如 '长沙 今天 天气'",
                    }
                },
                "required": ["query"],
            },
        },
    },

]


class MyAgent:
    def __init__(self, system_prompt,session_id="default"):
        self.client = OpenAI(
            api_key=os.getenv("LLM_API_KEY"), 
            base_url=os.getenv("LLM_BASE_URL","https://api.deepseek.com")
        )
        self.model = os.getenv("LLM_MODEL_ID","deepseek-chat")
        
        self.memory_file = os.path.join(BASE_DIR, f"memory_{session_id}.json",)
        self.system_prompt = system_prompt
        self.messages = []
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    self.messages = json.load(f)
                print(f"[系统提示：成功读取本地记忆，共 {len(self.messages)} 条历史消息]")
            except (json.JSONDecodeError, OSError) as e:
                print(f"[警告] 记忆文件损坏，已重置：{e}")
                self.messages = []
        # 保证 system prompt 永远在第一位，改 prompt 也能生效
        self.messages = [m for m in self.messages if m.get("role") != "system"]
        self.messages.insert(0, {"role": "system", "content": system_prompt})

        print("正在加载本地RAG数据库")
        self.chroma_dir = os.path.join(BASE_DIR, "chroma_db")
        self.chroma_client = chromadb.PersistentClient(path=self.chroma_dir)
        self.collection = self.chroma_client.get_or_create_collection(name="rule")
        self._refresh_knowledge_base()

    def _refresh_knowledge_base(self):
        """class.txt 内容变化时重建向量库。

        用 md5 指纹判断：指纹一致就跳过，避免每次启动重新灌库；
        指纹不一致或库为空时先删 collection 再重建，避免 id 重复。
        """
        source_path = os.path.join(BASE_DIR, "class.txt")
        meta_path = os.path.join(self.chroma_dir, ".source.json")

        if not os.path.exists(source_path):
            print("⚠️ 警告：没找到 class.txt，知识库为空。")
            logger.warning("知识库源文件不存在: %s", source_path)
            return

        with open(source_path, "rb") as f:
            raw = f.read()
        md5 = hashlib.md5(raw).hexdigest()

        meta = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, OSError):
                meta = {}

        if self.collection.count() > 0 and meta.get("md5") == md5:
            print(f"✅ 知识库已是最新（{self.collection.count()} 条，md5 {md5[:8]}），跳过重建。")
            return

        chunks = [line.strip() for line in raw.decode("utf-8").splitlines() if line.strip()]
        if not chunks:
            print("⚠️ class.txt 里没有可用内容，知识库为空。")
            return

        try:
            self.chroma_client.delete_collection("rule")
        except Exception as exc:  # 首次运行时 collection 可能不存在
            logger.info("删除旧 collection 跳过：%s", exc)
        self.collection = self.chroma_client.create_collection("rule")
        self.collection.add(
            documents=chunks,
            ids=[f"id_{i}" for i in range(len(chunks))],
        )

        os.makedirs(self.chroma_dir, exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "source": "class.txt",
                    "md5": md5,
                    "chunks": len(chunks),
                    "embedding": "default",
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        print(f"✅ 知识库重建完成，共 {len(chunks)} 条（md5 {md5[:8]}）。")
        logger.info("知识库重建: %d 条, md5=%s", len(chunks), md5)

    def save_memory(self):
        # 先写临时文件再替换，进程被杀也不会留下半截JSON
        self.messages = trim_history(self.messages)
        tmp = self.memory_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.messages, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.memory_file)

    def chat(self, user_input):
        self.messages = trim_history(self.messages)
        retrieved_context = ""
        augmented_input = user_input
        
        if self.collection.count()>0:
            results=self.collection.query(query_texts=[user_input],n_results=1)
            
            if results['documents'] and results['documents'][0]:
                distance = results['distances'][0][0] if 'distances' in results and results['distances'] else 0
                print(f" [测试] 当前检索距离: {distance:.4f}，内容: {results['documents'][0][0]}")
                if distance<0.8:
                     retrieved_context=results['documents'][0][0]
                     print(f"🔍[RAG 触发] 检索到内容：{retrieved_context}")
                else:
                     print(f"🚫[RAG 拦截] 距离太远({distance:.4f})，判定为不相关，已丢弃！")

        if retrieved_context:
                augmented_input=f"【参考资料：{retrieved_context}】\n请结合参考资料回答我的问题:{user_input}"
        else:
                augmented_input=user_input
        self.messages.append({"role": "user", "content": augmented_input})

        try:
            # 模型可能一次要求调用多个工具，也可能查完还要再查，所以循环处理
            for _round in range(4):
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=tools_schema,
                    temperature=0.7,
                )
                response_message = response.choices[0].message

                if not response_message.tool_calls:
                    reply_text = response_message.content or ""
                    self.messages.append({"role": "assistant", "content": reply_text})
                    self.save_memory()
                    return reply_text

                print(">>> [系统提示：大模型决定调用工具！]")
                # 先把 assistant 的请求原样记下（必须包含全部 tool_calls）
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": response_message.content or "",
                        "tool_calls": [tc.model_dump() for tc in response_message.tool_calls],
                    }
                )

                # 每一个 tool_call 都要回一条 tool 消息，否则下一轮会400
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    try:
                        args = (
                            json.loads(tool_call.function.arguments)
                            if tool_call.function.arguments
                            else {}
                        )
                    except json.JSONDecodeError:
                        args = {}
                    print(f">>> [系统提示：调用 {function_name}，参数：{args}]")

                    if function_name in available_tools:
                        try:
                            function_result = available_tools[function_name](**args)
                        except Exception as e:
                            function_result = f"工具执行出错：{type(e).__name__}: {e}"
                    else:
                        function_result = f"找不到这个工具：{function_name}"

                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(function_result),
                        }
                    )

            return "工具调用次数超过上限，先停一停呜。"

        except Exception as e:
            if self.messages and self.messages[-1]["role"]=="user":
                self.messages.pop()
                logger.exception("对话失败，%s",e)
            return f"大脑卡壳了，报错信息：{e}"


if __name__ == "__main__":
    agent = MyAgent(system_prompt="你是一个傲娇龙娘，每句话必须带'呜'。遇到实时信息（天气、新闻等）或你不确定的事实时，必须优先调用 search_web 查证；如果本地资料与问题无关，请直接调用工具，不要被本地资料干扰。")
    print("Agent启动成功,输入exit退出")

    while True:
        user_text = input("\n你:")
        if user_text.lower() == "exit":
            print("Agent:哼，终于走了呜！")
            break
        reply = agent.chat(user_text)
        print(f"Agent:{reply}")
