"""
Real Razorpay Test Mode integration: Checkout.js handoff, payment signature
verification, and the hardened, signature-verified webhook.

No real Razorpay credentials are used or required - `requests.post`/`.get`
in integrations/razorpay/provider.py are monkeypatched to return responses
shaped exactly like Razorpay's real Orders/Payments/Refunds API, so these
tests exercise the actual code path (HTTP call construction, response
handling, HMAC computation) against Razorpay's documented contract.
"""
import hashlib
import hmac
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from backend import main as main_module
from backend.domain.commerce.mandates import IntentMandate
from backend.domain.orders.models import OrderStatus
from backend.integrations.razorpay import provider as razorpay_provider
from backend.services.authorization.service import AuthorizationService
from backend.services.cart.service import cart_service
from backend.services.order.service import order_service
from backend.services.payment.service import payment_service
from conftest import auth_headers

client = TestClient(main_module.app)

FAKE_KEY_ID = "rzp_test_fake000000"
FAKE_KEY_SECRET = "fake_key_secret_for_tests"
FAKE_WEBHOOK_SECRET = "fake_webhook_secret_for_tests"


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture
def real_test_mode(monkeypatch):
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay_test")
    monkeypatch.setenv("RAZORPAY_KEY_ID", FAKE_KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", FAKE_KEY_SECRET)

    created_orders = {}

    def fake_post(url, auth=None, json=None, timeout=None):
        assert url.endswith("/orders")
        assert auth == (FAKE_KEY_ID, FAKE_KEY_SECRET)
        order_id = f"order_fake_{uuid.uuid4().hex[:12]}"
        order = {"id": order_id, "amount": json["amount"], "currency": json["currency"],
                 "receipt": json["receipt"], "status": "created", "notes": json.get("notes", {})}
        created_orders[order_id] = order
        return _FakeResponse(order)

    monkeypatch.setattr(razorpay_provider.requests, "post", fake_post)
    return created_orders


def _checkout(session_id: str, item_id: str = "d501", max_amount: float = 500, force_fail: bool = False):
    intent = IntentMandate.create(session_id=session_id, max_amount=max_amount, max_delivery_time_min=60, dietary_constraint=None)
    authorization = AuthorizationService.create(intent)
    cart = cart_service.create_cart(session_id, "r5")
    cart_service.add_item(cart.cart_id, item_id, "r5", role="primary")
    return order_service.checkout(cart, intent, authorization, force_fail=force_fail, buyer="test")


def _sign_checkout(order_id: str, payment_id: str) -> str:
    message = f"{order_id}|{payment_id}".encode()
    return hmac.new(FAKE_KEY_SECRET.encode(), message, hashlib.sha256).hexdigest()


def _sign_webhook(raw_body: bytes) -> str:
    return hmac.new(FAKE_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()


# --- signature primitives ---------------------------------------------------

def test_checkout_signature_verification_accepts_correctly_signed_payload(real_test_mode):
    sig = _sign_checkout("order_abc", "pay_xyz")
    assert payment_service.verify_checkout_signature("order_abc", "pay_xyz", sig) is True


def test_checkout_signature_verification_rejects_tampered_payload(real_test_mode):
    sig = _sign_checkout("order_abc", "pay_xyz")
    assert payment_service.verify_checkout_signature("order_abc", "pay_DIFFERENT", sig) is False


def test_webhook_signature_verification(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", FAKE_WEBHOOK_SECRET)
    body = b'{"event": "payment.captured"}'
    good_sig = _sign_webhook(body)
    assert payment_service.verify_webhook_signature(body, good_sig) is True
    assert payment_service.verify_webhook_signature(body, "wrong-signature") is False
    assert payment_service.verify_webhook_signature(body + b" ", good_sig) is False


def test_webhook_signature_verification_with_no_secret_configured(monkeypatch):
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    assert payment_service.verify_webhook_signature(b"{}", "anything") is False


# --- real test mode never simulates a payment outcome -----------------------

def test_real_test_mode_creates_order_and_awaits_checkout_never_simulating_capture(real_test_mode):
    session_id = f"rtm-{uuid.uuid4().hex[:8]}"
    # force_fail=True must be IGNORED in real test mode - never fabricate a failure either
    result = _checkout(session_id, force_fail=True)
    assert result["status"] == "awaiting_checkout"
    assert result["order"]["id"].startswith("order_fake_")
    assert result["checkout"]["key_id"] == FAKE_KEY_ID
    assert result["checkout"]["order_id"] == result["order"]["id"]
    steps = [e["step"] for e in result["audit_trail"]]
    assert "payment_captured" not in steps
    assert "payment_failed" not in steps
    assert "awaiting_checkout" in steps


def test_payment_mode_badge_reflects_real_test_mode(real_test_mode):
    resp = client.get("/api/payment-mode").json()
    assert resp["mode"] == "test"
    assert resp["provider"] == "razorpay_test"
    assert resp["key_id"] == FAKE_KEY_ID


def test_razorpay_test_mode_with_missing_keys_fails_loudly(monkeypatch):
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay_test")
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    resp = client.get("/api/payment-mode").json()
    assert resp["mode"] == "misconfigured"

    result = _checkout(f"misconfig-{uuid.uuid4().hex[:8]}")
    assert result["status"] == "provider_misconfigured"


# --- /api/order/verify-payment -----------------------------------------------

def test_verify_payment_marks_captured_on_valid_signature(real_test_mode):
    session_id = f"verify-ok-{uuid.uuid4().hex[:8]}"
    result = _checkout(session_id)
    order_id = result["order"]["id"]
    payment_id = f"pay_fake_{uuid.uuid4().hex[:10]}"
    signature = _sign_checkout(order_id, payment_id)

    resp = client.post("/api/order/verify-payment", json={
        "session_id": session_id, "razorpay_payment_id": payment_id,
        "razorpay_order_id": order_id, "razorpay_signature": signature,
    }, headers=auth_headers(session_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"

    steps = [e["step"] for e in body["audit_trail"]]
    assert "payment_captured" in steps
    captured_event = [e for e in body["audit_trail"] if e["step"] == "payment_captured"][0]
    assert captured_event["detail"]["signature_verified"] is True

    order = order_service.get_order_by_razorpay_id(order_id)
    assert order.status == OrderStatus.CAPTURED


def test_verify_payment_rejects_invalid_signature_and_does_not_capture(real_test_mode):
    session_id = f"verify-bad-{uuid.uuid4().hex[:8]}"
    result = _checkout(session_id)
    order_id = result["order"]["id"]

    resp = client.post("/api/order/verify-payment", json={
        "session_id": session_id, "razorpay_payment_id": "pay_whatever",
        "razorpay_order_id": order_id, "razorpay_signature": "totally-forged-signature",
    }, headers=auth_headers(session_id))
    assert resp.status_code == 400

    audit = client.get(f"/api/audit?session_id={session_id}", headers=auth_headers(session_id)).json()["events"]
    steps = [e["step"] for e in audit]
    assert "payment_captured" not in steps
    assert "payment_verification_failed" in steps


def test_verify_payment_cannot_be_forged_with_a_different_order_id(real_test_mode):
    """A caller cannot claim a cheaper/different order_id to get a
    favorable signature check - the server always uses ITS OWN stored
    order id."""
    session_id = f"verify-swap-{uuid.uuid4().hex[:8]}"
    result = _checkout(session_id)
    real_order_id = result["order"]["id"]
    payment_id = f"pay_fake_{uuid.uuid4().hex[:10]}"
    forged_signature = _sign_checkout("order_attacker_controlled", payment_id)

    resp = client.post("/api/order/verify-payment", json={
        "session_id": session_id, "razorpay_payment_id": payment_id,
        "razorpay_order_id": real_order_id, "razorpay_signature": forged_signature,
    }, headers=auth_headers(session_id))
    assert resp.status_code == 400


# --- hardened webhook ---------------------------------------------------------

def test_webhook_without_secret_configured_returns_501(monkeypatch):
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    resp = client.post("/api/webhook/razorpay", content=b"{}", headers={"x-razorpay-signature": "whatever"})
    assert resp.status_code == 501


def test_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", FAKE_WEBHOOK_SECRET)
    resp = client.post("/api/webhook/razorpay", content=b'{"event": "payment.captured"}',
                        headers={"x-razorpay-signature": "wrong"})
    assert resp.status_code == 400


def test_webhook_processes_signed_payment_captured_and_is_idempotent(monkeypatch, real_test_mode):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", FAKE_WEBHOOK_SECRET)

    session_id = f"webhook-ok-{uuid.uuid4().hex[:8]}"
    result = _checkout(session_id)
    order_id = result["order"]["id"]

    payload = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": f"pay_{uuid.uuid4().hex[:10]}", "order_id": order_id, "status": "captured"}}},
    }
    raw = json.dumps(payload).encode()
    sig = _sign_webhook(raw)
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    headers = {"x-razorpay-signature": sig, "x-razorpay-event-id": event_id, "content-type": "application/json"}

    r1 = client.post("/api/webhook/razorpay", content=raw, headers=headers)
    r2 = client.post("/api/webhook/razorpay", content=raw, headers=headers)  # Razorpay-style retry/duplicate

    assert r1.status_code == 200
    assert r1.json()["status"] == "processed"
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate_ignored"

    audit = client.get(f"/api/audit?session_id={session_id}", headers=auth_headers(session_id)).json()["events"]
    webhook_events = [e for e in audit if e["step"] == "webhook_received"]
    captured_events = [e for e in audit if e["step"] == "payment_captured"]
    assert len(webhook_events) == 1, "a duplicate webhook delivery must not log a second audit event"
    assert len(captured_events) == 1, "a duplicate webhook delivery must not double-apply the state transition"


def test_webhook_handles_payment_failed(monkeypatch, real_test_mode):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", FAKE_WEBHOOK_SECRET)

    session_id = f"webhook-fail-{uuid.uuid4().hex[:8]}"
    result = _checkout(session_id)
    order_id = result["order"]["id"]

    payload = {
        "event": "payment.failed",
        "payload": {"payment": {"entity": {"id": f"pay_{uuid.uuid4().hex[:10]}", "order_id": order_id, "status": "failed"}}},
    }
    raw = json.dumps(payload).encode()
    headers = {"x-razorpay-signature": _sign_webhook(raw), "x-razorpay-event-id": f"evt_{uuid.uuid4().hex[:12]}"}

    resp = client.post("/api/webhook/razorpay", content=raw, headers=headers)
    assert resp.status_code == 200

    audit = client.get(f"/api/audit?session_id={session_id}", headers=auth_headers(session_id)).json()["events"]
    steps = [e["step"] for e in audit]
    assert "payment_failed" in steps
    assert "payment_captured" not in steps
