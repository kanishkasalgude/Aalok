"""
Merchant identity, separate from Product (schema.py) - see ARCHITECTURE.md
"Unified schema" section for why: a real merchant integration owns a lot of
facts (policies, fulfillment profile, capabilities) that don't belong
copy-pasted onto every one of its products.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .capabilities import MerchantCapabilities, DEFAULT_MOCK_CAPABILITIES

# The 8 product categories this prototype's synthetic ecosystem spans
# (spec section 3/31), mirroring the categories Razorpay's own demoed
# agentic-commerce pilots span - not an exhaustive taxonomy, just this
# project's scope.
CATEGORIES = (
    "food", "grocery", "fashion", "beauty", "electronics",
    "jewellery", "entertainment", "services",
)


@dataclass
class Merchant:
    merchant_id: str
    name: str
    category: str  # one of CATEGORIES
    subcategory: str = ""
    open: bool = True
    tier: str = "mainstream"  # value | mainstream | premium - illustrative, not a real rating source
    rating: float = 4.0  # DEMO DATA - see catalog.py-derived note in ARCHITECTURE.md
    capabilities: MerchantCapabilities = field(default_factory=lambda: DEFAULT_MOCK_CAPABILITIES)
    location: str = "Pune, IN"
    is_synthetic: bool = True  # ALWAYS True in this project - see ARCHITECTURE.md "mock vs real"

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["capabilities"] = self.capabilities.to_dict()
        return d
