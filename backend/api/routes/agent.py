"""
POST /api/agent/chat - the generalized, category-general AI commerce chat
endpoint the new frontend uses. Additive only: this does not touch
POST /api/chat (kept exactly as-is, food-scoped, dish-shaped, for backward
compatibility - nothing currently depends on it since the frontend this
route replaces has been redesigned, but there's no reason to break its
contract either).

Unlike /api/chat, this endpoint does NOT force `intent.category = ["food"]`
- category comes entirely from parse_intent() (services/agent/intent.py),
which already spans all 8 categories via the LLM prompt (when an LLM key
is configured) or the heuristic keyword map (offline fallback). Everything
downstream - run_commerce_agent, CartService, AuthorizationService,
PolicyEngine, OrderService - was already category-agnostic; the only
food-specific thing in the whole pipeline was that one line in chat.py.

Checkout after a recommendation here reuses the EXISTING generalized
routes unchanged: POST /api/order/confirm (session-based, mirrors the
legacy flow) or POST /api/cart + POST /api/checkout/validate + POST
/api/orders (explicit cart-based flow) - both already work for any
category since they operate on whatever Product dict
session.recommendations holds, never assuming food.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...domain.audit import events
from ...domain.commerce.mandates import IntentMandate
from ...repositories import audit_repo
from ...services.agent.commerce_agent import DEFAULT_MAX_AMOUNT, DEFAULT_MAX_DELIVERY_MIN, run_commerce_agent
from ...services.agent.intent import parse_intent
from ...services.session.auth import VerifiedSession, check_body_session_id, require_session
from .chat import _log_upsell_offered, _store_recommendation

router = APIRouter()

# DEFAULT_MAX_DELIVERY_MIN (60 min) is a food-delivery guardrail - it makes
# sense as a default ceiling for same-day categories, but silently applying
# it to fashion/electronics/jewellery/entertainment/services (which
# realistically ship in hours-to-days, see each adapter's `delivery.eta_min`)
# would reject every one of those carts at the Policy Engine's delivery_time
# check by default, even though the user never asked for fast delivery. Only
# apply a default ceiling for the categories where "fast" is the normal
# expectation; otherwise leave it unbounded unless the user states one.
_CATEGORY_DEFAULT_DELIVERY_MIN = {"food": DEFAULT_MAX_DELIVERY_MIN, "grocery": 120}


class AgentChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    budget_override: Optional[float] = None
    max_time_override: Optional[int] = None
    category_override: Optional[str] = None


def _reply_text(agent_result: dict, merchant_count: int) -> str:
    primary = agent_result["primary"]
    if primary is None:
        return ("I couldn't find anything matching all of those constraints — "
                "try relaxing the budget, or naming the category more directly.")
    parts = [f"Found {len(agent_result['candidates'])} matching product(s) across {merchant_count} merchant(s). "
             f"Best match: {primary['title']} from {primary['merchant_name']} (₹{primary['price']:g}). "
             f"{agent_result['primary_reasoning']}"]
    upsell = agent_result["upsell"]
    if upsell:
        parts.append(f" You could also add {upsell['title']} (₹{upsell['price']:g}) — {agent_result['upsell_reasoning']}")
    return " ".join(parts)


@router.post("/api/agent/chat")
def agent_chat(req: AgentChatRequest, verified: VerifiedSession = Depends(require_session)):
    check_body_session_id(req.session_id, verified)
    session_id = verified.session_id

    intent = parse_intent(req.message)
    if req.category_override:
        intent.category = [req.category_override]
    if req.budget_override is not None:
        intent.max_price = req.budget_override
    if req.max_time_override is not None:
        intent.delivery_requirement = req.max_time_override

    effective_max_amount = intent.max_price or DEFAULT_MAX_AMOUNT
    detected_category = intent.category[0] if intent.category else None
    if intent.delivery_requirement is not None:
        effective_max_time = intent.delivery_requirement
    else:
        effective_max_time = _CATEGORY_DEFAULT_DELIVERY_MIN.get(detected_category)  # None = unbounded

    mandate = IntentMandate.create(session_id=session_id, max_amount=effective_max_amount,
                                    max_delivery_time_min=effective_max_time,
                                    dietary_constraint=intent.required_attributes.get("dietary_tags"),
                                    required_attributes=intent.required_attributes)
    audit_repo.log_event(session_id, events.INTENT_CAPTURED, "success", {
        "user_message": req.message, "parsed_intent": intent.to_dict(), "intent_mandate": mandate.to_dict(),
    })

    agent_result = run_commerce_agent(req.message, intent, session_id)
    merchant_count = len({c["merchant_id"] for c in agent_result["candidates"]})
    audit_repo.log_event(session_id, events.RECOMMENDATION_GENERATED,
                          "success" if agent_result["primary"] else "failed", {
        "trace": agent_result["trace"], "detected_category": intent.category,
        "primary_product_id": agent_result["primary"]["product_id"] if agent_result["primary"] else None,
        "upsell_product_id": agent_result["upsell"]["product_id"] if agent_result["upsell"] else None,
        "primary_reasoning": agent_result["primary_reasoning"], "upsell_reasoning": agent_result["upsell_reasoning"],
    })
    _log_upsell_offered(session_id, agent_result)

    _store_recommendation(session_id, mandate, agent_result)

    return {
        "session_id": session_id,
        "session_token": verified.token,
        "reply": _reply_text(agent_result, merchant_count),
        "intent": intent.to_dict(),
        "intent_mandate": mandate.to_dict(),
        "detected_category": intent.category,
        "merchant_count": merchant_count,
        "primary": agent_result["primary"],
        "upsell": agent_result["upsell"],
        "candidates": agent_result["candidates"],
    }
