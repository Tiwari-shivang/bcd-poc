from sqlalchemy.orm import Session
import DTOs
import helpers
from sqlalchemy import text

class AgentService:
    async def get_agent_response(self, request: DTOs.AgentChatRequest, db: Session):
        data = await helpers.generate_embeddings(request.message)
        query_embeddings = data.data[0].embedding
        results = helpers.search_data_embeddings(query_embeddings, db)
        context = []
        for row, distance in results:
            context.append(row.content)
        generated_query = helpers.llm_response(context=context, query_message=request.message)
        response = db.execute(text(generated_query.response))
        raw_data = response.mappings().all()
        llm_response = helpers.generate_normalized_llm_response(raw_data, request.message)
        return llm_response
