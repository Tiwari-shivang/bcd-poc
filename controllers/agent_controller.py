from fastapi import APIRouter, Depends
import config
import DTOs
from database import get_db
from sqlalchemy.orm import Session
import services

router = APIRouter()
ai_client = config.OpenAIClient
@router.post("/chat")
async def chat_agent(request: DTOs.AgentChatRequest, db:Session = Depends(get_db)):
    agent_service = services.AgentService()
    response = await agent_service.get_agent_response(request, db)
    return {"response": response}