from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from first_agent import MyAgent 

app=FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
agent = MyAgent(system_prompt="你是一个傲娇龙娘，每句话必须带'呜'。")

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    reply = agent.chat(req.message)
    return {"reply": reply}

if __name__ == "__main__":
    print("🚀 后端服务已启动，请打开 index.html")
    uvicorn.run(app, host="127.0.0.1", port=8000)
