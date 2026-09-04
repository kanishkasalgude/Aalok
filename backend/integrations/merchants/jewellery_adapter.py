"""Aurelia - synthetic BlueStone-style jewellery merchant (fictional)."""
from __future__ import annotations

from typing import Optional

from ...domain.catalog.capabilities import DEFAULT_MOCK_CAPABILITIES
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product, normalize_raw_product
from .base import MerchantAdapter

MERCHANT_ID = "jewellery-aurelia"
MERCHANT_NAME = "Aurelia"

RAW_PRODUCTS = [
    {"design_code": "j1", "title": "Gold Stud Earrings", "mrp": 18999, "price": 17499, "metal": "gold",
     "purity": "18k", "gemstone": None, "weight_g": 2.1, "certification": "BIS Hallmark", "complements": []},
    {"design_code": "j2", "title": "Silver Chain", "mrp": 2999, "price": 2599, "metal": "silver",
     "purity": "925", "gemstone": None, "weight_g": 8.5, "certification": "925 Silver Certified", "complements": ["j3"]},
    {"design_code": "j3", "title": "Diamond Pendant", "mrp": 24999, "price": 22999, "metal": "gold",
     "purity": "18k", "gemstone": "diamond", "weight_g": 1.8, "certification": "IGI Certified", "complements": ["j2"]},
    {"design_code": "j4", "title": "Classic Gold Ring", "mrp": 15999, "price": 14499, "metal": "gold",
     "purity": "22k", "gemstone": None, "weight_g": 3.2, "certification": "BIS Hallmark", "complements": []},
    {"design_code": "j5", "title": "Silver Bracelet", "mrp": 3499, "price": 2999, "metal": "silver",
     "purity": "925", "gemstone": None, "weight_g": 12.0, "certification": "925 Silver Certified", "complements": []},
    {"design_code": "j6", "title": "Pearl Necklace", "mrp": 8999, "price": 7999, "metal": "gold",
     "purity": "18k", "gemstone": "pearl", "weight_g": 5.5, "certification": "IGI Certified", "complements": []},
    {"design_code": "j7", "title": "Gold Bangles (Pair)", "mrp": 42999, "price": 39999, "metal": "gold",
     "purity": "22k", "gemstone": None, "weight_g": 14.0, "certification": "BIS Hallmark", "complements": []},
    {"design_code": "j8", "title": "Silver Anklet", "mrp": 1999, "price": 1699, "metal": "silver",
     "purity": "925", "gemstone": None, "weight_g": 6.0, "certification": "925 Silver Certified", "complements": []},
]


def _normalize(raw: dict) -> Product:
    return normalize_raw_product({
        "product_id": raw["design_code"], "title": raw["title"], "subcategory": raw["metal"],
        "description": f"{raw['title']}, {raw['purity']} {raw['metal']}, {raw['weight_g']}g.",
        "brand": MERCHANT_NAME, "price": raw["price"], "mrp": raw["mrp"],
        "discount": round((raw["mrp"] - raw["price"]) / raw["mrp"] * 100, 1),
        "availability": True,
        "attributes": {"metal": raw["metal"], "purity": raw["purity"], "gemstone": raw["gemstone"],
                        "weight_g": raw["weight_g"], "certification": raw["certification"]},
        "policies": {"returnable": True, "certification_included": True},
        "delivery": {"eta_min": 4320, "fee": 0.0}, "location": "Pune, IN",
        "complement_ids": raw["complements"],
    }, merchant_id=MERCHANT_ID, merchant_name=MERCHANT_NAME, category="jewellery")


class JewelleryAdapter(MerchantAdapter):
    def __init__(self):
        self.merchant = Merchant(merchant_id=MERCHANT_ID, name=MERCHANT_NAME, category="jewellery",
                                  subcategory="fine_jewellery", open=True, tier="premium", rating=4.5,
                                  capabilities=DEFAULT_MOCK_CAPABILITIES)

    def search(self, query: str = "", filters: Optional[dict] = None) -> list:
        filters = filters or {}
        out = []
        for raw in RAW_PRODUCTS:
            if filters.get("max_price") is not None and raw["price"] > filters["max_price"]:
                continue
            if filters.get("min_price") is not None and raw["price"] < filters["min_price"]:
                continue
            metal = (filters.get("required_attributes") or {}).get("metal")
            if metal and metal != raw["metal"]:
                continue
            out.append(_normalize(raw))
        return out

    def get_product(self, product_id: str) -> Optional[Product]:
        raw = next((r for r in RAW_PRODUCTS if r["design_code"] == product_id), None)
        return _normalize(raw) if raw else None
