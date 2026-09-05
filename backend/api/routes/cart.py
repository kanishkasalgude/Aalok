"""
New generalized cart CRUD surface (spec section 24).

Every route requires a verified session (Track 01 Phase 2 -
services/session/auth.py::require_session) and, for lookup-by-id routes,
checks that the caller's verified session actually owns the cart being
read/mutated - a cart_id is just a uuid, not a secret, so ownership is
what actually prevents one buyer from reading or tampering with another
buyer's cart.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...core.errors import CartMerchantMismatchError, ProductUnavailableError
from ...domain.audit import events
from ...repositories import audit_repo
from ...services.cart.service import cart_service
from ...services.session.auth import VerifiedSession, check_body_session_id, check_ownership, require_session

router = APIRouter()


class CreateCartRequest(BaseModel):
    session_id: Optional[str] = None
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
def create_cart(req: CreateCartRequest, verified: VerifiedSession = Depends(require_session)):
    check_body_session_id(req.session_id, verified)
    cart = cart_service.create_cart(verified.session_id, req.merchant_id)
    audit_repo.log_event(verified.session_id, events.CART_CREATED, "success", {"cart_id": cart.cart_id, "merchant_id": req.merchant_id})
    return {**cart.to_dict(), **verified.as_response_fields()}


@router.get("/api/cart/{cart_id}")
def get_cart(cart_id: str, verified: VerifiedSession = Depends(require_session)):
    cart = cart_service.get_cart(cart_id)
    if cart is None:
        return {"error": f"Unknown cart_id '{cart_id}'."}
    check_ownership(cart.session_id, verified, what="cart")
    return {**cart.to_dict(), **verified.as_response_fields()}


@router.post("/api/cart/{cart_id}/items")
def add_item(cart_id: str, req: AddItemRequest, verified: VerifiedSession = Depends(require_session)):
    existing = cart_service.get_cart(cart_id)
    if existing is not None:
        check_ownership(existing.session_id, verified, what="cart")
    try:
        cart = cart_service.add_item(cart_id, req.product_id, req.merchant_id, quantity=req.quantity,
                                      variant_id=req.variant_id, role=req.role)
    except (CartMerchantMismatchError, ProductUnavailableError) as e:
        return {"error": str(e)}
    audit_repo.log_event(cart.session_id, events.CART_MODIFIED, "success", {"cart_id": cart_id, "added": req.product_id})
    return {**cart.to_dict(), **verified.as_response_fields()}


@router.patch("/api/cart/{cart_id}/items/{item_id}")
def modify_item(cart_id: str, item_id: str, req: ModifyItemRequest, verified: VerifiedSession = Depends(require_session)):
    existing = cart_service.get_cart(cart_id)
    if existing is not None:
        check_ownership(existing.session_id, verified, what="cart")
    try:
        cart = cart_service.modify_item(cart_id, item_id, req.quantity)
    except ProductUnavailableError as e:
        return {"error": str(e)}
    audit_repo.log_event(cart.session_id, events.CART_MODIFIED, "success", {"cart_id": cart_id, "item_id": item_id, "quantity": req.quantity})
    return {**cart.to_dict(), **verified.as_response_fields()}


@router.delete("/api/cart/{cart_id}/items/{item_id}")
def remove_item(cart_id: str, item_id: str, verified: VerifiedSession = Depends(require_session)):
    existing = cart_service.get_cart(cart_id)
    if existing is not None:
        check_ownership(existing.session_id, verified, what="cart")
    try:
        cart = cart_service.remove_item(cart_id, item_id)
    except ProductUnavailableError as e:
        return {"error": str(e)}
    audit_repo.log_event(cart.session_id, events.CART_MODIFIED, "success", {"cart_id": cart_id, "removed": item_id})
    return {**cart.to_dict(), **verified.as_response_fields()}
