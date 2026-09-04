"""
OrderService.checkout() - THE single path from "here is a proposed cart" to
"money moved". Generalizes the pre-refactor main.py::
_run_cart_through_policy_and_payment (which every existing test/demo
already proved correct for the food vertical) to work over any cart/
merchant/category, while preserving every guarantee:

  revalidate (server-authoritative price/inventory - services/cart/service.py)
    -> lock a CartMandate snapshot
    -> AuthorizationService.check()  (is this mandate/session allowed at all)
    -> REJECT -> return, zero Razorpay calls
    -> PolicyEngine.evaluate_cart()  (is THIS cart valid: budget/inventory/
       price/merchant/attributes)
    -> REJECT -> return, zero Razorpay calls
    -> PASS -> reuse this cart's existing InternalOrder if one is already
       pending for this exact (cart_id, cart_version) - i.e. a retry -
       else create exactly one new order
    -> PaymentService.attempt_payment -> captured / failed (retryable, same
       order) / awaiting_checkout (real test mode)

Both Aalok's own conversational agent (api/routes/chat.py) and an
external AI buyer (api/routes/catalog.py's external-purchase route) call
this SAME method - not just "the same logic", literally the same code path.
Neither can reach Razorpay without going through AuthorizationService and
PolicyEngine first. There is no bypass.
"""
from __future__ import annotations

from typing import Optional

import requests

from ...core.errors import PaymentProviderMisconfigured
from ...domain.audit import events
from ...domain.cart.models import Cart
from ...domain.commerce.authorization import Authorization
from ...domain.commerce.mandates import CartMandate, IntentMandate
from ...domain.commerce.policy import PolicyEngine
from ...domain.orders.models import InternalOrder, OrderStatus
from ...integrations.merchants.registry import get_adapter
from ...repositories import audit_repo, order_repo
from ..authorization.service import AuthorizationService
from ..cart.service import CartService, cart_service
from ..payment.service import PaymentService, payment_service


class OrderService:
    def __init__(self, cart_service: CartService, payment_service: PaymentService):
        self._cart_service = cart_service
        self._payment_service = payment_service
        self._orders: dict = {}            # idempotency_key -> InternalOrder
        self._by_internal_id: dict = {}     # internal_order_id -> InternalOrder
        self._by_razorpay_id: dict = {}     # razorpay_order_id -> idempotency_key

    def get_order(self, internal_order_id: str) -> Optional[InternalOrder]:
        return self._by_internal_id.get(internal_order_id)

    def get_order_by_razorpay_id(self, razorpay_order_id: str) -> Optional[InternalOrder]:
        key = self._by_razorpay_id.get(razorpay_order_id)
        return self._orders.get(key) if key else None

    def get_order_by_payment_id(self, payment_id: str) -> Optional[InternalOrder]:
        return next((o for o in self._by_internal_id.values() if o.payment_id == payment_id), None)

    def list_orders(self, limit: int = 100) -> list:
        """Newest-first. Reads the in-memory order index (not the SQLite
        `orders` table, which only ever records terminal captured/failed
        rows for analytics) - this is the only place that also carries
        pending/awaiting_checkout orders and razorpay_order_id/payment_id,
        which the Orders/Payments pages need. Same in-memory-only lifetime
        as the rest of this prototype's session/cart state (see
        ARCHITECTURE.md "Known limitations")."""
        orders = sorted(self._by_internal_id.values(), key=lambda o: o.created_at, reverse=True)
        return orders[:limit]

    def validate(self, cart: Cart, intent: IntentMandate, authorization: Authorization, *,
                  buyer: str = "aalok_agent") -> dict:
        """The revalidate -> lock -> AuthorizationService.check -> PolicyEngine.evaluate_cart
        pipeline, WITHOUT creating an order or calling Razorpay - this is
        POST /api/checkout/validate's implementation, and checkout() below
        reuses it verbatim rather than duplicating the logic."""
        session_id = cart.session_id
        facts = self._cart_service.revalidate(cart)
        adapter = get_adapter(cart.merchant_id)
        merchant = adapter.merchant if adapter else None
        merchant_open = merchant.open if merchant else False
        delivery_minutes = max(facts["delivery_by_item"].values(), default=0)

        cart_items = [{"item_id": i.product_id, "name": i.name, "price": i.unit_price,
                       "quantity": i.quantity, "role": i.role} for i in cart.items]
        cart_mandate = CartMandate.create(parent_intent=intent, items=cart_items, merchant_id=cart.merchant_id,
                                           merchant_open=merchant_open, estimated_delivery_time_min=delivery_minutes)
        audit_repo.log_event(session_id, events.CART_CREATED, "success",
                              {"cart_mandate": cart_mandate.to_dict(), "buyer": buyer})

        authz_decision = AuthorizationService.check(authorization, merchant_id=cart.merchant_id,
                                                      category=merchant.category if merchant else None)
        audit_repo.log_event(session_id, events.AUTHORIZATION_CHECKED,
                              "success" if authz_decision.allowed else "rejected", authz_decision.to_dict())
        if not authz_decision.allowed:
            return {
                "allowed": False, "status": "rejected_by_authorization", "authorization_decision": authz_decision,
                "policy_decision": None, "cart_mandate": cart_mandate, "merchant": merchant, "facts": facts,
            }

        policy_decision = PolicyEngine.evaluate_cart(
            cart_mandate, intent, attributes_by_item=facts["attributes_by_item"],
            merchant_id_by_item=facts["merchant_id_by_item"], availability_by_item=facts["availability_by_item"],
        )
        audit_repo.log_event(session_id, events.POLICY_PASSED if policy_decision.allowed else events.POLICY_REJECTED,
                              "success" if policy_decision.allowed else "rejected", policy_decision.to_dict())
        return {
            "allowed": policy_decision.allowed, "status": "validated" if policy_decision.allowed else "rejected_by_policy",
            "authorization_decision": authz_decision, "policy_decision": policy_decision,
            "cart_mandate": cart_mandate, "merchant": merchant, "facts": facts,
        }

    def checkout(self, cart: Cart, intent: IntentMandate, authorization: Authorization, *,
                 force_fail: bool = False, buyer: str = "aalok_agent") -> dict:
        session_id = cart.session_id
        idem_key = cart.idempotency_key()
        pending = self._orders.get(idem_key)

        if pending and pending.status == OrderStatus.CAPTURED:
            # Idempotent no-op: this exact cart (same id, same version) was already paid.
            # Short-circuits BEFORE re-running Authorization/Policy - a ONE_TIME_CHECKOUT
            # authorization is consumed on first capture (see _apply_payment_result), so a
            # naive re-validation here would wrongly reject an already-successful re-confirm.
            audit_repo.log_event(session_id, events.ORDER_REUSED, "success", {
                "internal_order_id": pending.internal_order_id, "razorpay_order_id": pending.razorpay_order_id,
                "note": "Cart already captured - returning the existing result, no new Razorpay call made.",
            })
            return {
                "status": "success", "already_captured": True,
                "order": {"id": pending.razorpay_order_id, "amount": int(round(pending.amount * 100)),
                          "currency": pending.currency, "status": "captured"},
                "internal_order": pending.to_dict(), "razorpay_called": False,
                "audit_trail": audit_repo.get_audit_trail(session_id),
            }

        validation = self.validate(cart, intent, authorization, buyer=buyer)
        cart_mandate = validation["cart_mandate"]
        authz_decision = validation["authorization_decision"]
        merchant = validation["merchant"]

        if validation["status"] == "rejected_by_authorization":
            return {
                "status": "rejected_by_authorization", "authorization_decision": authz_decision.to_dict(),
                "cart_mandate": cart_mandate.to_dict(), "razorpay_called": False,
                "audit_trail": audit_repo.get_audit_trail(session_id),
            }
        policy_decision = validation["policy_decision"]
        if not validation["allowed"]:
            return {
                "status": "rejected_by_policy", "decision": policy_decision.to_dict(),
                "reasons": policy_decision.reasons, "cart_mandate": cart_mandate.to_dict(),
                "razorpay_called": False, "audit_trail": audit_repo.get_audit_trail(session_id),
            }

        try:
            if pending:
                order = pending
                audit_repo.log_event(session_id, events.ORDER_REUSED, "success", {
                    "internal_order_id": order.internal_order_id, "razorpay_order_id": order.razorpay_order_id,
                    "note": "Same cart (idempotency key unchanged) -> same order reused for this retry; "
                            "no duplicate Razorpay order was created.",
                })
            else:
                order = InternalOrder.create(cart.cart_id, cart.version, cart.merchant_id, session_id,
                                              cart_mandate.total_amount, cart_mandate.currency)
                rp_order = self._payment_service.create_razorpay_order(
                    order.amount, receipt=f"aalok-{order.internal_order_id}",
                    notes={"session_id": session_id, "internal_order_id": order.internal_order_id, "buyer": buyer},
                )
                order.razorpay_order_id = rp_order["id"]
                self._orders[idem_key] = order
                self._by_internal_id[order.internal_order_id] = order
                self._by_razorpay_id[order.razorpay_order_id] = idem_key
                audit_repo.log_event(session_id, events.ORDER_CREATED, "success",
                                      {"internal_order_id": order.internal_order_id, "razorpay_order": rp_order, "buyer": buyer})

            payment = self._payment_service.attempt_payment(order.razorpay_order_id, order.amount, force_fail=force_fail)
        except PaymentProviderMisconfigured as e:
            audit_repo.log_event(session_id, "payment_provider_error", "failed", {"error": str(e)})
            return {"status": "provider_misconfigured", "error": str(e),
                    "audit_trail": audit_repo.get_audit_trail(session_id)}
        except requests.exceptions.RequestException as e:
            # A REAL call to Razorpay's API genuinely failed - surfaced clearly, never swallowed
            # into a raw 500 and never silently retried as a mock success.
            audit_repo.log_event(session_id, "razorpay_api_error", "failed", {"error": str(e)})
            return {"status": "razorpay_api_error", "error": str(e),
                    "audit_trail": audit_repo.get_audit_trail(session_id)}

        return self._apply_payment_result(session_id, order, cart, cart_mandate, policy_decision,
                                           authz_decision, authorization, merchant, payment)

    def _apply_payment_result(self, session_id, order: InternalOrder, cart: Cart, cart_mandate: CartMandate,
                               policy_decision, authz_decision, authorization: Authorization, merchant,
                               payment: dict) -> dict:
        payment_status = payment.get("status")
        checkout_payload = None
        primary_item = next((i for i in cart.items if i.role == "primary"), cart.items[0] if cart.items else None)
        upsell_item = next((i for i in cart.items if i.role != "primary"), None)
        provider_mode = self._payment_service.get_active_provider().get("mode")
        order_payload = {"id": order.razorpay_order_id, "amount": int(round(order.amount * 100)),
                          "currency": order.currency, "receipt": f"aalok-{order.internal_order_id}",
                          "status": "created", "mode": provider_mode}

        if payment_status == "captured":
            # MOCK MODE ONLY - real test mode never returns "captured" synchronously.
            audit_repo.log_event(session_id, events.PAYMENT_ATTEMPTED, "success", {"payment": payment})
            audit_repo.log_event(session_id, events.PAYMENT_CAPTURED, "success",
                                  {"payment": payment, "internal_order_id": order.internal_order_id})
            order.set_status(OrderStatus.CAPTURED)
            order.payment_id = payment.get("id")
            AuthorizationService.consume(authorization)
            if primary_item and merchant:
                order_repo.record_order(session_id, cart.merchant_id, merchant.name, primary_item.product_id,
                                         upsell_item.product_id if upsell_item else None, order.amount,
                                         upsell_item is not None, "captured")
            audit_repo.log_event(session_id, events.ORDER_CONFIRMED, "success", {"internal_order_id": order.internal_order_id})
            final_status = "success"
        elif payment_status == "failed":
            audit_repo.log_event(session_id, events.PAYMENT_ATTEMPTED, "failed", {"payment": payment})
            audit_repo.log_event(session_id, events.PAYMENT_FAILED, "failed",
                                  {"payment": payment, "internal_order_id": order.internal_order_id})
            order.set_status(OrderStatus.FAILED)  # retryable: next call with the SAME cart reuses this order
            audit_repo.log_event(session_id, "recovery", "success", {
                "message": "Payment failed. Order left in a safe pending state - no duplicate order was "
                           "created, and the user can retry (same order) without being charged twice.",
                "internal_order_id": order.internal_order_id,
            })
            if primary_item and merchant:
                order_repo.record_order(session_id, cart.merchant_id, merchant.name, primary_item.product_id,
                                         upsell_item.product_id if upsell_item else None, order.amount,
                                         upsell_item is not None, "failed")
            final_status = "payment_failed"
        elif payment_status == "requires_checkout_js":
            provider = self._payment_service.get_active_provider()
            audit_repo.log_event(session_id, "awaiting_checkout", "pending", {
                "internal_order_id": order.internal_order_id,
                "note": "Real Razorpay Test Mode Order created. Waiting for Checkout.js completion and "
                        "server-side signature verification before any capture is recorded.",
            })
            final_status = "awaiting_checkout"
            description = primary_item.name if primary_item else ""
            if upsell_item:
                description += f" + {upsell_item.name}"
            checkout_payload = {"key_id": provider.get("key_id"), "order_id": order.razorpay_order_id,
                                 "amount": order_payload["amount"], "currency": order.currency,
                                 "name": "Aalok", "description": description}
        else:
            audit_repo.log_event(session_id, events.PAYMENT_ATTEMPTED, "pending", {"payment": payment})
            final_status = "pending"

        return {
            "status": final_status, "decision": policy_decision.to_dict(),
            "authorization_decision": authz_decision.to_dict(), "order": order_payload,
            "internal_order": order.to_dict(), "payment": payment, "checkout": checkout_payload,
            "cart_mandate": cart_mandate.to_dict(), "razorpay_called": True,
            "audit_trail": audit_repo.get_audit_trail(session_id),
        }

    def apply_external_confirmation(self, session_id: str, razorpay_order_id: str, payment_status: str,
                                      payment_id: str, extra: Optional[dict] = None) -> Optional[InternalOrder]:
        """Used by the verify-payment route and the webhook handler: both
        confirm a payment OUTSIDE the synchronous checkout() call (real
        Razorpay Checkout.js / an async webhook delivery). Idempotent: an
        already-CAPTURED order is a no-op."""
        order = self.get_order_by_razorpay_id(razorpay_order_id)
        if order is None:
            return None
        if order.status == OrderStatus.CAPTURED:
            return order
        if payment_status == "captured":
            order.set_status(OrderStatus.CAPTURED)
            order.payment_id = payment_id
        elif payment_status == "failed":
            order.set_status(OrderStatus.FAILED)
        return order


order_service = OrderService(cart_service, payment_service)
