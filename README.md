<div align="center">

# Aalok

**The deterministic gate between an AI agent's judgment and a merchant's money.**

Built for Razorpay's AI Buildathon — Track: **AI Growth & Agentic Commerce**

<br/>

![Track](https://img.shields.io/badge/track-AI%20Growth%20%26%20Agentic%20Commerce-0c0a09?style=flat-square)
![Python](https://img.shields.io/badge/python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-0c0a09?style=flat-square&logo=fastapi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-99%20passing-3FA66B?style=flat-square)
![Payments](https://img.shields.io/badge/Razorpay-Test%20Mode-528FF0?style=flat-square&logo=razorpay&logoColor=white)
![Runtime](https://img.shields.io/badge/db-SQLite%2C%20no%20Docker-777169?style=flat-square)
![UI](https://img.shields.io/badge/frontend-one%20screen-0D9488?style=flat-square)

</div>

<br/>

> **The interface is deliberately one screen. The system behind it is not.**
>
> Aalok's entire user-facing product is: ask a question, see results, add to cart, check out.
> Underneath that sits a federated catalog across 16 merchant adapters, an LLM tool-calling
> orchestrator with a hard structural boundary against payment code, a deterministic
> non-LLM policy engine, an authorization/mandate layer, idempotent order creation, real
> Razorpay Test Mode integration with server-side signature verification, webhook handling,
> refunds, and a full audit trail. **None of that is a screen. All of it runs.**

<br/>

## Table of contents

| | |
|---|---|
| [What is Aalok?](#-what-is-aalok) | [Deterministic policy engine](#-deterministic-policy-engine) |
| [Problem](#-problem) | [Authorization / mandates](#-authorization--mandates) |
| [Core user journey](#-core-user-journey) | [Payment architecture](#-payment-architecture) |
| [What was removed from the UI](#-what-was-removed-from-the-ui-and-what-still-runs-underneath) | [Razorpay Test Mode](#-razorpay-test-mode) |
| [Architecture](#-architecture) | [Idempotency](#-idempotency) |
| [Agent architecture](#-agent-architecture) | [Payment retry](#-payment-retry) |
| [Product retrieval](#-product-retrieval) | [Audit trail](#-audit-trail) |
| [Recommendation system](#-recommendation-system) | [Merchant architecture](#-merchant-architecture) |
| [Voice interaction](#-voice-interaction) | [Demo scenarios](#-demo-scenarios) |
| [Technical architecture](#-technical-architecture) | [Project structure](#-project-structure) |
| [Quick start](#-quick-start) | [Testing](#-testing) |
| [Configuration](#-configuration) | [Limitations](#-limitations) |

<br/>

---

## ▸ What is Aalok?

Aalok is an **AI-native commerce orchestration layer**. A shopper states an intent in plain
language — *"find me running shoes under ₹3000"* — and one agent searches every connected
merchant, compares across them, explains its pick, builds a cart, and takes the payment.

The thing that makes it more than a chat wrapper is what sits between the agent's
recommendation and the merchant's money: a **deterministic Commerce Policy Engine** that
re-derives every fact from the server and either passes or rejects the cart in plain Python.
The LLM proposes. It never authorizes.

Aalok federates **16 synthetic merchants across 8 categories** — food, grocery, fashion,
beauty, electronics, jewellery, entertainment and services. Every merchant in this
environment is synthetic; there is no real Swiggy/Zomato/BigBasket/Zepto integration
anywhere in the codebase.

<br/>

---

## ▸ Problem

Agentic commerce has an authorization problem, not a capability problem. An LLM that can
call `create_order()` is easy. An LLM that can be *trusted* to call it is not.

Three failures make agent-driven purchasing unshippable today:

1. **Hallucinated commerce.** A model that invents a product, a price, or an availability
   window will happily charge a card for it.
2. **Unbounded spend.** "Book me a table" and "book me the ₹40,000 tasting menu" are the
   same sentence to a model that has no ceiling.
3. **Unexplainable money movement.** When an agent charges a customer, someone has to be
   able to reconstruct *why* — for the customer, for support, and for the regulator.

Aalok's answer is a hard architectural split. The agent is given a **read/propose-only tool
surface** that structurally cannot reach a payment provider. Every cart it proposes is
re-validated against server-authoritative price and inventory, then gated by a deterministic
policy engine. Every step is written to an audit trail.

<br/>

---

## ▸ Core user journey

The entire product is one screen with two states.

```
  ┌─────────────────────────────────────────────────────────────┐
  │  1. LANDING            "Just ask Aalok"                      │
  │                        one input · type or speak             │
  └───────────────────────────┬─────────────────────────────────┘
                              │  user states an intent
                              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  2. CONVERSATION       user turn · agent reply · product     │
  │                        cards from every merchant, inline     │
  │                        (this replaces Discover + Merchants)  │
  └───────────────────────────┬─────────────────────────────────┘
                              │  add to cart
                              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  3. CART DRAWER        items · qty · subtotal · total        │
  └───────────────────────────┬─────────────────────────────────┘
                              │  checkout
                              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  4. AUTHORIZATION      payment result + the full receipt of  │
  │     + PAYMENT          every deterministic check that ran    │
  │                        (this replaces Orders + Audit)        │
  └─────────────────────────────────────────────────────────────┘
```

There is no navigation. There is no sidebar. There is one thing to do: **ask Aalok.**

<br/>

---

## ▸ What was removed from the UI (and what still runs underneath)

Aalok previously exposed every subsystem as its own dashboard page. That made it read as an
ecommerce admin console rather than a consumer product, so the dashboards were removed from
the interface. **The engineering they rendered was not removed** — it still powers the single
experience, is still routed, and is still tested.

| Removed screen | What backed it | Where that capability lives now |
|---|---|---|
| **Overview** — KPI cards, trend chart, activity table | `GET /api/analytics`, `GET /api/audit` | Routes live; the landing hero replaced the page |
| **Discover** — filterable federated product grid | `GET /api/catalog/search` | **Inside the conversation.** The agent runs the same federated gateway and renders results as cards |
| **Merchants** — merchant table + capability matrix | `GET /api/merchants` | Still fetched at boot; backs the authorization card's merchant + category rows |
| **Orders** — order list | `GET /api/orders`, `GET /api/orders/{id}` | Routes live and tested; the order result appears in the checkout drawer instead |
| **Payments** — payment/refund tables | `GET /api/payments/refunds`, refund service | Routes live and tested (`tests/test_refund.py`) |
| **Analytics** — funnel, category, merchant performance, growth experiment | `GET /api/analytics`, `GET /api/growth/experiment` | Routes live and tested (`tests/test_growth_experiment.py`) |
| **Audit Trail** — event timeline | `GET /api/audit` | **Inside the checkout.** The authorization card renders the real policy decision contextually |
| **Settings** | `GET /api/payment-mode` | The payment-mode chip in the header |

Deleted frontend files: 9 page modules, the hash router, and 7 dashboard-only components
(`statCard`, `chart`, `table`, `timeline`, `statusPill`, `skeleton`, `emptyState`), plus the
sidebar/topbar stylesheet and the Chart.js CDN dependency.

Deleted backend code: **one route** — `GET /analytics`, which served the SPA shell for a page
that no longer exists. Nothing else.

<br/>

---

## ▸ Architecture

A modular monolith. Dependencies point strictly inward; `domain/` imports nothing from
`services/`, and `services/` imports nothing from `api/`.

```
   api/routes/          thin FastAPI routers — HTTP concerns only
        │
        ▼
   services/            orchestration: agent, catalog, recommendation,
        │               cart, authorization, order, payment, refund, analytics
        ▼
   domain/              pure rules + data. No I/O. PolicyEngine lives here.
        ▲
        │
   integrations/        LLM (Gemini), 9 merchant adapters, Razorpay provider
   repositories/        SQLite persistence + audit log
```

The critical path — the only way money can move:

```
  user message
      │
      ▼
  parse_intent()                       LLM or deterministic keyword fallback
      │
      ▼
  IntentMandate.create()               spend ceiling · time ceiling · attributes
      │
      ▼
  run_commerce_agent()                 Gemini tool-calling loop over tools.py
      │                                (read/propose only — cannot reach payments)
      ▼
  cart proposed
      │
      ▼
  ┌─────────────────────────────────────────────────────────┐
  │  OrderService.checkout()  ← THE single path             │
  │                                                          │
  │   1. cart_service.revalidate()   server-authoritative    │
  │                                  price + inventory       │
  │   2. CartMandate.create()        immutable snapshot      │
  │   3. AuthorizationService.check()  may this session      │
  │                                    transact at all?      │
  │        └─ REJECT → return. Zero Razorpay calls.          │
  │   4. PolicyEngine.evaluate_cart()  is THIS cart valid?   │
  │        └─ REJECT → return. Zero Razorpay calls.          │
  │   5. reuse-or-create InternalOrder  (idempotency key)    │
  │   6. PaymentService.attempt_payment()                    │
  └─────────────────────────────────────────────────────────┘
```

Aalok's own agent (`POST /api/agent/chat` → cart → `POST /api/orders`) and a third-party AI
buyer (`POST /api/external/purchase`) call **literally the same method** — not "the same
logic", the same code path. There is no privileged route. `tests/test_security_boundary.py`
asserts this.

<br/>

---

## ▸ Agent architecture

Three stages, each independently degradable.

**1. Intent parsing** — `services/agent/intent.py`

Extracts category, budget ceiling, delivery-time requirement and required attributes from
free text. Uses Gemini when `GEMINI_API_KEY` is set; falls back to a deterministic keyword
and regex map covering all 8 categories when it isn't. The fallback is not a stub — the whole
product works offline through it.

**2. Tool-calling loop** — `services/agent/orchestrator.py`

A Gemini function-calling loop over the tool surface below. The model may call any tool any
number of times (bounded by `max_turns`), then **must** call `finalize_recommendation` exactly
once as its last action — a forced structured-output step. `finalize_recommendation` is
deliberately *not* in `ALL_TOOL_DECLARATIONS`: it is loop control, not a commerce operation.

**3. The tool boundary** — `services/agent/tools.py`

This module is the entire surface the LLM is ever handed:

```
search_catalog · get_product · compare_products · check_availability
get_delivery_estimate · find_complements · find_substitutes
create_cart · modify_cart · get_cart · get_order_status
```

Two properties are enforced structurally, not by convention:

- **Nothing raises.** Every tool returns a plain dict, using an `{"error": ...}` shape on
  failure, so a model calling a tool with fabricated or malformed arguments degrades the loop
  gracefully instead of crashing the request.
- **Nothing can move money.** The module does not import, reference or expose a Razorpay
  client, a payment provider, a webhook secret, a database credential, or any policy-override
  path. `create_cart` and `modify_cart` only ever *propose*. Nothing in the file can reach
  `OrderService.checkout()`.

`tests/test_ai_tool_boundary.py` asserts this by inspecting `ALL_TOOL_DECLARATIONS` and the
module's own globals — so the boundary fails a test if someone adds an import, rather than
failing in production.

If Gemini is unreachable or times out (`integrations/llm/gemini.py` enforces a hard overall
timeout), the loop degrades to `commerce_agent.py`'s deterministic path. The product does not
hang and does not stop working.

<br/>

---

## ▸ Product retrieval

**Federation** — `services/catalog/gateway.py`

One `search_catalog()` call fans out across every registered merchant adapter and returns a
single unified list. Every product is normalised into the **Unified Commerce Schema**
(`domain/catalog/schema.py`) so a jewellery item, a cinema ticket and a plate of dosa carry
the same top-level shape — `product_id`, `merchant_id`, `title`, `price`, `mrp`, `currency`,
`availability`, `delivery`, `attributes`, `relationships` — with category-specific fields
living inside `attributes` rather than forking the schema.

**Hybrid ranking** — `services/catalog/ranking.py`

Retrieval is deliberately hybrid, because embeddings are unreliable at hard numeric
constraints:

1. **Deterministic hard filter, in plain code** — price ceiling, delivery-time ceiling,
   required attributes, availability. A budget is never "semantically" satisfied.
2. **Semantic re-rank, within the survivors** — Gemini `text-embedding-004` ranks the
   remaining candidates by similarity to the user's free-text intent.

With no API key, step 2 falls back to price-ascending order. The hard filter never falls back,
because it is the part that carries the guarantee.

<br/>

---

## ▸ Recommendation system

`services/recommendation/service.py`, kept deliberately separate from retrieval.

Catalog search returns candidates; the recommender picks a primary and — critically — grounds
any upsell in a **declared catalog relationship**. An upsell candidate must appear in the
primary product's `relationships.complement_ids`, populated by the merchant adapter's own seed
data.

> The LLM may explain *why* a pairing is useful. It never gets to decide that the pairing
> exists.

This replaced an earlier food-only heuristic (restrict upsells to beverage/dessert-tagged
dishes) that did not generalise across categories. Rather than carry a heuristic forward into
7 more verticals, the rule was tightened to require real data.

<br/>

---

## ▸ Deterministic policy engine

`domain/commerce/policy.py`. **Non-LLM. This is the load-bearing component.**

`PolicyEngine.evaluate_cart()` is the only function allowed to decide whether a proposed cart
may proceed toward a Razorpay order. It runs identically for Aalok's own agent and for an
external AI buyer. It emits a per-check breakdown, not a pass/fail bit:

| Check | What it asserts |
|---|---|
| `mandate_validity` | The IntentMandate is still active and unexpired |
| `cart_expiry` | The cart snapshot hasn't aged out |
| `budget` | `cart_total ≤ max_amount` — the spend ceiling |
| `delivery_time` | Estimated delivery ≤ the stated ceiling (unbounded when none was stated) |
| `merchant_availability` | The merchant is actually open |
| `inventory` | Every line item is currently available, re-fetched from the adapter |
| `attributes` | Required attributes (e.g. dietary constraints) hold for every item |

The returned `PolicyDecision` carries `{allowed, decision, reason, reasons, checks,
mandate_id, cart_total, max_allowed, timestamp}`. **Every row rendered in the checkout drawer
is a live field from this object** — the UI paraphrases nothing.

A rejection returns *before any Razorpay call is made*. The response's `razorpay_called` flag
is `False`, and that is asserted in `tests/test_mandates.py`.

<br/>

---

## ▸ Authorization / mandates

`domain/commerce/mandates.py`, `domain/commerce/authorization.py`,
`services/authorization/service.py`.

Two mandates, one nested inside the other:

- **IntentMandate** — created the moment intent is captured. Carries `max_amount`,
  `max_delivery_time_min`, `dietary_constraint`, `required_attributes`, and an expiry. This is
  the user's stated envelope.
- **CartMandate** — created at checkout, snapshotting the *actual* cart (items, prices,
  merchant, merchant-open state, estimated delivery) against its parent IntentMandate. It is
  immutable: prices are locked from a server re-fetch, never from what the client sent.

**Authorization** is a separate gate that runs *before* policy, answering a different
question. Policy asks "is this cart valid?"; authorization asks "may this session transact at
all?" — checking mode, status and scope.

```
AuthorizationMode:    ONE_TIME_CHECKOUT (default — consumed on first capture)
                      USER_MANDATE      (longer-lived, reusable across checkouts)
                      FUTURE_AGENTIC_RESERVE (declared, deliberately NOT implemented)

AuthorizationStatus:  ACTIVE · EXPIRED · REVOKED · CONSUMED
```

Neither gate can be skipped. Neither is an LLM call.

<br/>

---

## ▸ Payment architecture

`services/payment/service.py` + `integrations/razorpay/provider.py`.

A `PaymentProvider` abstract base defines the full surface — `create_order`, `fetch_order`,
`attempt_payment`, `fetch_payment`, `verify_checkout_signature`, `verify_webhook_signature`,
`create_refund`, `fetch_refund` — with two implementations behind it:

- **`MockProvider`** — fully offline. Every response carries `"mode": "mock"`.
- **`RazorpayProvider`** — the real Test Mode REST API.

`get_active_provider()` resolves which is live and reports it honestly through
`GET /api/payment-mode`, which is what the header chip reads. There are four possible states:
`mock`, `test`, `misconfigured`, and mock-forced-despite-real-keys-present.

**Aalok never fails silently into mock mode.** If `PAYMENT_PROVIDER=razorpay_test` is set but
keys are missing, checkout returns `provider_misconfigured` and says so in the UI. A demo that
quietly degrades to fake payments is worse than one that stops.

Aalok also never re-implements payment collection UI. Real Test Mode checkout loads
**Razorpay's own Checkout.js widget** (`frontend/js/checkout.js`).

<br/>

---

## ▸ Razorpay Test Mode

What is real, precisely:

| Capability | Status |
|---|---|
| Orders API (`create_order` / `fetch_order`) | **Real** Test Mode REST call |
| Checkout.js widget | **Real** — Razorpay's own script, never re-implemented |
| Checkout signature verification | **Real** HMAC-SHA256, **server-side** |
| Webhook signature verification | **Real** HMAC-SHA256 over the raw body |
| Refunds API | **Real** Test Mode call |
| Payment capture | Test Mode — no real money moves |
| Merchant catalogs | **Synthetic** — 16 seeded adapters, no live merchant integration |

The browser's checkout callback is **never trusted on its own**. When Checkout.js returns,
the frontend reports the result to `POST /api/order/verify-payment`, and the server
recomputes the HMAC signature before anything is marked captured. A forged callback fails
verification and the order stays pending — asserted in `tests/test_razorpay_integration.py`.

<br/>

---

## ▸ Idempotency

`OrderService` keys orders on `cart.idempotency_key()` — derived from `(cart_id,
cart_version)`. The cart version increments on every mutation, so *modifying* a cart correctly
produces a new order, while *retrying* the same cart does not.

Three behaviours follow:

1. **Retry before capture** → the existing pending `InternalOrder` is reused, including its
   `razorpay_order_id`. No second Razorpay order is created.
2. **Retry after capture** → short-circuits to an idempotent no-op returning the original
   result, with `razorpay_called: False` and `already_captured: True`. This check runs
   *before* re-validation deliberately: a `ONE_TIME_CHECKOUT` authorization is consumed on
   first capture, so naive re-validation would wrongly reject an already-successful re-confirm.
3. **Every reuse is audited** as an `order_reused` event.

`tests/test_payment_safety.py` asserts the same Razorpay order id comes back across a retry.

<br/>

---

## ▸ Payment retry

A failed payment leaves the order **pending**, not dead. The checkout drawer surfaces a
**Retry payment** button that re-runs the identical cart — which is exactly what demonstrates
idempotency, because the drawer prints the Razorpay order id both times and it does not change.

The drawer also carries a **Simulate a failed payment** control next to checkout. It is not a
mock: it sets `force_fail=true` on the real `POST /api/orders` call, so the failure travels the
genuine `PaymentService.attempt_payment` → `payment_failed` path, writes real
`payment_attempted` / `payment_failed` audit events, and produces a genuinely retryable order.

<br/>

---

## ▸ Audit trail

`repositories/audit_repo.py`, with a named event vocabulary in `domain/audit/events.py` — 24
constants rather than string literals scattered across services, so the vocabulary is visible
in one place and typo-proof:

```
intent_captured · authorization_created/checked/expired/revoked
user_confirmation_required/received · catalog_search · recommendation_generated
cart_created · cart_modified · policy_evaluated/passed/rejected
order_created · order_reused · order_confirmed
payment_attempted/failed/captured/retry · webhook_received
refund_requested · refund_completed
```

Every commerce operation that matters writes one. **Chain-of-thought is never logged** — only
concise, user-safe reasoning plus the ids, amounts and decisions needed to reconstruct what
happened.

The trail is queryable at `GET /api/audit?session_id=…`. It no longer has a dashboard page;
the checkout drawer renders the decision that matters at the moment it matters.

<br/>

---

## ▸ Merchant architecture

`integrations/merchants/` — 9 adapter modules registered through `registry.py`, seeding **16
merchants across 8 categories**:

| Category | Merchants |
|---|---|
| Food | Grill & Greens · Spice Route · Wok This Way · Sprout & Steel · Curry Leaf · Basil & Bread · Tandoor Tales · Green Bowl Co. |
| Grocery | FreshKart · ZipMart |
| Fashion | Threadloom |
| Beauty | GlowNest |
| Electronics | CircuitBay |
| Jewellery | Aurelia |
| Entertainment | CineHall |
| Services | ConnectPlus |

Each adapter implements the same interface — catalog listing, product lookup, availability,
delivery estimate — and declares its own **capability matrix** (`domain/catalog/capabilities.py`):
`CATALOG`, `CHECKOUT`, `REFUNDS`, `SUBSCRIPTIONS`, `MARKETPLACE`, `AGENTIC_CHECKOUT`. Capabilities
a synthetic merchant does not actually implement are declared **off** rather than faked.

Merchants also carry real operational state — `open`/`closed`, tier, rating — which the policy
engine reads. Green Bowl Co. is seeded closed specifically so the `merchant_availability` check
has something true to fail on.

<br/>

---

## ▸ Voice interaction

Voice is an **input mode**, not a second product. There is no voice page, no voice route, and
no voice-specific backend.

```
  microphone tap
      │
      ▼
  Web Speech API (SpeechRecognition, en-IN)
      │  interim transcripts stream into the field as you speak
      ▼
  final transcript
      │
      ▼
  sendMessage(text, { viaVoice: true })   ← the SAME function the text
      │                                      composer calls
      ▼
  POST /api/agent/chat                    ← byte-identical request
      │
      ▼
  normal agent reply + product cards
      │
      ▼
  speechSynthesis reads the reply back    ← only when the turn arrived by voice
```

Design decisions worth naming:

- **`en-IN` recognition locale.** The catalog and prices are Indian; this measurably improves
  rupee amounts and product names like *Masala Dosa* or *kurta* over the `en-US` default.
- **Voice in, voice out.** A spoken question gets a spoken answer; a typed one doesn't. That
  keeps the modality the user chose and means no mute toggle has to exist.
- **Only the reply text is spoken**, not the product grid — the cards are already on screen,
  and reading eight of them aloud would be unusable.
- **No dead control.** Firefox and older Safari expose no `SpeechRecognition`. Rather than
  ship a microphone that cannot record, `micButtonHtml()` returns nothing and the button is
  never rendered. Text input is unaffected.
- **Aalok never talks over you.** Opening the microphone cancels any in-flight speech.

Files: `frontend/js/voice.js` (the API wrapper) and `frontend/js/components/composer.js` (the
shared control, rendered at two sizes on the landing and in the conversation).

<br/>

---

## ▸ Demo scenarios

All five run from the single screen. No hidden URLs, no dashboard.

**Demo 1 — the happy path**
> Ask *"Find me running shoes under ₹3000"*. The agent searches every merchant, ranks, and
> explains its top pick. Add it to cart → Checkout. The drawer shows payment captured plus the
> full authorization receipt: budget `₹2,499 / ₹3,000`, mandate valid, cart not expired,
> merchant open, inventory available, delivery constraint, attribute match.

**Demo 2 — deterministic policy rejection**
> Click *"see the policy engine reject a cart"* under the composer. This runs the real
> `POST /api/demo/policy-rejection`: a genuinely over-budget cart (₹218 against a ₹180 ceiling)
> through the same `OrderService.checkout()` every purchase uses. The rejection card appears
> **inside the conversation**, with the failing check highlighted and the note *"No Razorpay
> order was created. No money moved."* The reject is a real gate, not a canned response.

**Demo 3 — payment failure and retry**
> With items in the cart, click *"Simulate a failed payment"*. The order stays pending and a
> **Retry payment** button appears. Click it — the payment captures, and the Razorpay order id
> printed on the retry is **identical** to the one printed on the failure. That is idempotency,
> demonstrated rather than claimed.

**Demo 4 — successful authorization**
> Any successful checkout renders the complete decision receipt contextually in the drawer.
> Every row is a live field from the real `PolicyDecision` and `AuthorizationDecision`.

**Demo 5 — voice**
> Tap the microphone, say *"find me running shoes under three thousand rupees"*. The transcript
> becomes the user turn, the same agent pipeline runs, and the reply is read back. Identical
> flow to Demo 1 — because it is the same code path.

<br/>

---

## ▸ Technical architecture

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI (Python 3.11) | Pydantic request models give the LLM-facing routes real validation for free |
| Persistence | SQLite | No Docker, no service to start. Analytics + audit are durable; sessions/carts/orders are in-memory (see Limitations) |
| LLM | Gemini (`gemini-*` + `text-embedding-004`) | Function calling for the tool loop, embeddings for semantic re-rank. Both optional |
| Payments | Razorpay Test Mode + Checkout.js | Real Orders API, real HMAC verification, real webhooks |
| Frontend | Vanilla ES modules, no build step | ~1.5k lines of JS, ~870 of CSS, 12 modules. Served straight from FastAPI's static mount |
| Animation | [motion.dev](https://motion.dev) via CDN ESM | One easing curve, 180ms micro-interaction budget |
| Voice | Web Speech API | No dependency, no key, no server round-trip for STT/TTS |

**A note on the frontend's motion safety.** Entrance animations only ever animate `transform`,
never `opacity`. This is deliberate: a staggered animation can stall indefinitely in a
throttled background tab, and content whose visibility depends on an animation completing can
vanish permanently. CSS's default (fully visible) governs at all times; motion is a cosmetic
slide layered on top, never a gate.

<br/>

---

## ▸ Project structure

```
aalok/
├─ backend/
│  ├─ main.py                 app factory: routers, startup, static mount
│  ├─ core/                   config.py, errors.py
│  ├─ domain/                 pure data + business rules — no I/O
│  │  ├─ catalog/               Product (unified schema), Merchant, Capabilities
│  │  ├─ cart/                  Cart, CartItem, CartStatus
│  │  ├─ commerce/              Intent, Authorization, Mandates, PolicyEngine  ← the gate
│  │  ├─ orders/ payments/ refunds/   state + status enums
│  │  └─ audit/                 24 named audit event-type constants
│  ├─ services/               orchestration
│  │  ├─ agent/                 intent parsing · AI tool layer · Gemini tool loop
│  │  ├─ catalog/               federated gateway.py + hybrid ranking.py
│  │  ├─ recommendation/        grounded complements / substitutes / upsell
│  │  ├─ cart/ authorization/ order/ payment/ refund/    one service each
│  │  ├─ analytics/             platform + merchant analytics, agentic funnel
│  │  └─ session/               server-side session state
│  ├─ integrations/
│  │  ├─ llm/gemini.py          hard-timeout wrapper around the Gemini SDK
│  │  ├─ merchants/             9 synthetic adapters + registry (16 merchants)
│  │  └─ razorpay/              Mock + Real provider, MCP extension point
│  ├─ repositories/           SQLite persistence + audit log
│  └─ api/routes/             thin FastAPI routers
├─ frontend/                  ONE screen — no router, no pages/ directory
│  ├─ index.html
│  ├─ js/
│  │  ├─ main.js                shell · landing · view switching
│  │  ├─ conversation.js        the thread — this is the product
│  │  ├─ voice.js               Web Speech API wrapper (STT + TTS)
│  │  ├─ checkout.js            real Razorpay Checkout.js integration
│  │  ├─ api.js · state.js · format.js · motion.js
│  │  └─ components/            composer · productCard · cartDrawer · authorizationCard
│  └─ css/                      tokens · base · app · components · effects
├─ tests/                     99 tests
├─ experiments/growth_experiment.py    synthetic baseline-vs-agent benchmark
├─ examples/ai_buyer.py       standalone external AI buyer reference client
├─ ARCHITECTURE.md            deep module-by-module reference
└─ README.md
```

<br/>

---

## ▸ Quick start

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Both keys are optional — the product runs fully offline without either.

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Open **http://localhost:8000**. That is the whole app; there are no other pages.

<br/>

---

## ▸ Configuration

| Variable | Default | Effect |
|---|---|---|
| `GEMINI_API_KEY` | unset | Enables the real LLM path — intent parsing, the tool-calling loop, and semantic re-rank. Unset ⇒ deterministic keyword/regex fallback + price-ascending ranking. Everything still works. |
| `PAYMENT_PROVIDER` | `mock` | `razorpay_test` switches to the real Test Mode API. `mock` forces offline mode even if keys are present. |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | unset | Test Mode credentials (`rzp_test_*`). Required when `PAYMENT_PROVIDER=razorpay_test`, or checkout returns `provider_misconfigured`. |
| `RAZORPAY_WEBHOOK_SECRET` | unset | Required for webhook signature verification. |
| `DATABASE_URL` | `backend/aalok.db` | Delete the file to reset analytics/audit state. |

<br/>

---

## ▸ Testing

```bash
python -m pytest tests/ -v
```

**99 tests.** The ones that carry the architectural guarantees:

| File | What it proves |
|---|---|
| `test_mandates.py` | Policy engine: spend/time/diet/inventory bounds; rejection happens with `razorpay_called: False` |
| `test_authorization.py` | Mode/status/scope gating, consumption semantics |
| `test_ai_tool_boundary.py` | The LLM tool surface cannot reach payment or DB symbols — asserted by inspecting module globals |
| `test_security_boundary.py` | The external AI buyer has no privileged path; same gates apply |
| `test_payment_safety.py` | Idempotency — a retry reuses the same Razorpay order |
| `test_razorpay_integration.py` | Real signature verification, checkout + webhook HMAC |
| `test_refund.py` | Refund idempotency |
| `test_cart_service.py` | Cart lifecycle, server-authoritative revalidation |
| `test_catalog_gateway.py` | Federated search across all adapters |
| `test_ai_buyer.py` | The standalone external-buyer reference client |
| `test_growth_experiment.py` | The synthetic benchmark |
| `test_dashboard_reads.py` | The read-only aggregates that no longer have a screen — kept so the routes cannot rot |

<br/>

---

## ▸ Limitations

Honest ones, not roadmap items dressed up as constraints.

1. **All 16 merchants are synthetic.** There is no live Swiggy/Zomato/BigBasket/Zepto
   integration anywhere. The adapter interface is the real contribution; the seed data is
   scaffolding.
2. **Sessions, carts and in-flight orders are in-memory.** They do not survive a server
   restart. Only analytics and the audit trail are persisted to SQLite. Production would need
   a real store; this is a prototype's deliberate scope cut, not an oversight.
3. **No authentication.** There are no user accounts. `session_id` is a client-generated
   opaque string. Anyone who can reach the API can transact as any session.
4. **Test Mode only.** No real money moves. Live-mode keys would need PCI scope, KYC and a
   settlement account that are all out of scope here.
5. **`FUTURE_AGENTIC_RESERVE` is declared but not implemented.** The authorization mode exists
   in the enum as an extension point; there is no reserve-and-settle flow behind it.
6. **The growth experiment is a synthetic benchmark**, labelled as such in code and output. Its
   conversion assumptions are stated, not measured — no public benchmark splits conversion by
   "conversational agent vs conventional flow" for this category. Order values are sampled from
   the real seeded catalog; `time_to_cart` is illustrative only.
7. **Voice depends on the browser.** `SpeechRecognition` is Chromium/Safari; Firefox users get
   text input only, with the microphone correctly absent rather than broken. Chromium's
   implementation sends audio to a Google service for transcription.
8. **SQLite is single-writer.** Running multiple uvicorn processes against the same file will
   produce "database is locked" under concurrent writes.

<br/>

---

<div align="center">

**Aalok is incredibly simple to use, and deliberately sophisticated underneath.**

The complexity is hidden behind the experience — and documented here.

</div>
