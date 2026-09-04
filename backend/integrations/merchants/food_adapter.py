"""
Food merchant adapter - wraps Aalok's original seed catalog (8
fictional restaurants x 6-8 dishes each) verbatim. This is the richest,
already-sourced dataset in the project (see the provenance notes below,
carried over unchanged from the pre-refactor catalog.py), so rather than
inventing a ninth food dataset it is reused as-is: each restaurant becomes
its own FoodAdapter instance, giving the multi-merchant catalog 8 real food
merchants "for free".

--- Data provenance (Sept 2026 research pass, see project research doc) -------

Prices are calibrated against Perplexity-sourced 2026 Pune Swiggy/Zomato
listing samples and a Q1 2026 cuisine-basket analysis, not invented — see the
per-restaurant comments below for the specific adjustments that came out of
that pass (e.g. both protein shakes were originally priced as if they were
watered-down drinks; real protein-powder shakes on Indian delivery apps run
₹220-350).

`protein_g` / `carbs_g` are **recipe-estimated per the stated serving
assumption**, not lab nutrition-panel values — restaurant recipes vary 20-40%
in practice. They are anchored to commonly-cited per-100g macros (cooked
chicken breast ≈31g protein/0g carb, cooked quinoa ≈8g protein/39g carb per
cup, dal makhani ≈12g protein/30g carb per cup, tandoori chicken ≈28g
protein/4g carb per serving) rather than being asserted from the dish name.

`dietary_tags` for "high-protein" and "low-carb" are DERIVED from those grams
by `_compute_dietary_tags()` below, not hand-typed per dish. Thresholds used
(documented, not hidden in a boolean):
  high-protein  := protein_g >= 20   (Zomato Healthy-Mode-style threshold)
  low-carb      := carbs_g   <= 30   (total carbs, NOT net-of-fiber)
  low-carb is never applied to anything tagged "dessert".

`restaurant_tier` (value / mainstream / premium) reflects where each
restaurant's price points actually land against the sourced bands.

Delivery time is prep_time_min (dish-specific) + a courier leg that varies
by how long the kitchen step takes. See `estimate_courier_time_min()`.
"""
from __future__ import annotations

from typing import Optional

from ...core.errors import MerchantAdapterError
from ...domain.catalog.capabilities import DEFAULT_MOCK_CAPABILITIES
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product, normalize_raw_product
from .base import MerchantAdapter

HIGH_PROTEIN_G = 20
VERY_HIGH_PROTEIN_G = 40
LOW_CARB_MAX_G = 30

# `rating` is ILLUSTRATIVE/DEMO DATA for the UI's restaurant cards - a fixed,
# deterministic number per restaurant, not derived from any real review
# corpus.
RESTAURANTS = [
    {"id": "r1", "name": "Grill & Greens", "cuisine": "Continental", "open": True, "tier": "premium", "rating": 4.3},
    {"id": "r2", "name": "Spice Route", "cuisine": "North Indian", "open": True, "tier": "mainstream", "rating": 4.2},
    {"id": "r3", "name": "Wok This Way", "cuisine": "Chinese", "open": True, "tier": "mainstream", "rating": 4.1},
    {"id": "r4", "name": "Sprout & Steel", "cuisine": "Healthy/Fitness", "open": True, "tier": "premium", "rating": 4.5},
    {"id": "r5", "name": "Curry Leaf", "cuisine": "South Indian", "open": True, "tier": "value", "rating": 4.4},
    {"id": "r6", "name": "Basil & Bread", "cuisine": "Italian", "open": True, "tier": "mainstream", "rating": 4.0},
    {"id": "r7", "name": "Tandoor Tales", "cuisine": "Mughlai", "open": True, "tier": "mainstream", "rating": 4.3},
    {"id": "r8", "name": "Green Bowl Co.", "cuisine": "Vegan/Salads", "open": False, "tier": "premium", "rating": 4.2},
]

DISHES = [
    {"id": "d101", "restaurant_id": "r1", "name": "Grilled Chicken Breast Bowl", "price": 449,
     "category_tags": ["non-veg"], "protein_g": 50, "carbs_g": 48, "prep_time_min": 22,
     "description": "Grilled chicken breast with steamed greens and quinoa, high protein bowl."},
    {"id": "d102", "restaurant_id": "r1", "name": "Paneer Power Salad", "price": 379,
     "category_tags": ["veg"], "protein_g": 30, "carbs_g": 38, "prep_time_min": 18,
     "description": "Pan-seared paneer over a protein-rich salad with chickpeas and greens."},
    {"id": "d103", "restaurant_id": "r1", "name": "Classic Caesar Salad", "price": 299,
     "category_tags": ["veg"], "protein_g": 9, "carbs_g": 20, "prep_time_min": 15,
     "description": "Crisp romaine, parmesan, croutons, classic caesar dressing."},
    {"id": "d104", "restaurant_id": "r1", "name": "Iced Peach Tea", "price": 99,
     "category_tags": ["veg", "beverage"], "protein_g": 0, "carbs_g": 28, "prep_time_min": 5,
     "description": "Chilled peach iced tea, light and refreshing."},
    {"id": "d105", "restaurant_id": "r1", "name": "Protein Shake - Chocolate", "price": 249,
     "category_tags": ["veg", "beverage"], "protein_g": 25, "carbs_g": 14, "prep_time_min": 6,
     "description": "Chocolate whey protein shake, 25g protein, great post-meal add-on."},

    {"id": "d201", "restaurant_id": "r2", "name": "Butter Chicken with Rice", "price": 389,
     "category_tags": ["non-veg"], "protein_g": 32, "carbs_g": 58, "prep_time_min": 35,
     "description": "Rich creamy butter chicken curry served with steamed basmati rice."},
    {"id": "d202", "restaurant_id": "r2", "name": "Tandoori Chicken (Half)", "price": 349,
     "category_tags": ["non-veg"], "protein_g": 42, "carbs_g": 8, "prep_time_min": 40,
     "description": "Char-grilled tandoori chicken marinated in yogurt and spices, high protein."},
    {"id": "d203", "restaurant_id": "r2", "name": "Dal Makhani", "price": 249,
     "category_tags": ["veg"], "protein_g": 14, "carbs_g": 38, "prep_time_min": 28,
     "description": "Slow-cooked black lentils in a creamy tomato gravy."},
    {"id": "d204", "restaurant_id": "r2", "name": "Masala Papad", "price": 79,
     "category_tags": ["veg"], "protein_g": 3, "carbs_g": 18, "prep_time_min": 8,
     "description": "Crisp papad topped with onion, tomato and chaat masala."},
    {"id": "d205", "restaurant_id": "r2", "name": "Gulab Jamun (2 pc)", "price": 99,
     "category_tags": ["veg", "dessert"], "protein_g": 3, "carbs_g": 32, "prep_time_min": 6,
     "description": "Soft milk-solid dumplings soaked in rose-scented sugar syrup."},

    {"id": "d301", "restaurant_id": "r3", "name": "Chicken Schezwan Noodles", "price": 269,
     "category_tags": ["non-veg"], "protein_g": 22, "carbs_g": 55, "prep_time_min": 25,
     "description": "Wok-tossed noodles with chicken in spicy schezwan sauce."},
    {"id": "d302", "restaurant_id": "r3", "name": "Tofu & Broccoli Stir Fry", "price": 259,
     "category_tags": ["vegan"], "protein_g": 23, "carbs_g": 20, "prep_time_min": 20,
     "description": "High protein tofu stir fried with broccoli and garlic, light on carbs."},
    {"id": "d303", "restaurant_id": "r3", "name": "Veg Manchurian Dry", "price": 219,
     "category_tags": ["vegan"], "protein_g": 8, "carbs_g": 32, "prep_time_min": 22,
     "description": "Crispy vegetable dumplings tossed in tangy manchurian sauce."},
    {"id": "d304", "restaurant_id": "r3", "name": "Chicken Lollipop (6 pc)", "price": 279,
     "category_tags": ["non-veg"], "protein_g": 27, "carbs_g": 35, "prep_time_min": 24,
     "description": "Deep fried spicy chicken lollipops, a popular high-protein starter."},
    {"id": "d305", "restaurant_id": "r3", "name": "Lemon Iced Tea", "price": 89,
     "category_tags": ["vegan", "beverage"], "protein_g": 0, "carbs_g": 22, "prep_time_min": 5,
     "description": "Refreshing chilled lemon iced tea."},

    {"id": "d401", "restaurant_id": "r4", "name": "Grilled Fish Protein Bowl", "price": 469,
     "category_tags": ["non-veg"], "protein_g": 44, "carbs_g": 42, "prep_time_min": 20,
     "description": "Grilled fish fillet with quinoa and greens, a lean high protein bowl reaching fast."},
    {"id": "d402", "restaurant_id": "r4", "name": "Egg White & Chicken Bowl", "price": 399,
     "category_tags": ["non-veg"], "protein_g": 48, "carbs_g": 18, "prep_time_min": 18,
     "description": "Egg whites and grilled chicken over greens, high protein low-carb bowl."},
    {"id": "d403", "restaurant_id": "r4", "name": "Sprouts & Soy Chunk Bowl", "price": 259,
     "category_tags": ["vegan"], "protein_g": 26, "carbs_g": 24, "prep_time_min": 15,
     "description": "Soy chunks, sprouts and veggies, plant-based high protein bowl."},
    {"id": "d404", "restaurant_id": "r4", "name": "Cold-Pressed Watermelon Juice", "price": 119,
     "category_tags": ["vegan", "beverage"], "protein_g": 0, "carbs_g": 22, "prep_time_min": 5,
     "description": "Fresh cold-pressed watermelon juice, no added sugar."},
    {"id": "d405", "restaurant_id": "r4", "name": "Peanut Protein Shake", "price": 229,
     "category_tags": ["veg", "beverage"], "protein_g": 20, "carbs_g": 16, "prep_time_min": 6,
     "description": "Peanut butter protein shake, a solid post-workout add-on."},

    {"id": "d501", "restaurant_id": "r5", "name": "Masala Dosa", "price": 149,
     "category_tags": ["veg"], "protein_g": 7, "carbs_g": 48, "prep_time_min": 18,
     "description": "Crisp rice-lentil crepe filled with spiced potato masala."},
    {"id": "d502", "restaurant_id": "r5", "name": "Chicken Chettinad", "price": 359,
     "category_tags": ["non-veg"], "protein_g": 30, "carbs_g": 10, "prep_time_min": 32,
     "description": "Spicy South Indian chicken curry with roasted spices, high protein."},
    {"id": "d503", "restaurant_id": "r5", "name": "Sprouts Sundal", "price": 129,
     "category_tags": ["vegan"], "protein_g": 14, "carbs_g": 32, "prep_time_min": 12,
     "description": "Steamed sprouted moong dressed with coconut and curry leaf."},
    {"id": "d504", "restaurant_id": "r5", "name": "Filter Coffee", "price": 69,
     "category_tags": ["veg", "beverage"], "protein_g": 1, "carbs_g": 10, "prep_time_min": 5,
     "description": "Traditional South Indian filter coffee."},

    {"id": "d601", "restaurant_id": "r6", "name": "Grilled Chicken Pesto Pasta", "price": 399,
     "category_tags": ["non-veg"], "protein_g": 44, "carbs_g": 70, "prep_time_min": 26,
     "description": "Penne pasta with grilled chicken in basil pesto sauce."},
    {"id": "d602", "restaurant_id": "r6", "name": "Margherita Pizza (7 inch)", "price": 259,
     "category_tags": ["veg"], "protein_g": 18, "carbs_g": 55, "prep_time_min": 24,
     "description": "Classic margherita pizza with fresh basil and mozzarella."},
    {"id": "d603", "restaurant_id": "r6", "name": "Tiramisu", "price": 199,
     "category_tags": ["veg", "dessert"], "protein_g": 6, "carbs_g": 42, "prep_time_min": 5,
     "description": "Classic Italian coffee-flavoured layered dessert."},
    {"id": "d604", "restaurant_id": "r6", "name": "Sparkling Lemonade", "price": 99,
     "category_tags": ["veg", "beverage"], "protein_g": 0, "carbs_g": 24, "prep_time_min": 5,
     "description": "House-made sparkling lemonade."},

    {"id": "d701", "restaurant_id": "r7", "name": "Seekh Kebab Platter", "price": 349,
     "category_tags": ["non-veg"], "protein_g": 40, "carbs_g": 12, "prep_time_min": 30,
     "description": "Minced meat kebabs grilled in a tandoor, high protein platter."},
    {"id": "d702", "restaurant_id": "r7", "name": "Chicken Biryani", "price": 289,
     "category_tags": ["non-veg"], "protein_g": 24, "carbs_g": 68, "prep_time_min": 38,
     "description": "Fragrant dum-cooked chicken biryani with saffron rice."},
    {"id": "d703", "restaurant_id": "r7", "name": "Raita", "price": 59,
     "category_tags": ["veg"], "protein_g": 4, "carbs_g": 8, "prep_time_min": 5,
     "description": "Cooling yogurt side with cucumber and spices."},

    {"id": "d801", "restaurant_id": "r8", "name": "Vegan Buddha Bowl", "price": 329,
     "category_tags": ["vegan"], "protein_g": 28, "carbs_g": 65, "prep_time_min": 20,
     "description": "Chickpeas, tofu, quinoa and greens vegan protein bowl."},
    {"id": "d802", "restaurant_id": "r8", "name": "Green Detox Juice", "price": 129,
     "category_tags": ["vegan", "beverage"], "protein_g": 1, "carbs_g": 18, "prep_time_min": 5,
     "description": "Spinach, cucumber and apple cold-pressed detox juice."},
]

# {main_dish_id: [addon_ids]}, restaurant-scoped by construction - this is
# what grounds the upsell/complement relationship in real catalog data.
COMPLEMENTS = {
    "d101": ["d104", "d105"], "d102": ["d104", "d105"], "d103": ["d104"],
    "d201": ["d204", "d205"], "d202": ["d204", "d205"], "d203": ["d204", "d205"],
    "d301": ["d305"], "d302": ["d305"], "d303": ["d305"], "d304": ["d305"],
    "d401": ["d404", "d405"], "d402": ["d404", "d405"], "d403": ["d404", "d405"],
    "d501": ["d504"], "d502": ["d504"], "d503": ["d504"],
    "d601": ["d603", "d604"], "d602": ["d603", "d604"],
    "d701": ["d703"], "d702": ["d703"],
    "d801": ["d802"],
}


def _compute_dietary_tags(category_tags: list, protein_g: float, carbs_g: float) -> list:
    tags = list(category_tags)
    if protein_g >= HIGH_PROTEIN_G:
        tags.append("high-protein")
    if carbs_g <= LOW_CARB_MAX_G and "dessert" not in category_tags:
        tags.append("low-carb")
    return tags


for _d in DISHES:
    if "dietary_tags" not in _d:
        _d["dietary_tags"] = _compute_dietary_tags(_d.pop("category_tags"), _d["protein_g"], _d["carbs_g"])
        _d["complements"] = COMPLEMENTS.get(_d["id"], [])
del _d


def estimate_courier_time_min(prep_time_min: int) -> int:
    """Courier/last-mile leg, varied by how involved the kitchen step is."""
    if prep_time_min <= 7:
        return 19
    if prep_time_min <= 20:
        return 16
    return 15


def restaurant_by_id(rid: str) -> Optional[dict]:
    return next((r for r in RESTAURANTS if r["id"] == rid), None)


def dish_by_id(did: str) -> Optional[dict]:
    return next((d for d in DISHES if d["id"] == did), None)


def _enrich(d: dict) -> dict:
    r = restaurant_by_id(d["restaurant_id"])
    item = dict(d)
    item["restaurant_name"] = r["name"]
    item["cuisine"] = r["cuisine"]
    item["restaurant_tier"] = r["tier"]
    item["restaurant_open"] = r["open"]
    item["restaurant_rating"] = r["rating"]
    item["courier_time_min"] = estimate_courier_time_min(d["prep_time_min"])
    item["delivery_time_min"] = d["prep_time_min"] + item["courier_time_min"]
    return item


def enriched_dishes() -> list:
    return [_enrich(d) for d in DISHES]


def enriched_dish_by_id(did: str):
    d = dish_by_id(did)
    return _enrich(d) if d else None


def _dish_to_product(d: dict) -> Product:
    raw = {
        "product_id": d["id"],
        "title": d["name"],
        "description": d["description"],
        "brand": d["restaurant_name"],
        "price": d["price"],
        "availability": d["restaurant_open"],
        "attributes": {
            "dietary_tags": d["dietary_tags"],
            "protein_g": d["protein_g"],
            "carbs_g": d["carbs_g"],
            "prep_time_min": d["prep_time_min"],
        },
        "delivery": {"eta_min": d["delivery_time_min"], "fee": 0.0},
        "location": "Pune, IN",
        "complement_ids": d["complements"],
        "ai_metadata": {"cuisine": d["cuisine"], "restaurant_tier": d["restaurant_tier"]},
    }
    return normalize_raw_product(raw, merchant_id=d["restaurant_id"], merchant_name=d["restaurant_name"], category="food")


class FoodAdapter(MerchantAdapter):
    """One instance per restaurant - see module docstring."""

    def __init__(self, restaurant_id: str):
        r = restaurant_by_id(restaurant_id)
        if r is None:
            raise MerchantAdapterError(f"Unknown restaurant_id '{restaurant_id}'.")
        self._restaurant_id = restaurant_id
        self.merchant = Merchant(
            merchant_id=r["id"], name=r["name"], category="food", subcategory=r["cuisine"],
            open=r["open"], tier=r["tier"], rating=r["rating"],
            capabilities=DEFAULT_MOCK_CAPABILITIES,
        )

    def search(self, query: str = "", filters: Optional[dict] = None) -> list:
        filters = filters or {}
        dishes = [d for d in enriched_dishes() if d["restaurant_id"] == self._restaurant_id]
        max_price = filters.get("max_price")
        min_price = filters.get("min_price")
        max_delivery = filters.get("max_delivery_time_min")
        required_attrs = filters.get("required_attributes") or {}
        out = []
        for d in dishes:
            if max_price is not None and d["price"] > max_price:
                continue
            if min_price is not None and d["price"] < min_price:
                continue
            if max_delivery is not None and d["delivery_time_min"] > max_delivery:
                continue
            dietary = required_attrs.get("dietary_tags")
            if dietary and dietary not in d["dietary_tags"]:
                continue
            out.append(_dish_to_product(d))
        return out

    def get_product(self, product_id: str) -> Optional[Product]:
        d = enriched_dish_by_id(product_id)
        if not d or d["restaurant_id"] != self._restaurant_id:
            return None
        return _dish_to_product(d)


def all_food_adapters() -> list:
    return [FoodAdapter(r["id"]) for r in RESTAURANTS]


def all_food_products() -> list:
    """Every dish as a Product - used to warm the embedding cache at
    startup (see main.py)."""
    return [_dish_to_product(d) for d in enriched_dishes()]
