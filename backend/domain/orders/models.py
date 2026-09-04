"""
InternalOrder: the canonical Aalok identity for a transaction. The
Razorpay order id is a *reference* this object carries, never the other
way around - Aalok's own domain does not become dependent on Razorpay's
ids (spec section 3: "The internal order ID must remain the canonical
Aalok identity").
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class OrderStatus(str, Enum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


# Explicit transition table (spec section 17/19) - illegal transitions raise
# instead of status strings being scattered/assigned freely across the codebase.
ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {OrderStatus.AUTHORIZED, OrderStatus.CAPTURED, OrderStatus.FAILED, OrderStatus.CANCELLED},
    OrderStatus.AUTHORIZED: {OrderStatus.CAPTURED, OrderStatus.FAILED, OrderStatus.CANCELLED},
    # a failed order is retryable against the SAME internal/Razorpay order (see OrderService) -
    # so FAILED may transition directly to CAPTURED (a successful retry) or back to itself (a
    # repeated failure) without ever creating a second order.
    OrderStatus.FAILED: {OrderStatus.CAPTURED, OrderStatus.FAILED, OrderStatus.CANCELLED},
    OrderStatus.CAPTURED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: set(),
    OrderStatus.REFUNDED: set(),
}


def transition_order(current: OrderStatus, new: OrderStatus) -> OrderStatus:
    if new == current or new in ORDER_TRANSITIONS.get(current, set()):
        return new
    raise ValueError(f"Illegal order status transition: {current.value} -> {new.value}")


class CheckoutMode(str, Enum):
    SINGLE_MERCHANT = "single_merchant"  # IMPLEMENTED - MVP default, see ARCHITECTURE.md section 12
    MARKETPLACE = "marketplace"          # ARCHITECTED FOR FUTURE ONLY - maps to Razorpay Route/Linked
                                          # Accounts; no logic in this codebase branches on this value
                                          # beyond documenting the extension point.


@dataclass
class InternalOrder:
    internal_order_id: str
    cart_id: str
    cart_version: int
    merchant_id: str
    session_id: str
    amount: float
    currency: str
    idempotency_key: str
    status: OrderStatus = OrderStatus.CREATED
    checkout_mode: CheckoutMode = CheckoutMode.SINGLE_MERCHANT
    razorpay_order_id: Optional[str] = None
    payment_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @staticmethod
    def create(cart_id: str, cart_version: int, merchant_id: str, session_id: str,
               amount: float, currency: str = "INR") -> "InternalOrder":
        return InternalOrder(
            internal_order_id=f"ord-{uuid.uuid4().hex[:12]}",
            cart_id=cart_id, cart_version=cart_version, merchant_id=merchant_id, session_id=session_id,
            amount=amount, currency=currency, idempotency_key=f"checkout:{cart_id}:{cart_version}",
        )

    def set_status(self, new: OrderStatus) -> None:
        self.status = transition_order(self.status, new)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["status"] = self.status.value
        d["checkout_mode"] = self.checkout_mode.value
        return d
