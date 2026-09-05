"""
Shared pytest fixtures/helpers.

auth_headers() mints a valid signed session token for an arbitrary
session_id via services.session.auth.issue_token directly - this is
legitimate test-side use of the real signing function (the same one every
route's Depends(require_session) verifies against), not a forgery. It lets
tests that build session/cart/order state through direct service calls
(bypassing the HTTP layer, as most of this suite already did before Track
01 Phase 2's session auth) still exercise the HTTP routes that now require
a verified session for that same session_id.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from backend.services.session.auth import issue_token


def auth_headers(session_id: str) -> dict:
    token, _ = issue_token(session_id)
    return {"X-Session-Token": token}


@pytest.fixture(autouse=True)
def _isolated_payment_env(monkeypatch):
    """Tests must never inherit whatever real Razorpay credentials happen
    to be in the developer's local .env - backend.main's load_dotenv() runs
    at import time and sets these process-wide. Without this, a developer
    who set PAYMENT_PROVIDER=razorpay_test + real keys locally (e.g. to do
    the live Test Mode verification run described in the README) would see
    unrelated tests fail non-deterministically, since real test mode never
    simulates synchronous capture the way mock mode's tests assume.
    Individual tests that need specific values still set them via
    monkeypatch.setenv (e.g. the `real_test_mode` fixture in
    test_razorpay_integration.py), which layers on top of this cleanly."""
    for var in ("PAYMENT_PROVIDER", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"):
        monkeypatch.delenv(var, raising=False)
