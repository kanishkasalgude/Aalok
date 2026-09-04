"""GET /api/analytics - preserved shape, plus the new agentic funnel view."""
from __future__ import annotations

from fastapi import APIRouter

from ...services.analytics import service as analytics_service

router = APIRouter()


@router.get("/api/analytics")
def analytics():
    summary = analytics_service.platform_summary()
    breakdown = analytics_service.merchant_breakdown()
    insights = analytics_service.generate_insights(summary, breakdown)
    funnel = analytics_service.agentic_funnel()
    daily_trend = analytics_service.daily_trend()
    refunds = analytics_service.refund_summary()
    # `restaurants` keeps the pre-refactor key name (`restaurant_name`) for
    # frontend/analytics.html; `merchants` is the same data under the new
    # generalized key name (`merchant_name`) for API consumers.
    restaurants = [{**row, "restaurant_name": row["merchant_name"]} for row in breakdown]
    return {"summary": summary, "restaurants": restaurants, "merchants": breakdown,
            "insights": insights, "agentic_funnel": funnel, "daily_trend": daily_trend,
            "refunds": refunds}
