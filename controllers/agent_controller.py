from fastapi import APIRouter, Depends, Request, Response
import config
import DTOs
from database import get_db
from sqlalchemy.orm import Session
import services

router = APIRouter()
ai_client = config.OpenAIClient
@router.post("/chat")
async def chat_agent(http_request: Request, http_response: Response, request: DTOs.AgentChatRequest, db:Session = Depends(get_db)):
    agent_service = services.AgentService()
    response = await agent_service.get_agent_response(http_request, http_response, request, db)
    return {"response": response}