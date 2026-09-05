"""
The list of every connected merchant adapter in this prototype - what
services/catalog/gateway.py fans out to. Adding a new synthetic (or, later,
real) merchant means writing one adapter module and registering it here;
nothing else in the codebase needs to change (see ARCHITECTURE.md "How to
add a real merchant adapter").
"""
from __future__ import annotations

from typing import Optional

from .base import MerchantAdapter
from .beauty_adapter import BeautyAdapter
from .electronics_adapter import ElectronicsAdapter
from .entertainment_adapter import EntertainmentAdapter
from .fashion_adapter import FashionAdapter
from .food_adapter import all_food_adapters
from .grocery_adapter import GroceryAdapter
from .jewellery_adapter import JewelleryAdapter
from .legacy_gadgets_adapter import LegacyGadgetsAdapter
from .quickcommerce_adapter import QuickCommerceAdapter
from .services_adapter import ServicesAdapter

_REGISTRY: list = None  # lazily built - food adapters read catalog data at import time


def _build_registry() -> list:
    adapters: list = list(all_food_adapters())
    adapters += [
        GroceryAdapter(), FashionAdapter(), BeautyAdapter(), ElectronicsAdapter(),
        JewelleryAdapter(), EntertainmentAdapter(), ServicesAdapter(), QuickCommerceAdapter(),
        LegacyGadgetsAdapter(),
    ]
    return adapters


def all_adapters() -> list:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def get_adapter(merchant_id: str) -> Optional[MerchantAdapter]:
    return next((a for a in all_adapters() if a.merchant.merchant_id == merchant_id), None)


def adapters_for_category(category: Optional[str] = None) -> list:
    if category is None:
        return all_adapters()
    return [a for a in all_adapters() if a.merchant.category == category]


def list_merchants() -> list:
    return [a.merchant.to_dict() for a in all_adapters()]
