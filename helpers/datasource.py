"""Datasource constants for Salesforce vs OIP catalogue partitioning and routing."""

from __future__ import annotations

import re
from typing import Optional

SALESFORCE = "salesforce"
OIP = "oip"


def normalize_source(value: Optional[str]) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    v = str(value).strip().lower()
    if v in {"sf", "salesforce"}:
        return SALESFORCE
    if v in {"oip"}:
        return OIP
    return None


def parse_source_from_reply(message: str) -> Optional[str]:
    m = message.strip().lower()
    if len(m) > 128:
        return None
    for t in re.split(r"[\s,]+", m):
        n = normalize_source(t)
        if n:
            return n
        if "salesforce" in t:
            return SALESFORCE
        if t == "oip":
            return OIP
    if "salesforce" in m and "oip" not in m:
        return SALESFORCE
    if "oip" in m and "salesforce" not in m:
        return OIP
    return None
