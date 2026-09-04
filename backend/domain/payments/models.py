"""Payment-side state machine and capability model (spec sections 17-18)."""
from __future__ import annotations

from enum import Enum


class PaymentStatus(str, Enum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


PAYMENT_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.CREATED: {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED, PaymentStatus.FAILED, PaymentStatus.CANCELLED},
    PaymentStatus.AUTHORIZED: {PaymentStatus.CAPTURED, PaymentStatus.FAILED, PaymentStatus.CANCELLED},
    PaymentStatus.FAILED: {PaymentStatus.RETRYING, PaymentStatus.CANCELLED},
    PaymentStatus.RETRYING: {PaymentStatus.CAPTURED, PaymentStatus.FAILED},
    PaymentStatus.CAPTURED: {PaymentStatus.REFUNDED},
    PaymentStatus.CANCELLED: set(),
    PaymentStatus.REFUNDED: set(),
}


def transition_payment(current: PaymentStatus, new: PaymentStatus) -> PaymentStatus:
    if new == current or new in PAYMENT_TRANSITIONS.get(current, set()):
        return new
    raise ValueError(f"Illegal payment status transition: {current.value} -> {new.value}")


class PaymentCapability(str, Enum):
    """What a PaymentProvider can actually do. MVP only ever uses ONE_TIME;
    the rest name real Razorpay products this project does not implement -
    see ARCHITECTURE.md 'Explicitly deferred Razorpay capabilities'."""
    ONE_TIME = "one_time"              # IMPLEMENTED - Orders + Standard Checkout + webhook confirmation
    RECURRING = "recurring"            # NOT IMPLEMENTED - maps to Razorpay Subscriptions
    PAYMENT_LINK = "payment_link"      # NOT IMPLEMENTED - maps to Razorpay Payment Links
    QR = "qr"                          # NOT IMPLEMENTED - maps to Razorpay QR Codes
    INVOICE = "invoice"                # NOT IMPLEMENTED - maps to Razorpay Invoices
    MARKETPLACE = "marketplace"        # NOT IMPLEMENTED - maps to Razorpay Route/Linked Accounts
    AGENTIC = "agentic"                # NOT IMPLEMENTED / NOT CLAIMED - maps to UPI Reserve Pay / Agentic Payments
