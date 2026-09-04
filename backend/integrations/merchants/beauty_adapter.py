"""GlowNest - synthetic Honasa-style beauty/personal-care merchant (fictional)."""
from __future__ import annotations

from typing import Optional

from ...domain.catalog.capabilities import DEFAULT_MOCK_CAPABILITIES
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product, normalize_raw_product
from .base import MerchantAdapter

MERCHANT_ID = "beauty-glownest"
MERCHANT_NAME = "GlowNest"

RAW_PRODUCTS = [
    {"sku": "b1", "label": "Vitamin C Face Wash", "mrp": 349, "price": 279, "skin_type": "all", "volume_ml": 150,
     "cruelty_free": True, "complements": ["b2"]},
    {"sku": "b2", "label": "Vitamin C Serum", "mrp": 799, "price": 649, "skin_type": "all", "volume_ml": 30,
     "cruelty_free": True, "complements": ["b1"]},
    {"sku": "b3", "label": "Sunscreen SPF50 PA+++", "mrp": 499, "price": 399, "skin_type": "all", "volume_ml": 50,
     "cruelty_free": True, "complements": []},
    {"sku": "b4", "label": "Nourishing Lip Balm", "mrp": 149, "price": 119, "skin_type": "dry", "volume_ml": 10,
     "cruelty_free": True, "complements": []},
    {"sku": "b5", "label": "Onion Hair Shampoo", "mrp": 399, "price": 329, "skin_type": "n/a", "volume_ml": 300,
     "cruelty_free": True, "complements": ["b8"]},
    {"sku": "b6", "label": "Body Lotion", "mrp": 349, "price": 289, "skin_type": "dry", "volume_ml": 200,
     "cruelty_free": True, "complements": []},
    {"sku": "b7", "label": "Kohl Kajal", "mrp": 199, "price": 159, "skin_type": "n/a", "volume_ml": 3,
     "cruelty_free": False, "complements": []},
    {"sku": "b8", "label": "Onion Hair Oil", "mrp": 299, "price": 249, "skin_type": "n/a", "volume_ml": 200,
     "cruelty_free": True, "complements": ["b5"]},
]


def _normalize(raw: dict) -> Product:
    return normalize_raw_product({
        "product_id": raw["sku"], "title": raw["label"], "subcategory": "personal_care",
        "description": f"{raw['label']}, {raw['volume_ml']}ml.",
        "brand": MERCHANT_NAME, "price": raw["price"], "mrp": raw["mrp"],
        "discount": round((raw["mrp"] - raw["price"]) / raw["mrp"] * 100, 1),
        "availability": True,
        "attributes": {"skin_type": raw["skin_type"], "volume_ml": raw["volume_ml"], "cruelty_free": raw["cruelty_free"]},
        "delivery": {"eta_min": 180, "fee": 0.0}, "location": "Pune, IN",
        "complement_ids": raw["complements"],
    }, merchant_id=MERCHANT_ID, merchant_name=MERCHANT_NAME, category="beauty")


class BeautyAdapter(MerchantAdapter):
    def __init__(self):
        self.merchant = Merchant(merchant_id=MERCHANT_ID, name=MERCHANT_NAME, category="beauty",
                                  subcategory="personal_care", open=True, tier="mainstream", rating=4.4,
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
