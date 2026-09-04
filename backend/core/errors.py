"""Domain-independent error types used at integration/service boundaries.

Each one maps to a specific "fail gracefully" behavior described in the
architecture doc (section 26 of the task spec): a MerchantAdapterError from
one merchant must never break a federated search across the others; a
PaymentProviderMisconfigured must fail loudly rather than silently degrade
to mock mode; a policy/authorization rejection is a normal decision, not an
exception - only genuinely exceptional conditions raise.
"""
from __future__ import annotations


class MerchantAdapterError(RuntimeError):
    """Raised by a MerchantAdapter when it cannot serve a request (the mock
    equivalent of a merchant's API being temporarily unavailable). Caught by
    the catalog gateway per-adapter so one merchant failing never breaks a
    federated search across the others."""


class ProductUnavailableError(RuntimeError):
    """Raised when a cart/order revalidation step discovers a product is no
    longer available - the caller must not proceed to payment."""


class PaymentProviderMisconfigured(RuntimeError):
    """PAYMENT_PROVIDER=razorpay_test but real credentials are missing.
    Raised at call time (not import time) so a demo that only ever exercises
    mock mode isn't broken by a missing .env - but a demo explicitly asking
    for the real integration gets a loud, immediate error instead of a
    silently-mocked payment."""


class CartMerchantMismatchError(RuntimeError):
    """Raised when a caller tries to add an item from a different merchant
    to an existing cart. Aalok's MVP checkout policy is one merchant per
    cart/order/payment (see ARCHITECTURE.md section 12) - this is the
    enforcement point."""


class AuthorizationError(RuntimeError):
    """Raised for a structurally invalid authorization request (e.g. an
    unsupported AuthorizationMode). A normal expired/revoked/out-of-scope
    authorization is not an error - it's a AuthorizationDecision with
    allowed=False, exactly like a policy rejection is a decision, not an
    exception."""


class RefundError(RuntimeError):
    """Raised for an invalid refund request (no captured payment to refund
    against, amount exceeds what's refundable, or a duplicate refund
    already exists/in-flight for this order)."""
