"""New generalized cart CRUD surface (spec section 24)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ...core.errors import CartMerchantMismatchError, ProductUnavailableError
from ...domain.audit import events
from ...repositories import audit_repo
from ...services.cart.service import cart_service

router = APIRouter()


class CreateCartRequest(BaseModel):
    session_id: str
    merchant_id: str


class AddItemRequest(BaseModel):
    product_id: str
    merchant_id: str
    quantity: int = 1
    variant_id: Optional[str] = None
    role: str = "primary"


class ModifyItemRequest(BaseModel):
    quantity: int


@router.post("/api/cart")
def create_cart(req: CreateCartRequest):
    cart = cart_service.create_cart(req.session_id, req.merchant_id)
    audit_repo.log_event(req.session_id, events.CART_CREATED, "success", {"cart_id": cart.cart_id, "merchant_id": req.merchant_id})
    return cart.to_dict()


@router.get("/api/cart/{cart_id}")
def get_cart(cart_id: str):
    cart = cart_service.get_cart(cart_id)
    if cart is None:
        return {"error": f"Unknown cart_id '{cart_id}'."}
    return cart.to_dict()


@router.post("/api/cart/{cart_id}/items")
def add_item(cart_id: str, req: AddItemRequest):
    try:
        cart = cart_service.add_item(cart_id, req.product_id, req.merchant_id, quantity=req.quantity,
                                      variant_id=req.variant_id, role=req.role)
    except (CartMerchantMismatchError, ProductUnavailableError) as e:
        return {"error": str(e)}
    audit_repo.log_event(cart.session_id, events.CART_MODIFIED, "success", {"cart_id": cart_id, "added": req.product_id})
    return cart.to_dict()


@router.patch("/api/cart/{cart_id}/items/{item_id}")
def modify_item(cart_id: str, item_id: str, req: ModifyItemRequest):
    try:
        cart = cart_service.modify_item(cart_id, item_id, req.quantity)
    except ProductUnavailableError as e:
        return {"error": str(e)}
    audit_repo.log_event(cart.session_id, events.CART_MODIFIED, "success", {"cart_id": cart_id, "item_id": item_id, "quantity": req.quantity})
    return cart.to_dict()


@router.delete("/api/cart/{cart_id}/items/{item_id}")
def remove_item(cart_id: str, item_id: str):
    try:
        cart = cart_service.remove_item(cart_id, item_id)
    except ProductUnavailableError as e:
        return {"error": str(e)}
    audit_repo.log_event(cart.session_id, events.CART_MODIFIED, "success", {"cart_id": cart_id, "removed": item_id})
    return cart.to_dict()
