import json

import config
import DTOs
from models import EmbeddingModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from helpers import prompts
from helpers.sql_normalizer import normalize_enum_literals

ai_client = config.OpenAIClient


def _to_json_string(payload) -> str:
    """Serialise any payload (list of dicts, dict, scalar, None) to a clean
    pretty-printed JSON string the LLM can reliably parse.

    `default=str` is used as a fallback for types that JSON does not natively
    support (Decimal, datetime, date, UUID, etc.) so we never raise mid-prompt.
    """
    try:
        return json.dumps(payload, default=str, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        # Last-resort safety net — should be unreachable thanks to default=str.
        return str(payload)


def _serialize_history(last_context: list | None):
    """Produce a copy of `last_context` where each turn's `agent_response`
    is a JSON string. Keeps the SQL-generation prompt deterministic and
    unambiguous regardless of how upstream stores result rows.
    """
    if not last_context:
        return last_context
    return [
        {
            "user_query": turn.get("user_query", ""),
            "agent_response": _to_json_string(turn.get("agent_response")),
        }
        for turn in last_context
    ]

def sanitize_generated_query(query: str, *, apply_enum_normaliser: bool = True):
    sanitized_query = query.replace("\n", " ").replace("\t", " ").strip()
    if sanitized_query.upper() == "INVALID_QUERY":
        return sanitized_query
    if not apply_enum_normaliser:
        return sanitized_query
    return normalize_enum_literals(sanitized_query)


def fetch_embedding_contents_ordered(
    db: Session,
    *,
    catalog_source: str,
    ordered_keys: list[str],
) -> list[str]:
    stmt = select(EmbeddingModel.key, EmbeddingModel.content).where(
        EmbeddingModel.data_source == catalog_source,
        EmbeddingModel.key.in_(ordered_keys),
    )
    rows = db.execute(stmt).all()
    mapping = {key: ct for key, ct in rows if ct}
    out: list[str] = []
    for k in ordered_keys:
        raw = mapping.get(k)
        if raw and str(raw).strip():
            out.append(str(raw).strip())
    return out


def llm_response(
    context,
    query_message: str,
    last_context: list | None = None,
    *,
    execution_target: str = "Salesforce (BCD / CRM-aligned PostgreSQL)",
    apply_enum_normaliser: bool = True,
):
    response = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": ""},
            {
                "role": "user",
                "content": prompts.get_query_prompt(
                    context,
                    query_message,
                    _serialize_history(last_context),
                    execution_target=execution_target,
                ),
            },
        ],
        temperature=0.2,
    )
    query = DTOs.AgentChatResponse(
        response=sanitize_generated_query(
            response.choices[0].message.content,
            apply_enum_normaliser=apply_enum_normaliser,
        )
    )
    return query


def llm_fix_response(
    context,
    query_message: str,
    previous_sql: str,
    error_message: str,
    *,
    apply_enum_normaliser: bool = True,
):
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
        response=sanitize_generated_query(
            response.choices[0].message.content,
            apply_enum_normaliser=apply_enum_normaliser,
        )
    )
    return fixed

async def generate_embeddings(content: str):
    embeddings = ai_client.embeddings.create(
        input=content,
        model="text-embedding-3-small"
    )
    return embeddings

def search_data_embeddings(
    query_embedding, db: Session, limit: int = 10, *, catalog_source: str | None = None
):
    distance_arr = EmbeddingModel.data.cosine_distance(query_embedding)
    stmt = select(EmbeddingModel, distance_arr.label("distance"))
    if catalog_source is not None:
        stmt = stmt.where(EmbeddingModel.data_source == catalog_source)
    stmt = stmt.order_by(distance_arr.asc()).limit(limit)
    return db.execute(stmt).all()
def _strip_markdown_fences(text: str) -> str:
    """Remove any markdown code-fence wrapping the model may have added.

    Handles variants like ```html, ```HTML, ``` (plain), with or without a
    trailing fence, and trims surrounding whitespace so the caller always
    receives a bare HTML string.
    """
    stripped = text.strip()
    # Remove opening fence (```html, ```HTML, ``` …)
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1:]
    # Remove closing fence
    if stripped.endswith("```"):
        stripped = stripped[: stripped.rfind("```")]
    return stripped.strip()


def generate_normalized_llm_response(data, user_query, last_context: list | None = None):
    # Compute an unambiguous row count so the renderer can never confuse a
    # populated result with an empty one. Mirrored in the prompt as a hard rule.
    if isinstance(data, list):
        row_count = len(data)
    elif data is None:
        row_count = 0
    else:
        row_count = 1

    # Single-row UNWRAP: when the SQL returned exactly one row, hand the LLM a
    # single object instead of a 1-element array. The "single-object → details
    # card" branch is then the ONLY shape that fits, so the model cannot
    # accidentally render a 1-row table even if it ignores the precedence
    # rule. This pushes the routing decision out of the LLM and into code,
    # which is the only reliable place for it.
    render_data = data
    if isinstance(data, list) and row_count == 1:
        render_data = data[0]

    data_json = _to_json_string(render_data)

    response = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": ""},
            {
                "role": "user",
                "content": prompts.get_natural_lang_prmpt(
                    user_query=user_query,
                    raw_data=data_json,
                    last_context=_serialize_history(last_context),
                    row_count=row_count,
                ),
            },
        ],
    )
    return _strip_markdown_fences(response.choices[0].message.content)