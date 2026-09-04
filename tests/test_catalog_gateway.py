"""
AI Commerce Discovery Gateway tests (services/catalog/gateway.py): federated
multi-merchant search, normalization into the Unified Commerce Schema,
category/price filters, merchant-failure isolation, and dedupe.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.core.errors import MerchantAdapterError
from backend.integrations.merchants.registry import all_adapters, get_adapter
from backend.services.catalog import gateway


def test_search_spans_multiple_categories():
    products = gateway.search_catalog(query="", top_k=50)
    categories = {p.category for p in products}
    assert len(categories) >= 5, "federated search must span multiple merchant categories"


def test_search_scoped_to_one_category():
    products = gateway.search_catalog(query="", category="jewellery", top_k=20)
    assert len(products) > 0
    assert all(p.category == "jewellery" for p in products)


def test_search_scoped_to_multiple_merchants_stays_multi_merchant():
    products = gateway.search_catalog(query="", category="grocery", top_k=50)
    merchants = {p.merchant_id for p in products}
    assert len(merchants) >= 2, "grocery spans FreshKart and ZipMart - both should be represented"


def test_price_filters_are_hard_constraints():
    products = gateway.search_catalog(query="", category="fashion", max_price=800, top_k=50)
    assert len(products) > 0
    assert all(p.price <= 800 for p in products)


def test_normalization_produces_unified_schema_fields():
    products = gateway.search_catalog(query="", category="electronics", top_k=5)
    for p in products:
        assert p.product_id and p.merchant_id and p.merchant_name and p.category
        assert isinstance(p.attributes, dict)
        assert isinstance(p.relationships.complement_ids, list)


def test_unavailable_products_are_filtered_out():
    products = gateway.search_catalog(query="", category="fashion", top_k=50)
    assert all(p.availability for p in products)
    # Casual Sneakers (f9) is seeded out-of-stock - must never appear
    assert all(p.product_id != "f9" for p in products)


def test_one_merchant_failing_does_not_break_the_others(monkeypatch):
    grocery_adapters = [a for a in all_adapters() if a.merchant.category == "grocery"]
    assert len(grocery_adapters) >= 2
    broken = grocery_adapters[0]

    def _boom(*args, **kwargs):
        raise MerchantAdapterError("simulated merchant outage")

    monkeypatch.setattr(broken, "search", _boom)
    products = gateway.search_catalog(query="", category="grocery", top_k=50)
    assert len(products) > 0, "the surviving grocery merchant's products must still come back"
    assert all(p.merchant_id != broken.merchant.merchant_id for p in products)


def test_dedupe_by_product_id():
    products = gateway.search_catalog(query="", top_k=200)
    ids = [p.product_id for p in products]
    assert len(ids) == len(set(ids))


def test_get_product_returns_authoritative_current_state():
    product = gateway.get_product("j1", "jewellery-aurelia")
    assert product is not None
    assert product.title == "Gold Stud Earrings"


def test_get_product_unknown_id_returns_none():
    assert gateway.get_product("not-a-real-product-id") is None


def test_get_complements_are_grounded_in_catalog_data():
    complements = gateway.get_complements("d101", "r1")  # Grilled Chicken Breast Bowl
    assert len(complements) > 0
    assert all(c.availability for c in complements)


def test_get_substitutes_come_from_a_different_merchant():
    product = get_adapter("jewellery-aurelia").get_product("j2")  # Silver Chain
    substitutes = gateway.get_substitutes("j2", "jewellery-aurelia")
    for s in substitutes:
        assert s.merchant_id != product.merchant_id
        assert s.subcategory == product.subcategory
