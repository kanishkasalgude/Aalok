"""
AuthorizationService tests (services/authorization/service.py) - the layer
that runs BEFORE the Commerce Policy Engine and answers "is this mandate/
session even permitted to attempt a transaction of this shape at all"
(spec section 6). Deterministic, zero LLM calls.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from backend.core.errors import AuthorizationError
from backend.domain.commerce.authorization import AuthorizationMode, AuthorizationStatus
from backend.domain.commerce.mandates import IntentMandate
from backend.services.authorization.service import AuthorizationService


def _mandate(**overrides):
    defaults = dict(session_id="s1", max_amount=500)
    defaults.update(overrides)
    return IntentMandate.create(**defaults)


def test_valid_authorization_passes():
    authz = AuthorizationService.create(_mandate())
    decision = AuthorizationService.check(authz)
    assert decision.allowed
    assert decision.status == "active"


def test_expired_authorization_is_rejected():
    authz = AuthorizationService.create(_mandate())
    authz.expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    decision = AuthorizationService.check(authz)
    assert not decision.allowed
    assert "expired" in decision.reason


def test_revoked_authorization_is_rejected():
    authz = AuthorizationService.create(_mandate())
    AuthorizationService.revoke(authz)
    assert authz.status == AuthorizationStatus.REVOKED
    decision = AuthorizationService.check(authz)
    assert not decision.allowed


def test_consumed_one_time_authorization_is_rejected_on_reuse():
    authz = AuthorizationService.create(_mandate(), mode=AuthorizationMode.ONE_TIME_CHECKOUT)
    AuthorizationService.consume(authz)
    assert authz.status == AuthorizationStatus.CONSUMED
    decision = AuthorizationService.check(authz)
    assert not decision.allowed


def test_merchant_scope_restriction():
    authz = AuthorizationService.create(_mandate(), scope={"merchant_id": "r5"})
    assert AuthorizationService.check(authz, merchant_id="r5").allowed
    assert not AuthorizationService.check(authz, merchant_id="r1").allowed


def test_category_scope_restriction():
    authz = AuthorizationService.create(_mandate(), scope={"category": ["food"]})
    assert AuthorizationService.check(authz, category="food").allowed
    assert not AuthorizationService.check(authz, category="jewellery").allowed


def test_future_agentic_reserve_mode_is_not_implemented():
    """AuthorizationMode.FUTURE_AGENTIC_RESERVE names the conceptual slot
    for Razorpay's real UPI Reserve Pay product - this project has no
    self-serve API access to it and must never simulate it."""
    with pytest.raises(AuthorizationError):
        AuthorizationService.create(_mandate(), mode=AuthorizationMode.FUTURE_AGENTIC_RESERVE)
