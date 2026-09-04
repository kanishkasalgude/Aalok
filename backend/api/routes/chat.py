"""
POST /api/chat and POST /api/order/quick-add - Aalok's own conversational
agent's two entry points (natural-language chat, and clicking a dish
directly while browsing). Both build the SAME session["recommendations"]
shape (primary + grounded upsell), so /api/order/confirm afterwards is
identical regardless of how the item was chosen - one recommendation
pipeline, two entry points, exactly the pre-refactor design.

Response shape (`primary`/`upsell`) is intentionally still the legacy
dish-shaped dict (see _legacy.py) - the UI is out of scope for this
refactor and must not need to change. Internally this now runs through the
fully generalized Product/commerce_agent pipeline, scoped to category="food".
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ...domain.audit import events
from ...domain.commerce.authorization import AuthorizationMode
from ...domain.commerce.intent import Intent
from ...domain.commerce.mandates import IntentMandate
from ...repositories import audit_repo
from ...services.agent.commerce_agent import DEFAULT_MAX_AMOUNT, DEFAULT_MAX_DELIVERY_MIN, run_commerce_agent
from ...services.agent.intent import parse_intent
from ...services.authorization.service import AuthorizationService
from ...services.catalog import gateway
from ...services.recommendation import service as recommendation_service
from ...services.session.store import session_store
from ._legacy import product_to_dish_dict

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    budget_override: Optional[float] = None
    max_time_override: Optional[int] = None
    dietary_override: Optional[str] = None


class QuickAddRequest(BaseModel):
    session_id: Optional[str] = None
    item_id: str
    budget_override: Optional[float] = None


def _store_recommendation(session_id: str, mandate: IntentMandate, agent_result: dict) -> None:
    authorization = AuthorizationService.create(mandate, mode=AuthorizationMode.ONE_TIME_CHECKOUT)
    session = session_store.get_or_create(session_id)
    session.intent_mandate = mandate
    session.authorization = authorization
    session.recommendations = agent_result


@router.post("/api/chat")
def chat(req: ChatRequest):
    session_id = req.session_id or f"sess-{uuid.uuid4().hex[:10]}"

    intent = parse_intent(req.message)
    intent.category = ["food"]  # this legacy entry point is scoped to the food vertical
    if req.budget_override is not None:
        intent.max_price = req.budget_override
    if req.max_time_override is not None:
        intent.delivery_requirement = req.max_time_override
    if req.dietary_override:
        intent.required_attributes["dietary_tags"] = req.dietary_override

    effective_max_amount = intent.max_price or DEFAULT_MAX_AMOUNT
    effective_max_time = intent.delivery_requirement or DEFAULT_MAX_DELIVERY_MIN

    mandate = IntentMandate.create(session_id=session_id, max_amount=effective_max_amount,
                                    max_delivery_time_min=effective_max_time,
                                    dietary_constraint=intent.required_attributes.get("dietary_tags"))
    audit_repo.log_event(session_id, events.INTENT_CAPTURED, "success", {
        "user_message": req.message, "parsed_intent": intent.to_dict(), "intent_mandate": mandate.to_dict(),
        "note": "max_amount/max_delivery_time_min fall back to platform default guardrails "
                "when the user did not state an explicit ceiling.",
    })

    agent_result = run_commerce_agent(req.message, intent, session_id)
    audit_repo.log_event(session_id, events.RECOMMENDATION_GENERATED,
                          "success" if agent_result["primary"] else "failed", {
        "trace": agent_result["trace"],
        "primary_product_id": agent_result["primary"]["product_id"] if agent_result["primary"] else None,
        "upsell_product_id": agent_result["upsell"]["product_id"] if agent_result["upsell"] else None,
        "primary_reasoning": agent_result["primary_reasoning"], "upsell_reasoning": agent_result["upsell_reasoning"],
    })

    _store_recommendation(session_id, mandate, agent_result)

    if agent_result["primary"] is None:
        return {
            "session_id": session_id,
            "reply": "I couldn't find anything matching all of those constraints — want to relax the budget or time limit?",
            "intent_mandate": mandate.to_dict(), "primary": None, "upsell": None, "candidates": [],
        }

    primary = product_to_dish_dict(agent_result["primary"])
    upsell = product_to_dish_dict(agent_result["upsell"])
    reply_parts = [f"I'd recommend the {primary['name']} from {primary['restaurant_name']} "
                   f"(₹{primary['price']}, ~{primary['delivery_time_min']} min). {agent_result['primary_reasoning']}"]
    if upsell:
        reply_parts.append(f" You could add the {upsell['name']} (₹{upsell['price']}) — {agent_result['upsell_reasoning']}")

    return {
        "session_id": session_id, "reply": " ".join(reply_parts), "intent_mandate": mandate.to_dict(),
        "primary": primary, "upsell": upsell,
        "candidates": [product_to_dish_dict(c) for c in agent_result["candidates"]],
    }


@router.post("/api/order/quick-add")
def quick_add(req: QuickAddRequest):
    session_id = req.session_id or f"sess-{uuid.uuid4().hex[:10]}"
    primary = gateway.get_product(req.item_id)
    if primary is None:
        return {"error": f"Unknown item_id '{req.item_id}'."}

    effective_max_amount = req.budget_override or DEFAULT_MAX_AMOUNT
    mandate = IntentMandate.create(session_id=session_id, max_amount=effective_max_amount,
                                    max_delivery_time_min=DEFAULT_MAX_DELIVERY_MIN, dietary_constraint=None)
    audit_repo.log_event(session_id, events.INTENT_CAPTURED, "success", {
        "buyer": "direct_browse", "intent_mandate": mandate.to_dict(),
        "note": "Added directly from restaurant browsing, not the AI chat - default budget/time "
                "guardrails apply since none were stated.",
    })

    remaining_budget = effective_max_amount - primary.price
    grounded = recommendation_service.select_grounded_upsell(primary, remaining_budget)

    primary_reasoning = f"Added from {primary.merchant_name}'s menu."
    upsell_reasoning = f"Pairs with {primary.title} and fits your remaining budget." if grounded else ""
    agent_result = {
        "primary": primary.to_dict(), "upsell": grounded.to_dict() if grounded else None,
        "primary_reasoning": primary_reasoning, "upsell_reasoning": upsell_reasoning,
        "trace": [{"tool": "quick_add", "args": {"item_id": req.item_id}}],
        "candidates": [primary.to_dict()],
    }
    audit_repo.log_event(session_id, events.RECOMMENDATION_GENERATED, "success", {
        "buyer": "direct_browse", "primary_product_id": primary.product_id,
        "upsell_product_id": grounded.product_id if grounded else None,
        "primary_reasoning": primary_reasoning, "upsell_reasoning": upsell_reasoning,
    })

    _store_recommendation(session_id, mandate, agent_result)

    return {
        "session_id": session_id, "reply": primary_reasoning, "intent_mandate": mandate.to_dict(),
        "primary": product_to_dish_dict(agent_result["primary"]), "upsell": product_to_dish_dict(agent_result["upsell"]),
        "candidates": [product_to_dish_dict(agent_result["primary"])],
    }
