"""
The core architectural proof (spec section 28):

    LLM-generated cart -> malicious/invalid amount -> Commerce Policy
    Engine -> REJECT -> Razorpay create_order NOT CALLED

Also: an attempt to invoke a financial mutation directly (bypassing
Authorization/Policy) is structurally impossible from the AI tool layer -
the LLM never gets a path to Razorpay/PaymentService.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.domain.commerce.mandates import IntentMandate
from backend.services.agent import tools
from backend.services.authorization.service import AuthorizationService
from backend.services.cart.service import cart_service
from backend.services.order.service import order_service
from backend.services.payment.service import PaymentService


def test_malicious_cart_amount_is_rejected_before_any_razorpay_call(monkeypatch):
    """A cart claiming a price the catalog never authorized (simulating a
    compromised/hallucinating LLM, or a malicious client tampering with a
    cached price) must be caught by revalidation + the Policy Engine -
    never by trusting the client-supplied amount."""
    calls = {"count": 0}
    original = PaymentService.create_razorpay_order

    def counting(self, *args, **kwargs):
        calls["count"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PaymentService, "create_razorpay_order", counting)

    session_id = f"attack-{uuid.uuid4().hex[:8]}"
    # The "attacker" states an intent budget of just ₹1 - far below any real item -
    # and still tries to add a real ₹149 item and check out. Even though CartService
    # always re-fetches the AUTHORITATIVE price server-side (an attacker cannot
    # inject an arbitrary client-supplied amount into unit_price at all, since
    # add_item only ever takes a product_id, never a price), the budget mismatch
    # alone must be enough for the Policy Engine to reject this cart.
    intent = IntentMandate.create(session_id=session_id, max_amount=1.0, max_delivery_time_min=60, dietary_constraint=None)
    authorization = AuthorizationService.create(intent)
    cart = cart_service.create_cart(session_id, "r5")
    cart_service.add_item(cart.cart_id, "d501", "r5", role="primary")  # real price: ₹149

    result = order_service.checkout(cart, intent, authorization, buyer="attacker")

    assert result["status"] == "rejected_by_policy"
    assert result["decision"]["decision"] == "REJECT"
    assert result["razorpay_called"] is False
    assert calls["count"] == 0, "a rejected cart must NEVER reach Razorpay's Orders API"


def test_a_tampered_cart_item_price_is_never_trusted():
    """Even if something upstream (a buggy client, a compromised session)
    manages to write a fabricated unit_price directly onto a CartItem,
    CartService.revalidate() overwrites it with the authoritative catalog
    price before the Policy Engine ever sees the cart."""
    cart = cart_service.create_cart(f"tamper-{uuid.uuid4().hex[:8]}", "r5")
    cart_service.add_item(cart.cart_id, "d501", "r5", role="primary")
    cart.items[0].unit_price = 0.01  # simulate a tampered/hallucinated price
    cart_service.revalidate(cart)
    assert cart.items[0].unit_price == 149, "revalidation must overwrite a tampered price with the real one"


def test_llm_tool_layer_has_no_path_to_financial_mutation():
    """The AI tool layer (services/agent/tools.py) is the ONLY surface the
    LLM ever calls. It structurally cannot create a Razorpay order, capture
    a payment, issue a refund, or override a policy decision - those
    functions simply do not exist in its namespace or its tool
    declarations (see test_ai_tool_boundary.py for the full structural
    check)."""
    for forbidden in tools.FORBIDDEN_TOOL_NAMES:
        assert forbidden not in tools.NAME_TO_FUNC
        assert not hasattr(tools, forbidden)
