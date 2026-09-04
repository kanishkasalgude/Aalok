"""ZipMart - synthetic Zepto-style quick-commerce merchant (fictional)."""
from __future__ import annotations

from typing import Optional

from ...domain.catalog.capabilities import DEFAULT_MOCK_CAPABILITIES
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product, normalize_raw_product
from .base import MerchantAdapter

MERCHANT_ID = "quickcommerce-zipmart"
MERCHANT_NAME = "ZipMart"

RAW_PRODUCTS = [
    {"sku": "z1", "name": "Potato Chips", "pack_size": "150g", "mrp": 99, "price": 89, "category": "snacks", "complements": ["z3"]},
    {"sku": "z2", "name": "Instant Noodles (4-pack)", "pack_size": "280g", "mrp": 60, "price": 56, "category": "snacks", "complements": []},
    {"sku": "z3", "name": "Cold Drink 750ml", "pack_size": "750ml", "mrp": 45, "price": 40, "category": "beverages", "complements": ["z1"]},
    {"sku": "z4", "name": "Ice Cream Tub", "pack_size": "700ml", "mrp": 250, "price": 199, "category": "frozen", "complements": []},
    {"sku": "z5", "name": "Dish Wash Liquid", "pack_size": "500ml", "mrp": 130, "price": 109, "category": "household", "complements": []},
    {"sku": "z6", "name": "Toilet Paper (4 rolls)", "pack_size": "4pk", "mrp": 180, "price": 149, "category": "household", "complements": []},
    {"sku": "z7", "name": "Dark Chocolate Bar", "pack_size": "90g", "mrp": 120, "price": 99, "category": "snacks", "complements": []},
    {"sku": "z8", "name": "Energy Drink Can", "pack_size": "250ml", "mrp": 125, "price": 110, "category": "beverages", "complements": []},
]


def _normalize(raw: dict) -> Product:
    return normalize_raw_product({
        "product_id": raw["sku"], "title": raw["name"], "subcategory": raw["category"],
        "description": f"{raw['name']} ({raw['pack_size']}).",
        "brand": MERCHANT_NAME, "price": raw["price"], "mrp": raw["mrp"],
        "discount": round((raw["mrp"] - raw["price"]) / raw["mrp"] * 100, 1),
        "availability": True, "attributes": {"pack_size": raw["pack_size"]},
        "delivery": {"eta_min": 12, "fee": 15.0}, "location": "Pune, IN",  # the whole point of quick-commerce
        "complement_ids": raw["complements"],
    }, merchant_id=MERCHANT_ID, merchant_name=MERCHANT_NAME, category="grocery")


class QuickCommerceAdapter(MerchantAdapter):
    def __init__(self):
        self.merchant = Merchant(merchant_id=MERCHANT_ID, name=MERCHANT_NAME, category="grocery",
                                  subcategory="quick_commerce", open=True, tier="value", rating=4.3,
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
