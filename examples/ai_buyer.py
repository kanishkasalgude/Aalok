"""
examples/ai_buyer.py - a minimal, INDEPENDENT AI buyer client for Aalok.

This is deliberately NOT another LLM agent. It's a small script that proves
the full loop the buildathon brief asks for:

    External AI Buyer
           |
           v
    GET /api/catalog/feed          <- discover
           |
           v
    parse the JSON-LD, pick a product matching a simple NL requirement
                                     <- understand + select
           |
           v
    POST /api/external/purchase    <- transact
           |
           v
    Aalok's Commerce Policy Engine (mandates.py::check_cart_against_intent)
           |
           v
    Razorpay Order (or REJECT, zero Razorpay calls)

The important architectural point this script demonstrates: THIS client and
Aalok's own conversational chat agent both end up calling the exact same
backend method (`services/order/service.py::OrderService.checkout`). There is
no separate, more-trusted code path for an external caller - the second demo
below proves it by deliberately trying to overspend and getting rejected.

Usage:
    python examples/ai_buyer.py
    python examples/ai_buyer.py --requirement "high-protein meal under 300"
    python examples/ai_buyer.py --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import re
import sys

import requests

# Windows' default console codepage (cp1252) can't encode ₹ - reconfigure
# stdout to UTF-8 so this script's own print output (not the API, which is
# already UTF-8 JSON) doesn't crash on Windows terminals. No-op elsewhere.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DIETARY_ALIASES = {
    "vegetarian": "veg", "veg": "veg", "vegan": "vegan",
    "non-vegetarian": "non-veg", "non vegetarian": "non-veg", "non-veg": "non-veg",
    "high-protein": "high-protein", "high protein": "high-protein",
    "low-carb": "low-carb", "low carb": "low-carb",
    "dessert": "dessert", "beverage": "beverage",
}


# Comma-tolerant (Indian 1,00,000 and international 100,000 grouping both
# match) digit run, with an optional lakh/crore/k multiplier word resolved
# deterministically. A bare `\d+` here would stop at the first comma and
# silently turn "under ₹3,000" into 3 - see backend/services/agent/currency.py
# for the identical fix applied to Aalok's own intent parser.
_AMOUNT_RE = re.compile(
    r"under\s*(?:₹|rs\.?|inr)?\s*(\d+(?:,\d{2,3})*(?:\.\d+)?)\s*(lakh|lakhs|lac|crore|crores|k)?\b",
    re.IGNORECASE,
)
_MULTIPLIERS = {"lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "crore": 10_000_000, "crores": 10_000_000, "k": 1_000}


def parse_requirement(text: str) -> dict:
    """Simple keyword + regex parsing - intentionally not an LLM call. This
    mirrors what a real third-party shopping agent's OWN intent-parsing step
    would hand to Aalok; Aalok doesn't need to trust or re-derive it,
    because the Commerce Policy Engine re-validates everything server-side
    regardless of how the constraints were produced."""
    lower = text.lower()
    dietary = None
    for phrase, tag in DIETARY_ALIASES.items():
        if phrase in lower:
            dietary = tag
            break
    m = _AMOUNT_RE.search(lower)
    if m:
        max_amount = float(m.group(1).replace(",", "")) * _MULTIPLIERS.get((m.group(2) or "").lower(), 1)
    else:
        max_amount = 500.0
    return {"dietary_constraint": dietary, "max_amount": max_amount}


def fetch_catalog(base_url: str) -> list[dict]:
    """Step 1-2: discover + understand. Pulls the same agent-readable JSON-LD
    feed any real external AI shopping agent (ChatGPT, Perplexity, Gemini)
    would use to learn what Aalok sells."""
    resp = requests.get(f"{base_url}/api/catalog/feed", timeout=10)
    resp.raise_for_status()
    feed = resp.json()

    items = []
    for restaurant in feed["itemListElement"]:
        for menu_item in restaurant["hasMenu"]["hasMenuItem"]:
            props = {p["name"]: p["value"] for p in menu_item.get("additionalProperty", [])}
            items.append({
                "item_id": menu_item["identifier"],
                "name": menu_item["name"],
                "restaurant": restaurant["name"],
                "price": menu_item["offers"]["price"],
                "in_stock": menu_item["offers"]["availability"].endswith("InStock"),
                "dietary_tags": (props.get("dietary_tags") or "").split(","),
                "protein_g": props.get("protein_g"),
                "delivery_time_min": props.get("estimated_delivery_time_min"),
            })
    return items


def select_product(items: list[dict], requirement: dict) -> dict | None:
    """Step 3: select. Deterministic filtering, cheapest match first - same
    "hard constraints in code, not vibes" principle the backend's own RAG
    layer (rag.py) uses."""
    candidates = [
        it for it in items
        if it["in_stock"]
        and it["price"] <= requirement["max_amount"]
        and (requirement["dietary_constraint"] is None or requirement["dietary_constraint"] in it["dietary_tags"])
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda it: it["price"])
    return candidates[0]


def attempt_purchase(base_url: str, item_id: str, max_amount: float, dietary_constraint: str | None,
                      accept_upsell: bool = True) -> dict:
    """Step 4-5: transact through the SAME policy boundary Aalok's own
    agent uses. This client never computes a price or decides pass/fail
    itself - it just submits the proposal and reports what the server's
    Commerce Policy Engine decided."""
    resp = requests.post(
        f"{base_url}/api/external/purchase",
        json={
            "item_id": item_id,
            "max_amount": max_amount,
            "dietary_constraint": dietary_constraint,
            "accept_upsell": accept_upsell,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def run(base_url: str, requirement_text: str) -> None:
    print(f"External AI Buyer -> {base_url}")
    print(f"Requirement: \"{requirement_text}\"\n")

    requirement = parse_requirement(requirement_text)
    print(f"Parsed requirement: {requirement}\n")

    print("Discovering catalog via GET /api/catalog/feed ...")
    items = fetch_catalog(base_url)
    print(f"  -> discovered {len(items)} menu items across the feed.\n")

    chosen = select_product(items, requirement)
    if chosen is None:
        print("No catalog item matches this requirement. Exiting.")
        return
    print(f"Selected: {chosen['name']} ({chosen['restaurant']}) - ₹{chosen['price']}, "
          f"tags={chosen['dietary_tags']}\n")

    print("Transacting via POST /api/external/purchase ...")
    result = attempt_purchase(base_url, chosen["item_id"], requirement["max_amount"],
                               requirement["dietary_constraint"])
    decision = result.get("decision", {})
    print(f"  Commerce Policy Engine decision: {decision.get('decision')}  ({decision.get('reason')})")
    print(f"  Razorpay called: {result.get('razorpay_called')}")
    print(f"  Final status: {result.get('status')}")
    if result.get("order"):
        print(f"  Order: {result['order']['id']}  (mode={result['payment']['mode']})")
    print()

    # --- proves the trust boundary: this client cannot buy its way past the
    # gate by lying about its own budget in the request; the server re-fetches
    # the real price and checks it regardless of what this script claims. ---
    print("Demonstrating that this external client CANNOT bypass the policy engine")
    print(f"(deliberately re-requesting {chosen['name']} with an impossible ₹1 ceiling)...")
    bypass_attempt = attempt_purchase(base_url, chosen["item_id"], 1.0, None, accept_upsell=False)
    bdecision = bypass_attempt.get("decision", {})
    print(f"  Commerce Policy Engine decision: {bdecision.get('decision')}  ({bdecision.get('reason')})")
    print(f"  Razorpay called: {bypass_attempt.get('razorpay_called')}  (must be False)")
    assert bypass_attempt.get("razorpay_called") is False, "external buyer bypassed the policy engine!"
    print("  Confirmed: zero Razorpay calls were made for the rejected cart.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requirement", default="high-protein meal under 300")
    args = parser.parse_args()
    try:
        run(args.base_url, args.requirement)
    except requests.ConnectionError:
        print(f"Could not reach {args.base_url} - is the Aalok server running?", file=sys.stderr)
        sys.exit(1)
