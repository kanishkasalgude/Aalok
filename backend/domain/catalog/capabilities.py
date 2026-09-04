"""
What a merchant can actually do. The commerce layer must not assume every
merchant behaves identically (spec section 8) - a synthetic mock merchant in
this MVP only ever supports catalog browsing + single checkout; refunds,
subscriptions, marketplace settlement and agentic (mandate-based) checkout
are represented as capability flags a real merchant integration could one
day flip on, not implemented behavior.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MerchantCapabilities:
    catalog: bool = True
    checkout: bool = True
    refunds: bool = False
    subscriptions: bool = False
    marketplace: bool = False
    agentic_checkout: bool = False

    def to_dict(self) -> dict:
        return {
            "catalog": self.catalog,
            "checkout": self.checkout,
            "refunds": self.refunds,
            "subscriptions": self.subscriptions,
            "marketplace": self.marketplace,
            "agentic_checkout": self.agentic_checkout,
        }


# MVP default for every synthetic mock merchant in this project: they can be
# discovered and checked out against (through Aalok's own order/payment
# services, which DO support refunds - see services/refund) but they don't
# themselves expose subscriptions/marketplace/agentic capabilities.
DEFAULT_MOCK_CAPABILITIES = MerchantCapabilities(catalog=True, checkout=True)
