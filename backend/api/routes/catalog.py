"""
Catalog routes. GET /api/catalog and GET /api/catalog/feed are the
pre-refactor food-only routes, preserved byte-for-byte (the frontend and
examples/ai_buyer.py both depend on their exact shape). The rest are the
new generalized AI Commerce Discovery Gateway surface (spec section 24),
spanning every connected merchant/category.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from experiments.growth_experiment import run_experiment

from ...domain.audit import events
from ...integrations.merchants import food_adapter
from ...integrations.merchants.registry import list_merchants
from ...repositories import audit_repo
from ...services.catalog import gateway
from ...services.recommendation import service as recommendation_service

router = APIRouter()


# --- legacy, food-only, preserved exactly ------------------------------------

@router.get("/api/catalog")
def get_catalog():
    return {"restaurants": food_adapter.RESTAURANTS, "dishes": food_adapter.enriched_dishes()}


@router.get("/api/catalog/feed")
def get_catalog_feed():
    """Agent-readable JSON-LD feed (schema.org Restaurant + MenuItem/Product +
    Offer) - the pre-refactor food-only feed, unchanged, since
    examples/ai_buyer.py and its tests parse this exact shape."""
    PRICE_NOTE = "Listed price excludes GST, packaging, delivery and platform fees."
    dishes_by_restaurant: dict = {}
    for d in food_adapter.enriched_dishes():
        dishes_by_restaurant.setdefault(d["restaurant_id"], []).append(d)

    restaurants_ld = []
    for r in food_adapter.RESTAURANTS:
        menu_items = []
        for d in dishes_by_restaurant.get(r["id"], []):
            menu_items.append({
                "@type": "MenuItem", "identifier": d["id"], "name": d["name"], "description": d["description"],
                "suitableForDiet": [f"https://schema.org/{tag.replace('-', '').title()}Diet"
                                     for tag in d["dietary_tags"] if tag in ("vegan", "veg", "low-carb")],
                "nutrition": {"@type": "NutritionInformation", "proteinContent": f"{d['protein_g']}g",
                              "carbohydrateContent": f"{d['carbs_g']}g"},
                "offers": {"@type": "Offer", "price": d["price"], "priceCurrency": "INR",
                           "availability": "https://schema.org/InStock" if r["open"] else "https://schema.org/OutOfStock",
                           "description": PRICE_NOTE},
                "additionalProperty": [
                    {"@type": "PropertyValue", "name": "dietary_tags", "value": ",".join(d["dietary_tags"])},
                    {"@type": "PropertyValue", "name": "protein_g", "value": d["protein_g"]},
                    {"@type": "PropertyValue", "name": "carbs_g", "value": d["carbs_g"]},
                    {"@type": "PropertyValue", "name": "prep_time_min", "value": d["prep_time_min"]},
                    {"@type": "PropertyValue", "name": "courier_time_min", "value": d["courier_time_min"]},
                    {"@type": "PropertyValue", "name": "estimated_delivery_time_min", "value": d["delivery_time_min"]},
                ],
            })
        restaurants_ld.append({
            "@type": "Restaurant", "identifier": r["id"], "name": r["name"], "servesCuisine": r["cuisine"],
            "priceRange": {"value": "₹", "mainstream": "₹₹", "premium": "₹₹₹"}[r["tier"]],
            "openingHours": "Mo-Su 00:00-23:59" if r["open"] else "",
            "hasMenu": {"@type": "Menu", "hasMenuItem": menu_items},
        })

    return {
        "@context": "https://schema.org", "@type": "ItemList",
        "name": "Aalok Agent-Readable Restaurant Catalog",
        "description": ("Machine-readable feed of Aalok's restaurant partners and menus, intended for "
                         "consumption by AI shopping/ordering agents (not just Aalok's own in-app agent)."),
        "itemListElement": restaurants_ld,
    }


@router.get("/api/growth/experiment")
def growth_experiment():
    """SYNTHETIC BENCHMARK - see experiments/growth_experiment.py."""
    return run_experiment()


# --- new generalized AI Commerce Discovery Gateway surface -------------------

@router.get("/api/merchants")
def merchants():
    return {"merchants": list_merchants()}


@router.get("/api/catalog/search")
def search_catalog(query: str = "", category: Optional[str] = None, max_price: Optional[float] = None,
                    min_price: Optional[float] = None, location: Optional[str] = None,
                    merchant_ids: Optional[str] = None, top_k: int = 12):
    ids = merchant_ids.split(",") if merchant_ids else None
    products = gateway.search_catalog(query=query, category=category, max_price=max_price,
                                       min_price=min_price, location=location, merchant_ids=ids, top_k=top_k)
    audit_repo.log_event("catalog-search", events.CATALOG_SEARCH, "success",
                          {"query": query, "category": category, "result_count": len(products)})
    return {"results": [p.to_dict() for p in products]}


@router.get("/api/catalog/products/{product_id}")
def get_product(product_id: str, merchant_id: Optional[str] = None):
    product = gateway.get_product(product_id, merchant_id)
    if product is None:
        return {"error": f"Unknown product_id '{product_id}'."}
    return product.to_dict()


@router.get("/api/catalog/{product_id}/complements")
def get_complements(product_id: str, merchant_id: Optional[str] = None):
    return {"results": [p.to_dict() for p in recommendation_service.find_complements(product_id, merchant_id)]}


@router.get("/api/catalog/{product_id}/substitutes")
def get_substitutes(product_id: str, merchant_id: Optional[str] = None):
    return {"results": [p.to_dict() for p in recommendation_service.find_substitutes(product_id, merchant_id)]}
