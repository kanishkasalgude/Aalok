"""
Aalok Growth Experiment - a small, deterministic, reproducible simulation
comparing a conventional ("baseline") ordering flow against Aalok's
conversational recommendation + upsell flow ("AI agent"), for the AI Growth &
Agentic Commerce track's explicit ask for measurable growth evidence.

THIS IS A SYNTHETIC BENCHMARK, NOT MEASURED MERCHANT PERFORMANCE. Every
number below is either:
  (a) sourced from the Sept 2026 research pass this project already did on
      real Indian food-delivery industry benchmarks (see catalog.py's/
      audit.py's provenance notes) - cited inline, or
  (b) an explicitly labeled ASSUMPTION where no public figure exists for
      "conversational agent vs baseline ordering" specifically (nobody
      publishes that exact split) - a directional, defensible guess, not a
      measured fact.
Do not present this script's output as real merchant metrics - the UI labels
it "synthetic benchmark / simulation" wherever it's shown.

Run directly:  python experiments/growth_experiment.py
Import:        from experiments.growth_experiment import run_experiment
"""
from __future__ import annotations

import os
import random
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.integrations.merchants.food_adapter import enriched_dishes

SEED = 42
N_SESSIONS = 100

# --- sourced (Sept 2026 research pass, see project research doc) ----------
UPSELL_ACCEPTANCE_AI = 0.08       # generic e-commerce checkout cross-sell benchmark, 4-12% typical

# --- explicitly labeled assumptions - no public benchmark splits "AI agent
# vs conventional flow" for food-delivery ordering specifically ------------
BASELINE_CONVERSION_RATE = 0.55   # ASSUMPTION: conventional browse/filter flow, more abandonment
AI_CONVERSION_RATE = 0.75         # ASSUMPTION: a constraint-matched single recommendation reduces
                                   # mismatch-driven abandonment vs browsing a full catalog blind
BASELINE_UPSELL_RATE = 0.02       # ASSUMPTION: an unprompted/generic "add a drink?" checkbox
BASELINE_TIME_TO_CART_SEC = (60, 240)   # ASSUMPTION: browsing multiple listings before choosing
AI_TIME_TO_CART_SEC = (15, 60)          # ASSUMPTION: agent proposes one match immediately


def _catalog_prices():
    """Order values are sampled from Aalok's real seeded catalog prices,
    not invented numbers - only the session-level behavioral assumptions
    above are synthetic."""
    dishes = enriched_dishes()
    mains = [d for d in dishes if "beverage" not in d["dietary_tags"] and "dessert" not in d["dietary_tags"]]
    addons = [d for d in dishes if "beverage" in d["dietary_tags"] or "dessert" in d["dietary_tags"]]
    return mains, addons


def _simulate_group(rng: random.Random, n: int, conversion_rate: float, upsell_rate: float,
                     mains: list, addons: list, time_range: tuple) -> dict:
    conversions = 0
    revenue = 0.0
    upsell_orders = 0
    time_to_cart = []
    for _ in range(n):
        if rng.random() >= conversion_rate:
            continue  # session did not convert
        conversions += 1
        main = rng.choice(mains)
        total = main["price"]
        if addons and rng.random() < upsell_rate:
            total += rng.choice(addons)["price"]
            upsell_orders += 1
        revenue += total
        time_to_cart.append(rng.uniform(*time_range))

    aov = round(revenue / conversions, 2) if conversions else 0.0
    upsell_rate_actual = round(upsell_orders / conversions * 100, 1) if conversions else 0.0
    avg_time_to_cart = round(sum(time_to_cart) / len(time_to_cart), 1) if time_to_cart else 0.0
    return {
        "sessions": n,
        "conversions": conversions,
        "conversion_rate_pct": round(conversions / n * 100, 1),
        "aov": aov,
        "upsell_rate_pct": upsell_rate_actual,
        "revenue": round(revenue, 2),
        "avg_time_to_cart_sec": avg_time_to_cart,
    }


def run_experiment(seed: int = SEED, n_sessions: int = N_SESSIONS) -> dict:
    """Deterministic and reproducible: same seed -> byte-identical output,
    every time, on any machine (no wall-clock, no external calls). Metrics
    are CALCULATED from the simulated sessions below, not hard-coded."""
    mains, addons = _catalog_prices()
    rng_baseline = random.Random(seed)
    rng_ai = random.Random(seed + 1)  # a distinct but still deterministic stream

    baseline = _simulate_group(rng_baseline, n_sessions, BASELINE_CONVERSION_RATE,
                                BASELINE_UPSELL_RATE, mains, addons, BASELINE_TIME_TO_CART_SEC)
    ai_agent = _simulate_group(rng_ai, n_sessions, AI_CONVERSION_RATE,
                                UPSELL_ACCEPTANCE_AI, mains, addons, AI_TIME_TO_CART_SEC)

    def _uplift(before, after):
        return round((after - before) / before * 100, 1) if before else None

    uplift = {
        "conversion_rate_uplift_pct": _uplift(baseline["conversion_rate_pct"], ai_agent["conversion_rate_pct"]),
        "aov_uplift_pct": _uplift(baseline["aov"], ai_agent["aov"]),
        "revenue_uplift_pct": _uplift(baseline["revenue"], ai_agent["revenue"]),
    }

    return {
        "label": "SYNTHETIC BENCHMARK / SIMULATION - not real merchant performance",
        "seed": seed,
        "baseline": baseline,
        "ai_agent": ai_agent,
        "uplift": uplift,
        "assumptions": [
            f"Baseline conversion rate {BASELINE_CONVERSION_RATE*100:.0f}% / AI-agent conversion rate "
            f"{AI_CONVERSION_RATE*100:.0f}%: labeled assumptions - no public benchmark splits conversion "
            f"by 'conversational agent vs conventional flow' for food delivery specifically.",
            f"AI-agent upsell acceptance {UPSELL_ACCEPTANCE_AI*100:.0f}%: sourced from generic e-commerce "
            f"checkout cross-sell benchmarks (4-12% typical range).",
            f"Baseline upsell acceptance {BASELINE_UPSELL_RATE*100:.0f}%: labeled assumption, modeling an "
            f"unprompted/generic add-on checkbox rather than a targeted recommendation.",
            "Order values are sampled from Aalok's actual seeded catalog prices (backend/catalog.py), "
            "not invented numbers.",
            "time_to_cart is illustrative only (uniform-random within a stated range), not measured.",
        ],
    }


def _print_report(result: dict) -> None:
    b, a, u = result["baseline"], result["ai_agent"], result["uplift"]
    print("Aalok Growth Experiment")
    print("─" * 60)
    print(f"[{result['label']}]  seed={result['seed']}")
    print()
    print(f"{'':22}{'Baseline':>12}{'AI Agent':>12}")
    print(f"{'Sessions':22}{b['sessions']:>12}{a['sessions']:>12}")
    print(f"{'Conversions':22}{b['conversions']:>12}{a['conversions']:>12}")
    print(f"{'Conversion Rate':22}{str(b['conversion_rate_pct'])+'%':>12}{str(a['conversion_rate_pct'])+'%':>12}")
    print(f"{'AOV':22}{'₹'+str(b['aov']):>12}{'₹'+str(a['aov']):>12}")
    print(f"{'Upsell Rate':22}{str(b['upsell_rate_pct'])+'%':>12}{str(a['upsell_rate_pct'])+'%':>12}")
    print(f"{'Revenue':22}{'₹'+str(b['revenue']):>12}{'₹'+str(a['revenue']):>12}")
    print(f"{'Avg time-to-cart (s)':22}{b['avg_time_to_cart_sec']:>12}{a['avg_time_to_cart_sec']:>12}")
    print()
    print(f"Conversion uplift: {u['conversion_rate_uplift_pct']}%")
    print(f"AOV uplift:        {u['aov_uplift_pct']}%")
    print(f"Revenue uplift:    {u['revenue_uplift_pct']}%")
    print()
    print("Assumptions:")
    for note in result["assumptions"]:
        print(f"  - {note}")


if __name__ == "__main__":
    _print_report(run_experiment())
