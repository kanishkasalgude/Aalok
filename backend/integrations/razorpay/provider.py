"""
Razorpay TEST MODE payment provider, reorganized from the old top-level
razorpay_client.py into an explicit PaymentProvider interface with two
implementations - the HTTP/HMAC logic itself is unchanged (it was already
correct against Razorpay's documented Orders/Payments/Refunds/webhook
contracts).

Which provider is active is EXPLICIT via PAYMENT_PROVIDER (get_active_provider),
never silently inferred deep inside a call:
  PAYMENT_PROVIDER=razorpay_test  - real Razorpay test-mode REST API. If
                                     RAZORPAY_KEY_ID/SECRET aren't set, this
                                     raises PaymentProviderMisconfigured at
                                     call time rather than quietly mocking.
  PAYMENT_PROVIDER=mock           - forces mock mode even if keys are present.
  unset                           - inferred from whether RAZORPAY_KEY_ID is set.

Refunds are NEW in this refactor (the pre-refactor code had no refund path):
create_refund maps to Razorpay's real `POST /v1/payments/{id}/refund`
(only valid on a captured payment); fetch_refund to `GET /v1/refunds/{id}`.
The `refund.processed` webhook (not the synchronous API response) is
documented by Razorpay as the reliable source of final refund status - see
services/refund/service.py and api/routes/webhooks.py.

IMPORTANT: Razorpay also publishes an official MCP server
(github.com/razorpay/razorpay-mcp-server, 35+ tools) that could serve as an
alternate transport for this provider instead of raw REST calls. That is a
real product, but it is a merchant BACK-OFFICE automation surface, not a
consumer-checkout one - see integrations/razorpay/mcp_adapter.py for the
documented, deliberately-unimplemented extension point. It must never be
handed to the shopping LLM.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional

import requests

from ...core.errors import PaymentProviderMisconfigured

RAZORPAY_BASE = "https://api.razorpay.com/v1"


def _creds():
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if key_id and key_secret:
        return key_id, key_secret
    return None, None


def get_active_provider() -> dict:
    """Resolves which payment provider is actually active - the ONE place
    that inference from key-presence happens when PAYMENT_PROVIDER is
    unset. The frontend/API surfaces this so a demo is never ambiguous
    about which mode it's running in."""
    configured = os.environ.get("PAYMENT_PROVIDER", "").strip().lower()
    key_id, _ = _creds()
    webhook_secret_configured = bool(os.environ.get("RAZORPAY_WEBHOOK_SECRET"))
    if configured == "razorpay_test":
        if not key_id:
            return {"provider": "razorpay_test", "mode": "misconfigured", "keys_present": False,
                     "error": "PAYMENT_PROVIDER=razorpay_test but RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET "
                              "are not set."}
        return {"provider": "razorpay_test", "mode": "test", "keys_present": True,
                "key_id": key_id, "webhook_secret_configured": webhook_secret_configured}
    if configured == "mock":
        return {"provider": "mock", "mode": "mock", "keys_present": bool(key_id),
                 "webhook_secret_configured": webhook_secret_configured,
                 "note": "PAYMENT_PROVIDER=mock forces mock mode even though real keys are present."
                          if key_id else None}
    if key_id:
        return {"provider": "razorpay_test", "mode": "test", "keys_present": True,
                 "key_id": key_id, "webhook_secret_configured": webhook_secret_configured,
                 "note": "Inferred from RAZORPAY_KEY_ID being set; set PAYMENT_PROVIDER=razorpay_test explicitly to silence this."}
    return {"provider": "mock", "mode": "mock", "keys_present": False,
             "webhook_secret_configured": webhook_secret_configured,
             "note": "No PAYMENT_PROVIDER set and no Razorpay keys configured; defaulting to mock for local dev."}


def _require_provider_ready() -> dict:
    status = get_active_provider()
    if status["mode"] == "misconfigured":
        raise PaymentProviderMisconfigured(status["error"])
    return status


class PaymentProvider(ABC):
    """create_order/fetch_order/fetch_payment/verify_payment/handle_webhook
    (via verify_webhook_signature) + create_refund/fetch_refund - the exact
    set of Razorpay capabilities this MVP implements. See
    domain/payments/models.py::PaymentCapability for what's deliberately
    NOT here (subscriptions, payment links, QR, invoices, marketplace
    route, agentic/reserve-pay)."""

    @abstractmethod
    def create_order(self, amount_inr: float, receipt: str, notes: Optional[dict] = None) -> dict: ...

    @abstractmethod
    def fetch_order(self, order_id: str) -> dict: ...

    @abstractmethod
    def attempt_payment(self, order_id: str, amount_inr: float, force_fail: bool = False) -> dict: ...

    @abstractmethod
    def fetch_payment(self, payment_id: str) -> dict: ...

    @abstractmethod
    def verify_checkout_signature(self, order_id: str, payment_id: str, signature: str) -> bool: ...

    @abstractmethod
    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool: ...

    @abstractmethod
    def create_refund(self, payment_id: str, amount_inr: float, notes: Optional[dict] = None) -> dict: ...

    @abstractmethod
    def fetch_refund(self, refund_id: str) -> dict: ...


class MockProvider(PaymentProvider):
    """Exercises every step of the flow without hitting Razorpay's servers.
    Every response carries "mode": "mock"."""

    def create_order(self, amount_inr: float, receipt: str, notes: Optional[dict] = None) -> dict:
        amount_paise = int(round(amount_inr * 100))
        return {"mode": "mock", "id": f"order_mock_{uuid.uuid4().hex[:14]}", "amount": amount_paise,
                "currency": "INR", "receipt": receipt, "status": "created", "notes": notes or {}}

    def fetch_order(self, order_id: str) -> dict:
        return {"mode": "mock", "id": order_id, "status": "created"}

    def attempt_payment(self, order_id: str, amount_inr: float, force_fail: bool = False) -> dict:
        amount_paise = int(round(amount_inr * 100))
        if force_fail:
            return {"mode": "mock", "id": f"pay_mock_{uuid.uuid4().hex[:14]}", "order_id": order_id,
                    "amount": amount_paise, "status": "failed", "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Payment authentication failed (simulated failure for demo)."}
        time.sleep(0.3)  # a realistic UI state-transition delay
        return {"mode": "mock", "id": f"pay_mock_{uuid.uuid4().hex[:14]}", "order_id": order_id,
                "amount": amount_paise, "status": "captured"}

    def fetch_payment(self, payment_id: str) -> dict:
        return {"mode": "mock", "id": payment_id, "status": "captured"}

    def verify_checkout_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        return True  # nothing to verify in mock mode - there is no real Checkout.js session

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        return True

    def create_refund(self, payment_id: str, amount_inr: float, notes: Optional[dict] = None) -> dict:
        amount_paise = int(round(amount_inr * 100))
        return {"mode": "mock", "id": f"rfnd_mock_{uuid.uuid4().hex[:14]}", "payment_id": payment_id,
                "amount": amount_paise, "status": "processed", "notes": notes or {}}

    def fetch_refund(self, refund_id: str) -> dict:
        return {"mode": "mock", "id": refund_id, "status": "processed"}


class RazorpayProvider(PaymentProvider):
    """Real Razorpay TEST MODE Orders/Payments/Refunds REST API over HTTP
    Basic Auth, per Razorpay's documented contract. Requires
    PAYMENT_PROVIDER=razorpay_test + real RAZORPAY_KEY_ID/SECRET -
    _require_provider_ready() raises PaymentProviderMisconfigured otherwise,
    at call time, never silently degrading to mock."""

    def create_order(self, amount_inr: float, receipt: str, notes: Optional[dict] = None) -> dict:
        _require_provider_ready()
        key_id, key_secret = _creds()
        amount_paise = int(round(amount_inr * 100))
        resp = requests.post(f"{RAZORPAY_BASE}/orders", auth=(key_id, key_secret),
                              json={"amount": amount_paise, "currency": "INR", "receipt": receipt, "notes": notes or {}},
                              timeout=15)
        resp.raise_for_status()
        data = resp.json()
        data["mode"] = "test"
        return data

    def fetch_order(self, order_id: str) -> dict:
        _require_provider_ready()
        key_id, key_secret = _creds()
        resp = requests.get(f"{RAZORPAY_BASE}/orders/{order_id}", auth=(key_id, key_secret), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        data["mode"] = "test"
        return data

    def attempt_payment(self, order_id: str, amount_inr: float, force_fail: bool = False) -> dict:
        """Real test mode ALWAYS requires a real Checkout.js session -
        force_fail has no effect here on purpose. The Order exists on
        Razorpay's servers; nothing is captured/failed until the browser
        completes (or declines) Checkout.js and the result is verified
        server-side (verify_checkout_signature) or confirmed by the
        webhook."""
        _require_provider_ready()
        amount_paise = int(round(amount_inr * 100))
        return {
            "mode": "test", "id": f"pay_test_pending_{uuid.uuid4().hex[:10]}", "order_id": order_id,
            "amount": amount_paise, "status": "requires_checkout_js",
            "note": ("Real Razorpay test keys are configured. The Order was created via the live "
                     "Orders API. Completing payment requires the Razorpay Checkout.js widget "
                     "(loaded client-side) - open it with this order_id, and use the documented "
                     "Test Mode UPI handles: success@razorpay or failure@razorpay."),
        }

    def fetch_payment(self, payment_id: str) -> dict:
        key_id, key_secret = _creds()
        if not key_id:
            raise PaymentProviderMisconfigured("Cannot fetch payment: no Razorpay keys configured.")
        resp = requests.get(f"{RAZORPAY_BASE}/payments/{payment_id}", auth=(key_id, key_secret), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def verify_checkout_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        """HMAC-SHA256(order_id + "|" + payment_id, key_secret), per
        Razorpay's documented algorithm. `order_id` MUST be the id THIS
        SERVER created and stored, never one echoed back by the browser."""
        _, key_secret = _creds()
        if not key_secret:
            raise PaymentProviderMisconfigured("Cannot verify a Checkout signature: RAZORPAY_KEY_SECRET is not configured.")
        message = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(key_secret.encode(), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        """HMAC-SHA256 of the RAW request body using the separate Webhook
        Secret (Razorpay Dashboard) - NOT the same value as RAZORPAY_KEY_SECRET."""
        webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
        if not webhook_secret:
            return False
        expected = hmac.new(webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def create_refund(self, payment_id: str, amount_inr: float, notes: Optional[dict] = None) -> dict:
        """POST /v1/payments/{id}/refund - only valid on a captured
        payment (Razorpay rejects a refund request otherwise; that error
        surfaces as a normal requests.HTTPError to the caller)."""
        _require_provider_ready()
        key_id, key_secret = _creds()
        amount_paise = int(round(amount_inr * 100))
        resp = requests.post(f"{RAZORPAY_BASE}/payments/{payment_id}/refund", auth=(key_id, key_secret),
                              json={"amount": amount_paise, "notes": notes or {}}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        data["mode"] = "test"
        return data

    def fetch_refund(self, refund_id: str) -> dict:
        key_id, key_secret = _creds()
        if not key_id:
            raise PaymentProviderMisconfigured("Cannot fetch refund: no Razorpay keys configured.")
        resp = requests.get(f"{RAZORPAY_BASE}/refunds/{refund_id}", auth=(key_id, key_secret), timeout=15)
        resp.raise_for_status()
        return resp.json()


def get_provider() -> PaymentProvider:
    """Returns the concrete provider instance for the currently active
    mode - the single place PaymentService asks 'which provider'."""
    status = get_active_provider()
    if status["mode"] == "misconfigured":
        raise PaymentProviderMisconfigured(status["error"])
    return MockProvider() if status["mode"] == "mock" else RazorpayProvider()
