"""
Schema context builder.

The SQL-generation prompt was previously fed very thin context (just a
comma-separated list of column names per table), which caused the LLM to
hallucinate column names and enum values. This module renders a rich,
Markdown-style schema description directly from the SQLAlchemy model
metadata so types, enum values, primary keys and foreign keys are always
available to the LLM and always in sync with the models.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy import Enum as SAEnum

from database import BaseModel


def _format_type(column) -> str:
    column_type = column.type
    if isinstance(column_type, SAEnum) and column_type.enums:
        values = ", ".join(column_type.enums)
        return f"enum: {values}"
    try:
        return str(column_type).lower()
    except Exception:
        return column_type.__class__.__name__.lower()


def _format_column(column) -> str:
    parts: List[str] = [_format_type(column)]

    if column.primary_key:
        parts.append("Primary Key")
    if not column.nullable and not column.primary_key:
        parts.append("Not Null")
    if getattr(column, "unique", False):
        parts.append("Unique")

    for fk in column.foreign_keys:
        target = f"{fk.column.table.name}.{fk.column.name}"
        ondelete = getattr(fk, "ondelete", None)
        fk_str = f"Foreign Key -> {target}"
        if ondelete:
            fk_str += f", On Delete: {ondelete}"
        parts.append(fk_str)

    return f"* {column.name} ({', '.join(parts)})"


def _tables_by_name():
    return {
        mapper.local_table.name: mapper.local_table
        for mapper in BaseModel.registry.mappers
        if mapper.local_table is not None
    }


def build_schema_context(table_names: Optional[Iterable[str]] = None) -> str:
    """Return a Markdown-style schema description for the requested tables.

    If `table_names` is None or empty, every mapped table is rendered. Unknown
    names are silently skipped so the caller can pass whatever was retrieved
    from the embedding search without worrying about stale entries.
    """
    tables = _tables_by_name()

    if table_names:
        seen: set = set()
        ordered: List[str] = []
        for name in table_names:
            if name in tables and name not in seen:
                seen.add(name)
                ordered.append(name)
        selected = [tables[name] for name in ordered]
    else:
        selected = list(tables.values())

    if not selected:
        return ""

    blocks: List[str] = []
    for table in selected:
        lines = [f"## Table: {table.name}", "", "### Columns", ""]
        lines.extend(_format_column(col) for col in table.columns)
        blocks.append("\n".join(lines))

    return "\n\n---\n\n".join(blocks)
