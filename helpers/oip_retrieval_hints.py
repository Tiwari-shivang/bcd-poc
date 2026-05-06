"""When OIP vector rows are missing or sparse, infer candidate tables from schema_oip.json.

This keeps routing + schema context aligned with OIP analytical questions that share
terminology with CRM tables (projects, accounts, …) where embedding retrieval alone
would leave ``oip_best_distance`` unset and Salesforce would incorrectly win by default.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, List, Sequence, Tuple


class _Keyed:
    __slots__ = ("key",)

    def __init__(self, key: str) -> None:
        self.key = key


def _schema_path() -> Path | None:
    env = os.getenv("OIP_SCHEMA_PATH", "").strip()
    candidates: List[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(Path(__file__).resolve().parent.parent / "schema_oip.json")
    for p in candidates:
        if p.is_file():
            return p
    return None


_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "that",
        "this",
        "than",
        "then",
        "they",
        "them",
        "have",
        "has",
        "had",
        "was",
        "were",
        "are",
        "not",
        "but",
        "can",
        "will",
        "you",
        "your",
        "how",
        "any",
        "all",
        "per",
        "via",
        "get",
        "such",
        "also",
        "only",
        "just",
        "over",
        "out",
        "our",
        "its",
        "who",
        "way",
        "may",
        "new",
        "now",
        "one",
        "two",
        "first",
        "last",
        "here",
        "what",
        "when",
        "where",
        "which",
        "whom",
        "does",
        "did",
        "being",
        "each",
        "other",
        "some",
        "very",
        "much",
        "too",
        "list",
        "show",
        "give",
        "tell",
        "find",
    }
)


def _bare_tokens(question: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", question.lower())
        if len(t) >= 3 and t not in _STOP
    }


def _expand_tokens(toks: set[str]) -> set[str]:
    out = set(toks)
    for t in list(toks):
        if t == "countries":
            out.add("country")
        elif t == "country":
            out.add("countries")
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            out.add(t[:-1])
    return out


def _col_terms(identifier: str) -> set[str]:
    out: set[str] = set()
    for p in identifier.lower().split("_"):
        if p in {"id", "pk", "fk"} or len(p) < 2:
            continue
        out.add(p)
    return out


def _token_matches_lex_term(term: str, toks: set[str]) -> bool:
    if term in toks:
        return True
    if len(term) < 4:
        return False
    for tg in toks:
        if len(tg) < 4:
            continue
        if tg.startswith(term) or term.startswith(tg):
            return True
    return False


@lru_cache(maxsize=1)
def _table_lexicons() -> tuple[tuple[str, frozenset[str]], ...]:
    path = _schema_path()
    if path is None:
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    rows: list[tuple[str, frozenset[str]]] = []
    for tbl in data:
        tname = tbl.get("table")
        if not tname:
            continue
        terms: set[str] = set(_col_terms(str(tname)))
        for c in tbl.get("columns") or []:
            n = str(c.get("name", "") or "")
            terms.update(_col_terms(n))
        cleaned = frozenset(t for t in terms if len(t) >= 2)
        if cleaned:
            rows.append((str(tname), cleaned))
    return tuple(rows)


def _lexical_min_overlap() -> int:
    raw = os.getenv("OIP_LEXICAL_MIN_OVERLAP", "").strip()
    try:
        return max(1, min(int(raw), 8))
    except ValueError:
        return 2


def _router_pseudo_distance() -> float:
    raw = os.getenv("OIP_LEXICON_ROUTER_DISTANCE", "").strip()
    try:
        return max(0.18, min(float(raw), 0.62))
    except ValueError:
        return 0.47


def _lexical_top_k() -> int:
    raw = os.getenv("OIP_LEXICAL_TOP_K", "").strip()
    try:
        return max(3, min(int(raw), 16))
    except ValueError:
        return 10


def _table_anchor_boost(table_name: str, toks: set[str]) -> int:
    tn = table_name.lower()
    if tn in toks:
        return 2
    pts = 0
    for part in tn.split("_"):
        if len(part) >= 3 and part in toks:
            pts = max(pts, 1)
    return pts


def _score_oip_lexical(question: str) -> list[tuple[str, int]]:
    toks = _expand_tokens(_bare_tokens(question))
    if not toks:
        return []
    need = _lexical_min_overlap()
    out: list[tuple[str, int]] = []
    for tname, lex in _table_lexicons():
        matched = {term for term in lex if _token_matches_lex_term(term, toks)}
        score = len(matched) + _table_anchor_boost(tname, toks)
        if score >= need:
            out.append((tname, score))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out


def lexical_oip_hints_ordered(question: str) -> list[tuple[str, float]]:
    """Synthetic (table, pseudo-distance) tuples for router ordering (lower = better)."""
    synth = _router_pseudo_distance()
    ranked = _score_oip_lexical(question)[: _lexical_top_k()]
    return [(tbl, synth + idx * 0.0005) for idx, (tbl, _) in enumerate(ranked)]


def merge_oip_vector_hits(vector_hits: Sequence, question: str) -> list[tuple[Any, float]]:
    """Keep real pgvector neighbours, union keyed lexical hits, sorted by distance."""
    rows: list[tuple[Any, float]] = [(r, float(d)) for r, d in vector_hits]
    seen = {getattr(r, "key", None) for r, _ in rows if getattr(r, "key", None)}
    for tbl, dist in lexical_oip_hints_ordered(question):
        if tbl not in seen:
            rows.append((_Keyed(tbl), dist))
            seen.add(tbl)
    rows.sort(key=lambda x: float(x[1]))
    return rows


def iter_oip_hits_for_router(
    raw_vector_hits: Iterable,
    question: str,
) -> list[tuple[Any, float]]:
    return merge_oip_vector_hits(list(raw_vector_hits), question)
