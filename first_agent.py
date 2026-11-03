import os
import json
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def calculator(expression):
    try:
        result = eval(expression)
        return str(result)
    except Exception:
        return "算不出来呜，表达式写错了！"


def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


available_tools = {"calculator": calculator, "get_current_time": get_current_time}
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
]


class MyAgent:
    def __init__(self, system_prompt):
        self.client = OpenAI(
            api_key=os.getenv("LLM_API_KEY"), base_url="https://api.deepseek.com"
        )
        self.model = "deepseek-chat"
        self.memory_file="memory.json"
        self.system_prompt = system_prompt
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                self.messages = json.load(f)
            print(f"[系统提示：成功读取本地记忆，共 {len(self.messages)} 条历史消息]")
        else:
            self.messages = [{"role": "system", "content": system_prompt}]

    def save_memory(self):
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.messages, f, ensure_ascii=False, indent=2)
        

    def chat(self, user_input):
        self.messages.append({"role": "user", "content": user_input})

        try:  # 兄弟1：try
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=tools_schema,
                temperature=0.7,
            )

            response_message = response.choices[0].message  # 兄弟2：和 response 对齐

            if response_message.tool_calls:  # 兄弟3：if 和 response_message 对齐
                print(">>> [系统提示：大模型决定调用工具！]")
                tool_call = response_message.tool_calls[0]
                function_name = tool_call.function.name
                args = (
                    json.loads(tool_call.function.arguments)
                    if tool_call.function.arguments
                    else {}
                )
                print(f">>> [系统提示：调用 {function_name}，参数：{args}]")
                if function_name in available_tools:
                    function_result = available_tools[function_name](**args)
                else:
                    function_result = "找不到这个工具呜。"

                self.messages.append(response_message)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": function_result,
                    }
                )

                second_response = self.client.chat.completions.create(
                    model=self.model, messages=self.messages
                )
                reply_text = second_response.choices[0].message.content
                self.messages.append({"role": "assistant", "content": reply_text})
                self.save_memory()
                return reply_text

            else:  # 兄弟4：else 和 if 对齐
                reply_text = response_message.content
                self.messages.append({"role": "assistant", "content": reply_text})
                self.save_memory()
                return reply_text

        except Exception as e:  # 兄弟5：except 和 try 对齐
            return f"大脑卡壳了，报错信息：{e}"


if __name__ == "__main__":
    agent = MyAgent(system_prompt="你是一个傲娇龙娘，每句话必须带'呜'。")
    print("Agent启动成功,输入exit退出")

    while True:
        user_text = input("\n你:")
        if user_text.lower() == "exit":
            print("Agent:哼，终于走了呜！")
            break
        reply = agent.chat(user_text)
        print(f"Agent:{reply}")
