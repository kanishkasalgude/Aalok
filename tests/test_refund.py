"""
RefundService tests (spec section 13, new domain concept in this
refactor): a refund is only valid against a CAPTURED order, amounts are
bounds-checked, and a second refund request against an already-refunded
order is rejected rather than duplicated.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from backend.core.errors import RefundError
from backend.domain.commerce.mandates import IntentMandate
from backend.domain.refunds.models import RefundStatus
from backend.services.authorization.service import AuthorizationService
from backend.services.cart.service import cart_service
from backend.services.order.service import order_service
from backend.services.refund.service import RefundService
from backend.services.payment.service import payment_service


def _captured_order(session_id: str):
    intent = IntentMandate.create(session_id=session_id, max_amount=500, max_delivery_time_min=60, dietary_constraint=None)
    authorization = AuthorizationService.create(intent)
    cart = cart_service.create_cart(session_id, "r5")
    cart_service.add_item(cart.cart_id, "d501", "r5", role="primary")
    result = order_service.checkout(cart, intent, authorization, buyer="test")
    assert result["status"] == "success"
    return order_service.get_order(result["internal_order"]["internal_order_id"])


def test_valid_refund_on_a_captured_order():
    order = _captured_order(f"refund-ok-{uuid.uuid4().hex[:8]}")
    refund_service = RefundService(payment_service)
    refund = refund_service.create_refund(order, reason="customer requested cancellation")
    assert refund.status == RefundStatus.PROCESSED
    assert refund.amount == order.amount


def test_refund_rejected_for_a_non_captured_order():
    intent = IntentMandate.create(session_id=f"refund-notcap-{uuid.uuid4().hex[:8]}", max_amount=500,
                                   max_delivery_time_min=60, dietary_constraint=None)
    authorization = AuthorizationService.create(intent)
    cart = cart_service.create_cart(intent.session_id, "r5")
    cart_service.add_item(cart.cart_id, "d501", "r5", role="primary")
    result = order_service.checkout(cart, intent, authorization, buyer="test", force_fail=True)
    assert result["status"] == "payment_failed"
    order = order_service.get_order(result["internal_order"]["internal_order_id"])

    refund_service = RefundService(payment_service)
    with pytest.raises(RefundError):
        refund_service.create_refund(order, reason="should not be allowed")


def test_invalid_refund_amount_rejected():
    order = _captured_order(f"refund-badamt-{uuid.uuid4().hex[:8]}")
    refund_service = RefundService(payment_service)
    with pytest.raises(RefundError):
        refund_service.create_refund(order, reason="too much", amount=order.amount + 1000)
    with pytest.raises(RefundError):
        refund_service.create_refund(order, reason="negative", amount=-10)


def test_duplicate_refund_is_rejected_not_duplicated():
    order = _captured_order(f"refund-dup-{uuid.uuid4().hex[:8]}")
    refund_service = RefundService(payment_service)
    first = refund_service.create_refund(order, reason="first request")
    assert first.status == RefundStatus.PROCESSED
    with pytest.raises(RefundError):
        refund_service.create_refund(order, reason="second request - must not duplicate")
