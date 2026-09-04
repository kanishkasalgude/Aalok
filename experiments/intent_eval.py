"""
A small, honest check of the deterministic intent-parsing fallback
(services/agent/intent.py::_heuristic_parse_intent) - the path this
project actually runs on whenever GEMINI_API_KEY is unset, which is most
of the time in this environment.

THIS IS NOT A FORMAL BENCHMARK. It is 10 hand-labeled realistic queries,
checked against category and budget-ceiling extraction. Nothing here is
extrapolated into an "accuracy" claim beyond "N/10 passed on these exact
queries" - a different set of queries would produce a different number.
No number from this script should be quoted as a general capability claim.

Run directly:  python experiments/intent_eval.py
"""
from __future__ import annotations

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.services.agent.intent import _heuristic_parse_intent

# Each case: (query, expected category membership check, expected max_price)
# expected_category is a set of acceptable categories (some queries are
# legitimately ambiguous across two); expected_max_price is None when the
# query states no budget.
CASES = [
    ("Find me black running shoes under ₹3000", {"fashion"}, 3000),
    ("Dinner for two under ₹500", {"food"}, 500),
    ("Wireless headphones under ₹5000", {"electronics"}, 5000),
    ("Skincare for oily skin under ₹2000", {"beauty"}, 2000),
    ("Build a breakfast basket under ₹1000", {"grocery"}, 1000),
    ("Gold earrings under ₹3000", {"jewellery"}, 3000),
    ("Something to watch tonight", {"entertainment"}, None),
    ("Home cleaning service", {"services"}, None),
    ("Cotton kurta below 900 rupees", {"fashion"}, 900),
    ("Recharge my broadband plan under 800", {"services"}, 800),
]


def run_eval() -> dict:
    results = []
    for query, expected_categories, expected_max_price in CASES:
        intent = _heuristic_parse_intent(query)
        category_ok = bool(expected_categories & set(intent.category)) if expected_categories else True
        price_ok = intent.max_price == expected_max_price
        results.append({
            "query": query, "category_ok": category_ok, "price_ok": price_ok,
            "got_category": intent.category, "got_max_price": intent.max_price,
            "expected_category": sorted(expected_categories), "expected_max_price": expected_max_price,
        })
    category_pass = sum(1 for r in results if r["category_ok"])
    price_pass = sum(1 for r in results if r["price_ok"])
    return {"results": results, "category_pass": category_pass, "price_pass": price_pass, "total": len(results)}


if __name__ == "__main__":
    out = run_eval()
    for r in out["results"]:
        mark_c = "PASS" if r["category_ok"] else "FAIL"
        mark_p = "PASS" if r["price_ok"] else "FAIL"
        print(f"[{mark_c}/{mark_p}] {r['query']!r}")
        if not r["category_ok"]:
            print(f"         category: got {r['got_category']}, expected one of {r['expected_category']}")
        if not r["price_ok"]:
            print(f"         max_price: got {r['got_max_price']}, expected {r['expected_max_price']}")
    print(f"\nCategory extraction: {out['category_pass']}/{out['total']} on these {out['total']} labeled queries.")
    print(f"Budget extraction:   {out['price_pass']}/{out['total']} on these {out['total']} labeled queries.")
    print("\nThis is a fixed 10-query check, not a general accuracy measurement - see module docstring.")
