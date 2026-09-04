"""
AuthorizationService: is this mandate/session even permitted to attempt a
transaction of this shape at all - the step that runs BEFORE the Commerce
Policy Engine (domain/commerce/policy.py) in OrderService.checkout(). See
domain/commerce/authorization.py's module docstring for how this differs
from the Policy Engine. Deterministic, zero LLM calls, same as the Policy
Engine.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ...core.errors import AuthorizationError
from ...domain.commerce.authorization import (
    Authorization, AuthorizationDecision, AuthorizationMode, AuthorizationStatus,
)
from ...domain.commerce.mandates import IntentMandate


class AuthorizationService:
    @staticmethod
    def create(mandate: IntentMandate, mode: AuthorizationMode = AuthorizationMode.ONE_TIME_CHECKOUT,
               scope: Optional[dict] = None) -> Authorization:
        if mode == AuthorizationMode.FUTURE_AGENTIC_RESERVE:
            raise AuthorizationError(
                "AuthorizationMode.FUTURE_AGENTIC_RESERVE is not implemented in this MVP - it names the "
                "conceptual slot for Razorpay's real UPI Reserve Pay product, which this project has no "
                "self-serve API access to. See ARCHITECTURE.md 'Razorpay boundary'."
            )
        return Authorization.create(mandate_id=mandate.mandate_id, max_amount=mandate.max_amount,
                                     mode=mode, scope=scope)

    @staticmethod
    def check(authorization: Authorization, *, merchant_id: Optional[str] = None,
              category: Optional[str] = None) -> AuthorizationDecision:
        checks: dict = {}
        reasons: list = []

        status_ok = authorization.status == AuthorizationStatus.ACTIVE
        checks["status"] = {"status": "PASS" if status_ok else "FAIL", "value": authorization.status.value}
        if not status_ok:
            reasons.append(f"Authorization status is '{authorization.status.value}', not active.")

        now = datetime.now(timezone.utc)
        expired = now > datetime.fromisoformat(authorization.expires_at)
        checks["expiry"] = {"status": "FAIL" if expired else "PASS", "expires_at": authorization.expires_at}
        if expired:
            reasons.append("Authorization has expired.")

        scope_ok = True
        scoped_merchant = authorization.scope.get("merchant_id")
        if scoped_merchant and merchant_id and scoped_merchant != merchant_id:
            scope_ok = False
            reasons.append(f"Authorization is scoped to merchant '{scoped_merchant}', not '{merchant_id}'.")
        scoped_categories = authorization.scope.get("category")
        if scoped_categories and category and category not in scoped_categories:
            scope_ok = False
            reasons.append(f"Authorization is not scoped to category '{category}'.")
        checks["scope"] = {"status": "PASS" if scope_ok else "FAIL", "scope": authorization.scope}

        allowed = len(reasons) == 0
        reason = "Authorization is valid for this transaction." if allowed else reasons[0]
        return AuthorizationDecision(allowed=allowed, reason=reason, authorization_id=authorization.authorization_id,
                                      status=authorization.status.value, checks=checks)

    @staticmethod
    def revoke(authorization: Authorization) -> None:
        authorization.status = AuthorizationStatus.REVOKED

    @staticmethod
    def consume(authorization: Authorization) -> None:
        """ONE_TIME_CHECKOUT authorizations are marked CONSUMED after a
        successful checkout so they cannot be silently reused."""
        if authorization.mode == AuthorizationMode.ONE_TIME_CHECKOUT:
            authorization.status = AuthorizationStatus.CONSUMED
