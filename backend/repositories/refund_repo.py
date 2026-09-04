"""Persistence for the new Refund domain object (domain/refunds/models.py)."""
from __future__ import annotations

from .db import get_conn


def save_refund(refund) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO refunds (refund_id, internal_order_id, payment_id, amount, reason, status,
           provider_reference, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(refund_id) DO UPDATE SET status=excluded.status,
             provider_reference=excluded.provider_reference, updated_at=excluded.updated_at""",
        (refund.refund_id, refund.internal_order_id, refund.payment_id, refund.amount, refund.reason,
         refund.status.value, refund.provider_reference, refund.created_at, refund.updated_at),
    )
    conn.commit()
    conn.close()


def get_refund_for_order(internal_order_id: str) -> dict | None:
    """Used for refund idempotency: an order that already has a
    requested/processed refund must not get a second one."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM refunds WHERE internal_order_id=? ORDER BY created_at DESC LIMIT 1",
        (internal_order_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_refund(refund_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM refunds WHERE refund_id=?", (refund_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_refunds(limit: int = 100) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM refunds ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
