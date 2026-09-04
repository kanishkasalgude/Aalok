"""
CartService tests (services/cart/service.py): add/remove/quantity, total
calculation, expiry, and the MVP one-merchant-per-cart policy (spec section
12) - a cart pinned to one merchant must refuse an item from another.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from backend.core.errors import CartMerchantMismatchError, ProductUnavailableError
from backend.domain.cart.models import CartStatus
from backend.services.cart.service import CartService


def _service():
    return CartService()


def test_create_cart_starts_empty():
    cart = _service().create_cart("sess-1", "r5")
    assert cart.items == []
    assert cart.total == 0.0
    assert cart.status == CartStatus.ACTIVE
    assert cart.version == 1


def test_add_item_computes_totals():
    svc = _service()
    cart = svc.create_cart("sess-2", "r5")
    svc.add_item(cart.cart_id, "d501", "r5", role="primary")  # Masala Dosa, 149
    svc.add_item(cart.cart_id, "d504", "r5", quantity=2, role="addon")  # Filter Coffee, 69 x2
    assert cart.subtotal == 149 + 69 * 2
    assert cart.total == cart.subtotal
    assert cart.version == 3  # create doesn't bump version; each add_item does


def test_modify_item_quantity_updates_total():
    svc = _service()
    cart = svc.create_cart("sess-3", "r5")
    svc.add_item(cart.cart_id, "d501", "r5", role="primary")
    svc.modify_item(cart.cart_id, "d501", quantity=3)
    assert cart.items[0].quantity == 3
    assert cart.total == 149 * 3


def test_modify_item_to_zero_removes_it():
    svc = _service()
    cart = svc.create_cart("sess-4", "r5")
    svc.add_item(cart.cart_id, "d501", "r5", role="primary")
    svc.modify_item(cart.cart_id, "d501", quantity=0)
    assert cart.items == []
    assert cart.total == 0.0


def test_remove_item():
    svc = _service()
    cart = svc.create_cart("sess-5", "r5")
    svc.add_item(cart.cart_id, "d501", "r5", role="primary")
    svc.remove_item(cart.cart_id, "d501")
    assert cart.items == []


def test_add_item_from_a_different_merchant_is_rejected():
    """The MVP multi-merchant checkout policy: one merchant per cart."""
    svc = _service()
    cart = svc.create_cart("sess-6", "r5")
    svc.add_item(cart.cart_id, "d501", "r5", role="primary")
    with pytest.raises(CartMerchantMismatchError):
        svc.add_item(cart.cart_id, "j1", "jewellery-aurelia", role="addon")
    assert len(cart.items) == 1, "the rejected cross-merchant item must not have been added"


def test_add_unknown_product_raises():
    svc = _service()
    cart = svc.create_cart("sess-7", "r5")
    with pytest.raises(ProductUnavailableError):
        svc.add_item(cart.cart_id, "not-a-real-dish", "r5", role="primary")


def test_cart_expiry():
    svc = _service()
    cart = svc.create_cart("sess-8", "r5")
    assert not cart.is_expired()
    cart.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert cart.is_expired()


def test_revalidate_refreshes_authoritative_price_and_returns_facts():
    svc = _service()
    cart = svc.create_cart("sess-9", "r5")
    svc.add_item(cart.cart_id, "d501", "r5", role="primary")
    cart.items[0].unit_price = 1.0  # simulate a stale/tampered cached price
    facts = svc.revalidate(cart)
    assert cart.items[0].unit_price == 149  # re-fetched from the authoritative catalog
    assert facts["availability_by_item"]["d501"] is True
    assert "dietary_tags" in facts["attributes_by_item"]["d501"]
    assert facts["merchant_id_by_item"]["d501"] == "r5"


def test_idempotency_key_changes_with_version():
    svc = _service()
    cart = svc.create_cart("sess-10", "r5")
    key1 = cart.idempotency_key()
    svc.add_item(cart.cart_id, "d501", "r5", role="primary")
    key2 = cart.idempotency_key()
    assert key1 != key2, "a cart mutation must change the idempotency key (new logical checkout)"
