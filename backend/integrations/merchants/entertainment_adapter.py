"""CineHall - synthetic PVR-style entertainment (movie ticketing) merchant (fictional)."""
from __future__ import annotations

from typing import Optional

from ...domain.catalog.capabilities import DEFAULT_MOCK_CAPABILITIES
from ...domain.catalog.merchant import Merchant
from ...domain.catalog.schema import Product, normalize_raw_product
from .base import MerchantAdapter

MERCHANT_ID = "entertainment-cinehall"
MERCHANT_NAME = "CineHall"

RAW_PRODUCTS = [
    {"show_code": "s1", "movie_title": "Skyline Pursuit", "price_per_ticket": 280, "screen_type": "2D",
     "language": "English", "showtime": "19:30", "seats_available": 42, "complements": ["s7"]},
    {"show_code": "s2", "movie_title": "Skyline Pursuit", "price_per_ticket": 450, "screen_type": "IMAX",
     "language": "English", "showtime": "21:00", "seats_available": 18, "complements": ["s7"]},
    {"show_code": "s3", "movie_title": "Monsoon Melody", "price_per_ticket": 220, "screen_type": "2D",
     "language": "Hindi", "showtime": "18:00", "seats_available": 60, "complements": ["s7"]},
    {"show_code": "s4", "movie_title": "The Toy Forest", "price_per_ticket": 300, "screen_type": "3D",
     "language": "English", "showtime": "16:30", "seats_available": 50, "complements": ["s8"]},
    {"show_code": "s5", "movie_title": "Silent Corridor", "price_per_ticket": 260, "screen_type": "2D",
     "language": "Hindi", "showtime": "22:00", "seats_available": 30, "complements": ["s7"]},
    {"show_code": "s6", "movie_title": "Midnight Reckoning", "price_per_ticket": 240, "screen_type": "2D",
     "language": "English", "showtime": "23:45", "seats_available": 25, "complements": []},
    {"show_code": "s7", "movie_title": "Combo: Popcorn + Drink", "price_per_ticket": 349, "screen_type": "n/a",
     "language": "n/a", "showtime": "n/a", "seats_available": 999, "complements": []},
    {"show_code": "s8", "movie_title": "Combo: Kids Snack Box", "price_per_ticket": 249, "screen_type": "n/a",
     "language": "n/a", "showtime": "n/a", "seats_available": 999, "complements": []},
]


def _normalize(raw: dict) -> Product:
    is_ticket = raw["screen_type"] != "n/a"
    return normalize_raw_product({
        "product_id": raw["show_code"], "title": raw["movie_title"],
        "subcategory": "ticket" if is_ticket else "concession",
        "description": (f"{raw['movie_title']} - {raw['screen_type']}, {raw['language']}, {raw['showtime']}"
                         if is_ticket else raw["movie_title"]),
        "brand": MERCHANT_NAME, "price": raw["price_per_ticket"],
        "availability": raw["seats_available"] > 0,
        "attributes": {"screen_type": raw["screen_type"], "language": raw["language"], "showtime": raw["showtime"],
                        "seats_available": raw["seats_available"]},
        "delivery": {"eta_min": 0, "fee": 0.0}, "location": "Pune, IN",
        "complement_ids": raw["complements"],
    }, merchant_id=MERCHANT_ID, merchant_name=MERCHANT_NAME, category="entertainment")


class EntertainmentAdapter(MerchantAdapter):
    def __init__(self):
        self.merchant = Merchant(merchant_id=MERCHANT_ID, name=MERCHANT_NAME, category="entertainment",
                                  subcategory="cinema", open=True, tier="mainstream", rating=4.2,
                                  capabilities=DEFAULT_MOCK_CAPABILITIES)

    def search(self, query: str = "", filters: Optional[dict] = None) -> list:
        filters = filters or {}
        out = []
        for raw in RAW_PRODUCTS:
            if filters.get("max_price") is not None and raw["price_per_ticket"] > filters["max_price"]:
                continue
            if filters.get("min_price") is not None and raw["price_per_ticket"] < filters["min_price"]:
                continue
            out.append(_normalize(raw))
        return out

    def get_product(self, product_id: str) -> Optional[Product]:
        raw = next((r for r in RAW_PRODUCTS if r["show_code"] == product_id), None)
        return _normalize(raw) if raw else None
