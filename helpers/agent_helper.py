import config
import DTOs
from models import EmbeddingModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from helpers import prompts
from helpers.sql_normalizer import normalize_enum_literals

ai_client=config.OpenAIClient

def sanitize_generated_query(query: str):
    sanitized_query = query.replace("\n", " ").replace("\t", " ").strip()
    if sanitized_query.upper() == "INVALID_QUERY":
        return sanitized_query
    return normalize_enum_literals(sanitized_query)

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


def llm_fix_response(context, query_message: str, previous_sql: str, error_message: str):
    """Ask the LLM to repair a SQL query that failed at execution time."""
    response = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": ""},
            {
                "role": "user",
                "content": prompts.get_fix_query_prompt(
                    context, query_message, previous_sql, error_message
                ),
            },
        ],
        temperature=0.1,
    )
    fixed = DTOs.AgentChatResponse(
        response=sanitize_generated_query(response.choices[0].message.content)
    )
    return fixed

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