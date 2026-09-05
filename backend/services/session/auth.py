"""
Lightweight signed, expiring, anonymous session tokens (Track 01 Phase 2).

This is NOT a user-account system - there are no passwords, no signup
flow, no PII. It exists to close one specific gap: before this, `session_id`
was a 100% client-supplied/echoed string (backend/services/session/store.py)
with no verification anywhere, so any client could read or mutate ANY
session's cart/order/mandate simply by guessing or copying its id. A signed
token binds a session_id to an expiry with an HMAC only this server can
produce, so a client can prove it is the party that was issued a given
session_id without the system needing logins.

Token shape: "<session_id>:<expiry_epoch>:<hex hmac>", HMAC-SHA256 over
"<session_id>:<expiry_epoch>" - the same style already used for Razorpay
checkout/webhook signatures (integrations/razorpay/provider.py), so no new
dependency is introduced.

Production note (see README "Security Model"): this is deliberately scoped
to what a hackathon prototype needs - stable identity across a demo
session, unforgeable, expiring. A production deployment would replace this
with real merchant/customer identity infrastructure (OAuth/OIDC, a
persistent user store) sitting in front of the same authorization boundary.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Optional

from fastapi import Header, HTTPException

from ...core.config import get_settings
from .store import session_store

SESSION_TTL_SECONDS = 3600

# Generated ONCE per process if SESSION_SECRET isn't configured - never
# regenerated per-call (get_settings() deliberately re-reads env on every
# call for testability, but a secret that changed mid-process would
# invalidate every token issued moments earlier). Sessions are already
# in-memory-only (SessionStore), so a secret that doesn't survive a
# restart is the same tradeoff already made everywhere else here.
_EPHEMERAL_SECRET = secrets.token_hex(32)
_warned = False


def _secret() -> bytes:
    global _warned
    configured = get_settings().session_secret
    if configured:
        return configured.encode()
    if not _warned:
        print("[aalok] WARNING: SESSION_SECRET is not set - using a random secret generated for "
              "this process only. Session tokens will not remain valid across a server restart. "
              "Set SESSION_SECRET in .env for stable tokens.")
        _warned = True
    return _EPHEMERAL_SECRET.encode()


def _sign(session_id: str, expires_at: int) -> str:
    message = f"{session_id}:{expires_at}".encode()
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()


def issue_token(session_id: str, ttl_seconds: int = SESSION_TTL_SECONDS) -> tuple[str, int]:
    """Returns (token, expires_at_epoch)."""
    expires_at = int(time.time()) + ttl_seconds
    signature = _sign(session_id, expires_at)
    return f"{session_id}:{expires_at}:{signature}", expires_at


def verify_token(token: Optional[str]) -> Optional[str]:
    """Returns the session_id if the token is well-formed, correctly
    signed, and not expired - None otherwise (forged, tampered, malformed,
    or expired all collapse to the same "not valid" result, no partial
    trust)."""
    if not token:
        return None
    parts = token.split(":")
    if len(parts) != 3:
        return None
    session_id, expires_at_str, signature = parts
    try:
        expires_at = int(expires_at_str)
    except ValueError:
        return None
    if time.time() >= expires_at:
        return None
    expected = _sign(session_id, expires_at)
    if not hmac.compare_digest(expected, signature):
        return None
    return session_id


def mint_session() -> tuple[str, str, int]:
    """Creates a brand-new session_id + token pair. Returns
    (session_id, token, expires_at_epoch)."""
    import uuid
    session_id = f"sess-{uuid.uuid4().hex[:10]}"
    session_store.get_or_create(session_id)
    token, expires_at = issue_token(session_id)
    return session_id, token, expires_at


class VerifiedSession:
    """Result of require_session: the authenticated session_id, plus
    whether a brand-new session/token had to be minted (no token was
    presented) so the route can hand the new token back to the caller."""

    def __init__(self, session_id: str, token: str, expires_at: int, is_new: bool):
        self.session_id = session_id
        self.token = token
        self.expires_at = expires_at
        self.is_new = is_new

    def as_response_fields(self) -> dict:
        """Merge into any route's JSON response so the caller always has
        the current token, whether it was just minted or merely reused."""
        return {"session_id": self.session_id, "session_token": self.token}


def require_session(x_session_token: Optional[str] = Header(None)) -> VerifiedSession:
    """FastAPI dependency for every session-scoped route.

    - No header presented: mints a fresh, isolated session. This keeps the
      product's frictionless "just start chatting" UX - it does NOT require
      a login step - while making it cryptographically impossible to claim
      an EXISTING session_id you were never issued a token for.
    - Header presented but forged/tampered/expired: 401. This is the
      concrete guarantee behind the "forged session", "expired session" and
      "replay" test cases - there is no silent fallback to a fresh session
      here, because that would let an attacker discard a caught-out forgery
      attempt for free and just try again.
    - Header presented and valid: the verified session_id is authoritative
      for the rest of the request, regardless of what a request body's own
      `session_id` field claims (routes are responsible for rejecting a
      mismatch as an impersonation attempt - see api/routes/*.py).
    """
    if x_session_token is None:
        session_id, token, expires_at = mint_session()
        return VerifiedSession(session_id, token, expires_at, is_new=True)

    session_id = verify_token(x_session_token)
    if session_id is None:
        raise HTTPException(status_code=401, detail="Invalid, forged, or expired session token.")
    session_store.get_or_create(session_id)
    parts = x_session_token.split(":")
    expires_at = int(parts[1])
    return VerifiedSession(session_id, x_session_token, expires_at, is_new=False)


def check_ownership(resource_session_id: Optional[str], verified: VerifiedSession, what: str = "resource") -> None:
    """Raises 403 if the verified caller does not own the resource. Used at
    every cart/order lookup-by-id route - the id alone was never a secret
    (they're just uuids), ownership is what actually gates access."""
    if resource_session_id is not None and resource_session_id != verified.session_id:
        raise HTTPException(status_code=403, detail=f"This {what} does not belong to your session.")


def check_body_session_id(body_session_id: Optional[str], verified: VerifiedSession) -> None:
    """Raises 403 if a request body explicitly names a session_id that
    doesn't match the verified caller - i.e. an attempt to act as another
    session while presenting your own (or no) token."""
    if body_session_id is not None and body_session_id != verified.session_id:
        raise HTTPException(status_code=403, detail="session_id does not match your authenticated session.")
