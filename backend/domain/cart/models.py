"""
Cart as a proper domain object (spec section 11), not an ad hoc dict pair.

MVP multi-merchant policy (spec section 12, "preferred MVP"): one cart maps
to exactly one merchant. `CartService.add_item` is what actually enforces
this (raises CartMerchantMismatchError) - this module just carries the
`merchant_id` field the enforcement checks against.

`version` is the idempotency backbone (spec section 14): it increments on
every mutation, and OrderService keys a pending order by
`checkout:{cart_id}:{cart_version}` so a checkout retry against an
unmodified cart reuses the same order, while an actual cart edit
(new version) is treated as a new logical checkout.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class CartStatus(str, Enum):
    ACTIVE = "active"
    LOCKED = "locked"       # snapshotted into a CartMandate for a checkout attempt
    EXPIRED = "expired"
    CHECKED_OUT = "checked_out"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CartItem:
    merchant_id: str
    product_id: str
    name: str
    unit_price: float
    quantity: int = 1
    variant_id: str | None = None
    role: str = "primary"  # "primary" | "addon" - used by the policy engine's attribute check

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Cart:
    cart_id: str
    session_id: str
    merchant_id: str
    items: list = field(default_factory=list)  # list[CartItem]
    version: int = 1
    subtotal: float = 0.0
    discount: float = 0.0
    delivery_fee: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    currency: str = "INR"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    expires_at: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
    status: CartStatus = CartStatus.ACTIVE

    @staticmethod
    def create(session_id: str, merchant_id: str) -> "Cart":
        return Cart(cart_id=f"cart-{uuid.uuid4().hex[:10]}", session_id=session_id, merchant_id=merchant_id)

    def recalculate_totals(self) -> None:
        self.subtotal = round(sum(i.unit_price * i.quantity for i in self.items), 2)
        self.total = round(self.subtotal - self.discount + self.delivery_fee + self.tax, 2)
        self.updated_at = _now_iso()

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > datetime.fromisoformat(self.expires_at)

    def idempotency_key(self) -> str:
        return f"checkout:{self.cart_id}:{self.version}"

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["items"] = [i.to_dict() for i in self.items]
        d["status"] = self.status.value
        return d
