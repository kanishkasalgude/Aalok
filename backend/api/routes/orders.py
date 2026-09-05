"""
Order/checkout routes. POST /api/order/confirm, POST /api/external/purchase
and POST /api/demo/policy-rejection are the pre-refactor routes, preserved
byte-for-byte in behavior (all three still funnel into the exact same
OrderService.checkout() call - see services/order/service.py's docstring on
why that convergence matters). POST /api/checkout/validate, POST
/api/orders and GET /api/orders/{id} are the new generalized, merchant/
category-agnostic surface (spec section 24).

Every session-scoped route here requires a verified session (Track 01
Phase 2 - services/session/auth.py) and checks resource ownership by
internal_order_id where relevant. /api/external/purchase and
/api/demo/policy-rejection are deliberately exempt - see their own
docstrings for why that's safe.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...domain.audit import events
from ...domain.commerce.authorization import AuthorizationMode, AuthorizationStatus
from ...domain.commerce.mandates import IntentMandate
from ...repositories import audit_repo
from ...services.authorization.service import AuthorizationService
from ...services.cart.service import cart_service
from ...services.catalog import gateway
from ...services.order.service import order_service
from ...services.recommendation import service as recommendation_service
from ...services.session.store import session_store
from ...services.session.auth import VerifiedSession, check_body_session_id, check_ownership, issue_token, mint_session, require_session
from ...integrations.merchants.registry import get_adapter

router = APIRouter()


class ConfirmRequest(BaseModel):
    session_id: Optional[str] = None
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
    session_id: Optional[str] = None
    cart_id: str
    force_fail: bool = False


# --- legacy, preserved behavior -----------------------------------------------

@router.post("/api/order/confirm")
def confirm_order(req: ConfirmRequest, verified: VerifiedSession = Depends(require_session)):
    """Aalok's own conversational agent's confirm step - see
    api/routes/chat.py for how session.recommendations gets populated."""
    check_body_session_id(req.session_id, verified)
    session = session_store.get(verified.session_id)
    if not session or session.intent_mandate is None:
        return {"error": "Unknown or expired session. Send a new /api/chat message first.", **verified.as_response_fields()}

    agent_result = session.recommendations or {}
    primary = agent_result.get("primary")
    if primary is None:
        return {"error": "No recommendation to confirm for this session.", **verified.as_response_fields()}
    offered_upsell = agent_result.get("upsell")
    upsell = offered_upsell if (req.accept_upsell and offered_upsell) else None
    if offered_upsell:
        audit_repo.log_event(verified.session_id, events.UPSELL_ACCEPTED if upsell else events.UPSELL_DECLINED,
                              "success", {"upsell_product_id": offered_upsell["product_id"]})

    cart = cart_service.create_cart(verified.session_id, primary["merchant_id"])
    cart_service.add_item(cart.cart_id, primary["product_id"], primary["merchant_id"], role="primary")
    if upsell:
        cart_service.add_item(cart.cart_id, upsell["product_id"], upsell["merchant_id"], role="addon")

    result = order_service.checkout(cart, session.intent_mandate, session.authorization,
                                     force_fail=req.force_fail, buyer="aalok_agent")
    return {**result, **verified.as_response_fields()}


@router.post("/api/external/purchase")
def external_purchase(req: ExternalPurchaseRequest):
    """Public endpoint for a THIRD-PARTY AI buyer (see examples/ai_buyer.py):
    discover (GET /api/catalog/feed) -> understand -> select, then transact
    here. Deliberately NOT a special or more-trusted path: it calls the
    exact same OrderService.checkout() /api/order/confirm uses - the same
    Authorization + Policy checks, the same price/availability re-fetch,
    the same audit trail. There is no bypass.

    Deliberately NOT behind Depends(require_session): every call mints its
    own brand-new, isolated `external-*` session_id and never reads back
    ANY other session's cart/order/mandate - there is nothing here for a
    client-supplied session_id to impersonate. A `session_token` for that
    ephemeral session is still returned, so a real external agent that
    wants to poll its own order afterward (GET /api/orders/{id}, which IS
    ownership-checked) can prove it was the one who made this call."""
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

    remaining_budget = req.max_amount - primary.price
    grounded = recommendation_service.select_grounded_upsell(primary, remaining_budget)
    upsell_id = None
    if grounded:
        audit_repo.log_event(session_id, events.UPSELL_OFFERED, "success", {
            "primary_product_id": primary.product_id, "upsell_product_id": grounded.product_id,
        })
        if req.accept_upsell:
            cart_service.add_item(cart.cart_id, grounded.product_id, grounded.merchant_id, role="addon")
            upsell_id = grounded.product_id
            audit_repo.log_event(session_id, events.UPSELL_ACCEPTED, "success", {"upsell_product_id": grounded.product_id})
        else:
            audit_repo.log_event(session_id, events.UPSELL_DECLINED, "success", {"upsell_product_id": grounded.product_id})

    audit_repo.log_event(session_id, events.RECOMMENDATION_GENERATED, "success", {
        "buyer": "external_ai_buyer", "primary_product_id": req.item_id, "upsell_product_id": upsell_id,
        "note": "Selected directly by the external caller from the catalog feed, not Aalok's own agent.",
    })

    result = order_service.checkout(cart, mandate, authorization, force_fail=req.force_fail, buyer="external_ai_buyer")
    token, expires_at = issue_token(session_id)
    # Deliberately NOT "session_id"/"session_token": every other route uses
    # those exact keys as a signal to the frontend "this is YOUR refreshed
    # identity, adopt it" (see frontend/js/api.js). This mints a totally
    # unrelated, throwaway external-* identity - a browser tab driving the
    # Demo Control Panel's "External AI Buyer" button must never adopt it
    # as its own session, or it would silently lose its real identity.
    return {**result, "external_session_id": session_id, "external_session_token": token}


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


@router.post("/api/demo/successful-purchase")
def demo_successful_purchase():
    """DEMO - the golden path in one call, for the Demo Control Panel
    (Track 01 Phase 12). Same real pipeline as every other checkout here:
    revalidate -> AuthorizationService -> PolicyEngine -> OrderService ->
    PaymentService. Running Shoes (f5, ₹2,499) against a ₹3,000 ceiling -
    the exact numbers used throughout this README's reference demo."""
    session_id = f"demo-success-{uuid.uuid4().hex[:8]}"
    mandate = IntentMandate.create(session_id=session_id, max_amount=3000, max_delivery_time_min=None,
                                    dietary_constraint=None)
    audit_repo.log_event(session_id, events.INTENT_CAPTURED, "success", {
        "buyer": "successful_purchase_demo", "intent_mandate": mandate.to_dict(),
    })
    authorization = AuthorizationService.create(mandate, mode=AuthorizationMode.ONE_TIME_CHECKOUT)

    cart = cart_service.create_cart(session_id, "fashion-threadloom")
    cart_service.add_item(cart.cart_id, "f5", "fashion-threadloom", role="primary")
    audit_repo.log_event(session_id, events.RECOMMENDATION_GENERATED, "success", {
        "buyer": "successful_purchase_demo", "primary_product_id": "f5",
    })

    result = order_service.checkout(cart, mandate, authorization, buyer="successful_purchase_demo")
    token, _ = issue_token(session_id)
    # Not "session_id"/"session_token" - see external_purchase's comment
    # above on why a throwaway demo identity must never be adopted by the
    # browser tab that clicked the Demo Control Panel button.
    return {**result, "demo_session_id": session_id, "demo_session_token": token}


@router.post("/api/demo/cart-tampering")
def demo_cart_tampering():
    """DEMO - proves cart integrity, for the Demo Control Panel (Track 01
    Phase 12). Simulates a client that presented a forged, lower price
    (₹499) for an item that actually costs ₹2,499 (Running Shoes, f5) and
    was only ever authorized up to ₹600 on that false premise. The SAME
    CartService.revalidate() every real checkout goes through re-fetches
    the authoritative catalog price BEFORE the Policy Engine ever sees the
    cart - so the tampered price is never trusted, the true ₹2,499 total is
    what gets checked against the ₹600 ceiling, and the purchase is
    rejected with zero Razorpay calls. No special-cased logic: this is the
    exact same order_service.checkout() every other route uses."""
    session_id = f"demo-tamper-{uuid.uuid4().hex[:8]}"
    claimed_price = 499
    authorized_ceiling = 600
    mandate = IntentMandate.create(session_id=session_id, max_amount=authorized_ceiling,
                                    max_delivery_time_min=None, dietary_constraint=None)
    audit_repo.log_event(session_id, events.INTENT_CAPTURED, "success", {
        "buyer": "cart_tampering_demo", "intent_mandate": mandate.to_dict(),
        "note": f"Authorized up to ₹{authorized_ceiling} on the basis of a claimed ₹{claimed_price} price.",
    })
    authorization = AuthorizationService.create(mandate, mode=AuthorizationMode.ONE_TIME_CHECKOUT)

    cart = cart_service.create_cart(session_id, "fashion-threadloom")
    cart_service.add_item(cart.cart_id, "f5", "fashion-threadloom", role="primary")
    actual_catalog_price = cart.items[0].unit_price

    # The tamper: force the in-memory cart item to a lower price, as if an
    # attacker intercepted/forged the request between proposal and checkout.
    cart.items[0].unit_price = claimed_price
    cart.recalculate_totals()
    audit_repo.log_event(session_id, events.CART_MODIFIED, "success", {
        "buyer": "cart_tampering_demo",
        "note": f"Cart tampered to show ₹{claimed_price} (true catalog price is ₹{actual_catalog_price}).",
    })

    result = order_service.checkout(cart, mandate, authorization, buyer="cart_tampering_demo")
    token, _ = issue_token(session_id)
    return {
        **result, "demo_session_id": session_id, "demo_session_token": token,
        "tamper_demo": {"claimed_price": claimed_price, "authorized_ceiling": authorized_ceiling,
                         "actual_catalog_price": actual_catalog_price},
    }


@router.post("/api/demo/expired-authorization")
def demo_expired_authorization():
    """DEMO - proves expiry is enforced, for the Demo Control Panel (Track
    01 Phase 12 / security-invariant #8). A perfectly well-formed,
    well-within-budget cart is still rejected if its Authorization has
    aged out - AuthorizationService.check() runs BEFORE the Policy Engine
    ever sees the cart, so an expired authorization blocks the purchase
    regardless of how safe the cart itself is. No special-cased logic:
    the exact same order_service.checkout() every other route uses."""
    session_id = f"demo-expired-{uuid.uuid4().hex[:8]}"
    mandate = IntentMandate.create(session_id=session_id, max_amount=3000, max_delivery_time_min=None,
                                    dietary_constraint=None)
    audit_repo.log_event(session_id, events.INTENT_CAPTURED, "success", {
        "buyer": "expired_authorization_demo", "intent_mandate": mandate.to_dict(),
    })
    authorization = AuthorizationService.create(mandate, mode=AuthorizationMode.ONE_TIME_CHECKOUT)
    # Simulate time passing: this authorization was granted 30+ minutes ago
    # and was never used before its window closed.
    authorization.expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    cart = cart_service.create_cart(session_id, "fashion-threadloom")
    cart_service.add_item(cart.cart_id, "f5", "fashion-threadloom", role="primary")
    audit_repo.log_event(session_id, events.RECOMMENDATION_GENERATED, "success", {
        "buyer": "expired_authorization_demo", "primary_product_id": "f5",
        "note": "A well-within-budget cart (₹2,499 of ₹3,000) - the ONLY thing wrong here is that the "
                "authorization window has already closed.",
    })

    result = order_service.checkout(cart, mandate, authorization, buyer="expired_authorization_demo")
    token, _ = issue_token(session_id)
    return {**result, "demo_session_id": session_id, "demo_session_token": token}


@router.post("/api/demo/unauthorized-session")
def demo_unauthorized_session():
    """DEMO - proves session ownership is enforced, for the Demo Control
    Panel (security-invariant #5). Session A creates a real cart; session
    B (a completely different, independently-minted identity) then tries
    to read it. This exercises the exact same Depends(require_session) +
    check_ownership() path every cart route runs - see
    services/session/auth.py and tests/test_session_auth.py."""
    victim_id, victim_token, _ = mint_session()
    attacker_id, attacker_token, _ = mint_session()

    victim_cart = cart_service.create_cart(victim_id, "fashion-threadloom")
    cart_service.add_item(victim_cart.cart_id, "f5", "fashion-threadloom", role="primary")

    blocked = False
    reason = None
    try:
        check_ownership(victim_cart.session_id, VerifiedSession(attacker_id, attacker_token, 0, is_new=False), what="cart")
    except Exception as e:
        blocked = True
        reason = getattr(e, "detail", str(e))

    return {
        "attack": f"Session '{attacker_id}' attempted to read session '{victim_id}''s cart ({victim_cart.cart_id}).",
        "decision": "BLOCKED" if blocked else "ALLOWED",
        "reason": reason or "No ownership check triggered - this would be a real vulnerability.",
        "razorpay_called": False,
        "money_moved": False,
        "victim_session_id": victim_id, "attacker_session_id": attacker_id, "cart_id": victim_cart.cart_id,
    }


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
def checkout_validate(req: CheckoutRequest, verified: VerifiedSession = Depends(require_session)):
    check_body_session_id(req.session_id, verified)
    cart = cart_service.get_cart(req.cart_id)
    if cart is not None:
        check_ownership(cart.session_id, verified, what="cart")
    session = session_store.get(verified.session_id)
    if cart is None or session is None or session.intent_mandate is None:
        return {"error": "Unknown cart or session.", **verified.as_response_fields()}
    validation = order_service.validate(cart, session.intent_mandate, session.authorization)
    return {
        "status": validation["status"], "allowed": validation["allowed"],
        "authorization_decision": validation["authorization_decision"].to_dict(),
        "decision": validation["policy_decision"].to_dict() if validation["policy_decision"] else None,
        "cart_mandate": validation["cart_mandate"].to_dict(),
        **verified.as_response_fields(),
    }


@router.post("/api/orders")
def create_order(req: CheckoutRequest, verified: VerifiedSession = Depends(require_session)):
    check_body_session_id(req.session_id, verified)
    cart = cart_service.get_cart(req.cart_id)
    if cart is not None:
        check_ownership(cart.session_id, verified, what="cart")
    session = session_store.get(verified.session_id)
    if cart is None or session is None or session.intent_mandate is None:
        return {"error": "Unknown cart or session.", **verified.as_response_fields()}
    result = order_service.checkout(cart, session.intent_mandate, session.authorization,
                                     force_fail=req.force_fail, buyer="api_client")
    return {**result, **verified.as_response_fields()}


@router.get("/api/orders/{internal_order_id}")
def get_order(internal_order_id: str, verified: VerifiedSession = Depends(require_session)):
    order = order_service.get_order(internal_order_id)
    if order is None:
        return {"error": f"Unknown internal_order_id '{internal_order_id}'.", **verified.as_response_fields()}
    check_ownership(order.session_id, verified, what="order")
    return {**order.to_dict(), **verified.as_response_fields()}
