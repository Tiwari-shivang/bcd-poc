"""Salesforce vs OIP routing using dual catalogue retrieval + conservative rules."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

import config
from helpers import prompts
from helpers.datasource import OIP, SALESFORCE


@dataclass(frozen=True)
class RetrievalSnapshot:
    salesforce_keys: Tuple[str, ...]
    salesforce_best_distance: Optional[float]
    oip_keys: Tuple[str, ...]
    oip_best_distance: Optional[float]


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, "").strip())
    except (ValueError, AttributeError):
        return default


ROUTER_EMBEDDING_STRONG_MAX = _env_float("ROUTER_EMBEDDING_STRONG_MAX", 0.55)
# When raw (non-lexical) SF vs OIP best cosine distances differ by at most this,
# treat retrieval as ambiguous and ask the user to pick a database.
ROUTER_EMBEDDING_CLOSE_DELTA_MAX = _env_float("ROUTER_EMBEDDING_CLOSE_DELTA_MAX", 0.1)


def embeddings_ambiguous_close_distances(
    snapshot_embedding_only: RetrievalSnapshot,
) -> bool:
    """True when both catalogues have vector hits with similar best distances."""
    sk = snapshot_embedding_only.salesforce_keys
    ok = snapshot_embedding_only.oip_keys
    sd = snapshot_embedding_only.salesforce_best_distance
    od = snapshot_embedding_only.oip_best_distance
    if not sk or not ok or sd is None or od is None:
        return False
    return abs(float(sd) - float(od)) <= ROUTER_EMBEDDING_CLOSE_DELTA_MAX


def clarification_message() -> str:
    return (
        "Which database should I use for this answer — **Salesforce** or **OIP**? "
        "Reply with **Salesforce** or **OIP**, or send `\"data_source\": \"salesforce\"` "
        'or `"data_source": "oip"` with your request. '
        "I'll run **your question** against the database you choose."
    )

def snapshot_from_hits(sf_hits: Iterable, oip_hits: Iterable) -> RetrievalSnapshot:
    sk, sd = _dedupe(sf_hits)
    ok, od = _dedupe(oip_hits)
    return RetrievalSnapshot(tuple(sk), sd, tuple(ok), od)


def _dedupe(hits: Iterable, cap: int = 16) -> Tuple[list[str], Optional[float]]:
    seen: set[str] = set()
    keys: list[str] = []
    best: Optional[float] = None
    for row, dist in hits:
        k = getattr(row, "key", None)
        if not k or k in seen:
            continue
        dval = float(dist)
        best = dval if best is None else min(best, dval)
        seen.add(k)
        keys.append(k)
        if len(keys) >= cap:
            break
    return keys, best


def _strong(d: Optional[float]) -> bool:
    return d is not None and d <= ROUTER_EMBEDDING_STRONG_MAX


def decide_route_without_llm(snapshot: RetrievalSnapshot) -> str:
    s_ok = _strong(snapshot.salesforce_best_distance)
    o_ok = _strong(snapshot.oip_best_distance)
    if s_ok and o_ok:
        return "clarify"
    if s_ok and not o_ok:
        return SALESFORCE
    if o_ok and not s_ok:
        return OIP
    if snapshot.oip_keys and not snapshot.salesforce_keys:
        return OIP
    if snapshot.salesforce_keys and not snapshot.oip_keys:
        if s_ok:
            return SALESFORCE
        return "llm_vote"
    if not snapshot.salesforce_keys and not snapshot.oip_keys:
        return "llm_vote"
    return "llm_vote"


def llm_secondary_router_vote(user_message: str, snapshot: RetrievalSnapshot) -> str:
    client = config.OpenAIClient
    body = prompts.get_secondary_database_router_prompt(
        user_message=user_message,
        salesforce_tables=", ".join(snapshot.salesforce_keys[:8]) or "—",
        oip_tables=", ".join(snapshot.oip_keys[:8]) or "—",
        salesforce_distance=str(snapshot.salesforce_best_distance),
        oip_distance=str(snapshot.oip_best_distance),
    )
    rsp = client.chat.completions.create(
        model=config.AZURE_OPENAI_CHAT_DEPLOYMENT,
        messages=[
            {
                "role": "system",
                "content": "First line only: SALESFORCE, OIP, or ASK_USER.",
            },
            {"role": "user", "content": body},
        ],
        temperature=0.0,
        max_tokens=8,
    )
    line = (rsp.choices[0].message.content or "").strip().splitlines()[0].strip().upper()
    if line.startswith("SALESFORCE"):
        return SALESFORCE
    if line.startswith("OIP"):
        return OIP
    return "ASK_USER"


def final_route_from_evidence(
    user_message: str,
    snapshot: RetrievalSnapshot,
    *,
    snapshot_embedding_only: RetrievalSnapshot | None = None,
) -> str:
    if snapshot_embedding_only is not None and embeddings_ambiguous_close_distances(
        snapshot_embedding_only
    ):
        return "clarify"
    p = decide_route_without_llm(snapshot)
    if p == "clarify":
        return "clarify"
    if p in (SALESFORCE, OIP):
        return p
    v = llm_secondary_router_vote(user_message, snapshot)
    if v == "ASK_USER":
        return "clarify"
    return v
