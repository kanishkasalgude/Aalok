"""
Aalok backend - FastAPI app factory. Thin by design (spec section 24):
this file creates the app, includes routers, wires the startup hook, and
mounts the static frontend. All business logic lives in domain/ and
services/; all HTTP concerns live in api/routes/.

See ARCHITECTURE.md for the full system design. Short version: an AI
orchestrator (services/agent) proposes intent/cart via a strict tool layer
(services/agent/tools.py); a deterministic Authorization + Commerce Policy
Engine (services/authorization, domain/commerce/policy.py) - never an LLM
call - gates every cart before OrderService/PaymentService are ever allowed
to reach Razorpay (integrations/razorpay). Every step is written to an
audit trail (repositories/audit_repo.py).
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
load_dotenv()

if __package__ in (None, ""):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_repo_root = os.path.join(os.path.dirname(__file__), "..")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api.routes import agent, analytics, audit, cart, catalog, chat, orders, payments, webhooks
from .repositories.db import init_db
from .repositories.order_repo import seed_historical_orders
from .services.catalog.ranking import warm_embedding_cache
from .integrations.merchants.food_adapter import all_food_products

app = FastAPI(title="Aalok AI-Native Commerce API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(chat.router)
app.include_router(agent.router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(webhooks.router)
app.include_router(analytics.router)
app.include_router(audit.router)

# Run eagerly at import time (not just inside the startup hook below): the
# DB schema and seed data must exist the moment any route or test imports
# this module, regardless of whether the ASGI lifespan actually fires (a
# bare `TestClient(app)` used outside a `with` block never sends the
# lifespan startup message). Both are idempotent - safe to call again from
# the startup hook or a second import.
init_db()
seed_historical_orders()


@app.on_event("startup")
def _startup():
    init_db()
    seed_historical_orders()
    # Warm the RAG embedding cache for the food catalog (the vertical the
    # legacy chat UI exercises) - a no-op gracefully if no LLM key is set.
    warm_embedding_cache(all_food_products())


# --- static frontend ----------------------------------------------------------
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")

app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")


@app.middleware("http")
async def _no_cache_static(request: Request, call_next):
    """This is a prototype under active iteration, not a versioned release -
    a browser aggressively HTTP-caching /static/* across reloads (or even
    across a closed/reopened tab, since disk cache outlives the tab) means
    an edit can silently keep serving the previous file. Cheap enough at
    this traffic scale to just disable caching for everything under /static/."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


@app.get("/")
def index():
    return FileResponse(os.path.join(_frontend_dir, "index.html"))


@app.get("/analytics")
def analytics_page():
    """The dashboard is now a single-page app with client-side hash
    routing (frontend/js/router.js) - this just serves the same shell as
    `/`, which shows the Analytics view for the #/analytics hash. Kept as
    its own route so old bookmarks/links to /analytics keep working."""
    return FileResponse(os.path.join(_frontend_dir, "index.html"))
