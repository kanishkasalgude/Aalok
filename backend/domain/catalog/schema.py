"""
The Unified Commerce Schema (spec section 4). One canonical internal
product representation so AI tools/ranking/cart never need to understand
any individual merchant's proprietary response shape - that's the whole
point of the merchant-adapter -> normalizer -> Product pipeline
(integrations/merchants/*.py's `_normalize()` methods are the normalizer).

Category-specific facts (dietary_info, size, color, material, tech_specs,
compatibility, ...) live inside `attributes`, never as new top-level fields
- this is what lets one schema cover food/grocery/fashion/beauty/
electronics/jewellery/entertainment/services without N incompatible models.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ProductRelationships:
    complement_ids: list = field(default_factory=list)   # grounds upsells - real catalog data, never LLM-invented
    substitute_ids: list = field(default_factory=list)    # same subcategory, different merchant, similar price band

    def to_dict(self) -> dict:
        return {"complement_ids": self.complement_ids, "substitute_ids": self.substitute_ids}


@dataclass
class Product:
    product_id: str
    merchant_id: str
    merchant_name: str
    category: str
    subcategory: str
    title: str
    description: str
    brand: str
    price: float
    currency: str = "INR"
    mrp: Optional[float] = None
    discount: float = 0.0
    availability: bool = True
    variants: list = field(default_factory=list)          # e.g. [{"variant_id","label","price_delta"}]
    attributes: dict = field(default_factory=dict)         # category-specific facts live here
    images: list = field(default_factory=list)
    delivery: dict = field(default_factory=dict)            # {"eta_min": int, "fee": float}
    location: str = ""
    offers: list = field(default_factory=list)
    relationships: ProductRelationships = field(default_factory=ProductRelationships)
    policies: dict = field(default_factory=dict)              # e.g. {"returnable": bool, "cancellable": bool}
    deep_link: str = ""
    ai_metadata: dict = field(default_factory=dict)             # short, user-safe reasoning hints - never chain-of-thought

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["relationships"] = self.relationships.to_dict()
        return d


def normalize_raw_product(raw: dict, *, merchant_id: str, merchant_name: str, category: str) -> Product:
    """Shared normalizer entry point: a merchant adapter's raw, merchant-
    shaped dict -> the Unified Commerce Schema. Adapters call this (or build
    a Product directly for simple cases) from their own `_normalize()` -
    kept here, not per-adapter, so every adapter produces a structurally
    consistent Product even though their raw field names differ."""
    return Product(
        product_id=raw["product_id"],
        merchant_id=merchant_id,
        merchant_name=merchant_name,
        category=category,
        subcategory=raw.get("subcategory", ""),
        title=raw["title"],
        description=raw.get("description", ""),
        brand=raw.get("brand", merchant_name),
        price=float(raw["price"]),
        currency=raw.get("currency", "INR"),
        mrp=raw.get("mrp"),
        discount=float(raw.get("discount", 0.0)),
        availability=bool(raw.get("availability", True)),
        variants=raw.get("variants", []),
        attributes=raw.get("attributes", {}),
        images=raw.get("images", []),
        delivery=raw.get("delivery", {}),
        location=raw.get("location", ""),
        offers=raw.get("offers", []),
        relationships=ProductRelationships(
            complement_ids=raw.get("complement_ids", []),
            substitute_ids=raw.get("substitute_ids", []),
        ),
        policies=raw.get("policies", {}),
        deep_link=raw.get("deep_link", ""),
        ai_metadata=raw.get("ai_metadata", {}),
    )
