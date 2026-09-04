"""CircuitBay - synthetic consumer-electronics merchant (fictional)."""
from __future__ import annotations

from typing import Optional

from ...domain.catalog.capabilities import DEFAULT_MOCK_CAPABILITIES
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product, normalize_raw_product
from .base import MerchantAdapter

MERCHANT_ID = "electronics-circuitbay"
MERCHANT_NAME = "CircuitBay"

RAW_PRODUCTS = [
    {"model_code": "e1", "name": "Wireless Earbuds Pro", "mrp": 3999, "price": 2499,
     "tech_specs": {"battery_hours": 30, "bluetooth": "5.3", "anc": True}, "warranty_months": 12,
     "in_stock": True, "complements": ["e6"]},
    {"model_code": "e2", "name": "Portable Bluetooth Speaker", "mrp": 2999, "price": 1799,
     "tech_specs": {"battery_hours": 12, "waterproof": "IPX7"}, "warranty_months": 12,
     "in_stock": True, "complements": []},
    {"model_code": "e3", "name": "20000mAh Power Bank", "mrp": 1999, "price": 1299,
     "tech_specs": {"output": "22.5W fast charge", "ports": 2}, "warranty_months": 6,
     "in_stock": True, "complements": ["e7"]},
    {"model_code": "e4", "name": "Smartwatch Series X", "mrp": 5999, "price": 3999,
     "tech_specs": {"display": "AMOLED", "battery_days": 7, "compatibility": ["Android", "iOS"]},
     "warranty_months": 12, "in_stock": True, "complements": ["e5"]},
    {"model_code": "e5", "name": "Smartwatch Silicone Strap", "mrp": 599, "price": 399,
     "tech_specs": {"compatibility": ["Smartwatch Series X"]}, "warranty_months": 0,
     "in_stock": True, "complements": ["e4"]},
    {"model_code": "e6", "name": "Earbuds Charging Case", "mrp": 899, "price": 599,
     "tech_specs": {"compatibility": ["Wireless Earbuds Pro"]}, "warranty_months": 3,
     "in_stock": True, "complements": ["e1"]},
    {"model_code": "e7", "name": "65W USB-C GaN Charger", "mrp": 1499, "price": 999,
     "tech_specs": {"output": "65W", "ports": 2}, "warranty_months": 12,
     "in_stock": True, "complements": ["e3"]},
    {"model_code": "e8", "name": "Mechanical Keyboard TKL", "mrp": 4499, "price": 3299,
     "tech_specs": {"switch_type": "Red linear", "backlight": "RGB"}, "warranty_months": 12,
     "in_stock": False, "complements": []},
]


def _normalize(raw: dict) -> Product:
    return normalize_raw_product({
        "product_id": raw["model_code"], "title": raw["name"], "subcategory": "accessories",
        "description": f"{raw['name']} - {raw['warranty_months']} month warranty.",
        "brand": MERCHANT_NAME, "price": raw["price"], "mrp": raw["mrp"],
        "discount": round((raw["mrp"] - raw["price"]) / raw["mrp"] * 100, 1),
        "availability": raw["in_stock"],
        "attributes": {"tech_specs": raw["tech_specs"], "warranty_months": raw["warranty_months"]},
        "delivery": {"eta_min": 2880, "fee": 0.0}, "location": "Pune, IN",  # ~2 days
        "complement_ids": raw["complements"],
    }, merchant_id=MERCHANT_ID, merchant_name=MERCHANT_NAME, category="electronics")


class ElectronicsAdapter(MerchantAdapter):
    def __init__(self):
        self.merchant = Merchant(merchant_id=MERCHANT_ID, name=MERCHANT_NAME, category="electronics",
                                  subcategory="accessories", open=True, tier="mainstream", rating=4.3,
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
        raw = next((r for r in RAW_PRODUCTS if r["model_code"] == product_id), None)
        return _normalize(raw) if raw else None
