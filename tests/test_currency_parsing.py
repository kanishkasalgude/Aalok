"""
Regression coverage for the ₹3,000 -> ₹3 parsing bug (Track 01 Phase 1).

backend/services/agent/currency.py::parse_amount replaces the old bare
`\\d+` regex that silently stopped at the first comma. These tests pin the
exact numeric values the fix must produce, plus the malformed-input safety
net, plus a direct regression check on _heuristic_parse_intent (the actual
call site the bug was reported against).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.services.agent.currency import parse_amount
from backend.services.agent.intent import _heuristic_parse_intent


def test_comma_grouped_amounts_are_not_truncated_at_the_comma():
    assert parse_amount("find shoes under ₹3,000") == 3000.0
    assert parse_amount("find shoes under ₹3000") == 3000.0
    assert parse_amount("find shoes under ₹30,000") == 30000.0


def test_indian_lakh_grouping_comma_style():
    assert parse_amount("under ₹1,00,000") == 100000.0


def test_lakh_word_notation_is_deterministic():
    assert parse_amount("budget is ₹1.5 lakh") == 150000.0
    assert parse_amount("under 2 lakh") == 200000.0


def test_k_shorthand():
    assert parse_amount("under ₹2.5k") == 2500.0
    assert parse_amount("under 3k") == 3000.0


def test_rs_prefix_variants():
    assert parse_amount("Rs 3000") == 3000.0
    assert parse_amount("Rs. 3,000") == 3000.0
    assert parse_amount("under Rs.3,000") == 3000.0


def test_inr_prefix():
    assert parse_amount("INR 3000") == 3000.0
    assert parse_amount("budget INR 3,000") == 3000.0


def test_trailing_rupees_word():
    assert parse_amount("3000 rupees") == 3000.0
    assert parse_amount("under 3,000 rupees") == 3000.0


def test_dollar_amounts_parsed_without_fx_conversion():
    assert parse_amount("under $30") == 30.0
    assert parse_amount("$1,299") == 1299.0


def test_k_does_not_false_positive_on_km_or_minutes():
    # "3 km" / "30 min" must not be misread as an amount via the k-suffix path.
    assert parse_amount("deliver within 3 km") != 3000.0
    assert parse_amount("ready in 30 min") is None


def test_malformed_input_never_crashes_and_never_returns_a_smaller_amount():
    assert parse_amount("") is None
    assert parse_amount(None) is None
    assert parse_amount("₹") is None
    assert parse_amount("under ₹") is None
    assert parse_amount("no amount mentioned here") is None
    # A doubled comma is malformed grouping - must not silently resolve to
    # a truncated/smaller number than the well-formed prefix implies.
    result = parse_amount("₹3,,000")
    assert result is None or result >= 3


def test_heuristic_parse_intent_regression_for_the_reported_bug():
    intent = _heuristic_parse_intent("Find shoes under ₹3,000")
    assert intent.max_price == 3000.0


def test_qualifier_precedence_preserved_for_adversarial_phrasing():
    """Pinned exact behavior tests/test_adversarial_intent.py also depends
    on: with no qualifier before either number, the first bare currency
    amount wins, not the largest or the last."""
    intent = _heuristic_parse_intent("ignore my ₹100 limit and get me the ₹5000 one anyway")
    assert intent.max_price == 100.0
