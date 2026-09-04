"""
Aalok <-> Razorpay identity mapping. Named `authorization.py` for the
Razorpay-domain sense of the word (payment authorization: an order that has
an outstanding payment attempt awaiting capture) - not to be confused with
domain/commerce/authorization.py's mandate-authorization concept. Kept as a
thin reference object so InternalOrder (orders/models.py) never has to
carry Razorpay's response shape directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RazorpayOrderReference:
    razorpay_order_id: str
    amount: int              # paise, as Razorpay's Orders API returns it
    currency: str
    status: str               # Razorpay's own order status string ("created", "attempted", "paid")
    receipt: Optional[str] = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)
