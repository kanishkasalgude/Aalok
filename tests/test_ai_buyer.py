"""
External AI buyer flow, exercised through the real FastAPI app:

  - GET /api/catalog/feed is consumable (valid JSON-LD, has the fields an
    external agent needs to reason about price/diet/availability)
  - an external buyer can discover + select a product from the feed alone,
    using the same parsing logic examples/ai_buyer.py ships
  - an external buyer cannot bypass the Authorization/Commerce Policy Engine
  - the internal chat-driven path and the external-buyer path converge on
    the exact same OrderService.checkout() call - not just "the same
    logic", literally the same code path
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from fastapi.testclient import TestClient

from backend import main as main_module
from backend.api.routes import orders as orders_routes
from backend.services.payment.service import PaymentService
from ai_buyer import parse_requirement, select_product

client = TestClient(main_module.app)


def _fetch_feed_items():
    feed = client.get("/api/catalog/feed").json()
    items = []
    for restaurant in feed["itemListElement"]:
        for menu_item in restaurant["hasMenu"]["hasMenuItem"]:
            props = {p["name"]: p["value"] for p in menu_item.get("additionalProperty", [])}
            items.append({
                "item_id": menu_item["identifier"], "name": menu_item["name"], "restaurant": restaurant["name"],
                "price": menu_item["offers"]["price"], "in_stock": menu_item["offers"]["availability"].endswith("InStock"),
                "dietary_tags": (props.get("dietary_tags") or "").split(","),
            })
    return items


def test_catalog_feed_is_consumable():
    resp = client.get("/api/catalog/feed")
    assert resp.status_code == 200
    feed = resp.json()
    assert feed["@context"] == "https://schema.org"
    assert feed["@type"] == "ItemList"
    assert len(feed["itemListElement"]) > 0

    restaurant = feed["itemListElement"][0]
    assert restaurant["@type"] == "Restaurant"
    menu_item = restaurant["hasMenu"]["hasMenuItem"][0]
    assert menu_item["@type"] == "MenuItem"
    assert "identifier" in menu_item
    assert "price" in menu_item["offers"]
    assert "proteinContent" in menu_item["nutrition"]


def test_external_buyer_can_discover_and_select_a_product():
    items = _fetch_feed_items()
    assert len(items) > 0

    requirement = parse_requirement("high-protein meal under 300")
    chosen = select_product(items, requirement)
    assert chosen is not None
    assert chosen["price"] <= 300
    assert "high-protein" in chosen["dietary_tags"]


def test_external_buyer_cannot_bypass_policy_engine(monkeypatch):
    calls = {"count": 0}
    original = PaymentService.create_razorpay_order

    def counting_create_order(self, *args, **kwargs):
        calls["count"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PaymentService, "create_razorpay_order", counting_create_order)

    resp = client.post("/api/external/purchase", json={
        "item_id": "d501",       # Masala Dosa, ₹149
        "max_amount": 1.0,       # impossible ceiling
    })
    result = resp.json()
    assert result["status"] == "rejected_by_policy"
    assert result["razorpay_called"] is False
    assert result["decision"]["decision"] == "REJECT"
    assert calls["count"] == 0, "an external buyer must never reach Razorpay when the policy engine rejects"


def test_quick_add_uses_the_same_confirm_and_policy_pipeline():
    """The restaurant-browsing 'add to cart' path (not the AI chat) must
    still fully go through /api/order/confirm -> Authorization -> the
    Commerce Policy Engine -> the same payment path, with zero special-casing."""
    resp = client.post("/api/order/quick-add", json={"item_id": "d501"})
    data = resp.json()
    assert data["primary"]["id"] == "d501"
    session_id = data["session_id"]
    session_token = data["session_token"]

    confirm = client.post("/api/order/confirm", json={"session_id": session_id, "accept_upsell": False},
                           headers={"X-Session-Token": session_token}).json()
    assert confirm["status"] == "success"
    assert confirm["decision"]["decision"] == "PASS"


def test_quick_add_rejects_unknown_item():
    resp = client.post("/api/order/quick-add", json={"item_id": "not-a-real-id"})
    assert "error" in resp.json()


def test_external_buyer_uses_the_same_gate_as_the_chat_agent():
    """Not just 'the same logic' - literally the same function. Confirms
    both entry points delegate to the identical shared OrderService.checkout()."""
    chat_source = inspect.getsource(orders_routes.confirm_order)
    external_source = inspect.getsource(orders_routes.external_purchase)
    assert "order_service.checkout" in chat_source
    assert "order_service.checkout" in external_source
