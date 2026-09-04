"""
MerchantAdapter: the abstraction every synthetic merchant in this project
implements, and the shape a real merchant integration would implement later
(spec section 5). Each adapter INSTANCE represents one merchant - its raw
seed data is in that merchant's own field-naming conventions (deliberately
different per adapter, e.g. grocery's `mrp`/`pack_size` vs fashion's
`size`/`color`), and `search`/`get_product` are what actually normalize
that raw shape into the Unified Commerce Schema (domain/catalog/schema.py).

`create_cart`/`create_order` are deliberately NOT part of this interface:
in this architecture, cart and order are Aalok-owned domain concepts
(services/cart, services/order), not merchant-owned ones - a real merchant
adapter would only ever be asked for catalog/availability/delivery facts,
never to hold checkout state. See ARCHITECTURE.md "How to add a real
merchant adapter" for the reasoning.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ...core.errors import MerchantAdapterError
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product


class MerchantAdapter(ABC):
    merchant: Merchant

    @abstractmethod
    def search(self, query: str = "", filters: Optional[dict] = None) -> list:
        """Returns list[Product]. filters may include max_price, min_price,
        required_attributes (dict), subcategory. Raises MerchantAdapterError
        if this merchant cannot currently be reached (the mock equivalent of
        a real merchant API outage) - callers (the catalog gateway) must
        treat this as a per-merchant failure, not a whole-search failure."""
        raise NotImplementedError

    @abstractmethod
    def get_product(self, product_id: str) -> Optional[Product]:
        raise NotImplementedError

    def check_availability(self, product_id: str) -> bool:
        product = self.get_product(product_id)
        return bool(product and product.availability)

    def get_delivery_estimate(self, product_id: str, location: Optional[str] = None) -> dict:
        product = self.get_product(product_id)
        if not product:
            raise MerchantAdapterError(f"Unknown product_id '{product_id}' for merchant '{self.merchant.merchant_id}'.")
        return product.delivery
