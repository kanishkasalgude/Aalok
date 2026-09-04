"""
Shared helper: bound every Gemini call with a hard timeout, and remember if
the network/API is unreachable so subsequent calls short-circuit instantly
instead of hanging or retrying. Moved from the old top-level llm_utils.py,
logic unchanged. Every caller in this codebase treats a None/exception
result as "fall back to the deterministic/heuristic path" - see
services/agent, services/catalog/ranking.py, services/analytics.
"""
from __future__ import annotations

import concurrent.futures
import os

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_disabled = False  # once we see the API is unreachable, stop retrying for this process


def gemini_unreachable() -> bool:
    return _disabled


def call_with_timeout(fn, *args, timeout: float = 6.0, **kwargs):
    """Runs fn(*args, **kwargs) with a hard wall-clock timeout. Returns the
    result, or None on timeout/exception. Marks the API disabled after the
    first failure to avoid repeatedly paying the timeout cost."""
    global _disabled
    if _disabled:
        return None
    future = _executor.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except Exception:
        _disabled = True
        return None


def llm_api_key() -> str | None:
    """LLM_API_KEY is the canonical config name; GEMINI_API_KEY is kept as a
    fallback alias (see core/config.py) so existing .env files keep working."""
    return os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
