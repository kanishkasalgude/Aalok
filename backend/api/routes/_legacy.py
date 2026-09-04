"""
Adapter helpers used ONLY by the pre-refactor food-only routes (chat.py's
/api/chat and /api/order/quick-add, orders.py's /api/order/confirm family)
to keep their JSON response shape byte-identical to what frontend/app.js
already expects (`primary.name`, `.price`, `.restaurant_name`,
`.delivery_time_min`, `.dietary_tags`, `.cuisine`) - the UI is explicitly
out of scope for this refactor (see task spec section 29), so its response
contract must not change.

Every route that uses this still runs the SAME generalized
commerce_agent/cart_service/order_service pipeline underneath - this file
only translates the Unified Commerce Schema Product back into the legacy
dish-shaped dict at the API boundary, nothing more.
"""
from __future__ import annotations

from typing import Optional


def product_to_dish_dict(product: Optional[dict]) -> Optional[dict]:
    """`product` is a Product.to_dict() shaped dict (as returned by
    services.agent.commerce_agent.run_commerce_agent / services.catalog.gateway)."""
    if product is None:
        return None
    attrs = product.get("attributes", {})
    return {
        "id": product["product_id"],
        "restaurant_id": product["merchant_id"],
        "name": product["title"],
        "price": product["price"],
        "dietary_tags": attrs.get("dietary_tags", []),
        "protein_g": attrs.get("protein_g", 0),
        "carbs_g": attrs.get("carbs_g", 0),
        "prep_time_min": attrs.get("prep_time_min", 0),
        "restaurant_name": product["merchant_name"],
        "cuisine": product.get("ai_metadata", {}).get("cuisine", ""),
        "restaurant_tier": product.get("ai_metadata", {}).get("restaurant_tier", ""),
        "restaurant_open": product["availability"],
        "delivery_time_min": product.get("delivery", {}).get("eta_min", 0),
        "complements": product.get("relationships", {}).get("complement_ids", []),
    }
