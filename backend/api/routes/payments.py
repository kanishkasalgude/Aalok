"""
Payment + refund routes. GET /api/payment-mode, POST /api/order/verify-payment
and POST /api/order/payment-failed are the pre-refactor routes (the backend
counterparts to Razorpay Checkout.js's success `handler` and
`payment.failed` listener), preserved byte-for-byte in behavior. The rest
(POST /api/payments/create, GET /api/payments/{id}, refunds) are the new
generalized surface.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.errors import RefundError
from ...domain.audit import events
from ...domain.orders.models import OrderStatus
from ...repositories import audit_repo
from ...services.authorization.service import AuthorizationService
from ...services.cart.service import cart_service
from ...services.order.service import order_service
from ...services.payment.service import payment_service
from ...services.refund.service import refund_service
from ...services.session.store import session_store
from ...integrations.merchants.registry import get_adapter
from ...repositories import order_repo

router = APIRouter()


class VerifyPaymentRequest(BaseModel):
    session_id: str
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str


class PaymentFailedReport(BaseModel):
    session_id: str
    razorpay_order_id: str
    error_code: Optional[str] = None
    error_description: Optional[str] = None


class RefundRequest(BaseModel):
    reason: str
    amount: Optional[float] = None


class CheckoutRequest(BaseModel):
    session_id: str
    cart_id: str
    force_fail: bool = False


@router.get("/api/payment-mode")
def payment_mode():
    """Which payment provider is actually active - the frontend shows this
    as a persistent badge so a demo is never ambiguous about which mode
    it's running in."""
    return payment_service.get_active_provider()


def _record_and_consume(session_id: str, order, status: str) -> None:
    cart = cart_service.get_cart(order.cart_id)
    merchant = get_adapter(order.merchant_id)
    if not cart or not merchant:
        return
    primary_item = next((i for i in cart.items if i.role == "primary"), cart.items[0] if cart.items else None)
    upsell_item = next((i for i in cart.items if i.role != "primary"), None)
    if primary_item:
        order_repo.record_order(session_id, order.merchant_id, merchant.merchant.name, primary_item.product_id,
                                 upsell_item.product_id if upsell_item else None, order.amount,
                                 upsell_item is not None, status)
    if status == "captured":
        session = session_store.get(session_id)
        if session and session.authorization:
            AuthorizationService.consume(session.authorization)


@router.post("/api/order/verify-payment")
def verify_payment(req: VerifyPaymentRequest):
    """The backend counterpart to Checkout.js's success `handler`. THIS is
    what actually marks a cart payment_captured - never the browser
    callback firing by itself. Verifies razorpay_signature server-side
    against the order id THIS SERVER created, never trusting the request
    body's razorpay_order_id for the actual check."""
    order = order_service.get_order_by_razorpay_id(req.razorpay_order_id)
    if order is None or order.session_id != req.session_id:
        raise HTTPException(400, "Unknown order for this session - was it created by this server?")

    if order.status == OrderStatus.CAPTURED:
        return {"status": "success", "already_captured": True, "order": order.to_dict(),
                "audit_trail": audit_repo.get_audit_trail(req.session_id)}

    verified = payment_service.verify_checkout_signature(order.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature)
    if not verified:
        audit_repo.log_event(req.session_id, "payment_verification_failed", "failed", {
            "internal_order_id": order.internal_order_id, "razorpay_payment_id": req.razorpay_payment_id,
            "reason": "Checkout signature did not match - the callback is not trusted on its own.",
        })
        raise HTTPException(400, "Payment signature verification failed - payment NOT marked captured.")

    fetch_note = None
    try:
        remote = payment_service.fetch_payment(req.razorpay_payment_id)
        fetch_note = {"remote_status": remote.get("status")}
    except Exception as e:
        fetch_note = {"remote_confirmation_error": str(e)}

    payment = {"mode": "test", "id": req.razorpay_payment_id, "order_id": order.razorpay_order_id, "status": "captured"}
    audit_repo.log_event(req.session_id, events.PAYMENT_ATTEMPTED, "success", {"payment": payment})
    audit_repo.log_event(req.session_id, events.PAYMENT_CAPTURED, "success", {
        "payment": payment, "internal_order_id": order.internal_order_id,
        "signature_verified": True, "fetch_payment_confirmation": fetch_note,
    })
    order.set_status(OrderStatus.CAPTURED)
    order.payment_id = req.razorpay_payment_id
    _record_and_consume(req.session_id, order, "captured")
    audit_repo.log_event(req.session_id, events.ORDER_CONFIRMED, "success", {"internal_order_id": order.internal_order_id})

    return {"status": "success", "order": order.to_dict(), "payment": payment,
            "audit_trail": audit_repo.get_audit_trail(req.session_id)}


@router.post("/api/order/payment-failed")
def report_payment_failed(req: PaymentFailedReport):
    """The backend counterpart to Checkout.js's `rzp.on('payment.failed', ...)`
    listener. Never marks anything captured - only failed/pending, and only
    if it isn't already captured (race-safe against the webhook)."""
    order = order_service.get_order_by_razorpay_id(req.razorpay_order_id)
    if order is None or order.session_id != req.session_id:
        raise HTTPException(400, "Unknown order for this session.")

    if order.status == OrderStatus.CAPTURED:
        return {"status": "success", "note": "Already captured - ignoring a late failure report.",
                "audit_trail": audit_repo.get_audit_trail(req.session_id)}

    payment = {"mode": "test", "order_id": req.razorpay_order_id, "status": "failed",
               "error_code": req.error_code, "error_description": req.error_description}
    audit_repo.log_event(req.session_id, events.PAYMENT_ATTEMPTED, "failed", {"payment": payment})
    audit_repo.log_event(req.session_id, events.PAYMENT_FAILED, "failed",
                          {"payment": payment, "internal_order_id": order.internal_order_id})
    order.set_status(OrderStatus.FAILED)  # retryable: next /api/order/confirm call reuses the SAME order
    _record_and_consume(req.session_id, order, "failed")
    audit_repo.log_event(req.session_id, "recovery", "success", {
        "message": "Real Razorpay Test Mode payment declined. Order left in a safe pending state — "
                   "no duplicate order was created, and the user can retry (same order) with a "
                   "different UPI handle (e.g. success@razorpay).",
        "internal_order_id": order.internal_order_id,
    })
    return {"status": "payment_failed", "order_id": req.razorpay_order_id,
            "audit_trail": audit_repo.get_audit_trail(req.session_id)}


# --- new generalized surface --------------------------------------------------

@router.post("/api/payments/create")
def create_payment(req: CheckoutRequest):
    """Same underlying operation as POST /api/orders (OrderService.checkout
    revalidates -> authorizes -> policy-checks -> creates/reuses the order
    -> attempts payment) - exposed under /api/payments too, matching the
    spec's requested route inventory. There is no separate 'just charge
    this amount' path that skips Authorization/Policy."""
    cart = cart_service.get_cart(req.cart_id)
    session = session_store.get(req.session_id)
    if cart is None or session is None or session.intent_mandate is None:
        return {"error": "Unknown cart or session."}
    return order_service.checkout(cart, session.intent_mandate, session.authorization,
                                   force_fail=req.force_fail, buyer="api_client")


@router.get("/api/payments/refunds")
def list_refunds(limit: int = 100):
    """Registered BEFORE the /{payment_id} route below: FastAPI/Starlette
    matches routes in registration order, and a single-segment {payment_id}
    catch-all would otherwise swallow the literal path "refunds" first."""
    from ...repositories import refund_repo
    return {"refunds": refund_repo.list_refunds(limit=limit)}


@router.get("/api/payments/{payment_id}")
def get_payment(payment_id: str):
    order = order_service.get_order_by_payment_id(payment_id)
    if order is None:
        return {"error": f"Unknown payment_id '{payment_id}'."}
    return {"payment_id": payment_id, "internal_order_id": order.internal_order_id,
            "status": order.status.value, "amount": order.amount, "currency": order.currency}


@router.post("/api/payments/{internal_order_id}/refund")
def create_refund(internal_order_id: str, req: RefundRequest):
    order = order_service.get_order(internal_order_id)
    if order is None:
        return {"error": f"Unknown internal_order_id '{internal_order_id}'."}
    audit_repo.log_event(order.session_id, events.REFUND_REQUESTED, "pending",
                          {"internal_order_id": internal_order_id, "reason": req.reason})
    try:
        refund = refund_service.create_refund(order, req.reason, req.amount)
    except RefundError as e:
        return {"error": str(e)}
    audit_repo.log_event(order.session_id, events.REFUND_COMPLETED, "success", refund.to_dict())
    return refund.to_dict()


@router.get("/api/payments/refunds/{refund_id}")
def get_refund(refund_id: str):
    from ...repositories import refund_repo
    refund = refund_repo.get_refund(refund_id)
    if refund is None:
        return {"error": f"Unknown refund_id '{refund_id}'."}
    return refund
