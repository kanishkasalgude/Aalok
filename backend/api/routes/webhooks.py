"""
Production-shaped Razorpay webhook receiver (see ARCHITECTURE.md "Webhook
lifecycle"). Preserved byte-for-byte in behavior from the pre-refactor
main.py::razorpay_webhook, reorganized around a small WebhookEventRouter so
`payment.*`/`order.paid` events go to order confirmation and
`refund.processed` goes to RefundService, instead of one long if/elif.

1. reads the RAW body (signature is over raw bytes, not re-parsed JSON)
2. verifies X-Razorpay-Signature via HMAC-SHA256 with RAZORPAY_WEBHOOK_SECRET
3. dedupes on X-Razorpay-Event-Id (Razorpay's documented idempotency key)
4. handles payment.captured / payment.failed / order.paid / refund.processed
5. looks up the internal order via OrderService's razorpay_order_id index
6. is idempotent: a duplicate event_id returns 200 without touching state
   twice; an already-captured order is not re-recorded

No RAZORPAY_WEBHOOK_SECRET configured -> the endpoint refuses to process
ANYTHING (501), rather than silently accepting unverified payloads.
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException, Request

from ...domain.audit import events
from ...domain.orders.models import OrderStatus
from ...repositories import audit_repo
from ...services.order.service import order_service
from ...services.payment.service import payment_service
from .payments import _record_and_consume

router = APIRouter()


def _handle_payment_event(event_type: str, order_id: str, payment_id: str, session_id: str) -> None:
    order = order_service.get_order_by_razorpay_id(order_id)
    if not order:
        return
    audit_repo.log_event(session_id, events.WEBHOOK_RECEIVED, "success",
                          {"event": event_type, "order_id": order_id, "payment_id": payment_id})

    if event_type in ("payment.captured", "order.paid"):
        if order.status != OrderStatus.CAPTURED:
            payment = {"mode": "test", "id": payment_id, "order_id": order_id, "status": "captured"}
            audit_repo.log_event(session_id, events.PAYMENT_CAPTURED, "success",
                                  {"payment": payment, "internal_order_id": order.internal_order_id, "source": "webhook"})
            order.set_status(OrderStatus.CAPTURED)
            order.payment_id = payment_id
            _record_and_consume(session_id, order, "captured")
    elif event_type == "payment.failed":
        if order.status != OrderStatus.CAPTURED:
            payment = {"mode": "test", "id": payment_id, "order_id": order_id, "status": "failed"}
            audit_repo.log_event(session_id, events.PAYMENT_FAILED, "failed",
                                  {"payment": payment, "internal_order_id": order.internal_order_id, "source": "webhook"})
            order.set_status(OrderStatus.FAILED)
            _record_and_consume(session_id, order, "failed")


def _handle_refund_event(razorpay_refund_id: str, session_id: str) -> None:
    from ...services.refund.service import refund_service
    audit_repo.log_event(session_id, events.WEBHOOK_RECEIVED, "success",
                          {"event": "refund.processed", "razorpay_refund_id": razorpay_refund_id})
    refund_service.handle_refund_webhook(razorpay_refund_id)


@router.post("/api/webhook/razorpay")
@router.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")
    event_id = request.headers.get("x-razorpay-event-id")

    if not os.environ.get("RAZORPAY_WEBHOOK_SECRET"):
        raise HTTPException(501, "RAZORPAY_WEBHOOK_SECRET is not configured - refusing to process "
                                  "an unverifiable webhook. See README 'Webhook configuration'.")
    if not payment_service.verify_webhook_signature(raw_body, signature):
        raise HTTPException(400, "Invalid X-Razorpay-Signature - webhook rejected.")

    try:
        body = json.loads(raw_body)
    except ValueError:
        raise HTTPException(400, "Malformed webhook body.")

    event_type = body.get("event", "")
    payload = body.get("payload", {})
    payment_entity = (payload.get("payment", {}) or {}).get("entity", {})
    refund_entity = (payload.get("refund", {}) or {}).get("entity", {})
    order_id = payment_entity.get("order_id")
    payment_id = payment_entity.get("id")
    dedup_key = event_id or f"{event_type}:{payment_id or refund_entity.get('id')}:{order_id}"

    first_delivery = audit_repo.mark_webhook_processed(dedup_key, order_id or refund_entity.get("id", ""), event_type)
    if not first_delivery:
        return {"status": "duplicate_ignored", "event_id": dedup_key}

    if event_type == "refund.processed":
        internal_order = order_service.get_order_by_payment_id(refund_entity.get("payment_id", ""))
        session_id = internal_order.session_id if internal_order else "unknown-session"
        _handle_refund_event(refund_entity.get("id", ""), session_id)
        return {"status": "processed", "event_id": dedup_key}

    order = order_service.get_order_by_razorpay_id(order_id)
    if not order:
        # A real webhook for an order this process doesn't know about (e.g. a
        # restart) - acknowledge with 200 so Razorpay doesn't retry.
        return {"status": "processed", "event_id": dedup_key, "note": "Unknown order_id, no session to update."}

    _handle_payment_event(event_type, order_id, payment_id, order.session_id)
    return {"status": "processed", "event_id": dedup_key}
