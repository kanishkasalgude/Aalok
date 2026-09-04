# Aalok Architecture — AI-Native Commerce Core

## 1. Product thesis

Aalok is **not** a food-ordering chatbot, and it is **not** a replacement for Razorpay.

Aalok is an **AI-native commerce orchestration layer** that sits in front of Razorpay:
it understands natural-language shopping intent, discovers products across heterogeneous
synthetic merchants, normalizes their catalogs into one schema, recommends and builds a
cart, applies a deterministic authorization + policy gate, creates a canonical internal
order, and only then delegates the actual movement of money to Razorpay — reconciling the
result via signature verification and webhooks, with every step written to an audit trail.

```
AI USER / EXTERNAL AI BUYER
        │
        ▼
AI COMMERCE ORCHESTRATOR   (services/agent)        tool layer only — never touches
        │                                           Razorpay, the DB, or a policy decision
        ▼
INTENT → AI COMMERCE DISCOVERY GATEWAY (services/catalog) → RECOMMENDATION (services/recommendation)
        │
        ▼
CART (services/cart)        revalidated against merchant adapters — server-authoritative
        │                    price/availability, never a client-supplied amount
        ▼
AUTHORIZATION SERVICE (services/authorization)      is this mandate/session allowed to
        │                                            transact at all (validity/expiry/scope)
        ▼
COMMERCE POLICY ENGINE (domain/commerce/policy.py)  is THIS cart valid: budget / inventory /
        │  PASS                          │ REJECT   price / merchant availability / attributes
        │                                ▼
        │                     surfaced + audited, ZERO Razorpay calls
        ▼
INTERNAL ORDER (services/order)     idempotent, the canonical Aalok identity
        │
        ▼
RAZORPAY PROVIDER (integrations/razorpay)   Order → Standard Checkout → Payment → Signature verify
        │
        ▼
WEBHOOK CONFIRMATION (api/routes/webhooks)   idempotent, signature-verified
        │
        ▼
ORDER CONFIRMED → AUDIT TRAIL → ANALYTICS
        (REFUND SERVICE hangs off a confirmed order, same audit/idempotency discipline)
```

Razorpay remains the only component in this system that ever moves real money. Aalok's
job is everything *before* that: intent → discovery → cart → **bounded, gated** authorization
to transact.

## 2. System architecture — modular monolith

One FastAPI process, organized by domain boundary, not by microservice:

```
backend/
  main.py            app factory: routers, startup, static mount
  core/               config.py, errors.py
  domain/             pure data + business rules — no I/O
    catalog/            Product (unified schema), Merchant, MerchantCapabilities
    cart/                Cart, CartItem, CartStatus
    commerce/             Intent, Authorization(+Mode/Status), IntentMandate/CartMandate, PolicyEngine
    orders/                InternalOrder, OrderStatus, CheckoutMode
    payments/               PaymentStatus, PaymentCapability, RazorpayOrderReference
    refunds/                 Refund, RefundStatus
    audit/                    named audit event-type constants
  services/            orchestration — calls domain + integrations + repositories
    agent/               intent parsing, the AI tool layer, the Gemini function-calling
                          loop, grounded recommendation finalization
    catalog/               federated search (gateway.py) + hybrid ranking (ranking.py)
    recommendation/          grounded complements/substitutes/upsell
    cart/                     CartService
    authorization/             AuthorizationService
    order/                      OrderService  (the ONE checkout path)
    payment/                     PaymentService
    refund/                       RefundService
    analytics/                     platform/merchant analytics + agentic funnel
    session/                        server-side session state
  integrations/         talks to the outside world
    llm/gemini.py          hard-timeout wrapper around the Gemini SDK
    merchants/               MerchantAdapter + 9 synthetic merchant adapters + registry
    razorpay/                  PaymentProvider (Mock + Real) + documented MCP extension point
  repositories/          SQLite persistence
    db.py, audit_repo.py, order_repo.py, refund_repo.py
  api/routes/            thin FastAPI routers — validate → call service → return
```

No microservices, no Kubernetes, no Kafka/Redis/Postgres/vector DB — SQLite + a modular
monolith is sufficient for this prototype (spec section 24/deferred capabilities below).

## 3. Request lifecycle

```
Intent → Authorization → Cart → Policy evaluation → InternalOrder → RazorpayOrder →
Payment attempt → Payment verification → Webhook confirmation → Order confirmed [→ Refund]
```

Five independent state machines are tracked, never conflated: `CartStatus`,
`AuthorizationStatus`, `OrderStatus`, `PaymentStatus`, `RefundStatus` (each in its own
`domain/*/models.py`, with an explicit allowed-transitions table — illegal transitions raise
rather than being silently assigned).

## 4. AI Commerce Discovery Gateway & catalog federation — **IMPLEMENTED NOW**

`services/catalog/gateway.py::search_catalog()` is the ONE place the AI (or an external
caller) searches every connected merchant:

```
search_catalog(query, category, max_price, min_price, location, filters, merchant_ids)
       │
       ▼  fan out in parallel (ThreadPoolExecutor) to every matching MerchantAdapter
raw per-merchant results (already normalized to Product by each adapter's _normalize())
       │
       ▼  availability hard-filter → dedupe by product_id → hybrid rank (ranking.py)
Unified Product results
```

One merchant adapter raising `MerchantAdapterError` (the mock equivalent of a real
merchant's API being down) is caught and skipped — it never breaks a federated search
across the rest (`tests/test_catalog_gateway.py::test_one_merchant_failing_does_not_break_the_others`).

Ranking (`services/catalog/ranking.py`) is hybrid, not pure-semantic: a deterministic
hard-filter (price/delivery-time/attributes/availability) runs first in plain code, and only
the survivors are semantically re-ranked by Gemini text embeddings against the free-text
query — falling back to price-ascending order if no LLM key is configured. This keeps hard
numeric constraints outside the LLM's "judgment", the same principle that governs the
payment gate.

Aalok never claims to own a universal merchant/product database — the research this
project is grounded in is explicit that **Razorpay does not provide one either**; each
`Merchant` here is an explicitly synthetic, fictional brand (see section 8).

## 5. Unified Commerce Schema — **IMPLEMENTED NOW**

`domain/catalog/schema.py::Product` is one canonical representation spanning food, grocery,
fashion, beauty, electronics, jewellery, entertainment and services:

```
product_id, merchant_id, merchant_name, category, subcategory, title, description, brand,
price, currency, mrp, discount, availability, variants, attributes, images, delivery,
location, offers, relationships{complement_ids, substitute_ids}, policies, deep_link, ai_metadata
```

Category-specific facts (`dietary_tags`, `size`/`color`/`material`, `tech_specs`, `metal`/
`purity`, `screen_type`, `validity_days`, …) live inside `attributes` — never as new
top-level fields. `Merchant` (`domain/catalog/merchant.py`) is deliberately a *separate*
schema (identity, category, capabilities, policies, fulfillment) rather than being folded
into every one of its products — closer to how a real merchant-owned commerce system is
actually shaped.

`MerchantCapabilities` (`domain/catalog/capabilities.py`) — `catalog`, `checkout`,
`refunds`, `subscriptions`, `marketplace`, `agentic_checkout` — lets the commerce layer
represent heterogeneous merchants instead of assuming every merchant behaves identically.
Every synthetic merchant in this project has `catalog=True, checkout=True` and everything
else `False`.

## 6. Merchant adapter architecture — **IMPLEMENTED NOW (synthetic only)**

```python
class MerchantAdapter(ABC):
    def search(self, query, filters) -> list[Product]: ...
    def get_product(self, product_id) -> Product | None: ...
    def check_availability(self, product_id) -> bool: ...
    def get_delivery_estimate(self, product_id, location) -> dict: ...
```

`create_cart`/`create_order` are deliberately **not** part of this interface — cart and
order are Aalok-owned domain concepts (`services/cart`, `services/order`), not
merchant-owned ones. A real adapter would only ever be asked for catalog/availability/
delivery facts.

Each adapter *instance* is one merchant. 9 merchants are connected:

| Merchant | Category | Products | Notes |
|---|---|---|---|
| 8 restaurants (`food_adapter.py`) | food | ~35 dishes | reuses the project's original, already-sourced food catalog verbatim (one adapter instance per restaurant) |
| FreshKart (`grocery_adapter.py`) | grocery | 10 | synthetic, BigBasket-style |
| ZipMart (`quickcommerce_adapter.py`) | grocery (quick-commerce) | 8 | synthetic, Zepto-style, sub-15-min delivery |
| Threadloom (`fashion_adapter.py`) | fashion | 9 | synthetic |
| GlowNest (`beauty_adapter.py`) | beauty | 8 | synthetic, Honasa-style |
| CircuitBay (`electronics_adapter.py`) | electronics | 8 | synthetic |
| Aurelia (`jewellery_adapter.py`) | jewellery | 8 | synthetic, BlueStone-style |
| CineHall (`entertainment_adapter.py`) | entertainment | 8 | synthetic, PVR-style (tickets + concessions) |
| ConnectPlus (`services_adapter.py`) | services | 8 | synthetic, Vi-style (recharge/broadband/DTH) |

Every non-food adapter ships raw seed data in that merchant's own field-naming convention
(e.g. grocery's `mrp`/`pack_size`, fashion's `size`/`color`, jewellery's `metal`/`purity`) and
a `_normalize()` step that turns it into `Product` — a genuine normalization pass, not a
schema pass-through. **None of these are real integrations** — no real Swiggy/Zomato/
BigBasket/Zepto/BlueStone/PVR/Vi API or data is used anywhere in this project.

**How to add a real merchant adapter later:** implement `MerchantAdapter`'s four methods
against the real API, register the instance in `integrations/merchants/registry.py`, and
nothing else in the codebase changes — the gateway, cart, policy, and order layers are all
already merchant-agnostic.

**How an MCP-compatible merchant connector would eventually fit:** the same shape — an
adapter that satisfies `MerchantAdapter` by calling MCP tools instead of REST. Not built in
this project (no such synthetic merchant needed it), but the interface is what would host it.

## 7. Authorization vs. the Commerce Policy Engine — **IMPLEMENTED NOW**

Two distinct, both deterministic, both mandatory, both audited:

- **`AuthorizationService.check`** (`services/authorization/service.py`) — is this
  mandate/session even permitted to attempt a transaction of this shape at all? Checks
  mandate validity, expiry, revocation, and merchant/category scope. Runs first.
- **`PolicyEngine.evaluate_cart`** (`domain/commerce/policy.py`) — is *this specific* cart's
  amount/inventory/price/merchant-availability/attributes valid? Runs second, immediately
  before order creation.

`AuthorizationMode`: `ONE_TIME_CHECKOUT` (MVP default), `USER_MANDATE` (a longer-lived
mandate reusable across checkouts within its bounds), `FUTURE_AGENTIC_RESERVE` (a named
placeholder only — see section 12; constructing one raises `AuthorizationError`, nothing
simulates it).

`PolicyDecision` (`domain/commerce/policy.py`) returns exactly:

```json
{
  "allowed": false,
  "reason": "Cart total 218.0 exceeds the authorized spend ceiling 180.0 (over by 38.0).",
  "checks": {
    "mandate_validity": {"status": "PASS"}, "cart_expiry": {"status": "PASS"},
    "budget": {"status": "FAIL", "cart_total": 218.0, "maximum": 180.0},
    "delivery_time": {"status": "PASS"}, "merchant_availability": {"status": "PASS"},
    "inventory": {"status": "PASS"}, "attributes": {"status": "PASS"}
  },
  "mandate_id": "intent-...", "cart_total": 218.0, "max_allowed": 180.0,
  "timestamp": "...", "decision": "REJECT"
}
```

Zero LLM calls, zero prompt-based authorization. The LLM proposes a cart; it never sees,
calls, or can influence either check — both live inside `services/order/service.py`'s
`checkout()`, the only route to Razorpay order creation.

## 8. AI tool boundary — **IMPLEMENTED NOW**

`services/agent/tools.py` is the entire surface the LLM is ever handed:

```
search_catalog, get_product, compare_products, check_availability, get_delivery_estimate,
find_complements, find_substitutes, create_cart, modify_cart, get_cart, get_order_status
```

The LLM structurally **cannot** reach `create_razorpay_order`, `capture_payment`,
`refund_payment`, `verify_payment`, the webhook secret, DB credentials, or a policy-override
path — those symbols do not exist in the tools module (`tests/test_ai_tool_boundary.py`
asserts this directly, both via the declared tool list and via module-namespace inspection).
`create_cart`/`modify_cart` only ever **propose** a cart; nothing in `tools.py` can call
`OrderService.checkout()` or a `PaymentProvider`.

```
LLM → tool (tools.py) → service layer → Authorization + Policy → Order/Payment service → Razorpay
```

Every tool degrades gracefully on malformed input, a nonexistent product, or a fabricated
product id — it returns `{"error": ...}`, never raises, so a tool-calling loop never crashes
mid-conversation.

## 9. Cart lifecycle — **IMPLEMENTED NOW**

`services/cart/service.py::CartService`. MVP multi-merchant policy (spec section 12,
"preferred MVP"): **one merchant per cart/order/payment**. `Cart.merchant_id` is fixed at
creation; `add_item` raises `CartMerchantMismatchError` on a cross-merchant add. The AI can
present results from multiple merchants together in a conversation, but checkout is always
per-merchant — Aalok never claims a fake "universal checkout" the payment layer can't
actually settle. `CheckoutMode.MARKETPLACE` names the future extension point (section 12)
without implementing it.

`revalidate(cart)` re-fetches every item's authoritative product from its owning merchant
adapter and recomputes `subtotal/discount/delivery_fee/tax/total` server-side — this always
runs, inside `OrderService.checkout`, before Authorization/Policy. A client-supplied amount
can never reach Razorpay (`tests/test_security_boundary.py`).

## 10. Internal order / Razorpay order / checkout / payment lifecycle

```
InternalOrder                              RazorpayOrderReference
  internal_order_id  ← canonical identity     razorpay_order_id
  cart_id, cart_version                        amount, currency, status, receipt
  merchant_id, session_id
  amount, currency
  status: OrderStatus                        (a REFERENCE InternalOrder carries —
  razorpay_order_id ────────────────────────►  Aalok's own domain is never
  payment_id                                   dependent on Razorpay's ids)
  idempotency_key
```

`OrderService.checkout(cart, intent, authorization)`:

```
revalidate → lock CartMandate → Authorization.check → REJECT (0 Razorpay calls)
                                       │ PASS
                                Policy.evaluate_cart → REJECT (0 Razorpay calls)
                                       │ PASS
                          reuse-or-create InternalOrder (idempotent, section 11)
                                       │
                          PaymentService.attempt_payment
                              │              │                    │
                          captured        failed            requires_checkout_js
                        (mock only)    (retryable,          (REAL test mode: nothing
                                        same order)           is simulated — waits for
                                                               Checkout.js + signature
                                                               verification/webhook)
```

Both Aalok's own conversational agent (`/api/order/confirm`) and an external AI buyer
(`/api/external/purchase`) call this exact same method — not just "the same logic", the same
code path (`tests/test_ai_buyer.py::test_external_buyer_uses_the_same_gate_as_the_chat_agent`
asserts this via `inspect.getsource`).

## 11. Idempotency — **IMPLEMENTED NOW**

`Cart.version` increments on every mutation (add/modify/remove item).
`OrderService` keys a pending order by `checkout:{cart_id}:{cart_version}`
(`Cart.idempotency_key()`). On `checkout()`:

- no pending order for this key → create exactly one `InternalOrder` + one Razorpay order
- a pending order exists and isn't `CAPTURED` → **reuse it** (a retry after a failed
  payment attempt never creates a second order)
- a pending order exists and **is** `CAPTURED` → short-circuit before Authorization/Policy
  even run, return the existing result, make zero further Razorpay calls

Proven in `tests/test_payment_safety.py`: `test_retry_reuses_the_same_razorpay_order_id`,
`test_duplicate_checkout_on_an_already_captured_cart_makes_no_new_order_call`.

Refunds get their own idempotency: `RefundService.create_refund` rejects a second request
against an `internal_order_id` that already has a `requested`/`processed` refund
(`tests/test_refund.py::test_duplicate_refund_is_rejected_not_duplicated`).

## 12. Razorpay boundary — what's real, what's test mode, what's mocked

| Aalok concept | Razorpay object/API | Status |
|---|---|---|
| `InternalOrder` | Orders API (`POST /v1/orders`) | **IMPLEMENTED** — real REST call in test mode, `PAYMENT_PROVIDER=razorpay_test` |
| Checkout | Standard Checkout (Checkout.js) | **IMPLEMENTED** — real widget, unmodified frontend flow |
| Payment capture/state | Payments API (`fetch_payment`) | **IMPLEMENTED** |
| Signature verification | `HMAC-SHA256(order_id\|payment_id, key_secret)` | **IMPLEMENTED** — Razorpay's documented algorithm |
| Webhook | `X-Razorpay-Signature` + `X-Razorpay-Event-Id` dedupe | **IMPLEMENTED** |
| Refunds | `POST /v1/payments/{id}/refund` | **IMPLEMENTED** (mock + real-REST-shape test mode) — new in this refactor |
| Mock mode | n/a | **IMPLEMENTED** — every response tagged `"mode": "mock"`, exercises the full flow with zero network calls |
| Route / Linked Accounts (marketplace settlement) | split payments across sub-merchants | **ARCHITECTURAL EXTENSION ONLY** — `CheckoutMode.MARKETPLACE` enum value exists, no logic |
| UPI Reserve Pay (Razorpay's live "Agentic Payments" product) | consent-based, pre-authorized payments within a spending limit | **NOT IMPLEMENTED / NOT CLAIMED** — real and live per Razorpay's own site, but no self-serve API reference is available to this project (partnership sign-up only, no open developer docs found). `AuthorizationMode.FUTURE_AGENTIC_RESERVE` names the conceptual slot only; Aalok's own deterministic Authorization+Policy engine is what actually enforces spending bounds today, and nothing here ever claims to be calling real Reserve Pay |
| Agentic Payments on LLMs / Voice AI Payments | in-conversation purchase | **NOT AVAILABLE** — Razorpay's own site lists these as "coming soon" |
| Payment Links, Invoices, Subscriptions, QR Codes | | **NOT IMPLEMENTED** — real Razorpay products, out of scope for a one-time single-merchant checkout MVP; represented only as unused `PaymentCapability` enum values |
| Razorpay MCP Server (`razorpay-mcp-server`, 35+ tools) | merchant back-office automation (orders/payments/refunds/QR/settlements/payouts) | **ARCHITECTURAL EXTENSION POINT ONLY** (`integrations/razorpay/mcp_adapter.py`) — real official product, but it is a *merchant back-office* automation surface, not a consumer-checkout one. If wired in later it would sit behind `PaymentProvider` as an alternate transport, reachable only by Aalok's own deterministic order/payment logic — **never** exposed to the shopping LLM |
| Razorpay Agent Studio / Agentic Experience Platform | B2B agent marketplace for merchant payment-ops (disputes, dunning, reconciliation), built on the Claude Agent SDK | **NOT INTEGRATED** — a real, different Razorpay initiative solving a different problem (merchant back-office automation, not a consumer-facing AI shopping agent) |

`PaymentProvider` (`integrations/razorpay/provider.py`) is a clean interface —
`create_order/fetch_order/attempt_payment/fetch_payment/verify_checkout_signature/
verify_webhook_signature/create_refund/fetch_refund` — with `MockProvider` and
`RazorpayProvider` implementations. `get_active_provider()`/`PaymentProviderMisconfigured`
enforce **no silent fallback**: `PAYMENT_PROVIDER=razorpay_test` with missing keys fails
loudly at call time, never quietly degrades to a mocked payment mid-demo.

## 13. Webhook lifecycle — **IMPLEMENTED NOW**

```
raw request body → verify X-Razorpay-Signature (HMAC-SHA256, RAZORPAY_WEBHOOK_SECRET)
    → dedupe on X-Razorpay-Event-Id → WebhookEventRouter dispatch
    → payment.captured / order.paid / payment.failed → PaymentService + OrderService
    → refund.processed → RefundService
    → audit event → 200
```

No `RAZORPAY_WEBHOOK_SECRET` configured → the endpoint refuses to process **anything**
(`501`), never silently accepting an unverified delivery. Ordering/at-least-once delivery is
never assumed; a duplicate event id is a no-op (`tests/test_razorpay_integration.py`).

## 14. Audit trail — **IMPLEMENTED NOW**

SQLite-backed (`repositories/db.py` + `audit_repo.py`), one `audit_events` row per
significant step, using the named vocabulary in `domain/audit/events.py`:

```
intent_captured, authorization_created/checked/expired/revoked, user_confirmation_required/received,
catalog_search, recommendation_generated, cart_created, cart_modified,
policy_evaluated/passed/rejected, order_created, order_reused, order_confirmed,
payment_attempted/failed/captured, payment_retry, webhook_received,
refund_requested, refund_completed
```

Never logs chain-of-thought or secrets — only inputs necessary for verification, decisions,
ids, amounts, policy results, and provider references.

## 15. Analytics / event architecture — **IMPLEMENTED NOW**

`services/analytics/service.py` derives platform + per-merchant metrics (AOV, conversion,
upsell acceptance, AI-attributable revenue) from the real `orders` table, plus an
**agentic-commerce funnel** derived from the real `audit_events` table (`agentic_funnel()`):
`intent_captured → catalog_search → recommendation_generated → cart_created →
authorization_checked → policy_passed → payment_attempted → payment_captured →
order_confirmed`, with derived conversion rates and rejection/failure/retry counts.

`experiments/growth_experiment.py` remains the explicitly-labeled **SYNTHETIC BENCHMARK /
SIMULATION** — deterministic, seeded, using real catalog prices, but never mixed with the
real analytics above.

## 16. Known limitations (genuine, not additional feature ideas)

- In-memory session/cart/order state (`services/session`, `services/cart`,
  `services/order`) — fine for a single-process prototype; a production build would move
  this to Redis/a DB keyed by authenticated session, as the pre-refactor code already noted.
- The Gemini function-calling agent loop (`services/agent/orchestrator.py`) was not
  exercised against a live Gemini API in this environment (no outbound network access
  confirmed here); every code path was built to degrade to the deterministic fallback and is
  exercised that way by the test suite and the manual smoke test. The pattern (hard-timeout
  wrapper, heuristic fallback) is unchanged from the pre-refactor code, which was itself
  built and demoed under the same constraint.
- Recommendation quality in the no-LLM fallback path is a hard-filter + price-sort, exactly
  as before — it finds a constraint-satisfying item, not necessarily the *most relevant* one,
  without semantic ranking.
- `RefundService` has no UI (not required by spec) — API + tests only.
- The legacy food-only routes (`/api/chat`, `/api/order/quick-add`) translate the Unified
  Commerce Schema back into the pre-refactor dish-shaped response (`api/routes/_legacy.py`)
  so `frontend/app.js` needs zero changes; the Commerce Policy Engine's check *names* in
  that JSON did change (e.g. `price` → `budget`, `restaurant` → `merchant_availability`) as
  part of generalizing the engine — the frontend's policy-card renderer falls back to
  showing the raw check name/status for any name it doesn't have a pretty label for, so the
  flow still works end-to-end, just with slightly less polished labels for the renamed
  checks. Editing `frontend/app.js`'s label maps was out of scope for this backend-only task.
