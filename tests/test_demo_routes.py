"""
The two new one-call demo routes backing the Demo Control Panel (Track 01
Phase 12): POST /api/demo/successful-purchase and POST /api/demo/cart-tampering.
Both run through the exact same OrderService.checkout() pipeline as every
other route - these tests pin the outcomes the control panel's UI depends on.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from backend import main as main_module
from backend.services.payment.service import PaymentService

client = TestClient(main_module.app)


def _call_counter(monkeypatch, target_cls, attr_name):
    original = getattr(target_cls, attr_name)
    calls = {"count": 0}

    def wrapper(self, *args, **kwargs):
        calls["count"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(target_cls, attr_name, wrapper)
    return calls


def test_successful_purchase_demo_captures_and_calls_razorpay_exactly_once(monkeypatch):
    calls = _call_counter(monkeypatch, PaymentService, "create_razorpay_order")
    resp = client.post("/api/demo/successful-purchase")
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "success"
    assert result["razorpay_called"] is True
    assert result["decision"]["decision"] == "PASS"
    assert result["cart_mandate"]["total_amount"] == 2499.0
    assert calls["count"] == 1


def test_cart_tampering_demo_is_rejected_using_the_true_catalog_price():
    resp = client.post("/api/demo/cart-tampering")
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "rejected_by_policy"
    assert result["razorpay_called"] is False
    assert result["decision"]["decision"] == "REJECT"
    # The claimed/tampered price never reaches the policy engine - revalidate()
    # always restores the authoritative catalog price first.
    assert result["decision"]["cart_total"] == result["tamper_demo"]["actual_catalog_price"]
    assert result["tamper_demo"]["claimed_price"] < result["tamper_demo"]["actual_catalog_price"]
    assert result["decision"]["max_allowed"] == result["tamper_demo"]["authorized_ceiling"]


def test_cart_tampering_demo_makes_zero_razorpay_calls(monkeypatch):
    calls = _call_counter(monkeypatch, PaymentService, "create_razorpay_order")
    client.post("/api/demo/cart-tampering")
    assert calls["count"] == 0
