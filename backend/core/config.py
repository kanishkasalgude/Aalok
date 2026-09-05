"""
Central environment configuration. One place reads os.environ; every other
module gets its settings from here instead of scattering os.environ.get()
calls across services/integrations - makes it obvious what Aalok's
actual configuration surface is (spec section 32).

LLM_API_KEY is the new canonical name; GEMINI_API_KEY is kept as a fallback
alias so existing local .env files (and the deployed one) keep working
without edits.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_api_key: str | None
    payment_provider: str  # "" | "mock" | "razorpay_test"
    razorpay_key_id: str | None
    razorpay_key_secret: str | None
    razorpay_webhook_secret: str | None
    database_url: str
    session_secret: str | None

    @staticmethod
    def load() -> "Settings":
        return Settings(
            llm_provider=os.environ.get("LLM_PROVIDER", "gemini").strip().lower() or "gemini",
            llm_api_key=os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
            payment_provider=os.environ.get("PAYMENT_PROVIDER", "").strip().lower(),
            razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID"),
            razorpay_key_secret=os.environ.get("RAZORPAY_KEY_SECRET"),
            razorpay_webhook_secret=os.environ.get("RAZORPAY_WEBHOOK_SECRET"),
            database_url=os.environ.get("DATABASE_URL", "sqlite:///./backend/aalok.db"),
            session_secret=os.environ.get("SESSION_SECRET"),
        )


def get_settings() -> Settings:
    """Re-reads env on every call (cheap, and lets tests monkeypatch env vars
    per-test via os.environ / monkeypatch.setenv without a stale cache)."""
    return Settings.load()
