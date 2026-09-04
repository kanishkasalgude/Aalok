"""
Server-side session state (spec section 22) - the backend, not the
frontend, is authoritative for commerce state. In-memory, same tradeoff the
pre-refactor SESSIONS dict already made (fine for a single-process
prototype; a production build would move this to Redis/a DB keyed by
authenticated user session).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionState:
    session_id: str
    last_message: str = ""
    intent_mandate: object = None            # domain.commerce.mandates.IntentMandate
    authorization: object = None              # domain.commerce.authorization.Authorization
    selected_merchant_id: Optional[str] = None
    carts: dict = field(default_factory=dict)  # merchant_id -> cart_id
    recommendations: Optional[dict] = None      # last commerce_agent.run_commerce_agent() result
    checkout_state: str = "idle"                  # idle | awaiting_confirmation | awaiting_checkout | confirmed


class SessionStore:
    def __init__(self):
        self._sessions: dict = {}

    def get_or_create(self, session_id: str) -> SessionState:
        return self._sessions.setdefault(session_id, SessionState(session_id=session_id))

    def get(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)


session_store = SessionStore()
