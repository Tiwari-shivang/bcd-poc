import uuid

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import Request, Response
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

import DTOs
import helpers


MAX_SQL_REPAIR_ATTEMPTS = 2

# Tables that sit at the structural center of the schema and should be
# present in every prompt, regardless of which embeddings happen to win the
# similarity search. Without them, multi-hop JOINs (e.g. solutions → agreements
# → gcn → accounts) become impossible to express because the bridging table
# is missing from the rendered context.
CORE_ANCHOR_TABLES: tuple[str, ...] = ("accounts", "agreements")

# session_id strings of every seen user
active_users: list[str] = []

# [{"session_id": str, "previous_responses": [{"user_query": str, "agent_response": any}, ...]}, ...]
last_contexts: list[dict] = []


class AgentService:
    async def get_agent_response(
        self,
        http_request: Request,
        http_response: Response,
        request: DTOs.AgentChatRequest,
        db: Session,
    ):
        # ── 1. Resolve / create session ──────────────────────────────────────
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

        # ── 2. Retrieve existing conversation context for this user ───────────
        last_context = self._get_previous_responses(session_id)

        # ── 3. Embeddings → schema context ───────────────────────────────────
        data = await helpers.generate_embeddings(request.message)
        query_embeddings = data.data[0].embedding
        results = helpers.search_data_embeddings(query_embeddings, db)

        # Collect retrieved table names, preserving similarity order and
        # de-duplicating because multiple embedding rows can share a key.
        seen: set[str] = set()
        table_names: list[str] = []
        for row, distance in results:
            print("distance: ", distance)
            key = row.key
            if key and key not in seen:
                seen.add(key)
                table_names.append(key)

        # Always union in the core anchor tables. They are the structural
        # hubs of the schema (Customer/Account, Agreement) — almost every
        # business question routes through them.
        for anchor in CORE_ANCHOR_TABLES:
            if anchor not in seen:
                seen.add(anchor)
                table_names.append(anchor)

        # `build_schema_context` will FK-expand this seed by 1 hop, so even
        # bridging tables that are not explicitly mentioned in the question
        # (or retrieved by embeddings) will appear in the rendered schema.
        context = helpers.build_schema_context(table_names) or helpers.build_schema_context()

        # ── 4. Generate SQL (context-aware) ──────────────────────────────────
        generated_query = helpers.llm_response(
            context=context,
            query_message=request.message,
            last_context=last_context,
        )
        valid_query = generated_query.response.strip()
        if valid_query.upper() == "INVALID_QUERY":
            return "No search result for this"

        print("query: ", valid_query)

        # ── 5. Execute SQL (with auto-repair) ─────────────────────────────────
        raw_data = self._execute_with_repair(
            db=db,
            context=context,
            user_query=request.message,
            sql=valid_query,
        )
        if raw_data is None:
            return "No search result for this"

        # Normalise SQLAlchemy RowMapping objects into plain Python dicts at
        # the single source of truth. This guarantees that everything
        # downstream (the LLM renderer, conversation history, future SQL
        # follow-ups) sees clean, JSON-serialisable data instead of
        # `RowMapping` reprs (e.g. `Decimal('1.5')`, `datetime.date(...)`)
        # which the model can misinterpret as malformed/empty.
        serialized_data: list[dict] = [dict(row) for row in raw_data]
        print("raw data: ", serialized_data)

        # ── 6. Generate LLM / HTML response, passing conversation context ─────
        llm_response = helpers.generate_normalized_llm_response(
            serialized_data, request.message, last_context
        )

        # ── 7. Persist this turn into last_contexts ───────────────────────────
        self._save_to_context(session_id, request.message, serialized_data)

        return llm_response

    # ── Context helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _get_previous_responses(session_id: str) -> list[dict]:
        """Return the previous_responses list for this session, or [] if none."""
        for entry in last_contexts:
            if entry["session_id"] == session_id:
                return entry["previous_responses"]
        return []

    @staticmethod
    def _save_to_context(session_id: str, user_query: str, agent_response) -> None:
        """Append a new turn to last_contexts, creating the session entry if needed."""
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

    def _execute_with_repair(self, db: Session, context: str, user_query: str, sql: str):
        """Execute SQL, and if it fails ask the LLM to repair it using the DB error.

        On any DBAPI failure we roll back the session (otherwise the
        connection stays in an aborted state and every subsequent statement
        fails), then hand the original user question, schema context, failing
        SQL and the database error back to the LLM for a single correction
        pass. Bounded by MAX_SQL_REPAIR_ATTEMPTS so we never loop forever.
        """
        current_sql = sql
        last_error: str = ""

        for attempt in range(MAX_SQL_REPAIR_ATTEMPTS + 1):
            try:
                response = db.execute(text(current_sql))
                return response.mappings().all()
            except DBAPIError as exc:
                last_error = self._extract_db_error(exc)
                print(f"SQL attempt {attempt + 1} failed: {last_error}")

                try:
                    db.rollback()
                except SQLAlchemyError as rollback_exc:
                    print("rollback failed:", rollback_exc)

                if attempt >= MAX_SQL_REPAIR_ATTEMPTS:
                    break

                repaired = helpers.llm_fix_response(
                    context=context,
                    query_message=user_query,
                    previous_sql=current_sql,
                    error_message=last_error,
                )
                next_sql = repaired.response.strip()
                if not next_sql or next_sql.upper() == "INVALID_QUERY" or next_sql == current_sql:
                    break
                print(f"repaired query (attempt {attempt + 2}): {next_sql}")
                current_sql = next_sql

        print(f"giving up after SQL repair attempts; last error: {last_error}")
        return None

    @staticmethod
    def _extract_db_error(exc: DBAPIError) -> str:
        """Pull the concise driver message out of a SQLAlchemy DBAPIError."""
        orig = getattr(exc, "orig", None)
        if orig is not None:
            message = str(orig).strip()
            if message:
                return message
        return str(exc).strip()
