"""
Named audit event-type constants (spec section 19). Using these instead of
ad hoc string literals scattered across services makes the audit
vocabulary visible in one place and typo-proof. Every commerce operation
that matters produces one of these; chain-of-thought is never logged -
only concise, user-safe reasoning and the ids/amounts/decisions needed to
reconstruct what happened.
"""
from __future__ import annotations

INTENT_CAPTURED = "intent_captured"

AUTHORIZATION_CREATED = "authorization_created"
AUTHORIZATION_CHECKED = "authorization_checked"
AUTHORIZATION_EXPIRED = "authorization_expired"
AUTHORIZATION_REVOKED = "authorization_revoked"
USER_CONFIRMATION_REQUIRED = "user_confirmation_required"
USER_CONFIRMATION_RECEIVED = "user_confirmation_received"

CATALOG_SEARCH = "catalog_search"
RECOMMENDATION_GENERATED = "recommendation_generated"

CART_CREATED = "cart_created"
CART_MODIFIED = "cart_modified"

POLICY_EVALUATED = "policy_evaluated"
POLICY_PASSED = "policy_passed"
POLICY_REJECTED = "policy_rejected"

ORDER_CREATED = "order_created"
ORDER_REUSED = "order_reused"
ORDER_CONFIRMED = "order_confirmed"

PAYMENT_ATTEMPTED = "payment_attempted"
PAYMENT_FAILED = "payment_failed"
PAYMENT_CAPTURED = "payment_captured"
PAYMENT_RETRY = "payment_retry"

WEBHOOK_RECEIVED = "webhook_received"

REFUND_REQUESTED = "refund_requested"
REFUND_COMPLETED = "refund_completed"

ALL_EVENTS = [
    INTENT_CAPTURED, AUTHORIZATION_CREATED, AUTHORIZATION_CHECKED, AUTHORIZATION_EXPIRED,
    AUTHORIZATION_REVOKED, USER_CONFIRMATION_REQUIRED, USER_CONFIRMATION_RECEIVED,
    CATALOG_SEARCH, RECOMMENDATION_GENERATED, CART_CREATED, CART_MODIFIED,
    POLICY_EVALUATED, POLICY_PASSED, POLICY_REJECTED,
    ORDER_CREATED, ORDER_REUSED, ORDER_CONFIRMED,
    PAYMENT_ATTEMPTED, PAYMENT_FAILED, PAYMENT_CAPTURED, PAYMENT_RETRY,
    WEBHOOK_RECEIVED, REFUND_REQUESTED, REFUND_COMPLETED,
]
