"""
Hybrid retrieval, generalized from the old top-level rag.py (which only
ever ranked food dishes) to rank any list of Product across every
merchant/category the federated gateway returns.

Design (unchanged principle from rag.py): retrieval is hybrid, not
pure-semantic, because embeddings/LLMs are unreliable at hard numeric
constraints (budget ceilings, time ceilings) - so:
  1. Deterministic hard-filter: price, delivery time, attributes,
     availability - enforced in plain code.
  2. Semantic re-rank: within the survivors, Gemini text embeddings rank by
     similarity to the user's free-text intent.
Falls back to price-ascending order if embeddings are unavailable (no API
key / offline), so the product still works without an LLM key configured.
"""
from __future__ import annotations

import os
import re
from typing import Optional

import numpy as np

from ...integrations.llm.gemini import call_with_timeout, gemini_unreachable, llm_api_key

_EMBED_MODEL = "models/text-embedding-004"
_embeddings_cache: dict = {}  # product_id -> np.ndarray
_genai_ready = False


def _get_genai():
    global _genai_ready
    import google.generativeai as genai
    if not _genai_ready:
        api_key = llm_api_key()
        if api_key:
            genai.configure(api_key=api_key)
        _genai_ready = True
    return genai


def _embed_call(text: str):
    genai = _get_genai()
    result = genai.embed_content(model=_EMBED_MODEL, content=text, task_type="retrieval_document")
    return np.array(result["embedding"], dtype=np.float32)


def _embed_text(text: str) -> Optional[np.ndarray]:
    if not llm_api_key():
        return None
    return call_with_timeout(_embed_call, text, timeout=6.0)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def warm_embedding_cache(products: list) -> None:
    """Pre-computes an embedding per product (title + description). Safe to
    call repeatedly; skips products already cached; bails out early after
    the first unreachable-API failure so this never blocks app startup."""
    for product in products:
        if product.product_id in _embeddings_cache:
            continue
        text = f"{product.title} ({product.merchant_name}, {product.category}): {product.description}"
        vec = _embed_text(text)
        if vec is not None:
            _embeddings_cache[product.product_id] = vec
        elif gemini_unreachable():
            break


def hard_filter(products: list, *, max_price: Optional[float] = None, min_price: Optional[float] = None,
                 max_delivery_min: Optional[int] = None, required_attributes: Optional[dict] = None,
                 only_available: bool = True) -> list:
    """The deterministic pre-filter. Every constraint here is a hard AND."""
    out = []
    for p in products:
        if only_available and not p.availability:
            continue
        if max_price is not None and p.price > max_price:
            continue
        if min_price is not None and p.price < min_price:
            continue
        if max_delivery_min is not None and p.delivery.get("eta_min", 0) > max_delivery_min:
            continue
        if required_attributes:
            ok = True
            for key, expected in required_attributes.items():
                actual = p.attributes.get(key)
                if actual == expected:
                    continue
                if isinstance(actual, list) and expected in actual:
                    continue
                ok = False
                break
            if not ok:
                continue
        out.append(p)
    return out


_STOPWORDS = {"under", "below", "less", "than", "within", "find", "show", "me", "for",
              "the", "a", "an", "i", "need", "want", "of", "to", "with", "and", "rs", "inr"}


def _query_terms(query_text: str) -> list:
    return [t for t in re.findall(r"[a-z0-9]+", query_text.lower()) if len(t) > 2 and t not in _STOPWORDS]


def _keyword_score(product, terms: list) -> int:
    """No-embeddings relevance proxy: how many query terms appear in the
    product's title/description/attribute values. Cheap, deterministic,
    and - critically - still a hard AND with hard_filter()'s price/
    availability/attribute constraints, which already ran before this."""
    if not terms:
        return 0
    haystack = " ".join([product.title, product.description,
                          " ".join(str(v) for v in product.attributes.values())]).lower()
    return sum(1 for term in terms if term in haystack)


def rank(products: list, query_text: str, top_k: int = 10) -> list:
    """Hybrid: caller is expected to have already hard_filter()'d. Ranks
    survivors by semantic similarity to query_text when embeddings are
    available; otherwise by keyword-overlap relevance (title/description/
    attributes vs. the query's terms), falling back to price-ascending as
    the final tiebreak so results are never arbitrarily ordered."""
    if not products:
        return []
    query_vec = _embed_text(query_text) if query_text else None
    if query_vec is None:
        terms = _query_terms(query_text) if query_text else []
        return sorted(products, key=lambda p: (-_keyword_score(p, terms), p.price))[:top_k]

    warm_embedding_cache(products)
    scored = []
    for p in products:
        vec = _embeddings_cache.get(p.product_id)
        score = _cosine(query_vec, vec) if vec is not None else 0.0
        scored.append((score, p))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in scored[:top_k]]
