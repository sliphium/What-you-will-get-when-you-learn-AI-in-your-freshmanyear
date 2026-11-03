# 大一学 AI 我会得到什么？ (My First AI Agent)

这是我的大一 AI 实战项目。基于 Python (FastAPI) + 原生前端 + DeepSeek API 手搓的全栈 AI 智能体（Agent）。

## ✨ 核心功能
- **独立人格**：通过 System Prompt 注入了傲娇龙娘的人设。
- **长期记忆**：使用 JSONL 格式实现了上下文的持久化存储，跨越时空不失忆。
- **Function Calling**：内置了“计算器”和“查时间”工具，让 AI 能够动手干活。

## 🛠️ 技术栈
- 后端：Python, FastAPI, Uvicorn, OpenAI SDK (兼容 DeepSeek)
- 前端：HTML5, CSS3, 原生 JavaScript (Fetch API, ReadableStream)

## 🚀 如何运行
1. 克隆本项目到本地
2. 安装依赖：`pip install fastapi uvicorn openai python-dotenv`
3. 在根目录新建 `.env` 文件，写入：`LLM_API_KEY=你的DeepSeek_API_Key`
4. 启动后端：`python api_server.py`
5. 浏览器打开 `index.html` 即可开始聊天。

## 📝 碎碎念
从配环境报错、修 CSS、与代码大战三百回合，这大概就是大一学 AI 最真实的感受。
欢迎 Star！🌟
