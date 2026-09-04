"""
Payment-safety properties, exercised through the real FastAPI app (mock
payment mode - no network calls, no Razorpay credentials needed):

  - a cart rejected by the Commerce Policy Engine makes ZERO calls to
    create a Razorpay Order
  - an accepted cart makes EXACTLY ONE create_order call
  - a failed payment leaves the order pending/retryable, not duplicated
  - retrying the SAME cart reuses the SAME Razorpay Order id
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from backend import main as main_module
from backend.domain.commerce.mandates import IntentMandate
from backend.services.authorization.service import AuthorizationService
from backend.services.cart.service import cart_service
from backend.services.order.service import order_service
from backend.services.payment.service import PaymentService

client = TestClient(main_module.app)


def _call_counter(monkeypatch, target_cls, attr_name):
    """Wraps a method with a call counter while still invoking the real
    implementation (mock mode - no network), so behavior is unchanged and
    only the call count is observed."""
    original = getattr(target_cls, attr_name)
    calls = {"count": 0}

    def wrapper(self, *args, **kwargs):
        calls["count"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(target_cls, attr_name, wrapper)
    return calls


def test_rejected_cart_makes_zero_razorpay_order_calls(monkeypatch):
    calls = _call_counter(monkeypatch, PaymentService, "create_razorpay_order")
    result = client.post("/api/demo/policy-rejection").json()
    assert result["status"] == "rejected_by_policy"
    assert result["razorpay_called"] is False
    assert calls["count"] == 0


def test_accepted_cart_makes_exactly_one_razorpay_order_call(monkeypatch):
    calls = _call_counter(monkeypatch, PaymentService, "create_razorpay_order")
    result = client.post("/api/external/purchase", json={"item_id": "d501", "max_amount": 500}).json()
    assert result["status"] == "success"
    assert calls["count"] == 1


def test_failed_payment_is_pending_and_retryable_without_new_order(monkeypatch):
    calls = _call_counter(monkeypatch, PaymentService, "create_razorpay_order")
    r1 = client.post("/api/external/purchase", json={"item_id": "d501", "max_amount": 500, "force_fail": True}).json()
    assert r1["status"] == "payment_failed"
    assert calls["count"] == 1  # only the first attempt created an order


def test_retry_reuses_the_same_razorpay_order_id(monkeypatch):
    """The concrete guarantee: retrying a failed payment for the SAME cart
    must NOT create a second Razorpay Order."""
    calls = _call_counter(monkeypatch, PaymentService, "create_razorpay_order")
    session_id = f"test-retry-session-{uuid.uuid4().hex[:8]}"
    intent = IntentMandate.create(session_id=session_id, max_amount=500, max_delivery_time_min=60, dietary_constraint=None)
    authorization = AuthorizationService.create(intent)
    cart = cart_service.create_cart(session_id, "r5")
    cart_service.add_item(cart.cart_id, "d501", "r5", role="primary")

    r1 = order_service.checkout(cart, intent, authorization, force_fail=True, buyer="test")
    assert r1["status"] == "payment_failed"

    r2 = order_service.checkout(cart, intent, authorization, force_fail=False, buyer="test")
    assert r2["status"] == "success"

    assert r1["order"]["id"] == r2["order"]["id"], "retry must reuse the same Razorpay Order"
    assert calls["count"] == 1, "only ONE create_order call across both attempts"

    steps = [e["step"] for e in r2["audit_trail"]]
    assert "order_created" in steps
    assert "order_reused" in steps
    assert steps.count("order_created") == 1, "no duplicate order_created event"


def test_duplicate_checkout_on_an_already_captured_cart_makes_no_new_order_call(monkeypatch):
    calls = _call_counter(monkeypatch, PaymentService, "create_razorpay_order")
    session_id = f"test-dup-session-{uuid.uuid4().hex[:8]}"
    intent = IntentMandate.create(session_id=session_id, max_amount=500, max_delivery_time_min=60, dietary_constraint=None)
    authorization = AuthorizationService.create(intent)
    cart = cart_service.create_cart(session_id, "r5")
    cart_service.add_item(cart.cart_id, "d501", "r5", role="primary")

    r1 = order_service.checkout(cart, intent, authorization, buyer="test")
    assert r1["status"] == "success"

    r2 = order_service.checkout(cart, intent, authorization, buyer="test")
    assert r2.get("already_captured") is True
    assert r2["order"]["id"] == r1["order"]["id"]
    assert calls["count"] == 1, "checking out an already-captured cart again must not call Razorpay again"


# Webhook idempotency (signed, production-shaped) is covered in
# tests/test_razorpay_integration.py.
