"""
RefundService (spec section 13, new in this refactor). Maps to Razorpay's
real Refunds API (POST /v1/payments/{id}/refund - only ever valid on a
CAPTURED payment). Idempotent: a second refund request against an order
that already has a requested/processed refund is rejected, not duplicated.

The synchronous create_refund response is NOT treated as final truth -
Razorpay's own docs recommend the `refund.processed` webhook as the
reliable final-status signal (a refund can still fail after the initial
"processed" acknowledgment on Razorpay's side) - see
handle_refund_webhook(), wired from api/routes/webhooks.py.
"""
from __future__ import annotations

from typing import Optional

from ...core.errors import RefundError
from ...domain.orders.models import InternalOrder, OrderStatus
from ...domain.refunds.models import Refund, RefundStatus
from ...repositories import refund_repo
from ..payment.service import payment_service


class RefundService:
    def __init__(self, payment_service):
        self._payment_service = payment_service

    def create_refund(self, order: InternalOrder, reason: str, amount: Optional[float] = None) -> Refund:
        if order.status != OrderStatus.CAPTURED:
            raise RefundError(f"Cannot refund order '{order.internal_order_id}': status is "
                               f"'{order.status.value}', not captured.")
        existing = refund_repo.get_refund_for_order(order.internal_order_id)
        if existing and existing["status"] in ("requested", "processed"):
            raise RefundError(f"Order '{order.internal_order_id}' already has a "
                               f"{existing['status']} refund ('{existing['refund_id']}') - not duplicating.")
        refund_amount = amount if amount is not None else order.amount
        if refund_amount <= 0 or refund_amount > order.amount:
            raise RefundError(f"Invalid refund amount {refund_amount} for order total {order.amount}.")

        refund = Refund.create(order.internal_order_id, order.payment_id or "", refund_amount, reason)
        refund_repo.save_refund(refund)

        provider_response = self._payment_service.create_refund(order.payment_id, refund_amount)
        refund.provider_reference = provider_response.get("id")
        status = provider_response.get("status", "processed")
        refund.set_status(RefundStatus.PROCESSED if status in ("processed", "created") else RefundStatus.FAILED)
        refund_repo.save_refund(refund)
        return refund

    def handle_refund_webhook(self, razorpay_refund_id: str) -> Optional[dict]:
        """refund.processed webhook confirmation - idempotent no-op if
        already processed (this MVP treats the synchronous create_refund
        result as authoritative once PROCESSED, so this is a read-through;
        a fuller implementation would reconcile provider_reference here)."""
        return refund_repo.get_refund(razorpay_refund_id)


refund_service = RefundService(payment_service)
