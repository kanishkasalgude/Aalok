"""GET /api/audit - preserved shape."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from ...repositories import audit_repo

router = APIRouter()


@router.get("/api/audit")
def audit(session_id: Optional[str] = None):
    return {"events": audit_repo.get_audit_trail(session_id)}
