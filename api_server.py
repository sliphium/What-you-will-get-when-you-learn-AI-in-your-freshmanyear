from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading

from first_agent import MyAgent 

app=FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

agent_pool={}
lock=threading.Lock()

class ChatRequest(BaseModel):
    message:str
    session_id:str="default_user"
    
@app.post("/chat")
def chat_endpoint(req:ChatRequest):
    with lock:
        if req.session_id not in agent_pool:
            agent_pool[req.session_id]=MyAgent(
                system_prompt="你是一个傲娇龙娘，每句话必须带'呜'。",
                session_id=req.session_id
                
            )
        current_agent=agent_pool[req.session_id]
                
        try:
            reply=current_agent.chat(req.message)
            return {"reply":reply}
        except Exception as e:
            return {"reply":f"后端出错啦,{e}"}
    

if __name__ == "__main__":
    print("🚀 后端服务已启动，已支持多方访问，请打开 index.html")
    uvicorn.run(app, host="127.0.0.1", port=8000)
