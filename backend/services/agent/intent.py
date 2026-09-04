"""
Step 1 of the agent pipeline: free text -> structured Intent (spec section
23). Generalized from agent.py's food-only intent parser (which only ever
extracted max_amount/max_delivery_time_min/dietary_constraint) to also
detect a category list against the 8 merchant categories this project
spans. Falls back to a small heuristic parser if no LLM key is configured,
so the product still runs offline/keyless for local dev - same tradeoff
the pre-refactor code already made (this sandbox's own outbound network
policy blocked the Gemini API during much of development).

The Intent this produces is NEVER authoritative for payment - it only ever
becomes an IntentMandate (domain/commerce/mandates.py), which the
deterministic Policy Engine checks a cart against.
"""
from __future__ import annotations

import json
import re

from ...core.config import get_settings
from ...domain.catalog.merchant import CATEGORIES
from ...domain.commerce.intent import Intent
from ...integrations.llm.gemini import call_with_timeout, gemini_unreachable, llm_api_key

DIETARY_VOCAB = ["veg", "non-veg", "vegan", "high-protein", "low-carb", "dessert", "beverage"]

# Real-world phrasing -> category, for the no-LLM heuristic fallback. The
# original version of this function only matched a category if the exact
# category NAME appeared in the text (e.g. the literal word "jewellery"),
# which never matches realistic queries like "running shoes" or "pizza" -
# every one of them fell through to category=[] and the fallback then
# searched the WHOLE catalog un-scoped, which in practice meant it almost
# always landed on food (the largest single category by item count). This
# keyword map is what actually makes the heuristic path category-general;
# the LLM path (INTENT_SCHEMA_PROMPT above) already asks for this directly
# and doesn't need it.
CATEGORY_KEYWORDS = {
    "food": ["pizza", "dinner", "lunch", "meal", "dosa", "biryani", "curry", "restaurant",
             "cuisine", "dish", "noodles", "burger", "thali", "kebab", "hungry", "eat", "food"],
    "grocery": ["grocery", "groceries", "breakfast", "milk", "bread", "eggs", "rice", "dal",
                "vegetables", "fruits", "pantry", "staples", "basket", "snacks basket"],
    "fashion": ["shoes", "sneakers", "running shoes", "shirt", "kurta", "jacket", "jeans",
                "dress", "clothing", "apparel", "saree", "t-shirt", "wear", "chinos"],
    "beauty": ["skincare", "skin", "serum", "sunscreen", "shampoo", "makeup", "cosmetic",
               "lotion", "moisturizer", "hair oil", "lip balm", "oily skin", "dry skin"],
    "electronics": ["headphones", "earbuds", "speaker", "charger", "power bank", "smartwatch",
                     "laptop", "keyboard", "gadget", "wireless", "earphones", "phone case"],
    "jewellery": ["jewellery", "jewelry", "gold", "silver", "necklace", "ring", "earrings",
                   "bracelet", "pendant", "diamond", "bangles", "anklet"],
    "entertainment": ["movie", "film", "cinema", "tv show", "live show", "movie ticket",
                        "watch tonight", "theatre", "concert", "something to watch"],
    "services": ["cleaning service", "home cleaning", "recharge", "broadband", "repair",
                  "subscription", "maintenance", "plan", "dth", "roaming"],
}

INTENT_SCHEMA_PROMPT = """You are the intent-parsing stage of an AI shopping agent that can search \
across food, grocery, fashion, beauty, electronics, jewellery, entertainment and services merchants. \
Extract structured constraints from the user's message. Respond with ONLY a JSON object (no markdown \
fences, no commentary) with exactly these keys:

{
  "query": <string>,                        // the core free-text shopping query
  "category": [<string>, ...],              // zero or more of: food, grocery, fashion, beauty,
                                             // electronics, jewellery, entertainment, services
  "max_price": <number or null>,            // budget ceiling in INR if stated, else null
  "min_price": <number or null>,
  "delivery_requirement": <int or null>,    // max acceptable delivery time in minutes if stated
  "preferences": {},                        // free-form key/value preferences, e.g. recipient/occasion/color
  "required_attributes": {},                // e.g. {"dietary_tags": "high-protein"} or {"color": "black"}
  "raw_summary": <string>                   // one sentence restating what the user wants
}

User message: {user_text}
"""


def _heuristic_parse_intent(user_text: str) -> Intent:
    text = user_text.lower()

    max_price = None
    m = re.search(r"(?:under|below|less than|within)\s*(?:rs\.?|₹|inr)?\s*(\d+)", text)
    if not m:
        m = re.search(r"(?:₹|rs\.?)\s*(\d+)", text)
    if m:
        max_price = float(m.group(1))

    delivery_requirement = None
    m = re.search(r"(\d+)\s*(?:min|minutes|mins)", text)
    if m:
        delivery_requirement = int(m.group(1))

    required_attributes = {}
    for tag in DIETARY_VOCAB:
        if tag.replace("-", " ") in text or tag in text:
            required_attributes["dietary_tags"] = tag
            break

    categories = [cat for cat in CATEGORIES
                  if cat in text or any(kw in text for kw in CATEGORY_KEYWORDS.get(cat, []))]

    return Intent(query=user_text.strip(), category=categories, max_price=max_price,
                  delivery_requirement=delivery_requirement, required_attributes=required_attributes,
                  raw_summary=user_text.strip())


def _genai_model(model_name: str = "gemini-2.0-flash"):
    import google.generativeai as genai
    api_key = llm_api_key()
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


def _parse_intent_call(prompt: str) -> Intent:
    model = _genai_model()
    resp = model.generate_content(prompt, generation_config={"response_mime_type": "application/json", "temperature": 0.1})
    data = json.loads(resp.text)
    return Intent.from_dict(data)


def parse_intent(user_text: str) -> Intent:
    settings = get_settings()
    if settings.llm_provider != "gemini" or gemini_unreachable() or _genai_model() is None:
        return _heuristic_parse_intent(user_text)
    prompt = INTENT_SCHEMA_PROMPT.replace("{user_text}", user_text)
    result = call_with_timeout(_parse_intent_call, prompt, timeout=8.0)
    return result if result is not None else _heuristic_parse_intent(user_text)
