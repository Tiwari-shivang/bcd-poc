import json
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import bindparam, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

import helpers
import models
from helpers import datasource

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATHS = {
    datasource.SALESFORCE: PROJECT_ROOT / "schema.json",
    datasource.OIP: PROJECT_ROOT / "schema_oip.json",
}
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DISPLAY_COLUMN_CANDIDATES = (
    "name",
    "global_customer_name",
    "tool_or_service",
    "service_configuration",
    "client_name",
    "title",
    "alias",
)
ALLOWED_CHART_TYPES = {"pie", "bar", "line"}
CHART_CONFIG_KEYS_BY_TYPE = {
    "pie": ("name_key", "value_key"),
    "bar": ("x_key", "y_key"),
    "line": ("x_key", "y_key"),
}


@lru_cache(maxsize=4)
def _load_schema(schema_path: str) -> list[dict]:
    with Path(schema_path).open("r", encoding="utf-8") as schema_file:
        return json.load(schema_file)


@lru_cache(maxsize=16)
def _schema_tables_by_name(schema_path: str) -> dict[str, dict]:
    return {
        str(table.get("table")): table
        for table in _load_schema(schema_path)
        if table.get("table")
    }


@lru_cache(maxsize=32)
def _pick_display_column(schema_path: str, table_name: str) -> str | None:
    table = _schema_tables_by_name(schema_path).get(table_name)
    if not table:
        return None
    column_names = {column.get("name") for column in table.get("columns", [])}
    for candidate in DISPLAY_COLUMN_CANDIDATES:
        if candidate in column_names:
            return candidate
    return None


@lru_cache(maxsize=4)
def _build_foreign_key_resolution_map(schema_path: str) -> dict[str, tuple[str, str]]:
    resolution_map: dict[str, tuple[str, str]] = {}
    conflicts: set[str] = set()

    for table in _load_schema(schema_path):
        for column in table.get("columns", []):
            column_name = column.get("name")
            reference = column.get("references")
            if not column_name or not reference:
                continue

            target_table = str(reference).split(".", 1)[0]
            display_column = _pick_display_column(schema_path, target_table)
            if not display_column:
                continue

            candidate = (target_table, display_column)
            existing = resolution_map.get(column_name)
            if existing and existing != candidate:
                conflicts.add(column_name)
                resolution_map.pop(column_name, None)
                continue
            if column_name not in conflicts:
                resolution_map[column_name] = candidate

    return resolution_map


def _looks_like_uuid(value: object) -> bool:
    return isinstance(value, str) and bool(UUID_PATTERN.fullmatch(value.strip()))


def _resolved_output_key(column_name: str, display_column: str) -> str:
    if column_name.endswith("_id"):
        prefix = column_name[:-3]
        return f"{prefix}_{display_column}"
    if column_name == "id":
        return display_column
    return f"{column_name}_{display_column}"


def _is_acceptable_sql(sql: str) -> bool:
    q = sql.strip()
    if q.endswith(";"):
        q = q[:-1].rstrip()
    if not q or ";" in q:
        return False
    u = re.sub(r"\s+", " ", q).upper().strip()
    if not (u.startswith("SELECT ") or u.startswith("WITH ")):
        return False
    for bad in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE ", "CALL "):
        if bad in u:
            return False
    return True


def _safe_identifier(value: str) -> str:
    if not SAFE_IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value}")
    return value


class InsightsService:
    def parse_content_data(self, content):
        tables = []
        for row in content:
            txt = row[0]
            table_match = re.search(r"Table:\s*(\w+)", txt)
            table_name = table_match.group(1) if table_match else None

            columns = []
            col_matches = re.findall(r"- (\w+) \(([^)]+)\)", txt)

            for col_name, col_info in col_matches:
                col = {
                    "name": col_name,
                    "type": col_info.split(";")[0].strip(),
                }

                if "Primary Key" in col_info:
                    col["pk"] = True
                if "Foreign Key" in col_info:
                    fk_match = re.search(r"-> (\w+)\.(\w+)", col_info)
                    if fk_match:
                        col["fk"] = {
                            "table": fk_match.group(1),
                            "column": fk_match.group(2),
                        }

                columns.append(col)

            tables.append({"table": table_name, "columns": columns})
        return tables

    def _load_catalog_tables(self, vector_db: Session, catalog_source: str) -> list[dict]:
        stmt = select(models.EmbeddingModel.content).where(
            models.EmbeddingModel.data_source == catalog_source
        )
        embeddings = vector_db.execute(stmt).all()
        if embeddings:
            return self.parse_content_data(embeddings)

        schema_path = SCHEMA_PATHS[catalog_source]
        if not schema_path.is_file():
            return []
        return _load_schema(str(schema_path))

    def _fetch_display_values(
        self,
        exec_db: Session,
        schema_path: str,
        table_name: str,
        display_column: str,
        ids: set[str],
    ) -> dict[str, object]:
        if not ids:
            return {}

        tables = _schema_tables_by_name(schema_path)
        table = tables.get(table_name)
        if not table:
            return {}

        known_columns = {
            str(column.get("name"))
            for column in table.get("columns", [])
            if column.get("name")
        }
        if "id" not in known_columns or display_column not in known_columns:
            return {}

        safe_table = _safe_identifier(table_name)
        safe_display_column = _safe_identifier(display_column)
        stmt = text(
            f"SELECT id, {safe_display_column} "
            f"FROM {safe_table} "
            "WHERE id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        return {
            str(row["id"]): row[safe_display_column]
            for row in exec_db.execute(stmt, {"ids": sorted(ids)}).mappings().all()
        }

    def _resolve_uuid_fields(
        self,
        exec_db: Session,
        rows: list[dict],
        *,
        schema_path: str,
    ) -> list[dict]:
        if not rows:
            return rows

        resolution_map = _build_foreign_key_resolution_map(schema_path)
        ids_by_lookup: dict[tuple[str, str], set[str]] = {}

        for row in rows:
            for column_name, value in row.items():
                if not _looks_like_uuid(value):
                    continue
                lookup = resolution_map.get(column_name)
                if lookup:
                    ids_by_lookup.setdefault(lookup, set()).add(value)

        resolved_values = {
            lookup: self._fetch_display_values(exec_db, schema_path, lookup[0], lookup[1], ids)
            for lookup, ids in ids_by_lookup.items()
        }

        normalized_rows: list[dict] = []
        for row in rows:
            normalized_row: dict[str, object] = {}
            for column_name, value in row.items():
                if not _looks_like_uuid(value):
                    normalized_row[column_name] = value
                    continue

                lookup = resolution_map.get(column_name)
                if not lookup:
                    continue

                display_value = resolved_values.get(lookup, {}).get(value)
                normalized_row[_resolved_output_key(column_name, lookup[1])] = display_value

            normalized_rows.append(normalized_row)

        return normalized_rows

    def _execute_sql_rows(
        self,
        exec_db: Session,
        sql: str,
        *,
        schema_path: str,
    ) -> tuple[str, list[dict], str | None]:
        if not _is_acceptable_sql(sql):
            return (
                "skipped",
                [],
                "Query must be a single SELECT/WITH statement; write operations are blocked.",
            )

        try:
            result = exec_db.execute(text(sql))
            mappings = result.mappings().all()
            rows = [dict(m) for m in mappings]
            safe_rows = json.loads(json.dumps(rows, default=str))
            safe_rows = self._resolve_uuid_fields(exec_db, safe_rows, schema_path=schema_path)
            return "ok", safe_rows, None
        except DBAPIError as exc:
            try:
                exec_db.rollback()
            except SQLAlchemyError:
                pass
            return "error", [], str(exc.orig or exc).strip() or str(exc)
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            try:
                exec_db.rollback()
            except SQLAlchemyError:
                pass
            return "error", [], str(exc)

    def _execute_one_insight(
        self,
        exec_db: Session,
        insight: dict,
        *,
        schema_path: str,
    ) -> dict:
        base = {
            "insight_title": insight.get("insight_title") or "Insight",
            "insight_description": insight.get("insight_description"),
            "sql": insight.get("sql") or "",
        }

        status, rows, error = self._execute_sql_rows(exec_db, base["sql"], schema_path=schema_path)
        base["execution_status"] = status
        base["row_count"] = len(rows)
        base["rows"] = rows
        base["error"] = error
        return base

    def _normalize_chart_config(
        self,
        chart_type: str,
        chart_config: dict,
        rows: list[dict],
        *,
        schema_path: str,
    ) -> dict:
        if chart_type not in ALLOWED_CHART_TYPES:
            raise ValueError(f"Unsupported chart_type: {chart_type}")
        if not isinstance(chart_config, dict):
            raise ValueError("chart_config must be an object")

        required_keys = CHART_CONFIG_KEYS_BY_TYPE[chart_type]
        resolution_map = _build_foreign_key_resolution_map(schema_path)
        available_columns = {key for row in rows for key in row.keys()}
        normalized_config: dict[str, str] = {}

        for config_key in required_keys:
            raw_column = chart_config.get(config_key)
            if not isinstance(raw_column, str) or not raw_column.strip():
                raise ValueError(f"chart_config.{config_key} must be a non-empty string")
            column_name = raw_column.strip()
            if column_name not in available_columns and column_name in resolution_map:
                target_table, display_column = resolution_map[column_name]
                del target_table
                candidate = _resolved_output_key(column_name, display_column)
                if candidate in available_columns:
                    column_name = candidate
            if available_columns and column_name not in available_columns:
                raise ValueError(
                    f"chart_config.{config_key} references missing column '{raw_column}'"
                )
            normalized_config[config_key] = column_name

        optional_series = chart_config.get("series_key")
        if isinstance(optional_series, str) and optional_series.strip():
            series_column = optional_series.strip()
            if series_column not in available_columns and available_columns:
                raise ValueError(
                    f"chart_config.series_key references missing column '{optional_series}'"
                )
            normalized_config["series_key"] = series_column

        return normalized_config

    def _execute_one_chart(
        self,
        exec_db: Session,
        chart_spec: dict,
        *,
        schema_path: str,
    ) -> dict:
        base = {
            "chart_title": chart_spec.get("chart_title") or "Chart",
            "chart_description": chart_spec.get("chart_description"),
            "chart_type": chart_spec.get("chart_type"),
            "chart_config": chart_spec.get("chart_config") or {},
            "sql": chart_spec.get("sql") or "",
        }

        status, rows, error = self._execute_sql_rows(exec_db, base["sql"], schema_path=schema_path)
        base["execution_status"] = status
        base["row_count"] = len(rows)
        base["data"] = rows

        if status != "ok":
            base["error"] = error
            return base

        try:
            base["chart_config"] = self._normalize_chart_config(
                base["chart_type"],
                base["chart_config"],
                rows,
                schema_path=schema_path,
            )
            base["error"] = None
        except ValueError as exc:
            base["execution_status"] = "error"
            base["data"] = []
            base["row_count"] = 0
            base["error"] = str(exc)

        return base

    async def _get_insights_for_source(
        self,
        vector_db: Session,
        exec_db: Session | None,
        *,
        catalog_source: str,
        generator,
        parser,
    ) -> dict:
        if exec_db is None:
            return {
                "ok": False,
                "error": "oip_not_configured",
                "message": "OIP insights require `DB_URL_OIP` to be configured on the server.",
                "insights": [],
            }

        tables = self._load_catalog_tables(vector_db, catalog_source)
        if not tables:
            return {
                "ok": False,
                "error": "no_schema_context",
                "message": f"No schema context available for `{catalog_source}` insights.",
                "insights": [],
            }

        raw_insights = generator(tables)
        try:
            insights = parser(raw_insights)
        except ValueError as exc:
            return {
                "ok": False,
                "parse_error": str(exc),
                "raw_model_output": raw_insights[:8000],
                "insights": [],
            }

        schema_path = str(SCHEMA_PATHS[catalog_source])
        results: list[dict] = []
        for insight in insights:
            results.append(
                self._execute_one_insight(
                    exec_db,
                    insight,
                    schema_path=schema_path,
                )
            )

        return {"ok": True, "insights": results}

    async def _get_charts_for_source(
        self,
        vector_db: Session,
        exec_db: Session | None,
        *,
        catalog_source: str,
        generator,
        parser,
    ) -> dict:
        if exec_db is None:
            return {
                "ok": False,
                "error": "oip_not_configured",
                "message": "OIP chart APIs require `DB_URL_OIP` to be configured on the server.",
                "charts": [],
            }

        tables = self._load_catalog_tables(vector_db, catalog_source)
        if not tables:
            return {
                "ok": False,
                "error": "no_schema_context",
                "message": f"No schema context available for `{catalog_source}` chart APIs.",
                "charts": [],
            }

        raw_chart_specs = generator(tables)
        try:
            chart_specs = parser(raw_chart_specs)
        except ValueError as exc:
            return {
                "ok": False,
                "parse_error": str(exc),
                "raw_model_output": raw_chart_specs[:8000],
                "charts": [],
            }

        schema_path = str(SCHEMA_PATHS[catalog_source])
        results: list[dict] = []
        for chart_spec in chart_specs:
            results.append(
                self._execute_one_chart(
                    exec_db,
                    chart_spec,
                    schema_path=schema_path,
                )
            )

        return {"ok": True, "charts": results}

    async def get_salesforce_insights(
        self,
        vector_db: Session,
        sf_exec_db: Session,
    ) -> dict:
        return await self._get_insights_for_source(
            vector_db,
            sf_exec_db,
            catalog_source=datasource.SALESFORCE,
            generator=helpers.agent_helper.get_insights_salesforce,
            parser=helpers.agent_helper.parse_insights_json,
        )

    async def get_oip_insights(
        self,
        vector_db: Session,
        oip_exec_db: Session | None,
    ) -> dict:
        return await self._get_insights_for_source(
            vector_db,
            oip_exec_db,
            catalog_source=datasource.OIP,
            generator=helpers.agent_helper.get_insights_oip,
            parser=helpers.agent_helper.parse_insights_json,
        )

    async def get_salesforce_charts(
        self,
        vector_db: Session,
        sf_exec_db: Session,
    ) -> dict:
        return await self._get_charts_for_source(
            vector_db,
            sf_exec_db,
            catalog_source=datasource.SALESFORCE,
            generator=helpers.agent_helper.get_chart_specs_salesforce,
            parser=helpers.agent_helper.parse_chart_specs_json,
        )

    async def get_oip_charts(
        self,
        vector_db: Session,
        oip_exec_db: Session | None,
    ) -> dict:
        return await self._get_charts_for_source(
            vector_db,
            oip_exec_db,
            catalog_source=datasource.OIP,
            generator=helpers.agent_helper.get_chart_specs_oip,
            parser=helpers.agent_helper.parse_chart_specs_json,
        )
