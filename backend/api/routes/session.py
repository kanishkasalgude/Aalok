"""
POST /api/session - explicit session mint/refresh (Track 01 Phase 2).

Calling this with no token mints a brand-new anonymous session + signed
token. Calling it again with a still-valid token refreshes that SAME
session_id's expiry (so a demo doesn't get silently logged out mid-flow).
Every other session-scoped route also mints-on-first-use via
Depends(require_session), so calling this explicitly is a convenience for
clients that want to establish identity before their first real action -
the frontend does this on boot, and examples/ai_buyer.py can too.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services.session.auth import require_session, VerifiedSession

router = APIRouter()


@router.post("/api/session")
def create_or_refresh_session(verified: VerifiedSession = Depends(require_session)):
    return {**verified.as_response_fields(), "expires_at": verified.expires_at}
