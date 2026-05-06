import uuid
from typing import Any

from fastapi import Request, Response
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

import DTOs
import helpers
from database import oip_query_engine_configured
from helpers import datasource as ds
from helpers import oip_retrieval_hints
from helpers import schema_context
from helpers.router import (
    clarification_message,
    final_route_from_evidence,
    snapshot_from_hits,
)

MAX_SQL_REPAIR_ATTEMPTS = 2

CORE_ANCHOR_TABLES_SF: tuple[str, ...] = ("accounts", "agreements")
CORE_KEYS_OIP: tuple[str, ...] = ("accounts", "customers", "opportunities", "solutions")

# User-visible copy — keep in sync with product wording for empty OIP vector catalogue.
OIP_CATALOG_MISSING_MESSAGE = (
    "No **OIP** catalogue embeddings found. Set **`AUTO_SEED_OIP_EMBEDDINGS=1`** "
    "on startup (loads `schema_oip.json`) or POST `/file/upload` with `data_source=oip`."
)


def _paragraph_response(
    message: str,
    *,
    heading: str = "Response",
    sub_heading: str = "Here is what I found.",
    follow_up: str = "Would you like me to refine this further?",
) -> dict[str, Any]:
    return {
        "heading": heading,
        "subHeading": sub_heading,
        "follow_up": follow_up,
        "type": "paragraph",
        "value": message,
    }


def _response_oip_catalog_missing() -> dict[str, Any]:
    return {
        "response": _paragraph_response(
            OIP_CATALOG_MISSING_MESSAGE,
            heading="OIP Catalog Missing",
            sub_heading="The OIP catalog is not available for query routing.",
            follow_up="Would you like to use Salesforce data source instead?",
        ),
        "needs_database_choice": False,
        "resolved_data_source": ds.OIP,
        "error": "oip_catalog_missing",
    }


active_users: list[str] = []
last_contexts: list[dict] = []
pin_data_source_by_session: dict[str, str] = {}
# Stores the natural-language query when routing asks the user to pick Salesforce vs OIP.
pending_nl_query_by_session: dict[str, str] = {}


def _dedupe_ordered_keys(hit_keys: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for k in hit_keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _merge_anchor_oip(hit_keys: list[str]) -> list[str]:
    out = _dedupe_ordered_keys(hit_keys)
    seen = set(out)
    for a in CORE_KEYS_OIP:
        if a not in seen:
            out.append(a)
            seen.add(a)
    return out


def _is_short_db_pick_reply(message: str) -> bool:
    m = message.strip()
    return 0 < len(m) <= 96


def _looks_like_new_nl_question(message: str) -> bool:
    t = message.strip()
    if len(t) >= 140:
        return True
    low = t.lower()
    cues = (
        "which ",
        "what ",
        "how ",
        "when ",
        "where ",
        "who ",
        "show ",
        "list ",
        "find ",
        "count ",
        "tell me",
        "?",
    )
    return any(c in low for c in cues)


class AgentService:
    async def get_agent_response(
        self,
        http_request: Request,
        http_response: Response,
        request: DTOs.AgentChatRequest,
        vector_db: Session,
        sf_exec_db: Session,
        oip_exec_db: Session | None,
    ) -> dict[str, Any]:
        session_id = http_request.cookies.get("session_id")
        if not session_id:
            session_id = str(uuid.uuid4())
            http_response.set_cookie(
                key="session_id",
                value=session_id,
                httponly=True,
                samesite="lax",
            )

        if session_id not in active_users:
            active_users.append(session_id)

        last_context = self._get_previous_responses(session_id)

        routed: str | None = None
        explicit = ds.normalize_source(request.data_source)
        msg = request.message.strip()
        spoken = ds.parse_source_from_reply(msg) if len(msg) <= 128 else None

        pending = pending_nl_query_by_session.get(session_id)

        query_for_llm = msg

        if pending is not None:
            if explicit:
                query_for_llm = pending_nl_query_by_session.pop(session_id)
                routed = explicit
                pin_data_source_by_session[session_id] = explicit
            elif spoken is not None and _is_short_db_pick_reply(msg):
                query_for_llm = pending_nl_query_by_session.pop(session_id)
                routed = spoken
                pin_data_source_by_session[session_id] = spoken
            elif _looks_like_new_nl_question(msg):
                pending_nl_query_by_session.pop(session_id, None)
            else:
                return {
                    "response": _paragraph_response(
                        "I still need to know which database to use for your last question.",
                        heading="Database Selection Required",
                        sub_heading="Please choose the source before I continue.",
                        follow_up="Should I use Salesforce or OIP for this request?",
                    ),
                    "needs_database_choice": True,
                    "resolved_data_source": None,
                }

        if routed is None:
            if explicit:
                pin_data_source_by_session[session_id] = explicit
                routed = explicit
            elif spoken:
                pin_data_source_by_session[session_id] = spoken
                routed = spoken
            elif session_id in pin_data_source_by_session:
                routed = pin_data_source_by_session[session_id]

        emb = await helpers.generate_embeddings(query_for_llm)
        qvec = emb.data[0].embedding

        sf_hits = helpers.search_data_embeddings(
            qvec, vector_db, limit=10, catalog_source=ds.SALESFORCE
        )
        oip_hits = helpers.search_data_embeddings(
            qvec, vector_db, limit=10, catalog_source=ds.OIP
        )
        oip_hits_for_router = oip_retrieval_hints.merge_oip_vector_hits(
            oip_hits, query_for_llm
        )
        snapshot = snapshot_from_hits(sf_hits, oip_hits_for_router)
        snapshot_embedding_only = snapshot_from_hits(sf_hits, oip_hits)

        if routed is None:
            token = final_route_from_evidence(
                query_for_llm,
                snapshot,
                snapshot_embedding_only=snapshot_embedding_only,
            )
            if token == "clarify":
                pending_nl_query_by_session[session_id] = query_for_llm
                return {
                    "response": _paragraph_response(
                        clarification_message(),
                        heading="Need Clarification",
                        sub_heading="I need a data source selection to continue.",
                        follow_up="Do you want me to use Salesforce or OIP?",
                    ),
                    "needs_database_choice": True,
                    "resolved_data_source": None,
                }
            routed = token

        if routed == ds.OIP and not oip_query_engine_configured():
            return {
                "response": _paragraph_response(
                    "OIP routing was chosen but DB_URL_OIP is not configured.",
                    heading="OIP Not Configured",
                    sub_heading="The OIP database connection is currently unavailable.",
                    follow_up="Would you like to run this on Salesforce instead?",
                ),
                "needs_database_choice": False,
                "resolved_data_source": None,
                "error": "oip_not_configured",
            }

        exec_db = sf_exec_db if routed == ds.SALESFORCE else oip_exec_db

        sf_keys_unique: list[str] = []
        seen_sf: set[str] = set()
        for row, _ in sf_hits:
            k = getattr(row, "key", None)
            if k and k not in seen_sf:
                seen_sf.add(k)
                sf_keys_unique.append(k)
        for a in CORE_ANCHOR_TABLES_SF:
            if a not in seen_sf:
                seen_sf.add(a)
                sf_keys_unique.append(a)

        oip_hit_keys: list[str] = []
        seen_o = set()
        for row, _ in oip_hits_for_router:
            k = getattr(row, "key", None)
            if k and k not in seen_o:
                seen_o.add(k)
                oip_hit_keys.append(k)
        merged_oip = _merge_anchor_oip(oip_hit_keys)

        if routed == ds.SALESFORCE:
            ctx = (
                schema_context.build_schema_context(sf_keys_unique)
                or schema_context.build_schema_context()
            )
            exec_label = "Salesforce (BCD / CRM-aligned PostgreSQL)"
            enum_norm = True
        else:
            bodies = helpers.fetch_embedding_contents_ordered(
                vector_db,
                catalog_source=ds.OIP,
                ordered_keys=merged_oip,
            )
            ctx = schema_context.build_catalog_context_from_embeddings(bodies)
            if not ctx:
                ctx = schema_context.build_oip_context_from_repo_file(merged_oip)
            if not ctx:
                return _response_oip_catalog_missing()
            exec_label = "OIP warehouse PostgreSQL (schema_oip.json)"
            enum_norm = False

        if not ctx:
            return {
                "response": _paragraph_response(
                    "Schema catalogue unavailable for routing.",
                    heading="Schema Unavailable",
                    sub_heading="I could not build the schema context for this request.",
                    follow_up="Would you like to retry with a different data source?",
                ),
                "needs_database_choice": False,
                "resolved_data_source": routed,
                "error": "no_schema_context",
            }

        gen = helpers.llm_response(
            context=ctx,
            query_message=query_for_llm,
            last_context=last_context,
            execution_target=exec_label,
            apply_enum_normaliser=enum_norm,
        )
        sql_text = gen.response.strip()
        if sql_text.upper() == "INVALID_QUERY":
            return {
                "response": _paragraph_response(
                    "No search result for this",
                    heading="No Results",
                    sub_heading="I could not find matching records for this request.",
                    follow_up="Would you like to adjust filters or keywords?",
                ),
                "needs_database_choice": False,
                "resolved_data_source": routed,
            }
        raw = self._execute_with_repair(
            db=exec_db,
            context=ctx,
            user_query=query_for_llm,
            sql=sql_text,
            execution_label=exec_label,
            enum_norm=enum_norm,
        )
        if raw is None:
            return {
                "response": _paragraph_response(
                    "No search result for this",
                    heading="No Results",
                    sub_heading="The query did not return a usable dataset.",
                    follow_up="Would you like me to try a narrower or broader version?",
                ),
                "needs_database_choice": False,
                "resolved_data_source": routed,
            }

        serialized = [dict(row) for row in raw]

        formatted_response = helpers.generate_normalized_llm_response(
            serialized, query_for_llm, last_context
        )
        self._save_to_context(session_id, query_for_llm, serialized)

        return {
            "response": formatted_response,
            "needs_database_choice": False,
            "resolved_data_source": routed,
        }

    @staticmethod
    def _get_previous_responses(session_id: str) -> list[dict]:
        for entry in last_contexts:
            if entry["session_id"] == session_id:
                return entry["previous_responses"]
        return []

    @staticmethod
    def _save_to_context(session_id: str, user_query: str, agent_response) -> None:
        for entry in last_contexts:
            if entry["session_id"] == session_id:
                entry["previous_responses"].append(
                    {"user_query": user_query, "agent_response": agent_response}
                )
                return
        last_contexts.append(
            {
                "session_id": session_id,
                "previous_responses": [
                    {"user_query": user_query, "agent_response": agent_response}
                ],
            }
        )

    def _execute_with_repair(
        self,
        db: Session,
        context: str,
        user_query: str,
        sql: str,
        *,
        execution_label: str,
        enum_norm: bool,
    ):
        sql_cur = sql
        last_err = ""
        print(sql)
        for attempt in range(MAX_SQL_REPAIR_ATTEMPTS + 1):
            try:
                rsp = db.execute(text(sql_cur))
                return rsp.mappings().all()
            except DBAPIError as exc:
                last_err = self._extract_db_error(exc)
                print(f"[{execution_label}] SQL fail {attempt + 1}: {last_err}")
                try:
                    db.rollback()
                except SQLAlchemyError as rexc:
                    print("rollback:", rexc)
                if attempt >= MAX_SQL_REPAIR_ATTEMPTS:
                    break
                repaired = helpers.llm_fix_response(
                    context=context,
                    query_message=user_query,
                    previous_sql=sql_cur,
                    error_message=last_err,
                    apply_enum_normaliser=enum_norm,
                )
                nxt = repaired.response.strip()
                if not nxt or nxt.upper() == "INVALID_QUERY" or nxt == sql_cur:
                    break
                sql_cur = nxt

        print(f"[{execution_label}] giving up repairs: {last_err}")
        return None

    @staticmethod
    def _extract_db_error(exc: DBAPIError) -> str:
        orig = getattr(exc, "orig", None)
        if orig is not None:
            m = str(orig).strip()
            if m:
                return m
        return str(exc).strip()
