"""
Step 2b: wraps orchestrator.py's tool-calling loop with the deterministic
fallback and the grounded-upsell defensive checks - generalized from
agent.py's run_ordering_agent/_fallback_ordering/select_grounded_upsell
orchestration. Returns {primary, upsell, primary_reasoning,
upsell_reasoning, trace, candidates} where primary/upsell are Product
dicts or None - the same response shape the pre-refactor chat route
already returns to the frontend.

Whatever the LLM proposes here still has to pass AuthorizationService and
PolicyEngine (services/order/service.py) before any money moves - this
module's job is recommendation quality, never payment authority.
"""
from __future__ import annotations

from typing import Optional

from ...domain.commerce.intent import Intent
from ..catalog import gateway
from ..recommendation import service as recommendation_service
from . import orchestrator

DEFAULT_MAX_AMOUNT = 1000.0       # platform guardrail if the user states no explicit budget
DEFAULT_MAX_DELIVERY_MIN = 60     # platform guardrail if the user states no explicit time bound


def _fallback(user_text: str, intent: Intent) -> dict:
    category = intent.category[0] if intent.category else None
    candidates = gateway.search_catalog(
        query=intent.query or user_text, category=category, max_price=intent.max_price,
        min_price=intent.min_price,
        filters={"required_attributes": intent.required_attributes, "max_delivery_time_min": intent.delivery_requirement},
    )
    trace = [{"tool": "search_catalog", "args": intent.to_dict(), "result_count": len(candidates)}]
    if not candidates:
        return {"primary": None, "upsell": None, "primary_reasoning": "No products matched all constraints.",
                "upsell_reasoning": "", "trace": trace, "candidates": []}

    primary = recommendation_service.pick_primary(candidates)
    remaining_budget = (intent.max_price or DEFAULT_MAX_AMOUNT) - primary.price
    upsell = recommendation_service.select_grounded_upsell(primary, remaining_budget)
    trace.append({"tool": "finalize_recommendation",
                   "args": {"primary_product_id": primary.product_id, "upsell_product_id": upsell.product_id if upsell else ""}})
    return {
        "primary": primary, "upsell": upsell,
        "primary_reasoning": f"Best match within your constraints from {primary.merchant_name}.",
        "upsell_reasoning": (f"Pairs with {primary.title} and fits your remaining budget." if upsell else ""),
        "trace": trace, "candidates": candidates,
    }


def run_commerce_agent(user_text: str, intent: Intent, session_id: str) -> dict:
    llm_result = orchestrator.run_tool_loop(user_text, intent, session_id)
    if llm_result is None or not llm_result.get("args"):
        return _to_response_dict(_fallback(user_text, intent))

    args = llm_result["args"]
    trace = llm_result["trace"]
    merchant_id = args.get("merchant_id")
    primary = gateway.get_product(args.get("primary_product_id", ""), merchant_id)
    if primary is None:
        # The model finalized against a product id that doesn't actually exist -
        # never trust it; fall back to the deterministic path instead.
        fb = _fallback(user_text, intent)
        fb["trace"] = trace + fb["trace"]
        return _to_response_dict(fb)

    upsell_id = args.get("upsell_product_id", "") or ""
    upsell = gateway.get_product(upsell_id, primary.merchant_id) if upsell_id else None
    upsell_reasoning = args.get("upsell_reasoning", "")
    # Defensive check: the LLM may only ever SUGGEST an upsell - the actual
    # pairing must be grounded in catalog data (Product.relationships), not
    # invented. If the model's pick isn't a recognized complement, replace
    # it with the deterministically-scored candidate instead of trusting an
    # unvalidated pairing.
    if upsell and upsell.product_id not in primary.relationships.complement_ids:
        trace.append({"tool": "upsell_grounded_substitution", "args": {
            "llm_proposed_product_id": upsell.product_id,
            "reason": "not a recognized complement of the primary item in catalog data",
        }})
        remaining_budget = (intent.max_price or DEFAULT_MAX_AMOUNT) - primary.price
        upsell = recommendation_service.select_grounded_upsell(primary, remaining_budget)
        upsell_reasoning = f"Pairs with {primary.title} and fits the remaining budget." if upsell else ""

    trace.append({"tool": "finalize_recommendation", "args": args})
    return _to_response_dict({
        "primary": primary, "upsell": upsell, "primary_reasoning": args.get("primary_reasoning", ""),
        "upsell_reasoning": upsell_reasoning, "trace": trace, "candidates": [primary],
    })


def _to_response_dict(result: dict) -> dict:
    return {
        "primary": result["primary"].to_dict() if result["primary"] else None,
        "upsell": result["upsell"].to_dict() if result["upsell"] else None,
        "primary_reasoning": result["primary_reasoning"], "upsell_reasoning": result["upsell_reasoning"],
        "trace": result["trace"], "candidates": [c.to_dict() for c in result["candidates"]],
    }
