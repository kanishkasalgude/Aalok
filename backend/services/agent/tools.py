"""
THE STRICT AI TOOL INTERFACE (spec section 7). This module is the entire
surface the LLM is ever handed - every function here is safe to let an LLM
call with arbitrary/malformed/fabricated arguments: nothing raises on bad
input, everything returns a plain dict (an `{"error": ...}` shape on
failure) so a tool-calling loop degrades gracefully instead of crashing the
request.

STRUCTURAL BOUNDARY: this module's public namespace contains ONLY
commerce-domain read/propose operations. It does not import, reference, or
expose anything that can move money or bypass a policy decision - no
Razorpay client, no payment provider, no webhook secret, no database
credentials, no policy-override path. `create_cart`/`modify_cart` only ever
PROPOSE a cart; nothing in this file can call OrderService.checkout() or
reach a PaymentProvider. See tests/test_ai_tool_boundary.py, which asserts
this by inspecting ALL_TOOL_DECLARATIONS and this module's globals.
"""
from __future__ import annotations

from typing import Optional

from ...core.errors import CartMerchantMismatchError, MerchantAdapterError, ProductUnavailableError
from ..cart.service import cart_service
from ..catalog import gateway
from ..order.service import order_service
from ..recommendation import service as recommendation_service


def search_catalog(query: str = "", category: Optional[str] = None, max_price: Optional[float] = None,
                    min_price: Optional[float] = None, location: Optional[str] = None,
                    filters: Optional[dict] = None, merchant_ids: Optional[list] = None) -> dict:
    try:
        products = gateway.search_catalog(query=query or "", category=category, max_price=max_price,
                                           min_price=min_price, location=location, filters=filters,
                                           merchant_ids=merchant_ids)
        return {"results": [p.to_dict() for p in products]}
    except Exception as e:  # a malformed filter, etc - never crash the agent loop
        return {"error": str(e), "results": []}


def get_product(product_id: str, merchant_id: Optional[str] = None) -> dict:
    if not product_id:
        return {"error": "product_id is required."}
    product = gateway.get_product(product_id, merchant_id)
    if product is None:
        return {"error": f"Unknown product_id '{product_id}'."}
    return product.to_dict()


def compare_products(product_ids: list) -> dict:
    if not isinstance(product_ids, list) or not product_ids:
        return {"error": "product_ids must be a non-empty list.", "results": []}
    results = []
    for pid in product_ids:
        product = gateway.get_product(pid)
        if product:
            results.append(product.to_dict())
    return {"results": results}


def check_availability(product_id: str, merchant_id: Optional[str] = None) -> dict:
    product = gateway.get_product(product_id, merchant_id)
    if product is None:
        return {"error": f"Unknown product_id '{product_id}'.", "available": False}
    return {"available": product.availability}


def get_delivery_estimate(product_id: str, merchant_id: Optional[str] = None) -> dict:
    product = gateway.get_product(product_id, merchant_id)
    if product is None:
        return {"error": f"Unknown product_id '{product_id}'."}
    return product.delivery


def find_complements(product_id: str, merchant_id: Optional[str] = None) -> dict:
    return {"results": [p.to_dict() for p in recommendation_service.find_complements(product_id, merchant_id)]}


def find_substitutes(product_id: str, merchant_id: Optional[str] = None) -> dict:
    return {"results": [p.to_dict() for p in recommendation_service.find_substitutes(product_id, merchant_id)]}


def create_cart(session_id: str, merchant_id: str, items: Optional[list] = None) -> dict:
    if not merchant_id:
        return {"error": "merchant_id is required to create a cart (MVP is one-merchant-per-cart)."}
    try:
        cart = cart_service.create_cart(session_id, merchant_id)
        for item in (items or []):
            cart_service.add_item(cart.cart_id, item["product_id"], merchant_id,
                                   quantity=item.get("quantity", 1), role=item.get("role", "primary"))
        return cart.to_dict()
    except (ProductUnavailableError, CartMerchantMismatchError, MerchantAdapterError, KeyError) as e:
        return {"error": str(e)}


def modify_cart(cart_id: str, product_id: str, merchant_id: str, quantity: int = 1, role: str = "primary") -> dict:
    try:
        cart = cart_service.get_cart(cart_id)
        if cart is None:
            return {"error": f"Unknown cart_id '{cart_id}'."}
        existing = next((i for i in cart.items if i.product_id == product_id), None)
        if existing is None and quantity > 0:
            cart = cart_service.add_item(cart_id, product_id, merchant_id, quantity=quantity, role=role)
        else:
            cart = cart_service.modify_item(cart_id, product_id, quantity)
        return cart.to_dict()
    except (ProductUnavailableError, CartMerchantMismatchError, MerchantAdapterError) as e:
        return {"error": str(e)}


def get_cart(cart_id: str) -> dict:
    cart = cart_service.get_cart(cart_id)
    if cart is None:
        return {"error": f"Unknown cart_id '{cart_id}'."}
    return cart.to_dict()


def get_order_status(internal_order_id: str) -> dict:
    order = order_service.get_order(internal_order_id)
    if order is None:
        return {"error": f"Unknown internal_order_id '{internal_order_id}'."}
    return order.to_dict()


# --- Gemini function-calling declarations for the tools above ---------------
ALL_TOOL_DECLARATIONS = [
    {"name": "search_catalog", "description": "Search every connected merchant's catalog for products matching a free-text query plus optional filters.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"}, "category": {"type": "string"}, "max_price": {"type": "number"},
         "min_price": {"type": "number"}}, "required": []}},
    {"name": "get_product", "description": "Get one product's current authoritative details by id.",
     "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}, "merchant_id": {"type": "string"}},
                     "required": ["product_id"]}},
    {"name": "compare_products", "description": "Compare several products side by side by id.",
     "parameters": {"type": "object", "properties": {"product_ids": {"type": "array", "items": {"type": "string"}}},
                     "required": ["product_ids"]}},
    {"name": "check_availability", "description": "Check whether a product is currently available.",
     "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}, "merchant_id": {"type": "string"}},
                     "required": ["product_id"]}},
    {"name": "get_delivery_estimate", "description": "Get the delivery time/fee estimate for a product.",
     "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}, "merchant_id": {"type": "string"}},
                     "required": ["product_id"]}},
    {"name": "find_complements", "description": "Find real, catalog-declared complementary add-ons for a product.",
     "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}, "merchant_id": {"type": "string"}},
                     "required": ["product_id"]}},
    {"name": "find_substitutes", "description": "Find comparable substitute products from other merchants.",
     "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}, "merchant_id": {"type": "string"}},
                     "required": ["product_id"]}},
    {"name": "create_cart", "description": "Propose a new cart for one merchant, optionally with initial items. This only proposes a cart - it never charges anything.",
     "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}, "merchant_id": {"type": "string"}},
                     "required": ["session_id", "merchant_id"]}},
    {"name": "modify_cart", "description": "Add, change the quantity of, or remove (quantity=0) an item in a proposed cart.",
     "parameters": {"type": "object", "properties": {
         "cart_id": {"type": "string"}, "product_id": {"type": "string"}, "merchant_id": {"type": "string"},
         "quantity": {"type": "integer"}}, "required": ["cart_id", "product_id", "merchant_id"]}},
    {"name": "get_cart", "description": "Get a proposed cart's current contents and totals.",
     "parameters": {"type": "object", "properties": {"cart_id": {"type": "string"}}, "required": ["cart_id"]}},
    {"name": "get_order_status", "description": "Get the status of a previously created order.",
     "parameters": {"type": "object", "properties": {"internal_order_id": {"type": "string"}}, "required": ["internal_order_id"]}},
]

NAME_TO_FUNC = {
    "search_catalog": search_catalog, "get_product": get_product, "compare_products": compare_products,
    "check_availability": check_availability, "get_delivery_estimate": get_delivery_estimate,
    "find_complements": find_complements, "find_substitutes": find_substitutes, "create_cart": create_cart,
    "modify_cart": modify_cart, "get_cart": get_cart, "get_order_status": get_order_status,
}

# Names that must NEVER appear in this module - the structural boundary
# test (tests/test_ai_tool_boundary.py) asserts every one of these is
# absent from both ALL_TOOL_DECLARATIONS and NAME_TO_FUNC.
FORBIDDEN_TOOL_NAMES = {
    "create_razorpay_order", "capture_payment", "attempt_payment", "refund_payment", "create_refund",
    "verify_payment", "verify_webhook_signature", "handle_webhook", "override_policy", "access_webhook_secret",
    "access_database",
}
