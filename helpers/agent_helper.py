import config
import DTOs

ai_client=config.OpenAIClient

def get_prompt(context, query_message: str):
    prompt=f"""
You are an expert SQL query generator.

Your task is to generate a correct, optimized, and executable SQL query based strictly on the provided database schema context and the user’s question.

### Rules:

* ONLY return the SQL query.
* DO NOT include any explanation, comments, markdown, or extra text.
* DO NOT wrap the query in ``` or any formatting.
* The output must be plain SQL text only.
* Ensure the query is syntactically correct and production-ready.
* Use only the tables and columns provided in the schema context.
* Do NOT assume any schema outside the given context.
* Prefer explicit column selection instead of SELECT * unless necessary.
* Handle joins, filters, aggregations, and conditions correctly.
* If the question cannot be answered using the given schema, return exactly:
  INVALID_QUERY

### Schema Context:

{context}

### User Question:

{query_message}

### Output:

SQL query only.

"""
    return prompt

def llm_response(context, query_message: str):
    response = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":""},
            {"role":"user", "content": get_prompt(context, query_message)}
        ],
        temperature=0.2
    )
    response = DTOs.AgentChatResponse(response=response.choices[0].message.content)
    return response