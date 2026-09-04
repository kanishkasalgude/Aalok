"""
SQLite connection + schema init. Moved from the old top-level audit.py.
Kept as plain stdlib sqlite3 (no ORM, no Postgres/Redis) - sufficient for
this hackathon prototype per spec section 25, and it's what the working
audit trail already used.
"""
from __future__ import annotations

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "aalok.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            step TEXT,
            status TEXT,          -- pending | success | failed | rejected
            detail TEXT,          -- JSON blob
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            merchant_id TEXT,
            merchant_name TEXT,
            primary_item_id TEXT,
            upsell_item_id TEXT,   -- nullable
            total_amount REAL,
            upsell_accepted INTEGER, -- 0/1
            status TEXT,           -- captured | failed
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_webhooks (
            event_id TEXT PRIMARY KEY,
            razorpay_order_id TEXT,
            event_type TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS refunds (
            refund_id TEXT PRIMARY KEY,
            internal_order_id TEXT,
            payment_id TEXT,
            amount REAL,
            reason TEXT,
            status TEXT,
            provider_reference TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()
