"""
SQL post-processing utilities.

Postgres enums are case-sensitive, but LLMs frequently emit enum values in the
wrong case (e.g. `'implemented'` instead of `'Implemented'`), which causes
`psycopg2.errors.InvalidTextRepresentation` at execution time.

This module introspects every `Enum` column defined on our SQLAlchemy models,
builds a canonical lookup keyed by the lowercased value, and rewrites any
matching string literal in a generated SQL query to use the exact casing the
database expects. The models stay the single source of truth, so new enum
values are picked up automatically.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict

from sqlalchemy import Enum as SAEnum

from database import BaseModel


_STRING_LITERAL_RE = re.compile(r"'((?:[^']|'')*)'")


@lru_cache(maxsize=1)
def _canonical_enum_map() -> Dict[str, str]:
    """Return a mapping of lowercased enum value -> canonical enum value.

    Collisions (two enums with the same lowercased text but different canonical
    casing) are rare in practice; if one occurs the first encountered wins,
    which is acceptable for a POC.
    """
    canonical: Dict[str, str] = {}
    for mapper in BaseModel.registry.mappers:
        for column in mapper.local_table.columns:
            column_type = column.type
            if isinstance(column_type, SAEnum) and column_type.enums:
                for value in column_type.enums:
                    key = value.lower()
                    canonical.setdefault(key, value)
    return canonical


def normalize_enum_literals(sql: str) -> str:
    """Rewrite quoted string literals in `sql` to the canonical enum casing.

    Only literals whose lowercased value matches a known enum value are
    rewritten; all other literals are left untouched so we never rewrite
    unrelated data (names, addresses, etc.).
    """
    if not sql:
        return sql

    canonical = _canonical_enum_map()
    if not canonical:
        return sql

    def _replace(match: re.Match) -> str:
        raw_value = match.group(1).replace("''", "'")
        canonical_value = canonical.get(raw_value.lower())
        if canonical_value is None or canonical_value == raw_value:
            return match.group(0)
        escaped = canonical_value.replace("'", "''")
        return f"'{escaped}'"

    return _STRING_LITERAL_RE.sub(_replace, sql)
