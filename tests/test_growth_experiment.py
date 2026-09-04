"""
Growth experiment: must be deterministic/reproducible, and its metrics must
be genuinely calculated from the simulated sessions, not hard-coded constants.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.growth_experiment import run_experiment


def test_experiment_is_deterministic():
    r1 = run_experiment(seed=42)
    r2 = run_experiment(seed=42)
    assert r1 == r2, "same seed must produce byte-identical output"


def test_different_seeds_can_differ():
    r1 = run_experiment(seed=1)
    r2 = run_experiment(seed=2)
    assert r1 != r2


def test_metrics_are_calculated_not_hardcoded():
    result = run_experiment(seed=42, n_sessions=100)
    for group_name in ("baseline", "ai_agent"):
        g = result[group_name]
        assert g["sessions"] == 100
        assert 0 <= g["conversions"] <= g["sessions"]
        # conversion_rate_pct must equal conversions/sessions*100, not a fixed constant
        assert g["conversion_rate_pct"] == round(g["conversions"] / g["sessions"] * 100, 1)
        # revenue must be internally consistent with AOV * conversions (within rounding)
        if g["conversions"] > 0:
            assert abs(g["revenue"] - g["aov"] * g["conversions"]) < 1.0

    uplift = result["uplift"]
    b, a = result["baseline"], result["ai_agent"]
    expected_conv_uplift = round((a["conversion_rate_pct"] - b["conversion_rate_pct"]) / b["conversion_rate_pct"] * 100, 1)
    assert uplift["conversion_rate_uplift_pct"] == expected_conv_uplift


def test_order_values_come_from_real_catalog_prices():
    from backend.integrations.merchants.food_adapter import enriched_dishes
    catalog_prices = {d["price"] for d in enriched_dishes()}
    result = run_experiment(seed=42)
    # AOV for either group must be achievable from sums of real catalog prices
    # (a single dish, or a dish + an addon) - not an arbitrary invented number.
    possible_totals = set(catalog_prices) | {
        m + a for m in catalog_prices for a in catalog_prices if m + a < 2000
    }
    assert result["baseline"]["aov"] == 0 or any(
        abs(result["baseline"]["aov"] - t) < 50 for t in possible_totals
    )


def test_result_is_labeled_synthetic():
    result = run_experiment()
    assert "SYNTHETIC" in result["label"].upper()
    assert len(result["assumptions"]) > 0
