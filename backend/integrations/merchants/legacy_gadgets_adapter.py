"""
RetroTech Traders - a second, DELIBERATELY MESSY electronics merchant
(Track 01 Phase 6: "the current merchant sources are synthetic
integration fixtures designed to exercise heterogeneous merchant data").

Every other adapter in this project ships clean, already-typed Python
dicts (see electronics_adapter.py's RAW_PRODUCTS for the contrast). This
one instead simulates the shape a real legacy inventory export actually
arrives in - a flat, loosely-typed feed with:

  - entirely different field names (SKU/ItemName, not model_code/name)
  - price formatted as a currency STRING ("Rs. 1,499"), not a number -
    the same class of parsing problem services/agent/currency.py fixes
    for user-typed budgets, faced here on the ingestion side instead
  - availability encoded as "Y"/"N", not a boolean
  - variant-level inventory (a colour -> quantity map) instead of one
    top-level in-stock flag - overall availability is DERIVED from it
  - optional fields (Description, MRP) genuinely missing on some rows,
    not just empty strings

_normalize() below is the adapter boundary doing its actual job: every
one of these quirks is resolved here, and nothing past this module ever
sees RetroTech's raw shape - normalize_raw_product() still produces the
exact same Unified Commerce Schema Product every other merchant does.
"""
from __future__ import annotations

import re
from typing import Optional

from ...domain.catalog.capabilities import DEFAULT_MOCK_CAPABILITIES
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product, normalize_raw_product
from .base import MerchantAdapter

MERCHANT_ID = "electronics-retrotech"
MERCHANT_NAME = "RetroTech Traders"

# A flat, CSV-export-shaped feed - deliberately inconsistent with every
# other adapter's raw schema, and even slightly inconsistent WITHIN
# itself (missing "MRP"/"Description" on some rows), the way a real
# legacy export dumped from someone else's inventory system would be.
RAW_PRODUCTS = [
    {"SKU": "RT-100", "ItemName": "Refurbished Wired Earphones", "Price": "Rs. 249",
     "MRP": "Rs. 399", "Description": "Classic 3.5mm wired earphones, refurbished and tested.",
     "VariantStock": {"black": 12, "white": 4}, "Warranty": "3 months"},
    {"SKU": "RT-101", "ItemName": "USB 2.0 Flash Drive 32GB", "Price": "Rs. 349",
     "VariantStock": {"default": 0}, "Warranty": "1 year"},  # no MRP, no Description - both genuinely missing
    {"SKU": "RT-102", "ItemName": "Wired Optical Mouse", "Price": "Rs. 199", "MRP": "Rs. 299",
     "Description": "Basic 3-button optical mouse.", "VariantStock": {"black": 20, "grey": 9}, "Warranty": "6 months"},
    {"SKU": "RT-103", "ItemName": "HDMI Cable 1.5m", "Price": "Rs. 149",
     "VariantStock": {"default": 15}, "Warranty": "N/A"},
    {"SKU": "RT-104", "ItemName": "Universal Travel Adapter", "Price": "Rs. 449", "MRP": "Rs. 599",
     "Description": "All-in-one plug adapter for 150+ countries.", "VariantStock": {"white": 0, "black": 0},
     "Warranty": "1 year"},
]

_PRICE_RE = re.compile(r"([\d,]+(?:\.\d+)?)")


def _parse_legacy_price(raw_value: str) -> float:
    """RetroTech's export embeds the currency marker and thousands commas
    IN the price string ('Rs. 1,499') instead of shipping a bare number -
    the same "don't truncate at the comma" fix
    backend/services/agent/currency.py applies to user-typed budgets,
    needed here on the merchant-ingestion side instead."""
    match = _PRICE_RE.search(raw_value)
    if not match:
        raise ValueError(f"RetroTech feed: unparseable price '{raw_value}'")
    return float(match.group(1).replace(",", ""))


def _normalize(raw: dict) -> Product:
    price = _parse_legacy_price(raw["Price"])
    mrp_raw = raw.get("MRP")  # genuinely absent on some rows, not just falsy
    mrp = _parse_legacy_price(mrp_raw) if mrp_raw else None
    discount = round((mrp - price) / mrp * 100, 1) if mrp else 0.0

    variant_stock: dict = raw["VariantStock"]
    total_units = sum(variant_stock.values())
    variants = [{"variant_id": name, "label": name.title(), "stock": qty} for name, qty in variant_stock.items()]

    return normalize_raw_product({
        "product_id": raw["SKU"], "title": raw["ItemName"], "subcategory": "accessories",
        "description": raw.get("Description", ""),  # missing on some rows - normalize_raw_product defaults it
        "price": price, "mrp": mrp, "discount": discount,
        "availability": total_units > 0,
        "variants": variants,
        "attributes": {"variant_stock": variant_stock, "warranty": raw["Warranty"], "condition": "refurbished/legacy stock"},
        "delivery": {"eta_min": 4320, "fee": 49.0}, "location": "Delhi, IN",  # ~3 days, legacy/liquidation stock
    }, merchant_id=MERCHANT_ID, merchant_name=MERCHANT_NAME, category="electronics")


class LegacyGadgetsAdapter(MerchantAdapter):
    def __init__(self):
        self.merchant = Merchant(merchant_id=MERCHANT_ID, name=MERCHANT_NAME, category="electronics",
                                  subcategory="accessories", open=True, tier="budget", rating=3.7,
                                  capabilities=DEFAULT_MOCK_CAPABILITIES)

    def search(self, query: str = "", filters: Optional[dict] = None) -> list:
        filters = filters or {}
        out = []
        for raw in RAW_PRODUCTS:
            product = _normalize(raw)
            if filters.get("max_price") is not None and product.price > filters["max_price"]:
                continue
            if filters.get("min_price") is not None and product.price < filters["min_price"]:
                continue
            out.append(product)
        return out

    def get_product(self, product_id: str) -> Optional[Product]:
        raw = next((r for r in RAW_PRODUCTS if r["SKU"] == product_id), None)
        return _normalize(raw) if raw else None
