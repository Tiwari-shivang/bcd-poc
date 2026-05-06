"""
Schema context builder.

This module renders a rich, Markdown-style schema description directly from
the SQLAlchemy model metadata so types, enum values, primary keys and foreign
keys are always available to the LLM and always in sync with the models.

Two production-grade enhancements over the original implementation:

1. **FK-graph expansion** — when the caller passes a *seed* set of tables
   retrieved by embeddings, we walk the foreign-key graph one hop in BOTH
   directions and pull in every directly-related table. This guarantees that
   *bridging* tables (e.g. `agreements` sits between `gcn` and `program_sol`)
   are present in the context even when their name does not appear in the
   user's question. Without this, multi-hop JOINs are impossible to express.

2. **Explicit Relationships block** — at the bottom of the rendered context
   we emit a flat list of every FK edge between the selected tables, e.g.
   ``program_sol.agreement_id -> agreements.id``. The model no longer has to
   reconstruct the join graph by scanning per-column metadata.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import Enum as SAEnum

from database import BaseModel
from helpers import catalog_summary


# ──────────────────────────────────────────────────────────────────────────────
# Column / table rendering
# ──────────────────────────────────────────────────────────────────────────────


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


def _tables_by_name() -> Dict[str, object]:
    return {
        mapper.local_table.name: mapper.local_table
        for mapper in BaseModel.registry.mappers
        if mapper.local_table is not None
    }


# ──────────────────────────────────────────────────────────────────────────────
# Foreign-key graph
# ──────────────────────────────────────────────────────────────────────────────


def _build_fk_graph() -> Dict[str, Set[str]]:
    """Return a bidirectional adjacency map of FK relationships across all
    mapped tables. Used to expand a seed set of tables to include every
    directly-related table (parents AND children)."""
    graph: Dict[str, Set[str]] = defaultdict(set)
    for mapper in BaseModel.registry.mappers:
        if mapper.local_table is None:
            continue
        src = mapper.local_table.name
        for col in mapper.local_table.columns:
            for fk in col.foreign_keys:
                tgt = fk.column.table.name
                if tgt == src:
                    continue
                graph[src].add(tgt)
                graph[tgt].add(src)
    return graph


def _expand_with_related(seed: Iterable[str], hops: int = 1) -> List[str]:
    """Expand the seed set by walking the FK graph `hops` times.

    Order is preserved: original seed first, then newly-added tables in BFS
    order so the rendered context keeps the most-relevant tables on top.
    """
    graph = _build_fk_graph()
    seen: Set[str] = set()
    ordered: List[str] = []

    def _add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            ordered.append(name)

    frontier: List[str] = []
    for name in seed:
        _add(name)
        frontier.append(name)

    for _ in range(max(hops, 0)):
        next_frontier: List[str] = []
        for table in frontier:
            for nbr in sorted(graph.get(table, ())):
                if nbr not in seen:
                    _add(nbr)
                    next_frontier.append(nbr)
        if not next_frontier:
            break
        frontier = next_frontier

    return ordered


# ──────────────────────────────────────────────────────────────────────────────
# Relationships block
# ──────────────────────────────────────────────────────────────────────────────


def _render_relationships_block(table_names: Iterable[str]) -> str:
    """Render an explicit list of FK edges between the selected tables.

    Output looks like:

        ## Relationships (Foreign Keys)

        - program_sol.agreement_id -> agreements.id
        - agreements.gcn_id        -> gcn.id
        - gcn.account_id           -> accounts.id
    """
    table_set = set(table_names)
    edges: List[Tuple[str, str, str, str]] = []
    seen: Set[Tuple[str, str, str, str]] = set()

    for mapper in BaseModel.registry.mappers:
        if mapper.local_table is None:
            continue
        src = mapper.local_table.name
        if src not in table_set:
            continue
        for col in mapper.local_table.columns:
            for fk in col.foreign_keys:
                tgt = fk.column.table.name
                if tgt not in table_set:
                    continue
                edge = (src, col.name, tgt, fk.column.name)
                if edge in seen:
                    continue
                seen.add(edge)
                edges.append(edge)

    if not edges:
        return ""

    # Pad source columns for readability so the ``->`` arrows align in the
    # rendered prompt; this small visual cue noticeably reduces JOIN errors.
    src_width = max(len(f"{s}.{c}") for s, c, _, _ in edges)
    lines = ["## Relationships (Foreign Keys)", ""]
    for src, src_col, tgt, tgt_col in edges:
        left = f"{src}.{src_col}".ljust(src_width)
        lines.append(f"- {left} -> {tgt}.{tgt_col}")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def build_schema_context(
    table_names: Optional[Iterable[str]] = None,
    *,
    expand_related: bool = True,
    related_hops: int = 1,
    include_relationships: bool = True,
) -> str:
    """Return a Markdown-style schema description for the requested tables.

    Args:
        table_names: Seed table names (typically from embedding retrieval).
            If `None` or empty, every mapped table is rendered.
        expand_related: If True (default), expand the seed set through the
            FK graph so directly-related (parent/child/bridge) tables are
            always available. Critical for multi-hop JOIN correctness.
        related_hops: Number of FK hops to walk during expansion.
        include_relationships: If True (default), append a flat list of FK
            edges between the selected tables to make JOIN paths explicit.
    """
    tables = _tables_by_name()

    if table_names:
        # Drop unknowns (stale embedding rows, typos, etc.) before expansion.
        cleaned: List[str] = []
        seen: Set[str] = set()
        for name in table_names:
            if name in tables and name not in seen:
                seen.add(name)
                cleaned.append(name)

        if expand_related and cleaned:
            ordered = _expand_with_related(cleaned, hops=related_hops)
        else:
            ordered = cleaned

        selected = [tables[name] for name in ordered if name in tables]
    else:
        selected = list(tables.values())

    if not selected:
        return ""

    blocks: List[str] = []
    for table in selected:
        lines = [f"## Table: {table.name}", "", "### Columns", ""]
        lines.extend(_format_column(col) for col in table.columns)
        blocks.append("\n".join(lines))

    if include_relationships:
        rel_block = _render_relationships_block(t.name for t in selected)
        if rel_block:
            blocks.append(rel_block)

    return "\n\n---\n\n".join(blocks)


def build_catalog_context_from_embeddings(contents: list[str]) -> str:
    """Build SQL prompt context from stored embedding text (OIP path)."""
    parts = [str(c).strip() for c in contents if c and str(c).strip()]
    if not parts:
        return ""
    return "## OIP schema (from catalogue)\n\n" + "\n\n---\n\n".join(parts)


def _resolve_oip_schema_path(explicit: Optional[Path] = None) -> Optional[Path]:
    if explicit is not None:
        return explicit if explicit.is_file() else None
    env = os.getenv("OIP_SCHEMA_PATH", "").strip()
    if env:
        p = Path(env).expanduser()
        return p if p.is_file() else None
    default = Path(__file__).resolve().parent.parent / "schema_oip.json"
    return default if default.is_file() else None


def build_oip_context_from_repo_file(
    ordered_table_keys: List[str],
    *,
    schema_path: Optional[Path] = None,
) -> str:
    """Fallback when vector DB has no OIP embeddings: ship `schema_oip.json`.

    Honour ``OIP_SCHEMA_PATH`` env or sibling ``schema_oip.json`` in the repo root.
    If ``ordered_table_keys`` matches nothing (stale embedding keys only), emits
    the full catalogue from the JSON file so OIP NL→SQL still works offline.
    """
    path = _resolve_oip_schema_path(schema_path)
    if path is None:
        return ""
    try:
        raw_tables = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    if not isinstance(raw_tables, list):
        return ""
    by_name = {str(t.get("table")): t for t in raw_tables if t.get("table")}
    summaries: List[str] = []
    seen: Set[str] = set()
    for k in ordered_table_keys:
        if not k or k in seen:
            continue
        row = by_name.get(k)
        if not row:
            continue
        seen.add(k)
        summaries.append(catalog_summary.build_table_catalog_summary(row))
    if not summaries:
        for t in raw_tables:
            if t.get("table"):
                summaries.append(catalog_summary.build_table_catalog_summary(t))
    if not summaries:
        return ""
    return build_catalog_context_from_embeddings(summaries)
