"""
The AI Commerce Discovery Gateway (spec section 6/10): the ONE service
through which the AI (or any external caller) searches every connected
merchant. The AI never calls a merchant adapter directly.

Pipeline: search_catalog() -> fan out to adapters in parallel -> raw
per-merchant results -> (already normalized to Product by each adapter,
see integrations/merchants/*) -> availability filter -> dedupe -> rank
(services/catalog/ranking.py) -> Unified Product results.

One merchant adapter failing (MerchantAdapterError) never breaks the
others - it's logged and skipped, exactly the graceful-degradation
behavior spec section 26 asks for.
"""
from __future__ import annotations

import concurrent.futures
from typing import Optional

from ...core.errors import MerchantAdapterError
from ...domain.catalog.schema import Product
from ...integrations.merchants.registry import all_adapters, adapters_for_category, get_adapter
from . import ranking

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)


def _search_one(adapter, query: str, filters: dict) -> list:
    try:
        return adapter.search(query, filters)
    except MerchantAdapterError:
        return []


def search_catalog(query: str = "", category: Optional[str] = None, max_price: Optional[float] = None,
                    min_price: Optional[float] = None, location: Optional[str] = None,
                    filters: Optional[dict] = None, merchant_ids: Optional[list] = None,
                    top_k: int = 12) -> list:
    """Returns list[Product]. `filters` may carry `required_attributes`,
    `max_delivery_time_min`. `merchant_ids` restricts the fan-out to
    specific merchants (used when a cart/checkout is already scoped to one
    merchant); `category` restricts by category instead."""
    filters = dict(filters or {})
    if max_price is not None:
        filters["max_price"] = max_price
    if min_price is not None:
        filters["min_price"] = min_price

    if merchant_ids:
        candidates = [a for a in all_adapters() if a.merchant.merchant_id in merchant_ids]
    else:
        candidates = adapters_for_category(category)

    futures = [_executor.submit(_search_one, a, query, filters) for a in candidates]
    raw_results: list = []
    for f in concurrent.futures.as_completed(futures):
        raw_results.extend(f.result())

    # availability + delivery-time hard filter (merchant-level price/attr
    # filters already applied inside each adapter's search())
    filtered = ranking.hard_filter(raw_results, max_delivery_min=filters.get("max_delivery_time_min"),
                                    only_available=True)

    # dedupe by product_id (defensive - synthetic merchants never actually
    # collide today, but a real federation could)
    seen = set()
    deduped = []
    for p in filtered:
        if p.product_id in seen:
            continue
        seen.add(p.product_id)
        deduped.append(p)

    return ranking.rank(deduped, query, top_k=top_k)


def get_product(product_id: str, merchant_id: Optional[str] = None) -> Optional[Product]:
    """Re-fetches a single product's AUTHORITATIVE current state. If
    merchant_id is known (the normal case - cart items always know their
    merchant), this is a single direct adapter call; otherwise it searches
    every adapter (used by AI tools that only got a bare product_id)."""
    if merchant_id:
        adapter = get_adapter(merchant_id)
        return adapter.get_product(product_id) if adapter else None
    for adapter in all_adapters():
        try:
            product = adapter.get_product(product_id)
        except MerchantAdapterError:
            continue
        if product:
            return product
    return None


def get_complements(product_id: str, merchant_id: Optional[str] = None) -> list:
    """Grounded in Product.relationships.complement_ids - real catalog
    data, never LLM-invented (spec section 21)."""
    product = get_product(product_id, merchant_id)
    if not product:
        return []
    out = []
    for cid in product.relationships.complement_ids:
        c = get_product(cid, product.merchant_id)
        if c and c.availability:
            out.append(c)
    return out


def get_substitutes(product_id: str, merchant_id: Optional[str] = None, price_tolerance_pct: float = 25.0) -> list:
    """Deterministic, never LLM-invented: same subcategory, a DIFFERENT
    merchant, price within +/- price_tolerance_pct of the original."""
    product = get_product(product_id, merchant_id)
    if not product:
        return []
    low = product.price * (1 - price_tolerance_pct / 100)
    high = product.price * (1 + price_tolerance_pct / 100)
    out = []
    for adapter in all_adapters():
        if adapter.merchant.merchant_id == product.merchant_id:
            continue
        try:
            candidates = adapter.search("", {})
        except MerchantAdapterError:
            continue
        for c in candidates:
            if (c.subcategory == product.subcategory and c.category == product.category
                    and c.availability and low <= c.price <= high):
                out.append(c)
    return out
