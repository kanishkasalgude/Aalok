"""
Recommendation logic, separated from catalog retrieval (spec section 21):
catalog search returns candidates; this module picks a primary and grounds
any upsell/complement/substitute suggestion in REAL catalog relationships
(Product.relationships, populated by each merchant adapter's seed data),
never an LLM-invented pairing. The LLM may explain why something is
useful; it never gets to decide that a relationship exists.

Generalized from the old agent.py::select_grounded_upsell, which additionally
restricted the food vertical's candidate pool to beverage/dessert-tagged
dishes as a heuristic proxy for "this is an add-on, not a second main
course". That heuristic doesn't generalize across categories, so this
version tightens the rule instead of carrying the heuristic forward: an
upsell candidate must be a DECLARED complement of the primary item
(Product.relationships.complement_ids) - grounded in data, not guessed.
"""
from __future__ import annotations

from typing import Optional

from ...domain.catalog.schema import Product
from ..catalog import gateway


def pick_primary(candidates: list) -> Optional[Product]:
    """Candidates are assumed already ranked (services/catalog/ranking.py) -
    this just names the "take the top result" step."""
    return candidates[0] if candidates else None


def select_grounded_upsell(primary: Product, remaining_budget: float) -> Optional[Product]:
    """Best-scoring valid upsell for `primary`, or None. Every candidate is
    a real, declared complement (see module docstring) that is currently
    available and fits the remaining budget - an LLM may only ever suggest
    accepting it, never invent or substitute the pairing itself."""
    if remaining_budget <= 0:
        return None
    candidates = []
    for complement_id in primary.relationships.complement_ids:
        c = gateway.get_product(complement_id, primary.merchant_id)
        if c and c.availability and c.price <= remaining_budget:
            candidates.append(c)
    if not candidates:
        return None

    def _budget_fit(c: Product) -> float:
        return 1.0 - 0.3 * (c.price / remaining_budget)

    candidates.sort(key=_budget_fit, reverse=True)
    return candidates[0]


def find_complements(product_id: str, merchant_id: Optional[str] = None) -> list:
    return gateway.get_complements(product_id, merchant_id)


def find_substitutes(product_id: str, merchant_id: Optional[str] = None) -> list:
    return gateway.get_substitutes(product_id, merchant_id)
