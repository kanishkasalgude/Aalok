"""
Order/checkout routes. POST /api/order/confirm, POST /api/external/purchase
and POST /api/demo/policy-rejection are the pre-refactor routes, preserved
byte-for-byte in behavior (all three still funnel into the exact same
OrderService.checkout() call - see services/order/service.py's docstring on
why that convergence matters). POST /api/checkout/validate, POST
/api/orders and GET /api/orders/{id} are the new generalized, merchant/
category-agnostic surface (spec section 24).
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ...domain.audit import events
from ...domain.commerce.authorization import AuthorizationMode
from ...domain.commerce.mandates import IntentMandate
from ...repositories import audit_repo
from ...services.authorization.service import AuthorizationService
from ...services.cart.service import cart_service
from ...services.catalog import gateway
from ...services.order.service import order_service
from ...services.recommendation import service as recommendation_service
from ...services.session.store import session_store
from ...integrations.merchants.registry import get_adapter

router = APIRouter()


class ConfirmRequest(BaseModel):
    session_id: str
    accept_upsell: bool = False
    force_fail: bool = False  # lets the demo deliberately trigger the handled-failure path


class ExternalPurchaseRequest(BaseModel):
    item_id: str
    max_amount: float
    max_delivery_time_min: Optional[int] = None
    dietary_constraint: Optional[str] = None
    accept_upsell: bool = False
    force_fail: bool = False


class CheckoutRequest(BaseModel):
    session_id: str
    cart_id: str
    force_fail: bool = False


# --- legacy, preserved behavior -----------------------------------------------

@router.post("/api/order/confirm")
def confirm_order(req: ConfirmRequest):
    """Aalok's own conversational agent's confirm step - see
    api/routes/chat.py for how session.recommendations gets populated."""
    session = session_store.get(req.session_id)
    if not session or session.intent_mandate is None:
        return {"error": "Unknown or expired session. Send a new /api/chat message first."}

    agent_result = session.recommendations or {}
    primary = agent_result.get("primary")
    if primary is None:
        return {"error": "No recommendation to confirm for this session."}
    upsell = agent_result.get("upsell") if (req.accept_upsell and agent_result.get("upsell")) else None

    cart = cart_service.create_cart(req.session_id, primary["merchant_id"])
    cart_service.add_item(cart.cart_id, primary["product_id"], primary["merchant_id"], role="primary")
    if upsell:
        cart_service.add_item(cart.cart_id, upsell["product_id"], upsell["merchant_id"], role="addon")

    return order_service.checkout(cart, session.intent_mandate, session.authorization,
                                   force_fail=req.force_fail, buyer="aalok_agent")


@router.post("/api/external/purchase")
def external_purchase(req: ExternalPurchaseRequest):
    """Public endpoint for a THIRD-PARTY AI buyer (see examples/ai_buyer.py):
    discover (GET /api/catalog/feed) -> understand -> select, then transact
    here. Deliberately NOT a special or more-trusted path: it calls the
    exact same OrderService.checkout() /api/order/confirm uses - the same
    Authorization + Policy checks, the same price/availability re-fetch,
    the same audit trail. There is no bypass."""
    session_id = f"external-{uuid.uuid4().hex[:10]}"
    primary = gateway.get_product(req.item_id)
    if primary is None:
        return {"error": f"Unknown item_id '{req.item_id}'. Fetch /api/catalog/feed to discover valid ids."}

    mandate = IntentMandate.create(session_id=session_id, max_amount=req.max_amount,
                                    max_delivery_time_min=req.max_delivery_time_min,
                                    dietary_constraint=req.dietary_constraint)
    audit_repo.log_event(session_id, events.INTENT_CAPTURED, "success", {
        "buyer": "external_ai_buyer", "stated_constraints": req.model_dump(), "intent_mandate": mandate.to_dict(),
    })
    authorization = AuthorizationService.create(mandate, mode=AuthorizationMode.ONE_TIME_CHECKOUT)

    cart = cart_service.create_cart(session_id, primary.merchant_id)
    cart_service.add_item(cart.cart_id, primary.product_id, primary.merchant_id, role="primary")

    upsell_id = None
    if req.accept_upsell:
        remaining_budget = req.max_amount - primary.price
        grounded = recommendation_service.select_grounded_upsell(primary, remaining_budget)
        if grounded:
            cart_service.add_item(cart.cart_id, grounded.product_id, grounded.merchant_id, role="addon")
            upsell_id = grounded.product_id

    audit_repo.log_event(session_id, events.RECOMMENDATION_GENERATED, "success", {
        "buyer": "external_ai_buyer", "primary_product_id": req.item_id, "upsell_product_id": upsell_id,
        "note": "Selected directly by the external caller from the catalog feed, not Aalok's own agent.",
    })

    return order_service.checkout(cart, mandate, authorization, force_fail=req.force_fail, buyer="external_ai_buyer")


@router.post("/api/demo/policy-rejection")
def demo_policy_rejection():
    """DEMO A - AI safety / policy rejection. Proves the Commerce Policy
    Engine rejects an invalid cart BEFORE any Razorpay Order is created -
    razorpay_called is always False here. Deliberately hardcodes Masala
    Dosa + Filter Coffee (d501 + d504 = ₹218) against a tight ₹180 ceiling -
    the cart still goes through the exact same OrderService.checkout() path
    as everything else; the REJECT is the real gate, not a canned response."""
    session_id = f"demo-reject-{uuid.uuid4().hex[:8]}"
    mandate = IntentMandate.create(session_id=session_id, max_amount=180, max_delivery_time_min=60,
                                    dietary_constraint=None)
    audit_repo.log_event(session_id, events.INTENT_CAPTURED, "success", {
        "buyer": "policy_rejection_demo", "intent_mandate": mandate.to_dict(),
        "note": "Deliberately tight ₹180 ceiling, to demonstrate the Commerce Policy Engine rejecting an "
                "over-budget cart before any Razorpay call is made.",
    })
    authorization = AuthorizationService.create(mandate, mode=AuthorizationMode.ONE_TIME_CHECKOUT)

    cart = cart_service.create_cart(session_id, "r5")
    cart_service.add_item(cart.cart_id, "d501", "r5", role="primary")
    cart_service.add_item(cart.cart_id, "d504", "r5", role="addon")
    audit_repo.log_event(session_id, events.RECOMMENDATION_GENERATED, "success", {
        "buyer": "policy_rejection_demo", "primary_product_id": "d501", "upsell_product_id": "d504",
        "note": "Masala Dosa (₹149) + Filter Coffee (₹69) = ₹218, deliberately proposed above the ₹180 "
                "ceiling to trigger a policy-engine REJECT.",
    })

    return order_service.checkout(cart, mandate, authorization, buyer="policy_rejection_demo")


# --- new, generalized surface --------------------------------------------------

@router.get("/api/orders")
def list_orders(limit: int = 100):
    """Newest-first order list for the Orders/Payments dashboard pages -
    see services/order/service.py::OrderService.list_orders. `category` is
    resolved per row from the merchant registry (not stored on InternalOrder
    itself)."""
    out = []
    for order in order_service.list_orders(limit=limit):
        adapter = get_adapter(order.merchant_id)
        d = order.to_dict()
        d["category"] = adapter.merchant.category if adapter else None
        d["merchant_name"] = adapter.merchant.name if adapter else order.merchant_id
        out.append(d)
    return {"orders": out}


@router.post("/api/checkout/validate")
def checkout_validate(req: CheckoutRequest):
    cart = cart_service.get_cart(req.cart_id)
    session = session_store.get(req.session_id)
    if cart is None or session is None or session.intent_mandate is None:
        return {"error": "Unknown cart or session."}
    validation = order_service.validate(cart, session.intent_mandate, session.authorization)
    return {
        "status": validation["status"], "allowed": validation["allowed"],
        "authorization_decision": validation["authorization_decision"].to_dict(),
        "decision": validation["policy_decision"].to_dict() if validation["policy_decision"] else None,
        "cart_mandate": validation["cart_mandate"].to_dict(),
    }


@router.post("/api/orders")
def create_order(req: CheckoutRequest):
    cart = cart_service.get_cart(req.cart_id)
    session = session_store.get(req.session_id)
    if cart is None or session is None or session.intent_mandate is None:
        return {"error": "Unknown cart or session."}
    return order_service.checkout(cart, session.intent_mandate, session.authorization,
                                   force_fail=req.force_fail, buyer="api_client")


@router.get("/api/orders/{internal_order_id}")
def get_order(internal_order_id: str):
    order = order_service.get_order(internal_order_id)
    if order is None:
        return {"error": f"Unknown internal_order_id '{internal_order_id}'."}
    return order.to_dict()
