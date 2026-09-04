"""
AP2-pattern Intent Mandate / Cart Mandate. Moved from the old top-level
mandates.py, generalized from "restaurant" to "merchant" so it applies to
any of Aalok's synthetic categories, not just food.

`dietary_constraint` is kept (not generalized away) because it is genuinely
still how the food vertical's constraint is expressed and every existing
food test asserts against it; `required_attributes` is the general form
other categories use (e.g. a fashion request for {"color": "black"}). The
Policy Engine (policy.py) checks both.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IntentMandate:
    mandate_id: str
    session_id: str
    max_amount: float
    currency: str
    max_delivery_time_min: Optional[int]
    dietary_constraint: Optional[str]          # food-specific convenience constraint, e.g. "high-protein"
    required_attributes: dict = field(default_factory=dict)  # generalized attribute constraints, any category
    requires_human_approval: bool = True
    created_at: str = field(default_factory=_now_iso)
    status: str = "active"

    @staticmethod
    def create(session_id: str, max_amount: float, max_delivery_time_min: Optional[int] = None,
               dietary_constraint: Optional[str] = None, required_attributes: Optional[dict] = None,
               currency: str = "INR") -> "IntentMandate":
        return IntentMandate(
            mandate_id=f"intent-{uuid.uuid4().hex[:10]}",
            session_id=session_id,
            max_amount=max_amount,
            currency=currency,
            max_delivery_time_min=max_delivery_time_min,
            dietary_constraint=dietary_constraint,
            required_attributes=required_attributes or {},
        )

    def to_dict(self):
        return self.__dict__.copy()


@dataclass
class CartMandate:
    mandate_id: str
    parent_intent_id: str
    items: list  # list of {item_id, name, price, quantity, role}
    total_amount: float
    currency: str
    estimated_delivery_time_min: int
    merchant_id: str
    merchant_open: bool
    created_at: str = field(default_factory=_now_iso)
    expires_at: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())

    @staticmethod
    def create(parent_intent: IntentMandate, items: list, merchant_id: str,
               merchant_open: bool, estimated_delivery_time_min: int) -> "CartMandate":
        total = round(sum(i["price"] * i.get("quantity", 1) for i in items), 2)
        return CartMandate(
            mandate_id=f"cart-{uuid.uuid4().hex[:10]}",
            parent_intent_id=parent_intent.mandate_id,
            items=items,
            total_amount=total,
            currency=parent_intent.currency,
            estimated_delivery_time_min=estimated_delivery_time_min,
            merchant_id=merchant_id,
            merchant_open=merchant_open,
        )

    def to_dict(self):
        return self.__dict__.copy()
