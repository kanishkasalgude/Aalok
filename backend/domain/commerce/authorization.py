"""
Authorization is a separate concept from the Commerce Policy Engine
(policy.py) - see ARCHITECTURE.md "Authorization vs Policy".

Authorization answers: "is this session/agent even permitted to attempt a
transaction of this shape at all" (is the mandate valid, unexpired,
unrevoked, and does the requested merchant/category fall inside its
scope)? Policy answers a narrower, later question: "is THIS SPECIFIC cart's
amount/inventory/price/merchant valid against that authorization?"

AuthorizationMode.FUTURE_AGENTIC_RESERVE exists ONLY as a named placeholder
for Razorpay's real, live "UPI Reserve Pay" product (consent-based,
pre-authorized payments within an approved spending limit - see
ARCHITECTURE.md "Razorpay boundary"). This project has no self-serve API
access to it, so nothing in this codebase ever constructs an Authorization
in that mode beyond the enum value itself - AuthorizationService.check()
raises AuthorizationError if it's ever reached, rather than simulating it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


class AuthorizationMode(str, Enum):
    ONE_TIME_CHECKOUT = "one_time_checkout"      # MVP default - one IntentMandate, consumed per checkout
    USER_MANDATE = "user_mandate"                # a longer-lived mandate reusable across multiple checkouts
    FUTURE_AGENTIC_RESERVE = "future_agentic_reserve"  # NOT IMPLEMENTED - see module docstring


class AuthorizationStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CONSUMED = "consumed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Authorization:
    authorization_id: str
    mode: AuthorizationMode
    mandate_id: str
    max_amount: float
    scope: dict = field(default_factory=dict)     # e.g. {"merchant_id": ..., "category": [...]}
    status: AuthorizationStatus = AuthorizationStatus.ACTIVE
    created_at: str = field(default_factory=_now_iso)
    expires_at: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat())

    @staticmethod
    def create(mandate_id: str, max_amount: float, mode: AuthorizationMode = AuthorizationMode.ONE_TIME_CHECKOUT,
               scope: Optional[dict] = None) -> "Authorization":
        return Authorization(authorization_id=f"authz-{uuid.uuid4().hex[:10]}", mode=mode,
                              mandate_id=mandate_id, max_amount=max_amount, scope=scope or {})

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["mode"] = self.mode.value
        d["status"] = self.status.value
        return d


@dataclass
class AuthorizationDecision:
    allowed: bool
    reason: str
    authorization_id: str
    status: str
    checks: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return dict(self.__dict__)
