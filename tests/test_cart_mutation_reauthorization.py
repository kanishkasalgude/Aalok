"""
Proves a guarantee that already holds by construction (CartService bumps
cart.version on every mutation; OrderService.checkout()/validate() always
re-derive AuthorizationService.check() and PolicyEngine.evaluate_cart()
from the CURRENT cart, never a cached decision) but was previously
undemonstrated by an explicit test: an authorization/policy PASS for one
cart state must not silently remain valid once the cart changes.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.domain.commerce.authorization import AuthorizationMode
from backend.domain.commerce.mandates import IntentMandate
from backend.services.authorization.service import AuthorizationService
from backend.services.cart.service import cart_service
from backend.services.order.service import order_service


def test_validate_rejects_after_cart_mutated_over_budget():
    """order_service.validate() - the read-only revalidate -> authorize ->
    policy pipeline that checkout() itself reuses - must independently
    re-derive its decision from the cart's CURRENT contents every time
    it's called, not from whatever passed a moment earlier."""
    session_id = f"mutate-{uuid.uuid4().hex[:8]}"
    intent = IntentMandate.create(session_id=session_id, max_amount=200, max_delivery_time_min=60, dietary_constraint=None)
    authorization = AuthorizationService.create(intent)
    cart = cart_service.create_cart(session_id, "r5")
    cart_service.add_item(cart.cart_id, "d501", "r5", role="primary")  # Masala Dosa, ₹149

    first = order_service.validate(cart, intent, authorization)
    assert first["allowed"] is True
    assert first["policy_decision"].checks["budget"]["cart_total"] == 149

    cart_service.add_item(cart.cart_id, "d504", "r5", role="addon")  # + Filter Coffee, ₹69 -> ₹218

    second = order_service.validate(cart, intent, authorization)
    assert second["allowed"] is False
    assert second["policy_decision"].checks["budget"]["status"] == "FAIL"
    assert second["policy_decision"].checks["budget"]["cart_total"] == 218, (
        "re-evaluation must reflect the CURRENT (mutated) cart total, not the earlier ₹149 snapshot"
    )


def test_checkout_does_not_grandfather_a_mutated_cart_past_its_earlier_pass():
    """End-to-end version of the same guarantee, through the real
    money-moving path. Uses AuthorizationMode.USER_MANDATE (not consumed
    on capture, unlike the ONE_TIME_CHECKOUT default) so the SAME
    authorization survives both calls - isolating the thing under test to
    cart mutation, not authorization consumption."""
    session_id = f"mutate-e2e-{uuid.uuid4().hex[:8]}"
    intent = IntentMandate.create(session_id=session_id, max_amount=200, max_delivery_time_min=60, dietary_constraint=None)
    authorization = AuthorizationService.create(intent, mode=AuthorizationMode.USER_MANDATE)
    cart = cart_service.create_cart(session_id, "r5")
    cart_service.add_item(cart.cart_id, "d501", "r5", role="primary")  # ₹149

    first = order_service.checkout(cart, intent, authorization, buyer="test")
    assert first["status"] == "success"
    assert first["razorpay_called"] is True

    cart_service.add_item(cart.cart_id, "d504", "r5", role="addon")  # -> ₹218, over the ₹200 ceiling

    second = order_service.checkout(cart, intent, authorization, buyer="test")
    assert second["status"] == "rejected_by_policy", (
        "a cart mutated past its budget after an earlier successful checkout must not be "
        "treated as pre-approved"
    )
    assert second["razorpay_called"] is False
    assert second["decision"]["checks"]["budget"]["cart_total"] == 218
