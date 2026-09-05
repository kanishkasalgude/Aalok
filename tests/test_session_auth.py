"""
Session authentication (Track 01 Phase 2): forged/expired/missing tokens,
cross-user resource access, and session_id impersonation attempts.

Before this, session_id was a 100% client-supplied/echoed string with no
verification anywhere - any client could read or mutate any other
session's cart/order simply by supplying its id. These tests pin the
concrete guarantees services/session/auth.py now provides.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from backend import main as main_module
from backend.services.session.auth import issue_token, verify_token

client = TestClient(main_module.app)


# --- token primitives ---------------------------------------------------------

def test_missing_token_auto_mints_a_fresh_session_not_an_error():
    resp = client.post("/api/session")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"].startswith("sess-")
    assert body["session_token"]
    assert verify_token(body["session_token"]) == body["session_id"]


def test_forged_token_is_rejected():
    token, _ = issue_token("sess-victim")
    session_id, expires_at, signature = token.split(":")
    tampered = f"{session_id}:{expires_at}:{'0' * len(signature)}"
    resp = client.get("/api/cart/whatever-cart-id", headers={"X-Session-Token": tampered})
    assert resp.status_code == 401


def test_tampering_with_the_session_id_inside_a_valid_token_is_rejected():
    """Changing WHICH session_id a token claims, without re-signing,
    must invalidate the signature - proves the signature actually binds
    to the session_id, not just to a static secret."""
    token, _ = issue_token("sess-alice")
    _, expires_at, signature = token.split(":")
    forged = f"sess-bob:{expires_at}:{signature}"
    assert verify_token(forged) is None


def test_expired_token_is_rejected():
    token, _ = issue_token("sess-old", ttl_seconds=-10)
    assert verify_token(token) is None
    resp = client.get("/api/cart/whatever-cart-id", headers={"X-Session-Token": token})
    assert resp.status_code == 401


def test_replaying_an_expired_token_does_not_grant_access_even_to_its_own_session():
    """An expired token cannot be replayed even to act on the SESSION IT
    WAS ORIGINALLY ISSUED FOR - expiry is absolute, not just "for other
    people's data"."""
    session_id = "sess-was-valid-once"
    token, _ = issue_token(session_id, ttl_seconds=-1)
    resp = client.post("/api/session", headers={"X-Session-Token": token})
    assert resp.status_code == 401


def test_malformed_token_is_rejected():
    for bad in ["not-a-token", "a:b", "a:b:c:d", ""]:
        assert verify_token(bad) is None


# --- cross-user resource access -----------------------------------------------

def _create_cart_for(session_id: str) -> str:
    token, _ = issue_token(session_id)
    resp = client.post("/api/cart", json={"merchant_id": "r5"}, headers={"X-Session-Token": token})
    assert resp.status_code == 200
    return resp.json()["cart_id"]


def test_cross_user_cart_read_is_forbidden():
    cart_id = _create_cart_for("sess-alice")
    bob_token, _ = issue_token("sess-bob")
    resp = client.get(f"/api/cart/{cart_id}", headers={"X-Session-Token": bob_token})
    assert resp.status_code == 403


def test_cross_user_cart_mutation_is_forbidden():
    cart_id = _create_cart_for("sess-alice")
    bob_token, _ = issue_token("sess-bob")
    resp = client.post(f"/api/cart/{cart_id}/items",
                        json={"product_id": "d501", "merchant_id": "r5"},
                        headers={"X-Session-Token": bob_token})
    assert resp.status_code == 403

    resp = client.delete(f"/api/cart/{cart_id}/items/d501", headers={"X-Session-Token": bob_token})
    assert resp.status_code == 403


def test_owner_can_still_read_their_own_cart():
    cart_id = _create_cart_for("sess-alice")
    alice_token, _ = issue_token("sess-alice")
    resp = client.get(f"/api/cart/{cart_id}", headers={"X-Session-Token": alice_token})
    assert resp.status_code == 200
    assert resp.json()["cart_id"] == cart_id


def test_cross_user_order_read_is_forbidden():
    from backend.domain.commerce.mandates import IntentMandate
    from backend.services.authorization.service import AuthorizationService
    from backend.services.cart.service import cart_service
    from backend.services.order.service import order_service

    session_id = "sess-order-owner"
    intent = IntentMandate.create(session_id=session_id, max_amount=500, max_delivery_time_min=60, dietary_constraint=None)
    authorization = AuthorizationService.create(intent)
    cart = cart_service.create_cart(session_id, "r5")
    cart_service.add_item(cart.cart_id, "d501", "r5", role="primary")
    result = order_service.checkout(cart, intent, authorization, buyer="test")
    order_id = result["internal_order"]["internal_order_id"]

    attacker_token, _ = issue_token("sess-attacker")
    resp = client.get(f"/api/orders/{order_id}", headers={"X-Session-Token": attacker_token})
    assert resp.status_code == 403

    owner_token, _ = issue_token(session_id)
    resp = client.get(f"/api/orders/{order_id}", headers={"X-Session-Token": owner_token})
    assert resp.status_code == 200


# --- session_id impersonation via request body ---------------------------------

def test_body_session_id_mismatching_the_verified_token_is_forbidden():
    alice_token, _ = issue_token("sess-alice")
    resp = client.post("/api/chat", json={"session_id": "sess-bob", "message": "hello"},
                        headers={"X-Session-Token": alice_token})
    assert resp.status_code == 403


def test_body_session_id_matching_the_verified_token_is_allowed():
    alice_token, _ = issue_token("sess-alice")
    resp = client.post("/api/chat", json={"session_id": "sess-alice", "message": "find shoes under 3000"},
                        headers={"X-Session-Token": alice_token})
    assert resp.status_code == 200


# --- self-contained demo/external routes never leak a foreign identity ---------

def test_external_purchase_does_not_return_generic_session_fields():
    """/api/external/purchase mints its own throwaway external-* identity
    and must NOT return it under the generic "session_id"/"session_token"
    keys - frontend/js/api.js treats those as 'this is MY refreshed
    identity, adopt it' on every response. If external_purchase used the
    generic keys, a browser tab running the Demo Control Panel's
    'External AI Buyer' button would silently overwrite its own real
    session identity with this unrelated one."""
    resp = client.post("/api/external/purchase", json={"item_id": "d501", "max_amount": 500})
    body = resp.json()
    assert "session_id" not in body
    assert "session_token" not in body
    assert body["external_session_id"].startswith("external-")
    assert verify_token(body["external_session_token"]) == body["external_session_id"]


def test_demo_routes_do_not_return_generic_session_fields():
    for path in ("/api/demo/successful-purchase", "/api/demo/cart-tampering"):
        body = client.post(path).json()
        assert "session_id" not in body, path
        assert "session_token" not in body, path
        assert body["demo_session_id"].startswith("demo-")
        assert verify_token(body["demo_session_token"]) == body["demo_session_id"]


# --- audit trail is identity-scoped --------------------------------------------

def test_audit_query_param_cannot_read_another_sessions_trail():
    alice_token, _ = issue_token("sess-alice")
    resp = client.get("/api/audit?session_id=sess-bob", headers={"X-Session-Token": alice_token})
    assert resp.status_code == 403
