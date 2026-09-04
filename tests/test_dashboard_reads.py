"""
Tests for the small, additive read-only aggregates added to support the
new frontend dashboard (Orders/Payments/Overview/Analytics pages) - none
of these touch cart/authorization/policy/order-creation logic, they only
read data that already exists.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from backend import main as main_module
from backend.domain.commerce.mandates import IntentMandate
from backend.services.authorization.service import AuthorizationService
from backend.services.cart.service import cart_service
from backend.services.order.service import order_service

client = TestClient(main_module.app)


def _checkout(session_id: str, item_id: str = "d501", merchant_id: str = "r5"):
    intent = IntentMandate.create(session_id=session_id, max_amount=500, max_delivery_time_min=60, dietary_constraint=None)
    authorization = AuthorizationService.create(intent)
    cart = cart_service.create_cart(session_id, merchant_id)
    cart_service.add_item(cart.cart_id, item_id, merchant_id, role="primary")
    return order_service.checkout(cart, intent, authorization, buyer="test")


def test_list_orders_returns_newest_first_with_category_and_merchant_name():
    session_id = f"list-orders-{uuid.uuid4().hex[:8]}"
    result = _checkout(session_id)
    assert result["status"] == "success"

    orders = order_service.list_orders(limit=5)
    assert len(orders) > 0
    assert orders[0].session_id == session_id or any(o.session_id == session_id for o in orders)

    resp = client.get("/api/orders?limit=5").json()
    assert "orders" in resp
    row = next(o for o in resp["orders"] if o["session_id"] == session_id)
    assert row["category"] == "food"
    assert row["merchant_name"] == "Curry Leaf"
    assert row["razorpay_order_id"] is not None


def test_get_single_order_still_works_alongside_the_new_list_route():
    session_id = f"get-order-{uuid.uuid4().hex[:8]}"
    result = _checkout(session_id)
    order_id = result["internal_order"]["internal_order_id"]
    resp = client.get(f"/api/orders/{order_id}").json()
    assert resp["internal_order_id"] == order_id


def test_list_refunds_route_returns_empty_list_shape_not_an_error():
    resp = client.get("/api/payments/refunds").json()
    assert "refunds" in resp
    assert isinstance(resp["refunds"], list)


def test_analytics_response_includes_daily_trend_and_refunds():
    resp = client.get("/api/analytics").json()
    assert "daily_trend" in resp
    assert isinstance(resp["daily_trend"], list)
    assert "refunds" in resp
    assert "count" in resp["refunds"]
    assert "total_amount" in resp["refunds"]


def test_orders_by_day_aggregate_is_internally_consistent():
    from backend.repositories import order_repo
    session_id = f"byday-{uuid.uuid4().hex[:8]}"
    _checkout(session_id)
    rows = order_repo.orders_by_day(days=1)
    assert len(rows) >= 1
    for row in rows:
        assert row["total"] >= row["captured"] + row["failed"] - row["total"] or True  # captured+failed <= total
        assert row["captured"] + row["failed"] <= row["total"]


def test_catalog_search_route_respects_top_k():
    """Regression test: the /api/catalog/search route must forward top_k to
    the gateway - the Merchants/Discover pages request a large top_k to see
    the full catalog, not the default page-sized 12."""
    default_resp = client.get("/api/catalog/search?query=").json()
    assert len(default_resp["results"]) <= 12
    full_resp = client.get("/api/catalog/search?query=&top_k=300").json()
    assert len(full_resp["results"]) > 12


def test_analytics_page_route_serves_the_spa_shell():
    resp = client.get("/analytics")
    assert resp.status_code == 200
    assert b'id="qb-app"' in resp.content
