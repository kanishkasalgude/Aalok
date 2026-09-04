"""ConnectPlus - synthetic Vi-style telecom/services merchant (fictional)."""
from __future__ import annotations

from typing import Optional

from ...domain.catalog.capabilities import DEFAULT_MOCK_CAPABILITIES
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product, normalize_raw_product
from .base import MerchantAdapter

MERCHANT_ID = "services-connectplus"
MERCHANT_NAME = "ConnectPlus"

RAW_PRODUCTS = [
    {"plan_code": "p1", "plan_name": "Prepaid Basic", "mrp": 199, "price": 199, "validity_days": 28,
     "data_gb": 1.5, "talktime": "unlimited", "category": "prepaid", "complements": []},
    {"plan_code": "p2", "plan_name": "Prepaid Value", "mrp": 599, "price": 599, "validity_days": 84,
     "data_gb": 2, "talktime": "unlimited", "category": "prepaid", "complements": ["p6"]},
    {"plan_code": "p3", "plan_name": "Prepaid 5G Unlimited", "mrp": 999, "price": 999, "validity_days": 84,
     "data_gb": 3, "talktime": "unlimited", "category": "prepaid", "complements": ["p6"]},
    {"plan_code": "p4", "plan_name": "Home Broadband 40Mbps", "mrp": 799, "price": 799, "validity_days": 30,
     "data_gb": None, "talktime": "n/a", "category": "broadband", "complements": []},
    {"plan_code": "p5", "plan_name": "Home Broadband 100Mbps", "mrp": 1299, "price": 1299, "validity_days": 30,
     "data_gb": None, "talktime": "n/a", "category": "broadband", "complements": []},
    {"plan_code": "p6", "plan_name": "OTT Combo Add-on", "mrp": 149, "price": 129, "validity_days": 28,
     "data_gb": None, "talktime": "n/a", "category": "addon", "complements": ["p2"]},
    {"plan_code": "p7", "plan_name": "DTH Monthly Pack", "mrp": 350, "price": 320, "validity_days": 30,
     "data_gb": None, "talktime": "n/a", "category": "dth", "complements": []},
    {"plan_code": "p8", "plan_name": "International Roaming Pack", "mrp": 1999, "price": 1799, "validity_days": 10,
     "data_gb": 5, "talktime": "limited", "category": "addon", "complements": []},
]


def _normalize(raw: dict) -> Product:
    return normalize_raw_product({
        "product_id": raw["plan_code"], "title": raw["plan_name"], "subcategory": raw["category"],
        "description": f"{raw['plan_name']} - {raw['validity_days']} day validity.",
        "brand": MERCHANT_NAME, "price": raw["price"], "mrp": raw["mrp"], "discount": 0.0,
        "availability": True,
        "attributes": {"validity_days": raw["validity_days"], "data_gb": raw["data_gb"], "talktime": raw["talktime"]},
        "delivery": {"eta_min": 0, "fee": 0.0}, "location": "Pune, IN",  # instant activation, no physical delivery
        "complement_ids": raw["complements"],
    }, merchant_id=MERCHANT_ID, merchant_name=MERCHANT_NAME, category="services")


class ServicesAdapter(MerchantAdapter):
    def __init__(self):
        self.merchant = Merchant(merchant_id=MERCHANT_ID, name=MERCHANT_NAME, category="services",
                                  subcategory="telecom", open=True, tier="mainstream", rating=3.9,
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
        raw = next((r for r in RAW_PRODUCTS if r["plan_code"] == product_id), None)
        return _normalize(raw) if raw else None
