import config
import DTOs
from models import EmbeddingModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from helpers import prompts

ai_client=config.OpenAIClient

def sanitize_generated_query(query: str):
    sanitized_query = query.replace("\n", " ").replace("\t", " ")
    return sanitized_query

def llm_response(context, query_message: str):
    response = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":""},
            {"role":"user", "content": prompts.get_query_prompt(context, query_message)}
        ],
        temperature=0.2
    )
    query = DTOs.AgentChatResponse(response=sanitize_generated_query(response.choices[0].message.content))
    return query

async def generate_embeddings(content: str):
    embeddings = ai_client.embeddings.create(
        input=content,
        model="text-embedding-3-small"
    )
    return embeddings

def search_data_embeddings(query_embedding, db: Session):
    distance_arr = EmbeddingModel.data.cosine_distance(query_embedding)
    query = (
        select(EmbeddingModel, distance_arr.label("distance")).order_by(distance_arr.asc()).limit(5)
    )
    context = db.execute(query).all()
    return context

def generate_normalized_llm_response(data, user_query):
    response = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": ""},
            {"role": "user", "content": prompts.get_natural_lang_prmpt(user_query, data)}
        ]
    )
    return response.choices[0].message.content