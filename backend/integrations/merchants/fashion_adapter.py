"""Threadloom - synthetic fashion merchant (fictional)."""
from __future__ import annotations

from typing import Optional

from ...domain.catalog.capabilities import DEFAULT_MOCK_CAPABILITIES
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product, normalize_raw_product
from .base import MerchantAdapter

MERCHANT_ID = "fashion-threadloom"
MERCHANT_NAME = "Threadloom"

RAW_PRODUCTS = [
    {"item_code": "f1", "product_name": "Men's Cotton T-Shirt", "mrp": 999, "selling_price": 599,
     "size": ["S", "M", "L", "XL"], "color": "Navy", "material": "100% Cotton", "stock_qty": 40, "complements": ["f6"]},
    {"item_code": "f2", "product_name": "Women's Printed Kurta", "mrp": 1499, "selling_price": 899,
     "size": ["S", "M", "L"], "color": "Maroon", "material": "Rayon", "stock_qty": 25, "complements": ["f7"]},
    {"item_code": "f3", "product_name": "Denim Jacket", "mrp": 2999, "selling_price": 1999,
     "size": ["M", "L", "XL"], "color": "Blue", "material": "Denim", "stock_qty": 15, "complements": []},
    {"item_code": "f4", "product_name": "Formal Shirt", "mrp": 1299, "selling_price": 799,
     "size": ["S", "M", "L", "XL"], "color": "White", "material": "Cotton Blend", "stock_qty": 30, "complements": []},
    {"item_code": "f5", "product_name": "Running Shoes", "mrp": 3499, "selling_price": 2499,
     "size": ["7", "8", "9", "10"], "color": "Black", "material": "Mesh", "stock_qty": 20, "complements": []},
    {"item_code": "f6", "product_name": "Ankle Socks (3-pack)", "mrp": 399, "selling_price": 249,
     "size": ["Free"], "color": "White", "material": "Cotton", "stock_qty": 60, "complements": ["f1"]},
    {"item_code": "f7", "product_name": "Statement Earrings", "mrp": 599, "selling_price": 349,
     "size": ["Free"], "color": "Gold-tone", "material": "Alloy", "stock_qty": 35, "complements": ["f2"]},
    {"item_code": "f8", "product_name": "Chinos", "mrp": 1799, "selling_price": 1199,
     "size": ["30", "32", "34", "36"], "color": "Beige", "material": "Cotton Twill", "stock_qty": 22, "complements": []},
    {"item_code": "f9", "product_name": "Casual Sneakers", "mrp": 2799, "selling_price": 1899,
     "size": ["7", "8", "9", "10"], "color": "White", "material": "Canvas", "stock_qty": 0, "complements": []},
]


def _normalize(raw: dict) -> Product:
    return normalize_raw_product({
        "product_id": raw["item_code"], "title": raw["product_name"], "subcategory": "apparel",
        "description": f"{raw['product_name']} in {raw['color']}, {raw['material']}.",
        "brand": MERCHANT_NAME, "price": raw["selling_price"], "mrp": raw["mrp"],
        "discount": round((raw["mrp"] - raw["selling_price"]) / raw["mrp"] * 100, 1),
        "availability": raw["stock_qty"] > 0,
        "variants": [{"variant_id": s, "label": f"Size {s}"} for s in raw["size"]],
        "attributes": {"size": raw["size"], "color": raw["color"], "material": raw["material"]},
        "delivery": {"eta_min": 4320, "fee": 49.0}, "location": "Pune, IN",  # ~3 days
        "complement_ids": raw["complements"],
    }, merchant_id=MERCHANT_ID, merchant_name=MERCHANT_NAME, category="fashion")


class FashionAdapter(MerchantAdapter):
    def __init__(self):
        self.merchant = Merchant(merchant_id=MERCHANT_ID, name=MERCHANT_NAME, category="fashion",
                                  subcategory="apparel", open=True, tier="mainstream", rating=4.1,
                                  capabilities=DEFAULT_MOCK_CAPABILITIES)

    def search(self, query: str = "", filters: Optional[dict] = None) -> list:
        filters = filters or {}
        out = []
        for raw in RAW_PRODUCTS:
            if filters.get("max_price") is not None and raw["selling_price"] > filters["max_price"]:
                continue
            if filters.get("min_price") is not None and raw["selling_price"] < filters["min_price"]:
                continue
            required = (filters.get("required_attributes") or {}).get("color")
            if required and required.lower() != raw["color"].lower():
                continue
            out.append(_normalize(raw))
        return out

    def get_product(self, product_id: str) -> Optional[Product]:
        raw = next((r for r in RAW_PRODUCTS if r["item_code"] == product_id), None)
        return _normalize(raw) if raw else None
