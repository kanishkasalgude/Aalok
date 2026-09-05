"""
Upsell audit events (Track 01 Phase 7): UPSELL_OFFERED fires whenever a
grounded complement is surfaced, UPSELL_ACCEPTED/UPSELL_DECLINED record
what the buyer actually did with it - exercised through the external buyer
route since it's the simplest single-call path that carries an upsell
(Masala Dosa d501 pairs with Filter Coffee d504 in the food adapter's
seed data - see backend/integrations/merchants/food_adapter.py).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from backend import main as main_module

client = TestClient(main_module.app)


def _steps(audit_trail):
    return [e["step"] for e in audit_trail]


def test_upsell_offered_and_accepted_are_both_logged():
    resp = client.post("/api/external/purchase", json={
        "item_id": "d501", "max_amount": 500, "accept_upsell": True,
    })
    result = resp.json()
    steps = _steps(result["audit_trail"])
    assert "upsell_offered" in steps
    assert "upsell_accepted" in steps
    assert "upsell_declined" not in steps


def test_upsell_offered_but_declined_is_logged_as_declined_not_accepted():
    resp = client.post("/api/external/purchase", json={
        "item_id": "d501", "max_amount": 500, "accept_upsell": False,
    })
    result = resp.json()
    steps = _steps(result["audit_trail"])
    assert "upsell_offered" in steps
    assert "upsell_declined" in steps
    assert "upsell_accepted" not in steps


def test_no_upsell_available_logs_neither_offered_nor_accepted_nor_declined():
    # A ceiling too tight for ANY complement to fit the remaining budget -
    # no grounded pairing exists, so nothing should be logged as offered.
    resp = client.post("/api/external/purchase", json={
        "item_id": "d501", "max_amount": 149.0, "accept_upsell": True,
    })
    result = resp.json()
    steps = _steps(result["audit_trail"])
    assert "upsell_offered" not in steps
    assert "upsell_accepted" not in steps
    assert "upsell_declined" not in steps
