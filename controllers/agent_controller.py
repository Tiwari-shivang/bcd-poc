from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

import DTOs
import services
from database import get_db, get_db_vector, get_optional_db_oip

router = APIRouter()


@router.post("/chat", response_model=DTOs.AgentChatResponse)
async def chat_agent(
    http_request: Request,
    http_response: Response,
    request: DTOs.AgentChatRequest,
    vector_db: Session = Depends(get_db_vector),
    sf_exec_db: Session = Depends(get_db),
    oip_exec_db: Session | None = Depends(get_optional_db_oip),
):
    agent_service = services.AgentService()
    payload = await agent_service.get_agent_response(
        http_request,
        http_response,
        request,
        vector_db,
        sf_exec_db,
        oip_exec_db,
    )
    return DTOs.AgentChatResponse(**payload)
