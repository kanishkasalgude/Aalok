"""
FreshKart - synthetic BigBasket-style grocery merchant (fictional; no real
FreshKart/BigBasket integration or data is used). Raw catalog fields
deliberately use this merchant's own naming (`sku`, `mrp`, `pack_size`) to
exercise a genuine normalization step, not just a schema pass-through.
"""
from __future__ import annotations

from typing import Optional

from ...domain.catalog.capabilities import DEFAULT_MOCK_CAPABILITIES
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product, normalize_raw_product
from .base import MerchantAdapter

MERCHANT_ID = "grocery-freshkart"
MERCHANT_NAME = "FreshKart"

RAW_PRODUCTS = [
    {"sku": "g1", "name": "Basmati Rice", "pack_size": "5kg", "mrp": 699, "price": 599, "category": "staples",
     "in_stock": True, "brand": "FreshKart Essentials", "complements": ["g2"]},
    {"sku": "g2", "name": "Toor Dal", "pack_size": "1kg", "mrp": 180, "price": 159, "category": "staples",
     "in_stock": True, "brand": "FreshKart Essentials", "complements": ["g1"]},
    {"sku": "g3", "name": "Sunflower Oil", "pack_size": "1L", "mrp": 210, "price": 189, "category": "staples",
     "in_stock": True, "brand": "FreshKart Essentials", "complements": []},
    {"sku": "g4", "name": "Toned Milk", "pack_size": "1L", "mrp": 68, "price": 66, "category": "dairy",
     "in_stock": True, "brand": "DairyPure", "complements": ["g5"]},
    {"sku": "g5", "name": "Brown Bread", "pack_size": "400g", "mrp": 55, "price": 49, "category": "bakery",
     "in_stock": True, "brand": "FreshKart Bakes", "complements": ["g4"]},
    {"sku": "g6", "name": "Bananas", "pack_size": "1 dozen", "mrp": 65, "price": 59, "category": "produce",
     "in_stock": True, "brand": "FreshKart Farms", "complements": []},
    {"sku": "g7", "name": "Onions", "pack_size": "1kg", "mrp": 45, "price": 39, "category": "produce",
     "in_stock": True, "brand": "FreshKart Farms", "complements": ["g8"]},
    {"sku": "g8", "name": "Tomatoes", "pack_size": "1kg", "mrp": 50, "price": 42, "category": "produce",
     "in_stock": True, "brand": "FreshKart Farms", "complements": ["g7"]},
    {"sku": "g9", "name": "Farm Eggs", "pack_size": "12 pc", "mrp": 90, "price": 84, "category": "dairy",
     "in_stock": True, "brand": "DairyPure", "complements": []},
    {"sku": "g10", "name": "Green Tea", "pack_size": "100g", "mrp": 220, "price": 199, "category": "beverages",
     "in_stock": False, "brand": "LeafSteep", "complements": []},
]


def _normalize(raw: dict) -> Product:
    return normalize_raw_product({
        "product_id": raw["sku"], "title": raw["name"], "subcategory": raw["category"],
        "description": f"{raw['name']} ({raw['pack_size']}) from {raw['brand']}.",
        "brand": raw["brand"], "price": raw["price"], "mrp": raw["mrp"],
        "discount": round((raw["mrp"] - raw["price"]) / raw["mrp"] * 100, 1) if raw["mrp"] else 0.0,
        "availability": raw["in_stock"], "attributes": {"pack_size": raw["pack_size"]},
        "delivery": {"eta_min": 90, "fee": 25.0}, "location": "Pune, IN",
        "complement_ids": raw["complements"],
    }, merchant_id=MERCHANT_ID, merchant_name=MERCHANT_NAME, category="grocery")


class GroceryAdapter(MerchantAdapter):
    def __init__(self):
        self.merchant = Merchant(merchant_id=MERCHANT_ID, name=MERCHANT_NAME, category="grocery",
                                  subcategory="supermarket", open=True, tier="value", rating=4.2,
                                  capabilities=DEFAULT_MOCK_CAPABILITIES)

    def search(self, query: str = "", filters: Optional[dict] = None) -> list:
        filters = filters or {}
        out = []
        for raw in RAW_PRODUCTS:
            if filters.get("max_price") is not None and raw["price"] > filters["max_price"]:
                continue
            if filters.get("min_price") is not None and raw["price"] < filters["min_price"]:
                continue
            out.append(_normalize(raw))
        return out

    def get_product(self, product_id: str) -> Optional[Product]:
        raw = next((r for r in RAW_PRODUCTS if r["sku"] == product_id), None)
        return _normalize(raw) if raw else None
