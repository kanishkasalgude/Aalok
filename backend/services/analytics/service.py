"""
Platform-level and merchant-level analytics, aggregated from the real
`orders` table (moved from the old top-level analytics.py, generalized
from restaurant_breakdown to merchant_breakdown), plus a new
agentic-commerce funnel view derived from the real `audit_events` table
(spec section 16/20). Includes a couple of Gemini-generated natural-
language "insights" over the aggregate numbers (never raw per-user data).

experiments/growth_experiment.py remains the separately-labeled SYNTHETIC
benchmark - never mixed with the real numbers computed here.
"""
from __future__ import annotations

from collections import defaultdict

from ...core.config import get_settings
from ...domain.audit import events as ev
from ...integrations.llm.gemini import call_with_timeout, gemini_unreachable, llm_api_key
from ...repositories.db import get_conn
from ...repositories import order_repo, refund_repo


def platform_summary() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM orders").fetchall()
    conn.close()

    total_orders = len(rows)
    captured = [r for r in rows if r["status"] == "captured"]
    failed = [r for r in rows if r["status"] == "failed"]
    upsell_orders = [r for r in captured if r["upsell_accepted"]]

    aov = round(sum(r["total_amount"] for r in captured) / len(captured), 2) if captured else 0.0
    conversion_rate = round(len(captured) / total_orders * 100, 1) if total_orders else 0.0
    upsell_rate = round(len(upsell_orders) / len(captured) * 100, 1) if captured else 0.0
    ai_revenue = round(sum(r["total_amount"] for r in captured), 2)

    return {
        "total_orders": total_orders, "captured_orders": len(captured), "failed_orders": len(failed),
        "average_order_value": aov, "conversion_rate_pct": conversion_rate,
        "upsell_acceptance_rate_pct": upsell_rate, "ai_assisted_revenue": ai_revenue,
    }


def merchant_breakdown() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM orders").fetchall()
    conn.close()

    by_merchant = defaultdict(list)
    for r in rows:
        by_merchant[r["merchant_name"]].append(r)

    out = []
    for name, orders in by_merchant.items():
        captured = [o for o in orders if o["status"] == "captured"]
        upsell = [o for o in captured if o["upsell_accepted"]]
        aov = round(sum(o["total_amount"] for o in captured) / len(captured), 2) if captured else 0.0
        out.append({
            "merchant_name": name, "orders": len(orders), "captured": len(captured),
            "average_order_value": aov,
            "upsell_acceptance_rate_pct": round(len(upsell) / len(captured) * 100, 1) if captured else 0.0,
        })
    out.sort(key=lambda x: x["captured"], reverse=True)
    return out


# Backward-compatible alias for the pre-refactor name.
restaurant_breakdown = merchant_breakdown


def daily_trend(days: int = 14) -> list:
    """Real per-day order/capture/failure/revenue series (from the same
    `orders` table platform_summary() reads) - powers the Overview page's
    trend chart. Never a synthetic/interpolated series."""
    return order_repo.orders_by_day(days=days)


def refund_summary() -> dict:
    refunds = refund_repo.list_refunds(limit=1000)
    processed = [r for r in refunds if r["status"] == "processed"]
    return {
        "count": len(refunds),
        "processed_count": len(processed),
        "total_amount": round(sum(r["amount"] for r in processed), 2),
        "recent": refunds[:10],
    }


FUNNEL_STEPS = [
    ev.INTENT_CAPTURED, ev.CATALOG_SEARCH, ev.RECOMMENDATION_GENERATED, ev.CART_CREATED,
    ev.AUTHORIZATION_CHECKED, ev.POLICY_PASSED, ev.PAYMENT_ATTEMPTED, ev.PAYMENT_CAPTURED, ev.ORDER_CONFIRMED,
]


def agentic_funnel() -> dict:
    """Distinct-session counts per funnel step, plus step-to-step
    conversion rates - derived entirely from real audit_events, never
    hardcoded counters (spec section 20)."""
    conn = get_conn()
    counts = {}
    for step in FUNNEL_STEPS:
        row = conn.execute(
            "SELECT COUNT(DISTINCT session_id) AS c FROM audit_events WHERE step=?", (step,)
        ).fetchone()
        counts[step] = row["c"]
    policy_rejected = conn.execute(
        "SELECT COUNT(DISTINCT session_id) AS c FROM audit_events WHERE step=?", (ev.POLICY_REJECTED,)
    ).fetchone()["c"]
    payment_failed = conn.execute(
        "SELECT COUNT(DISTINCT session_id) AS c FROM audit_events WHERE step=?", (ev.PAYMENT_FAILED,)
    ).fetchone()["c"]
    payment_retry = conn.execute(
        "SELECT COUNT(DISTINCT session_id) AS c FROM audit_events WHERE step=?", (ev.PAYMENT_RETRY,)
    ).fetchone()["c"]
    conn.close()

    def _rate(numerator_step, denominator_step):
        d = counts.get(denominator_step, 0)
        return round(counts.get(numerator_step, 0) / d * 100, 1) if d else 0.0

    return {
        "steps": counts,
        "intent_to_cart_conversion_pct": _rate(ev.CART_CREATED, ev.INTENT_CAPTURED),
        "cart_to_checkout_conversion_pct": _rate(ev.PAYMENT_ATTEMPTED, ev.CART_CREATED),
        "checkout_to_payment_conversion_pct": _rate(ev.PAYMENT_CAPTURED, ev.PAYMENT_ATTEMPTED),
        "policy_rejection_sessions": policy_rejected,
        "payment_failure_sessions": payment_failed,
        "payment_retry_sessions": payment_retry,
    }


def _heuristic_insights(summary: dict, breakdown: list) -> list:
    insights = []
    if breakdown:
        top = max(breakdown, key=lambda r: r["upsell_acceptance_rate_pct"])
        insights.append(
            f"{top['merchant_name']} has the highest upsell acceptance rate at "
            f"{top['upsell_acceptance_rate_pct']}%, well above the platform average of "
            f"{summary['upsell_acceptance_rate_pct']}%."
        )
    insights.append(
        f"Average order value across AI-assisted orders is ₹{summary['average_order_value']}, "
        f"with a {summary['conversion_rate_pct']}% conversion rate from agent recommendation to captured payment."
    )
    return insights


def _insights_call(summary: dict, breakdown: list):
    import google.generativeai as genai
    genai.configure(api_key=llm_api_key())
    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt = (
        "You are a merchant analytics assistant for a multi-category AI commerce platform. Given this "
        "aggregate JSON data (no personal user data, just counts and averages), write exactly 2 short, "
        "concrete, non-generic insight sentences a merchant ops manager would find actionable. No preamble, "
        "no markdown, just the 2 sentences on separate lines.\n\n"
        f"Platform summary: {summary}\nPer-merchant breakdown: {breakdown}"
    )
    resp = model.generate_content(prompt, generation_config={"temperature": 0.4})
    lines = [l.strip("-• \n") for l in resp.text.strip().split("\n") if l.strip()]
    return lines[:3] if lines else None


def generate_insights(summary: dict, breakdown: list) -> list:
    settings = get_settings()
    if settings.llm_provider != "gemini" or not llm_api_key() or gemini_unreachable():
        return _heuristic_insights(summary, breakdown)
    lines = call_with_timeout(_insights_call, summary, breakdown, timeout=8.0)
    return lines if lines else _heuristic_insights(summary, breakdown)
