from fastapi import APIRouter, Depends
import config
import DTOs
from sqlalchemy import select
from database import get_db
from sqlalchemy.orm import Session
import models
import helpers

router = APIRouter()
ai_client = config.OpenAIClient
@router.post("/chat")
async def chat_agent(request: DTOs.AgentChatRequest, db:Session = Depends(get_db)):
    embeddings = ai_client.embeddings.create(
        input=request.message,
        model="text-embedding-3-small"
    )
    query_embeddings = embeddings.data[0].embedding
    distance_attr = models.EmbeddingModel.data.cosine_distance(query_embeddings)
    query=(
        select(models.EmbeddingModel, (1 - distance_attr).label("similarity")).order_by(distance_attr).limit(5)
    )
    result= db.execute(query).all()
    context=[]
    for row, score in result:
        context.append(row.content)
        print(f"Score: {score}, content: {row.content}, embedding: {row.data}")
    llm_response = helpers.llm_response(context=context, query_message=request.message)
    print(llm_response)
    return llm_response