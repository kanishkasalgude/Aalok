"""
PaymentService: the only thing in this codebase that talks to
integrations/razorpay/provider.py. Wraps the active PaymentProvider
(mock or real, chosen by get_active_provider() - never silently) plus
PaymentStatus transition bookkeeping. OrderService is the only caller.
"""
from __future__ import annotations

from typing import Optional

from ...domain.payments.models import PaymentStatus, transition_payment
from ...integrations.razorpay.provider import RazorpayProvider, get_active_provider, get_provider

# Signature verification (checkout + webhook) is a pure cryptographic check
# against whatever RAZORPAY_KEY_SECRET/RAZORPAY_WEBHOOK_SECRET is
# configured - it is NOT mode-dependent (unlike order creation/payment
# attempts, which genuinely differ between mock and real Razorpay). Always
# verified with the real algorithm, via a plain RazorpayProvider instance,
# regardless of whether PAYMENT_PROVIDER is currently "mock" - matching the
# pre-refactor razorpay_client.py, where these were standalone functions
# with no provider-mode branching at all.
_signature_verifier = RazorpayProvider()


class PaymentService:
    def get_active_provider(self) -> dict:
        return get_active_provider()

    def create_razorpay_order(self, amount_inr: float, receipt: str, notes: Optional[dict] = None) -> dict:
        return get_provider().create_order(amount_inr, receipt, notes)

    def attempt_payment(self, razorpay_order_id: str, amount_inr: float, force_fail: bool = False) -> dict:
        return get_provider().attempt_payment(razorpay_order_id, amount_inr, force_fail=force_fail)

    def fetch_payment(self, payment_id: str) -> dict:
        return get_provider().fetch_payment(payment_id)

    def verify_checkout_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        return _signature_verifier.verify_checkout_signature(order_id, payment_id, signature)

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        return _signature_verifier.verify_webhook_signature(raw_body, signature)

    def create_refund(self, payment_id: str, amount_inr: float, notes: Optional[dict] = None) -> dict:
        return get_provider().create_refund(payment_id, amount_inr, notes)

    def fetch_refund(self, refund_id: str) -> dict:
        return get_provider().fetch_refund(refund_id)

    @staticmethod
    def next_status(current: PaymentStatus, new: PaymentStatus) -> PaymentStatus:
        return transition_payment(current, new)


payment_service = PaymentService()
