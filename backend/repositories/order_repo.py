"""
Real-order history (for analytics) + historical demo-data seeding. Moved
from the old top-level audit.py, generalized from restaurant_id/name to
merchant_id/name so analytics works across every category, not just food.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from .db import get_conn


def orders_by_day(days: int = 14) -> list[dict]:
    """Daily order/capture/failure counts + captured revenue for the last
    `days` days, for the Overview page's trend chart - a real aggregate
    over the same `orders` table analytics already reads, not a synthetic
    series."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_conn()
    rows = conn.execute(
        """SELECT substr(created_at, 1, 10) AS day,
                  COUNT(*) AS total,
                  SUM(CASE WHEN status='captured' THEN 1 ELSE 0 END) AS captured,
                  SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                  SUM(CASE WHEN status='captured' THEN total_amount ELSE 0 END) AS revenue
           FROM orders WHERE created_at >= ? GROUP BY day ORDER BY day ASC""",
        (since,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_order(session_id: str, merchant_id: str, merchant_name: str, primary_item_id: str,
                  upsell_item_id: str | None, total_amount: float, upsell_accepted: bool, status: str) -> dict:
    order = {
        "id": f"ord-{uuid.uuid4().hex[:10]}",
        "session_id": session_id,
        "merchant_id": merchant_id,
        "merchant_name": merchant_name,
        "primary_item_id": primary_item_id,
        "upsell_item_id": upsell_item_id,
        "total_amount": total_amount,
        "upsell_accepted": 1 if upsell_accepted else 0,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    conn = get_conn()
    conn.execute(
        """INSERT INTO orders (id, session_id, merchant_id, merchant_name, primary_item_id,
           upsell_item_id, total_amount, upsell_accepted, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (order["id"], order["session_id"], order["merchant_id"], order["merchant_name"],
         order["primary_item_id"], order["upsell_item_id"], order["total_amount"],
         order["upsell_accepted"], order["status"], order["created_at"]),
    )
    conn.commit()
    conn.close()
    return order


def seed_historical_orders(n: int = 60):
    """Seed some plausible historical orders so the analytics dashboard has
    something meaningful on first run. Idempotent-ish: skips if orders
    already exist. Uses the food adapter's restaurants/dishes (the richest,
    already-sourced seed data in this project) exactly as the original
    audit.py did - see integrations/merchants/food_adapter.py for the
    provenance notes on these numbers."""
    from ..integrations.merchants.food_adapter import RESTAURANTS, DISHES

    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
    conn.close()
    if count > 0:
        return

    random.seed(42)
    now = datetime.now(timezone.utc)
    for _ in range(n):
        restaurant = random.choice([r for r in RESTAURANTS if r["open"]])
        r_dishes = [d for d in DISHES if d["restaurant_id"] == restaurant["id"]]
        primary = random.choice(r_dishes)
        upsell_candidates = [d for d in r_dishes if d["id"] != primary["id"] and
                              ("beverage" in d["dietary_tags"] or "dessert" in d["dietary_tags"])]
        upsell_accepted = random.random() < 0.08
        upsell = random.choice(upsell_candidates) if (upsell_candidates and upsell_accepted) else None
        total = primary["price"] + (upsell["price"] if upsell else 0)
        status = "captured" if random.random() > 0.05 else "failed"
        session_id = f"seed-{uuid.uuid4().hex[:8]}"
        created_at = (now - timedelta(days=random.randint(0, 29), hours=random.randint(0, 23))).isoformat()

        conn = get_conn()
        conn.execute(
            """INSERT INTO orders (id, session_id, merchant_id, merchant_name, primary_item_id,
               upsell_item_id, total_amount, upsell_accepted, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (f"ord-{uuid.uuid4().hex[:10]}", session_id, restaurant["id"], restaurant["name"],
             primary["id"], upsell["id"] if upsell else None, total,
             1 if upsell else 0, status, created_at),
        )
        conn.commit()
        conn.close()
