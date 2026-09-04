"""
Structured intent representation (spec section 23). The LLM (or the
offline heuristic fallback) populates this from free text; the backend
validates its structure and shape, but the intent itself is NEVER
authoritative for payment - it only ever becomes an IntentMandate (see
mandates.py), which the deterministic Policy Engine checks a cart against.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Intent:
    query: str
    category: list = field(default_factory=list)          # e.g. ["fashion", "beauty"]
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    preferences: dict = field(default_factory=dict)         # e.g. {"recipient": "sister", "occasion": "birthday"}
    delivery_requirement: Optional[int] = None                # max minutes, if stated
    required_attributes: dict = field(default_factory=dict)     # e.g. {"dietary_tags": "high-protein"}
    raw_summary: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(d: dict) -> "Intent":
        known = {f for f in Intent.__dataclass_fields__}
        return Intent(**{k: v for k, v in d.items() if k in known and v is not None} | {
            "query": d.get("query") or d.get("raw_summary", ""),
        })
