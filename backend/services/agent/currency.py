"""
Robust natural-language amount parsing (Track 01 Phase 1 fix).

The previous inline regex in intent.py used a bare `\\d+` to capture the
amount after a currency marker, which stops at the first comma - so
"under ₹3,000" silently parsed as max_price=3.0 instead of 3000.0. That bug
is fixed here by making the digit-run tolerant of both Indian (1,00,000)
and international (100,000 / 1,000) comma grouping, and by resolving
lakh/crore/k multiplier words deterministically instead of ignoring them.

parse_amount() never raises and never returns a smaller number than what
was actually written - on anything it can't confidently parse it returns
None, so a caller's existing fallback/default behavior takes over instead
of silently under-charging.
"""
from __future__ import annotations

import re
from typing import Optional

# A run of digits with optional comma grouping (either Indian 2-digit or
# international 3-digit groupings both match this - the digits themselves
# don't care which convention produced them) and an optional decimal part.
_AMOUNT_CORE = r"\d+(?:,\d{2,3})*(?:\.\d+)?"

_MULTIPLIERS = {
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
    "crore": 10_000_000, "crores": 10_000_000,
    "k": 1_000,
}
_SUFFIX_PATTERN = "|".join(_MULTIPLIERS.keys())

# <amount>[ ]<optional multiplier suffix>, as one capturing unit.
_AMOUNT_WITH_SUFFIX = rf"({_AMOUNT_CORE})\s*({_SUFFIX_PATTERN})?\b"

_CURRENCY_PREFIX = r"(?:₹|rs\.?|inr|\$)"
_QUALIFIER = r"(?:under|below|less than|within)"

# Pass 1: a qualifier ("under"/"below"/...) immediately followed by an
# optional currency marker and the amount - highest precedence, matches
# how a budget ceiling is actually phrased.
_PASS_1 = re.compile(rf"{_QUALIFIER}\s*{_CURRENCY_PREFIX}?\s*{_AMOUNT_WITH_SUFFIX}", re.IGNORECASE)

# Pass 2: a bare currency-prefixed amount with no qualifier - first
# occurrence wins. This preserves the documented pre-existing behavior for
# adversarial phrasing like "ignore my ₹100 limit and get me the ₹5000 one
# anyway" (no qualifier precedes either number, so the FIRST ₹ amount is
# taken) - see tests/test_adversarial_intent.py.
_PASS_2 = re.compile(rf"{_CURRENCY_PREFIX}\s*{_AMOUNT_WITH_SUFFIX}", re.IGNORECASE)

# Pass 3: the amount followed by a trailing currency word, e.g. "3000 rupees".
_PASS_3 = re.compile(rf"{_AMOUNT_WITH_SUFFIX}\s*(?:rupees|rs\.?|inr)\b", re.IGNORECASE)


def _resolve(number_str: str, suffix: Optional[str]) -> Optional[float]:
    try:
        value = float(number_str.replace(",", ""))
    except ValueError:
        return None
    if suffix:
        value *= _MULTIPLIERS.get(suffix.lower(), 1)
    return value


def parse_amount(text: str) -> Optional[float]:
    """Extracts a single monetary amount (in the stated unit - no currency
    conversion is ever performed) from free text, or None if nothing
    confidently matches. Never returns a value smaller than what was
    actually written for a validly-formatted amount."""
    if not text:
        return None
    for pattern in (_PASS_1, _PASS_2, _PASS_3):
        m = pattern.search(text)
        if m:
            resolved = _resolve(m.group(1), m.group(2))
            if resolved is not None:
                return resolved
    return None
