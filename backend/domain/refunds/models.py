"""
Refund as a first-class domain object (spec section 13) - new in this
refactor. Maps to Razorpay's real Refunds API (`POST /v1/payments/{id}/refund`,
only ever on a captured payment; final status is confirmed by the
`refund.processed` webhook, not just the synchronous API response - see
integrations/razorpay/provider.py). No UI for this; API + tests only.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class RefundStatus(str, Enum):
    REQUESTED = "requested"
    PROCESSED = "processed"
    FAILED = "failed"
    REVERSED = "reversed"   # rare - mirrors Razorpay's own refund states


REFUND_TRANSITIONS: dict[RefundStatus, set[RefundStatus]] = {
    RefundStatus.REQUESTED: {RefundStatus.PROCESSED, RefundStatus.FAILED},
    RefundStatus.PROCESSED: {RefundStatus.REVERSED},
    RefundStatus.FAILED: set(),
    RefundStatus.REVERSED: set(),
}


def transition_refund(current: RefundStatus, new: RefundStatus) -> RefundStatus:
    if new == current or new in REFUND_TRANSITIONS.get(current, set()):
        return new
    raise ValueError(f"Illegal refund status transition: {current.value} -> {new.value}")


@dataclass
class Refund:
    refund_id: str
    internal_order_id: str
    payment_id: str
    amount: float
    reason: str
    status: RefundStatus = RefundStatus.REQUESTED
    provider_reference: Optional[str] = None  # Razorpay's refund id, once created
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @staticmethod
    def create(internal_order_id: str, payment_id: str, amount: float, reason: str) -> "Refund":
        return Refund(refund_id=f"rfnd-{uuid.uuid4().hex[:10]}", internal_order_id=internal_order_id,
                      payment_id=payment_id, amount=amount, reason=reason)

    def set_status(self, new: RefundStatus) -> None:
        self.status = transition_refund(self.status, new)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["status"] = self.status.value
        return d
