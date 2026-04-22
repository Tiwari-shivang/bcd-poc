from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

import DTOs
import helpers


MAX_SQL_REPAIR_ATTEMPTS = 2


class AgentService:
    async def get_agent_response(self, request: DTOs.AgentChatRequest, db: Session):
        data = await helpers.generate_embeddings(request.message)
        query_embeddings = data.data[0].embedding
        results = helpers.search_data_embeddings(query_embeddings, db)

        # Use the retrieved rows only to pick which tables are relevant; the
        # actual schema description is rendered from the SQLAlchemy models so
        # the LLM always sees accurate column names, types and enum values.
        table_names = []
        for row, distance in results:
            print("distance: ", distance)
            if row.key:
                table_names.append(row.key)

        context = helpers.build_schema_context(table_names) or helpers.build_schema_context()

        generated_query = helpers.llm_response(context=context, query_message=request.message)
        valid_query = generated_query.response.strip()
        if valid_query.upper() == "INVALID_QUERY":
            return "No search result for this"

        print("query: ", valid_query)

        raw_data = self._execute_with_repair(
            db=db,
            context=context,
            user_query=request.message,
            sql=valid_query,
        )
        if raw_data is None:
            return "No search result for this"

        llm_response = helpers.generate_normalized_llm_response(raw_data, request.message)
        return llm_response

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
