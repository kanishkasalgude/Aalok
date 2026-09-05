"""
GET /api/audit - preserved shape, now identity-scoped (Track 01 Phase 2).

The session_id query param is kept ONLY as an escape hatch for an
external-buyer caller polling its own `external-*` session's trail with
the session_token that /api/external/purchase handed it - it must still
match the verified token's session_id, never an arbitrary one, so a query
param can never be used to read a different session's audit trail.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from ...repositories import audit_repo
from ...services.session.auth import VerifiedSession, check_body_session_id, require_session

router = APIRouter()


@router.get("/api/audit")
def audit(session_id: Optional[str] = None, verified: VerifiedSession = Depends(require_session)):
    check_body_session_id(session_id, verified)
    return {"events": audit_repo.get_audit_trail(verified.session_id), **verified.as_response_fields()}
