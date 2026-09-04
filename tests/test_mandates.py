"""
Commerce Policy Engine tests (domain/commerce/policy.py), moved from the
old top-level mandates.py's check_cart_against_intent to
PolicyEngine.evaluate_cart. Same guarantees as before, generalized field
names (merchant_id/merchant_open instead of restaurant_id/restaurant_open,
"budget"/"merchant_availability"/"attributes"/"mandate_validity"/
"cart_expiry" instead of "price"/"restaurant"/"diet"/"mandate_expiry").
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.domain.commerce.mandates import IntentMandate, CartMandate
from backend.domain.commerce.policy import PolicyEngine


def _base_intent(**overrides):
    defaults = dict(session_id="test-session", max_amount=500, max_delivery_time_min=30,
                     dietary_constraint="high-protein")
    defaults.update(overrides)
    return IntentMandate.create(**defaults)


def test_gate_passes_valid_cart():
    intent = _base_intent()
    cart = CartMandate.create(
        parent_intent=intent,
        items=[{"item_id": "d401", "name": "Grilled Fish Protein Bowl", "price": 469, "quantity": 1}],
        merchant_id="r4", merchant_open=True, estimated_delivery_time_min=20,
    )
    result = PolicyEngine.evaluate_cart(cart, intent, attributes_by_item={"d401": {"dietary_tags": ["non-veg", "high-protein", "low-carb"]}})
    assert result.allowed
    assert result.reasons == []


def test_gate_rejects_over_budget_cart():
    intent = _base_intent(max_amount=300)
    cart = CartMandate.create(
        parent_intent=intent,
        items=[{"item_id": "d401", "name": "Grilled Fish Protein Bowl", "price": 469, "quantity": 1}],
        merchant_id="r4", merchant_open=True, estimated_delivery_time_min=20,
    )
    result = PolicyEngine.evaluate_cart(cart, intent)
    assert not result.allowed
    assert any("exceeds the authorized spend ceiling" in r for r in result.reasons)
    assert result.checks["budget"]["status"] == "FAIL"


def test_gate_rejects_too_slow_cart():
    intent = _base_intent(max_delivery_time_min=15)
    cart = CartMandate.create(
        parent_intent=intent,
        items=[{"item_id": "d401", "name": "Grilled Fish Protein Bowl", "price": 469, "quantity": 1}],
        merchant_id="r4", merchant_open=True, estimated_delivery_time_min=20,
    )
    result = PolicyEngine.evaluate_cart(cart, intent)
    assert not result.allowed
    assert any("exceeds the authorized ceiling" in r for r in result.reasons)


def test_gate_rejects_dietary_violation():
    intent = _base_intent(dietary_constraint="vegan")
    cart = CartMandate.create(
        parent_intent=intent,
        items=[{"item_id": "d401", "name": "Grilled Fish Protein Bowl", "price": 469, "quantity": 1}],
        merchant_id="r4", merchant_open=True, estimated_delivery_time_min=20,
    )
    result = PolicyEngine.evaluate_cart(cart, intent, attributes_by_item={"d401": {"dietary_tags": ["non-veg", "high-protein", "low-carb"]}})
    assert not result.allowed
    assert any("dietary constraint" in r for r in result.reasons)
    assert result.checks["attributes"]["status"] == "FAIL"


def test_gate_rejects_closed_merchant():
    intent = _base_intent()
    cart = CartMandate.create(
        parent_intent=intent,
        items=[{"item_id": "d801", "name": "Vegan Buddha Bowl", "price": 329, "quantity": 1}],
        merchant_id="r8", merchant_open=False, estimated_delivery_time_min=20,
    )
    result = PolicyEngine.evaluate_cart(cart, intent)
    assert not result.allowed
    assert any("closed" in r for r in result.reasons)


def test_gate_does_not_reject_non_dietary_addon():
    """Regression test: a drink/dessert add-on that doesn't itself carry the
    dietary tag (e.g. "high-protein") must NOT block the order - the
    constraint binds the primary dish, not every accompaniment."""
    intent = _base_intent(dietary_constraint="high-protein")
    cart = CartMandate.create(
        parent_intent=intent,
        items=[
            {"item_id": "d503", "name": "Sprouts Sundal", "price": 129, "quantity": 1, "role": "primary"},
            {"item_id": "d504", "name": "Filter Coffee", "price": 69, "quantity": 1, "role": "addon"},
        ],
        merchant_id="r5", merchant_open=True, estimated_delivery_time_min=24,
    )
    result = PolicyEngine.evaluate_cart(cart, intent, attributes_by_item={
        "d503": {"dietary_tags": ["vegan", "high-protein"]},
        "d504": {"dietary_tags": ["veg"]},  # deliberately does NOT satisfy "high-protein"
    })
    assert result.allowed
    assert result.reasons == []


def test_gate_still_rejects_non_conforming_primary():
    intent = _base_intent(dietary_constraint="vegan")
    cart = CartMandate.create(
        parent_intent=intent,
        items=[{"item_id": "d401", "name": "Grilled Fish Protein Bowl", "price": 469, "quantity": 1, "role": "primary"}],
        merchant_id="r4", merchant_open=True, estimated_delivery_time_min=20,
    )
    result = PolicyEngine.evaluate_cart(cart, intent, attributes_by_item={"d401": {"dietary_tags": ["non-veg", "high-protein", "low-carb"]}})
    assert not result.allowed
    assert any("Primary item" in r for r in result.reasons)


def test_gate_rejects_mismatched_intent_reference():
    intent = _base_intent()
    other_intent = _base_intent()
    cart = CartMandate.create(
        parent_intent=other_intent,
        items=[{"item_id": "d401", "name": "Grilled Fish Protein Bowl", "price": 469, "quantity": 1}],
        merchant_id="r4", merchant_open=True, estimated_delivery_time_min=20,
    )
    result = PolicyEngine.evaluate_cart(cart, intent)
    assert not result.allowed
    assert any("does not reference the active Intent Mandate" in r for r in result.reasons)
    assert result.checks["mandate_validity"]["status"] == "FAIL"


def test_gate_rejects_expired_cart():
    intent = _base_intent()
    cart = CartMandate.create(
        parent_intent=intent,
        items=[{"item_id": "d401", "name": "Grilled Fish Protein Bowl", "price": 469, "quantity": 1}],
        merchant_id="r4", merchant_open=True, estimated_delivery_time_min=20,
    )
    cart.expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    result = PolicyEngine.evaluate_cart(cart, intent)
    assert not result.allowed
    assert any("expired" in r for r in result.reasons)
    assert result.checks["cart_expiry"]["status"] == "FAIL"
    assert result.decision == "REJECT"


def test_gate_rejects_item_from_a_different_merchant():
    """Defense in depth: even if a cart somehow ends up with a line item
    that belongs to a different merchant than the cart claims, the gate
    must catch it - a single checkout can only come from one merchant."""
    intent = _base_intent(dietary_constraint=None)
    cart = CartMandate.create(
        parent_intent=intent,
        items=[
            {"item_id": "d401", "name": "Grilled Fish Protein Bowl", "price": 469, "quantity": 1, "role": "primary"},
            {"item_id": "d501", "name": "Masala Dosa", "price": 149, "quantity": 1, "role": "addon"},
        ],
        merchant_id="r4", merchant_open=True, estimated_delivery_time_min=20,
    )
    result = PolicyEngine.evaluate_cart(cart, intent, merchant_id_by_item={"d401": "r4", "d501": "r5"})
    assert not result.allowed
    assert result.checks["merchant_availability"]["same_merchant"] is False
    assert any("another merchant" in r for r in result.reasons)


def test_gate_rejects_unavailable_inventory():
    intent = _base_intent(dietary_constraint=None)
    cart = CartMandate.create(
        parent_intent=intent,
        items=[{"item_id": "d401", "name": "Grilled Fish Protein Bowl", "price": 469, "quantity": 1, "role": "primary"}],
        merchant_id="r4", merchant_open=True, estimated_delivery_time_min=20,
    )
    result = PolicyEngine.evaluate_cart(cart, intent, availability_by_item={"d401": False})
    assert not result.allowed
    assert result.checks["inventory"]["status"] == "FAIL"
    assert any("no longer available" in r for r in result.reasons)


def test_gate_structured_decision_schema_on_pass():
    intent = _base_intent()
    cart = CartMandate.create(
        parent_intent=intent,
        items=[{"item_id": "d401", "name": "Grilled Fish Protein Bowl", "price": 469, "quantity": 1}],
        merchant_id="r4", merchant_open=True, estimated_delivery_time_min=20,
    )
    result = PolicyEngine.evaluate_cart(cart, intent, attributes_by_item={"d401": {"dietary_tags": ["non-veg", "high-protein", "low-carb"]}})
    assert result.decision == "PASS"
    assert result.failed_checks() == []
    for name in ("budget", "delivery_time", "attributes", "merchant_availability", "mandate_validity", "cart_expiry", "inventory"):
        assert result.checks[name]["status"] == "PASS"
    d = result.to_dict()
    for key in ("allowed", "reason", "checks", "mandate_id", "cart_total", "max_allowed", "timestamp"):
        assert key in d
