"""
Audit trail store + webhook idempotency ledger. Moved from the old
top-level audit.py, logic unchanged - see domain/audit/events.py for the
event-type vocabulary callers should use for `step`.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from .db import get_conn


def is_webhook_processed(event_id: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM processed_webhooks WHERE event_id=?", (event_id,)).fetchone()
    conn.close()
    return row is not None


def mark_webhook_processed(event_id: str, razorpay_order_id: str, event_type: str) -> bool:
    """Idempotently records a webhook delivery. Returns True if this call
    actually recorded it (first delivery), False if it was already there
    (a replay/duplicate delivery, which Razorpay's own docs say to expect
    and handle idempotently)."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO processed_webhooks (event_id, razorpay_order_id, event_type, created_at) VALUES (?,?,?,?)",
            (event_id, razorpay_order_id, event_type, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def log_event(session_id: str, step: str, status: str, detail: dict) -> dict:
    event = {
        "id": f"evt-{uuid.uuid4().hex[:10]}",
        "session_id": session_id,
        "step": step,
        "status": status,
        "detail": json.dumps(detail, default=str),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_events (id, session_id, step, status, detail, created_at) VALUES (?,?,?,?,?,?)",
        (event["id"], event["session_id"], event["step"], event["status"], event["detail"], event["created_at"]),
    )
    conn.commit()
    conn.close()
    out = dict(event)
    out["detail"] = detail
    return out


def get_audit_trail(session_id: str | None = None, limit: int = 200) -> list[dict]:
    conn = get_conn()
    if session_id:
        rows = conn.execute(
            "SELECT * FROM audit_events WHERE session_id=? ORDER BY created_at ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(d["detail"])
        except Exception:
            pass
        out.append(d)
    return out
