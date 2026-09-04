"""
CartService: create/add/modify/remove/get/revalidate a Cart (spec section
11). In-memory (a cart is pre-checkout, ephemeral, session-scoped state -
same tradeoff the pre-refactor SESSIONS dict already made; a production
build would move this to Redis/a DB keyed by authenticated session).

Enforces the MVP multi-merchant checkout policy (spec section 12): a cart
is pinned to one merchant at creation, and `add_item` refuses an item from
any other merchant (CartMerchantMismatchError) - "preferred MVP: one
merchant per cart/order/payment", not a fake universal checkout.

`revalidate()` is the price/inventory safety pipeline (spec section 10):
it re-fetches every item's AUTHORITATIVE current product from the owning
merchant adapter (never trusting whatever price/availability was cached on
the cart item from an earlier moment) and recomputes totals server-side.
This always runs, inside OrderService.checkout, before authorization/policy
- a client can never make its own supplied amount become the checkout total.
"""
from __future__ import annotations

from typing import Optional

from ...core.errors import CartMerchantMismatchError, ProductUnavailableError
from ...domain.cart.models import Cart, CartItem, CartStatus
from ..catalog import gateway


class CartService:
    def __init__(self):
        self._carts: dict = {}

    def create_cart(self, session_id: str, merchant_id: str) -> Cart:
        cart = Cart.create(session_id, merchant_id)
        self._carts[cart.cart_id] = cart
        return cart

    def get_cart(self, cart_id: str) -> Optional[Cart]:
        return self._carts.get(cart_id)

    def add_item(self, cart_id: str, product_id: str, merchant_id: str, quantity: int = 1,
                 variant_id: Optional[str] = None, role: str = "primary") -> Cart:
        cart = self._require_cart(cart_id)
        if merchant_id != cart.merchant_id:
            raise CartMerchantMismatchError(
                f"Cart '{cart_id}' is scoped to merchant '{cart.merchant_id}'; cannot add an item from "
                f"'{merchant_id}'. Aalok's MVP checkout policy is one merchant per cart - see "
                f"ARCHITECTURE.md section 12."
            )
        product = gateway.get_product(product_id, merchant_id)
        if product is None:
            raise ProductUnavailableError(f"Unknown product_id '{product_id}' for merchant '{merchant_id}'.")
        cart.items.append(CartItem(merchant_id=merchant_id, product_id=product_id, name=product.title,
                                    unit_price=product.price, quantity=quantity, variant_id=variant_id, role=role))
        cart.version += 1
        cart.recalculate_totals()
        return cart

    def modify_item(self, cart_id: str, product_id: str, quantity: int) -> Cart:
        cart = self._require_cart(cart_id)
        item = next((i for i in cart.items if i.product_id == product_id), None)
        if item is None:
            raise ProductUnavailableError(f"Item '{product_id}' is not in cart '{cart_id}'.")
        if quantity <= 0:
            cart.items.remove(item)
        else:
            item.quantity = quantity
        cart.version += 1
        cart.recalculate_totals()
        return cart

    def remove_item(self, cart_id: str, product_id: str) -> Cart:
        return self.modify_item(cart_id, product_id, quantity=0)

    def revalidate(self, cart: Cart) -> dict:
        """Re-fetches every item's authoritative product, updates prices/
        recomputes totals in place, and returns the per-item facts the
        Policy Engine needs: {availability_by_item, attributes_by_item,
        merchant_id_by_item}, keyed by product_id."""
        availability_by_item, attributes_by_item, merchant_id_by_item, delivery_by_item = {}, {}, {}, {}
        for item in cart.items:
            product = gateway.get_product(item.product_id, item.merchant_id)
            if product is None:
                availability_by_item[item.product_id] = False
                continue
            item.unit_price = product.price  # authoritative - never trust a stale cached price
            item.name = product.title
            availability_by_item[item.product_id] = product.availability
            attributes_by_item[item.product_id] = product.attributes
            merchant_id_by_item[item.product_id] = product.merchant_id
            delivery_by_item[item.product_id] = product.delivery.get("eta_min", 0)
        cart.recalculate_totals()
        return {"availability_by_item": availability_by_item, "attributes_by_item": attributes_by_item,
                "merchant_id_by_item": merchant_id_by_item, "delivery_by_item": delivery_by_item}

    def _require_cart(self, cart_id: str) -> Cart:
        cart = self._carts.get(cart_id)
        if cart is None:
            raise ProductUnavailableError(f"Unknown cart_id '{cart_id}'.")
        return cart


# Module-level singleton - mirrors the simplicity of the pre-refactor
# in-memory SESSIONS dict; services/session/store.py wraps the session-level
# bookkeeping on top of this.
cart_service = CartService()
