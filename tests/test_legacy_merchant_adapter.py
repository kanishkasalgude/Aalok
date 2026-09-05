"""
Merchant realism (Track 01 Phase 6): RetroTech Traders is a deliberately
messy second electronics merchant - different field names, string-formatted
prices with an embedded currency marker and thousands commas, "Y"/"N"-style
inconsistency, variant-level inventory instead of one stock flag, and
optional fields genuinely absent on some rows. These tests pin that the
adapter boundary resolves all of this into the same Unified Commerce Schema
every other (clean) adapter also produces - nothing downstream ever has to
know RetroTech's feed looks any different.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.integrations.merchants.legacy_gadgets_adapter import LegacyGadgetsAdapter
from backend.integrations.merchants.registry import get_adapter


def test_legacy_adapter_is_registered_and_reachable_by_merchant_id():
    adapter = get_adapter("electronics-retrotech")
    assert adapter is not None
    assert adapter.merchant.name == "RetroTech Traders"
    assert adapter.merchant.category == "electronics"


def test_messy_price_string_is_parsed_to_a_correct_float():
    adapter = LegacyGadgetsAdapter()
    product = adapter.get_product("RT-100")
    assert product.price == 249.0
    assert product.mrp == 399.0
    assert product.discount > 0


def test_missing_optional_fields_default_safely_not_crash():
    adapter = LegacyGadgetsAdapter()
    product = adapter.get_product("RT-101")  # no MRP, no Description in the raw feed
    assert product.mrp is None
    assert product.discount == 0.0
    assert product.description == ""


def test_availability_is_derived_from_variant_level_stock_not_a_top_level_flag():
    adapter = LegacyGadgetsAdapter()
    in_stock = adapter.get_product("RT-100")   # black:12, white:4
    out_of_stock = adapter.get_product("RT-101")  # default:0
    all_variants_zero = adapter.get_product("RT-104")  # white:0, black:0
    assert in_stock.availability is True
    assert out_of_stock.availability is False
    assert all_variants_zero.availability is False


def test_normalized_product_has_the_same_shape_as_every_other_adapter():
    adapter = LegacyGadgetsAdapter()
    product = adapter.get_product("RT-102")
    # Same Unified Commerce Schema fields as a clean adapter's product -
    # the whole point of the normalizer boundary.
    assert product.product_id == "RT-102"
    assert product.merchant_id == "electronics-retrotech"
    assert isinstance(product.variants, list)
    assert product.variants[0]["stock"] >= 0
    assert "variant_stock" in product.attributes


def test_legacy_merchant_is_searchable_through_the_federated_gateway():
    from backend.services.catalog import gateway
    results = gateway.search_catalog(query="", category="electronics", max_price=1000)
    retrotech_ids = {p.product_id for p in results if p.merchant_id == "electronics-retrotech"}
    assert "RT-100" in retrotech_ids or "RT-102" in retrotech_ids or "RT-103" in retrotech_ids
