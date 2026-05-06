import json
import hashlib
import random
from openai import NotFoundError

import config
import DTOs
from models import EmbeddingModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from helpers import prompts
from helpers.sql_normalizer import normalize_enum_literals

ai_client = config.OpenAIClient
chat_model = config.AZURE_OPENAI_CHAT_DEPLOYMENT
embedding_model = config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT
EMBEDDING_DIM = 1536


class _EmbeddingDatum:
    def __init__(self, embedding: list[float]):
        self.embedding = embedding


class _EmbeddingResponse:
    def __init__(self, embedding: list[float]):
        self.data = [_EmbeddingDatum(embedding)]


def _local_deterministic_embedding(content: str, dim: int = EMBEDDING_DIM) -> list[float]:
    seed = int(hashlib.sha256(content.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    vec = [rng.uniform(-1.0, 1.0) for _ in range(dim)]
    norm = sum(v * v for v in vec) ** 0.5
    if norm == 0:
        return [0.0] * dim
    return [v / norm for v in vec]


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
        model=chat_model,
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
        model=chat_model,
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
    try:
        embeddings = ai_client.embeddings.create(
            input=content,
            model=embedding_model
        )
        return embeddings
    except NotFoundError as exc:
        embedding = _local_deterministic_embedding(content)
        return _EmbeddingResponse(embedding)

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


def _default_json_response(user_query: str, row_count: int, value: str | None = None) -> dict:
    heading = "No Results" if row_count == 0 else "Response"
    topic = (user_query or "request").strip()
    topic = topic[:120] if topic else "request"
    sub_heading = (
        f"No matching records were found for: {topic}."
        if row_count == 0
        else f"Returned {row_count} record(s) for: {topic}."
    )
    follow_up = (
        "Would you like to refine the filters and try again?"
        if row_count == 0
        else "Would you like me to drill down into a specific field?"
    )
    return {
        "heading": heading,
        "subHeading": sub_heading,
        "follow_up": follow_up,
        "type": "paragraph",
        "value": value or sub_heading,
    }


def _coerce_response_shape(payload: dict, *, row_count: int, user_query: str) -> dict:
    out = dict(payload)
    out["heading"] = str(out.get("heading") or "Response")
    out["subHeading"] = str(out.get("subHeading") or "Here is what I found.")
    out["follow_up"] = str(
        out.get("follow_up")
        or (
            "Would you like the next 15 records for this list?"
            if out.get("type") == "table" and row_count == 15
            else "Would you like me to narrow this down further?"
        )
    )

    kind = str(out.get("type") or "paragraph").lower()
    if kind not in {"paragraph", "table", "card"}:
        kind = "paragraph"
    out["type"] = kind

    if kind == "paragraph":
        out = {
            "heading": out["heading"],
            "subHeading": out["subHeading"],
            "follow_up": out["follow_up"],
            "type": "paragraph",
            "value": str(out.get("value") or out["subHeading"]),
        }
        return out

    if kind == "table":
        header = out.get("header")
        body = out.get("body")
        if not isinstance(header, list):
            header = []
        header = [str(h) for h in header]
        if not isinstance(body, list):
            body = []

        normalized_body: list[list] = []
        for row in body:
            if isinstance(row, list):
                normalized_body.append(row)
            elif isinstance(row, dict):
                if not header:
                    header = [str(k) for k in row.keys()]
                normalized_body.append([row.get(col) for col in header])

        out = {
            "heading": out["heading"],
            "subHeading": out["subHeading"],
            "follow_up": out["follow_up"],
            "type": "table",
            "header": header,
            "body": normalized_body,
        }
        return out

    # card
    headers = out.get("headers")
    normalized_headers: list[dict] = []
    if isinstance(headers, list):
        for item in headers:
            if isinstance(item, dict):
                normalized_headers.append(
                    {
                        "key": str(item.get("key", "")),
                        "value": item.get("value", "—"),
                    }
                )

    out = {
        "heading": out["heading"],
        "subHeading": out["subHeading"],
        "follow_up": out["follow_up"],
        "type": "card",
        "headers": normalized_headers,
    }
    return out


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
        model=chat_model,
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
    raw = _strip_markdown_fences(response.choices[0].message.content or "")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _default_json_response(user_query, row_count, value=raw or None)

    if not isinstance(parsed, dict):
        return _default_json_response(user_query, row_count)

    return _coerce_response_shape(parsed, row_count=row_count, user_query=user_query)

def get_insights_salesforce(content):
    insights_prompt = prompts.get_insights_salesforce_prompt(content)
    response = ai_client.chat.completions.create(
        model=chat_model,
        messages=[
            {"role": "system", "content": ""},
            {
                "role": "user",
                "content": insights_prompt,
            },
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content or ""
    return _strip_markdown_fences(raw).strip()


def get_insights_oip(content):
    insights_prompt = prompts.get_insights_oip_prompt(content)
    response = ai_client.chat.completions.create(
        model=chat_model,
        messages=[
            {"role": "system", "content": ""},
            {
                "role": "user",
                "content": insights_prompt,
            },
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content or ""
    return _strip_markdown_fences(raw).strip()


def get_chart_specs_salesforce(content):
    chart_prompt = prompts.get_chart_specs_salesforce_prompt(content)
    response = ai_client.chat.completions.create(
        model=chat_model,
        messages=[
            {"role": "system", "content": ""},
            {
                "role": "user",
                "content": chart_prompt,
            },
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content or ""
    return _strip_markdown_fences(raw).strip()


def get_chart_specs_oip(content):
    chart_prompt = prompts.get_chart_specs_oip_prompt(content)
    response = ai_client.chat.completions.create(
        model=chat_model,
        messages=[
            {"role": "system", "content": ""},
            {
                "role": "user",
                "content": chart_prompt,
            },
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content or ""
    return _strip_markdown_fences(raw).strip()


def parse_insights_json(raw: str) -> list[dict]:
    """Parse strict JSON array from insights LLM output; raises ValueError if invalid."""
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Insights response is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("Insights JSON must be a top-level array")
    out = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Insight index {i} must be an object")
        sql = item.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError(f"Insight index {i} missing string 'sql'")
        out.append(
            {
                "insight_title": item.get("insight_title"),
                "insight_description": item.get("insight_description"),
                "sql": sql.strip(),
            }
        )
    return out


def parse_salesforce_insights_json(raw: str) -> list[dict]:
    return parse_insights_json(raw)


def parse_chart_specs_json(raw: str) -> list[dict]:
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Chart response is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("Chart JSON must be a top-level array")

    allowed_chart_types = {"pie", "bar", "line"}
    out = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Chart index {i} must be an object")
        sql = item.get("sql")
        chart_type = item.get("chart_type")
        chart_config = item.get("chart_config")
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError(f"Chart index {i} missing string 'sql'")
        if chart_type not in allowed_chart_types:
            raise ValueError(
                f"Chart index {i} must have chart_type in {sorted(allowed_chart_types)}"
            )
        if not isinstance(chart_config, dict):
            raise ValueError(f"Chart index {i} missing object 'chart_config'")
        out.append(
            {
                "chart_title": item.get("chart_title"),
                "chart_description": item.get("chart_description"),
                "chart_type": chart_type,
                "chart_config": chart_config,
                "sql": sql.strip(),
            }
        )
    return out
