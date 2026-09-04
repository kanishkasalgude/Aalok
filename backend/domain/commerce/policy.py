"""
THE COMMERCE POLICY ENGINE. Deterministic, non-LLM. Generalized from the
original mandates.py::check_cart_against_intent (food/restaurant-only) to
work over any merchant/category, with the exact same guarantee: this is the
ONLY function allowed to decide whether a proposed cart may proceed toward
a Razorpay Order, and it runs identically regardless of whether the cart
came from Aalok's own conversational agent or an external AI buyer
(both funnel through services/order/service.py::OrderService.checkout,
the single shared code path).

This runs AFTER AuthorizationService.check() (domain/commerce/authorization.py)
in the checkout pipeline - Authorization asks "is this mandate/session
allowed to transact at all", Policy asks "is THIS cart valid". Neither can
be skipped; neither is an LLM call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .mandates import CartMandate, IntentMandate


@dataclass
class PolicyDecision:
    """Matches the spec's required response shape
    {allowed, reason, checks, mandate_id, cart_total, max_allowed, timestamp}
    plus extra detail (`decision`, `reasons`, `failed_checks()`) the audit
    trail and UI use for a full per-check breakdown, not just a pass/fail bit."""
    allowed: bool
    reason: str
    checks: dict = field(default_factory=dict)
    mandate_id: str = ""
    cart_total: float = 0.0
    max_allowed: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reasons: list = field(default_factory=list)
    decision: str = "PASS"

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "checks": self.checks,
            "mandate_id": self.mandate_id,
            "cart_total": self.cart_total,
            "max_allowed": self.max_allowed,
            "timestamp": self.timestamp,
            "decision": self.decision,
            "reasons": self.reasons,
            # legacy alias kept for the pre-refactor UI/tests that read `.passed`
            "passed": self.allowed,
        }

    def failed_checks(self) -> list:
        return [name for name, c in self.checks.items() if c.get("status") == "FAIL"]


class PolicyEngine:
    """Stateless - a thin namespace around evaluate_cart() so services call
    `PolicyEngine.evaluate_cart(...)` (matches the spec's requested shape)
    without needing to instantiate anything."""

    @staticmethod
    def evaluate_cart(cart: CartMandate, intent: IntentMandate, *,
                       attributes_by_item: Optional[dict] = None,
                       merchant_id_by_item: Optional[dict] = None,
                       availability_by_item: Optional[dict] = None) -> PolicyDecision:
        """
        attributes_by_item: {item_id: {attribute_name: value_or_list}} - the
          revalidated, authoritative Product.attributes for each cart item.
        merchant_id_by_item: {item_id: merchant_id} - defense in depth: every
          line item must actually belong to the cart's declared merchant.
        availability_by_item: {item_id: bool} - the revalidated, authoritative
          availability for each item (default True if not supplied).
        """
        checks: dict = {}
        reasons: list = []

        # --- mandate validity ------------------------------------------------
        mandate_ok = True
        if cart.parent_intent_id != intent.mandate_id:
            mandate_ok = False
            reasons.append("Cart does not reference the active Intent Mandate for this session.")
        if intent.status != "active":
            mandate_ok = False
            reasons.append(f"Intent Mandate status is '{intent.status}', not 'active'.")
        checks["mandate_validity"] = {"status": "PASS" if mandate_ok else "FAIL", "mandate_id": intent.mandate_id}

        # --- cart expiry -------------------------------------------------------
        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(cart.expires_at)
        expired = now > expires
        if expired:
            reasons.append("Cart Mandate has expired; the price/availability snapshot is stale.")
        checks["cart_expiry"] = {"status": "FAIL" if expired else "PASS", "expires_at": cart.expires_at, "expired": expired}

        # --- budget --------------------------------------------------------------
        budget_ok = cart.total_amount <= intent.max_amount + 1e-6
        checks["budget"] = {"status": "PASS" if budget_ok else "FAIL", "cart_total": cart.total_amount, "maximum": intent.max_amount}
        if not budget_ok:
            over_by = round(cart.total_amount - intent.max_amount, 2)
            reasons.append(
                f"Cart total {cart.total_amount} exceeds the authorized spend ceiling {intent.max_amount} "
                f"(over by {over_by})."
            )

        # --- delivery time -----------------------------------------------------------
        if intent.max_delivery_time_min is not None:
            time_ok = cart.estimated_delivery_time_min <= intent.max_delivery_time_min
            checks["delivery_time"] = {"status": "PASS" if time_ok else "FAIL",
                                        "estimated_minutes": cart.estimated_delivery_time_min,
                                        "maximum_minutes": intent.max_delivery_time_min}
            if not time_ok:
                reasons.append(
                    f"Estimated delivery time {cart.estimated_delivery_time_min} min exceeds the "
                    f"authorized ceiling of {intent.max_delivery_time_min} min."
                )
        else:
            checks["delivery_time"] = {"status": "PASS", "estimated_minutes": cart.estimated_delivery_time_min, "maximum_minutes": None}

        # --- merchant availability: open + every item actually belongs to this merchant ---
        merchant_ok = cart.merchant_open
        mismatched = []
        if merchant_id_by_item:
            for item in cart.items:
                item_merchant = merchant_id_by_item.get(item["item_id"])
                if item_merchant is not None and item_merchant != cart.merchant_id:
                    mismatched.append(item["name"])
        same_merchant = len(mismatched) == 0
        if not same_merchant:
            merchant_ok = False
        checks["merchant_availability"] = {"status": "PASS" if merchant_ok else "FAIL",
                                            "same_merchant": same_merchant, "open": cart.merchant_open}
        if not cart.merchant_open:
            reasons.append("Merchant is currently closed/unavailable; cannot fulfil this order.")
        if mismatched:
            reasons.append(
                f"Cart mixes items from another merchant ({', '.join(mismatched)}); "
                f"a single checkout can only come from one merchant (see MVP multi-merchant policy)."
            )

        # --- inventory: every item still available at revalidation time -----------------
        unavailable = []
        if availability_by_item:
            for item in cart.items:
                if availability_by_item.get(item["item_id"], True) is False:
                    unavailable.append(item["name"])
        inventory_ok = len(unavailable) == 0
        checks["inventory"] = {"status": "PASS" if inventory_ok else "FAIL", "unavailable_items": unavailable}
        if unavailable:
            reasons.append(f"Item(s) no longer available: {', '.join(unavailable)}.")

        # --- attributes: dietary_constraint (legacy) + required_attributes (general) -----
        attr_ok = True
        if attributes_by_item:
            for item in cart.items:
                role = item.get("role", "primary")
                if role != "primary":
                    continue
                attrs = attributes_by_item.get(item["item_id"], {})
                if intent.dietary_constraint:
                    tags = attrs.get("dietary_tags", [])
                    if intent.dietary_constraint not in tags:
                        attr_ok = False
                        reasons.append(
                            f"Primary item '{item['name']}' does not satisfy the '{intent.dietary_constraint}' "
                            f"dietary constraint the user authorized."
                        )
                for key, expected in (intent.required_attributes or {}).items():
                    actual = attrs.get(key)
                    matches = actual == expected or (isinstance(actual, list) and expected in actual)
                    if not matches:
                        attr_ok = False
                        reasons.append(
                            f"Primary item '{item['name']}' does not satisfy the required attribute "
                            f"'{key}={expected}'."
                        )
        checks["attributes"] = {"status": "PASS" if attr_ok else "FAIL",
                                 "dietary_constraint": intent.dietary_constraint,
                                 "required_attributes": intent.required_attributes}

        allowed = len(reasons) == 0
        decision = "PASS" if allowed else "REJECT"
        reason = "Cart satisfies all purchase constraints." if allowed else reasons[0]

        return PolicyDecision(allowed=allowed, reason=reason, checks=checks, mandate_id=intent.mandate_id,
                               cart_total=cart.total_amount, max_allowed=intent.max_amount,
                               reasons=reasons, decision=decision)


# Backward-compatible function alias - some early tests/spec text call this
# check_cart_against_intent(); keep both names working rather than forcing a
# rename everywhere.
def check_cart_against_intent(cart: CartMandate, intent: IntentMandate, **kwargs) -> PolicyDecision:
    return PolicyEngine.evaluate_cart(cart, intent, **kwargs)
