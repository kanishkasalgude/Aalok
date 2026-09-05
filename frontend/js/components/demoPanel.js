/* ============================================================
   Demo Control Panel (Track 01 Phase 12) - buttons for a presenter to
   trigger deterministic scenarios, for demo purposes ONLY.

   Every button below calls a REAL backend endpoint that runs through the
   exact same OrderService.checkout() pipeline (revalidate -> Authorization
   -> Commerce Policy Engine -> PaymentService) as the conversational UI.
   This panel does not bypass, mock, or shortcut any of that - it only
   chooses which real inputs to send. See backend/api/routes/orders.py's
   /api/demo/* routes for the two scenarios that needed a small dedicated
   endpoint (successful-purchase, cart-tampering); the rest reuse routes
   the real UI already calls.
   ============================================================ */
import { api } from "../api.js";
import { state } from "../state.js";
import { money, escapeHtml } from "../format.js";
import { authorizationCard, moneyBanner } from "./authorizationCard.js";
import { auditTrailDisclosure } from "./auditTrail.js";
import { fadeInUp } from "../motion.js";

const CLOSE_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>`;

let els = {};
let lastFailedCartId = null;

export function mountDemoPanel() {
  const backdrop = document.createElement("div");
  backdrop.className = "qb-drawer-backdrop";

  const drawer = document.createElement("div");
  drawer.className = "qb-drawer";
  drawer.setAttribute("role", "dialog");
  drawer.setAttribute("aria-label", "Demo Control Panel");
  drawer.setAttribute("aria-modal", "true");
  drawer.innerHTML = `
    <div class="qb-drawer-header">
      <div class="qb-drawer-title">Demo Control Panel</div>
      <button class="qb-drawer-close" data-action="close-demo" aria-label="Close demo panel">${CLOSE_ICON}</button>
    </div>
    <div class="qb-drawer-body qb-scroll" id="qb-demo-body"></div>
  `;

  document.body.append(backdrop, drawer);
  els = { backdrop, drawer, body: drawer.querySelector("#qb-demo-body") };

  backdrop.addEventListener("click", closeDemoPanel);
  drawer.querySelector('[data-action="close-demo"]').addEventListener("click", closeDemoPanel);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawer.classList.contains("open")) closeDemoPanel();
  });

  renderScenarioList();
}

export function openDemoPanel() {
  els.backdrop.classList.add("open");
  els.drawer.classList.add("open");
}

export function closeDemoPanel() {
  els.backdrop.classList.remove("open");
  els.drawer.classList.remove("open");
}

/* ---------------- scenarios ---------------- */

async function runSuccessfulPurchase() {
  const res = await api.successfulPurchaseDemo();
  return res.data;
}

async function runBudgetRejection() {
  const res = await api.policyRejectionDemo();
  return res.data;
}

async function runCartTampering() {
  const res = await api.cartTamperingDemo();
  return res.data;
}

async function runPaymentFailure() {
  // POST /api/orders requires this session to already have an intent
  // mandate (set by any prior chat/agent-chat call) - a real agent turn is
  // the correct way to establish one for the CURRENT browser session with
  // a category-appropriate (unbounded, for fashion) delivery ceiling,
  // rather than quick-add's food-shaped 60-minute default. The cart this
  // scenario actually checks out (and later retries) is built explicitly
  // below, from the same item the agent surfaces.
  await api.agentChat({ message: "Running shoes under ₹3000" });
  const cartRes = await api.createCart(state.sessionId, "fashion-threadloom");
  const cartId = cartRes.data.cart_id;
  await api.addCartItem(cartId, { product_id: "f5", merchant_id: "fashion-threadloom" });
  const res = await api.createOrder(state.sessionId, cartId, /* forceFail */ true);
  lastFailedCartId = cartId;
  return res.data;
}

async function runPaymentRetry() {
  if (!lastFailedCartId) {
    return { status: "no_prior_failure", error: "Run “Payment Failure” first, then retry the same cart." };
  }
  const res = await api.createOrder(state.sessionId, lastFailedCartId, /* forceFail */ false);
  return res.data;
}

async function runExternalBuyer() {
  const res = await api.externalBuyerDemo({ item_id: "d501", max_amount: 500, accept_upsell: false });
  return res.data;
}

async function runUpsellAccepted() {
  const add = await api.quickAdd("d501");
  const res = await api.confirmOrder(add.data.session_id, /* acceptUpsell */ true);
  return res.data;
}

async function runUpsellDeclined() {
  const add = await api.quickAdd("d501");
  const res = await api.confirmOrder(add.data.session_id, /* acceptUpsell */ false);
  return res.data;
}

async function runExpiredAuthorization() {
  const res = await api.expiredAuthorizationDemo();
  return res.data;
}

async function runUnauthorizedSession() {
  const res = await api.unauthorizedSessionDemo();
  return res.data;
}

async function runInventoryChange() {
  // Casual Sneakers (f9, Threadloom) is seeded with stock_qty=0 - a
  // genuinely out-of-stock item. budget_override keeps this scenario
  // isolated to the inventory check alone (₹1,899 is under the ceiling,
  // so budget PASSES and inventory is the only thing that can fail).
  await api.agentChat({ message: "Casual sneakers", budget_override: 3000 });
  const cartRes = await api.createCart(state.sessionId, "fashion-threadloom");
  const cartId = cartRes.data.cart_id;
  await api.addCartItem(cartId, { product_id: "f9", merchant_id: "fashion-threadloom" });
  const res = await api.createOrder(state.sessionId, cartId, false);
  return res.data;
}

async function runDuplicatePayment() {
  await api.agentChat({ message: "Running shoes under ₹3000" });
  const cartRes = await api.createCart(state.sessionId, "fashion-threadloom");
  const cartId = cartRes.data.cart_id;
  await api.addCartItem(cartId, { product_id: "f5", merchant_id: "fashion-threadloom" });
  await api.createOrder(state.sessionId, cartId, false); // captures for real
  const res = await api.createOrder(state.sessionId, cartId, false); // duplicate attempt, same cart+version
  return res.data;
}

const SCENARIOS = [
  { key: "success", label: "Successful Purchase", run: runSuccessfulPurchase },
  { key: "budget", label: "Budget Rejection", run: runBudgetRejection },
  { key: "tamper", label: "Cart Tampering", run: runCartTampering },
  { key: "expired", label: "Expired Authorization", run: runExpiredAuthorization },
  { key: "unauthorized", label: "Unauthorized Session", run: runUnauthorizedSession },
  { key: "inventory", label: "Inventory Change", run: runInventoryChange },
  { key: "duplicate", label: "Duplicate Payment", run: runDuplicatePayment },
  { key: "fail", label: "Payment Failure", run: runPaymentFailure },
  { key: "retry", label: "Payment Retry", run: runPaymentRetry },
  { key: "external", label: "External AI Buyer", run: runExternalBuyer },
  { key: "upsellYes", label: "Upsell Accepted", run: runUpsellAccepted },
  { key: "upsellNo", label: "Upsell Declined", run: runUpsellDeclined },
];

/* ---------------- rendering ---------------- */

function tamperNote(data) {
  if (!data.tamper_demo) return "";
  const t = data.tamper_demo;
  return `
    <div class="qb-note danger stacked" style="margin-bottom:12px;">
      <strong>Cart validation failed</strong>
      <span>Claimed price ${money(t.claimed_price)} (authorized up to ${money(t.authorized_ceiling)}) — the server independently
      re-fetched the true catalog price, ${money(t.actual_catalog_price)}, before the policy engine ever saw the cart.
      The authorized cart no longer matched the purchase request. Purchase blocked.</span>
    </div>`;
}

/** The "attack" shape (currently just /api/demo/unauthorized-session) isn't
 *  a checkout outcome at all - it's a raw ownership check, so it gets its
 *  own ATTACK / DECISION / REASON rendering instead of forcing it through
 *  authorizationCard's checkout-shaped fields. */
function renderAttackResult(container, label, data) {
  const blocked = data.decision === "BLOCKED";
  container.innerHTML = `
    <div class="qb-demo-result-head">${escapeHtml(label)} <span class="qb-demo-status-pill ${blocked ? "status-rejected_by_policy" : "status-success"}">${escapeHtml(data.decision)}</span></div>
    <div class="qb-attack-card">
      <div class="qb-attack-row"><span>ATTACK</span><div>${escapeHtml(data.attack)}</div></div>
      <div class="qb-attack-row"><span>REASON</span><div>${escapeHtml(data.reason)}</div></div>
    </div>
    ${moneyBanner({ razorpay_called: data.razorpay_called, status: data.money_moved ? "success" : "rejected_by_policy" })}
  `;
  fadeInUp(container, { duration: 0.24 });
  container.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderResult(container, label, data) {
  if (!data || data.error) {
    container.innerHTML = `<div class="qb-note danger">${escapeHtml((data && data.error) || "Something went wrong running this scenario.")}</div>`;
    fadeInUp(container, { duration: 0.2 });
    return;
  }
  if (data.attack) return renderAttackResult(container, label, data);
  const receipt = (data.authorization_decision || data.decision)
    ? authorizationCard({ authorizationDecision: data.authorization_decision, decision: data.decision, cartMandate: data.cart_mandate })
    : "";
  container.innerHTML = `
    <div class="qb-demo-result-head">${escapeHtml(label)} <span class="qb-demo-status-pill status-${escapeHtml(data.status || "unknown")}">${escapeHtml((data.status || "unknown").replace(/_/g, " "))}</span></div>
    ${moneyBanner(data)}
    ${tamperNote(data)}
    ${receipt}
    ${auditTrailDisclosure(data.audit_trail)}
  `;
  fadeInUp(container, { duration: 0.24 });
  container.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

const AI_BUYER_PIPELINE = ["External AI Buyer", "Aalok Catalog", "Product Discovery", "Purchase Proposal", "Aalok Authorization", "Razorpay"];

function aiBuyerPipelineHtml() {
  const steps = AI_BUYER_PIPELINE.map((s) => `<span class="qb-pipeline-step">${escapeHtml(s)}</span>`).join('<span class="qb-pipeline-arrow">&rarr;</span>');
  return `
    <div class="qb-pipeline-card">
      <div class="qb-pipeline-title">External AI Buyer</div>
      <div class="qb-pipeline-flow">${steps}</div>
      <div class="qb-pipeline-note"><strong>Any AI buyer can discover the catalog. No AI buyer can bypass authorization.</strong> Aalok's own agent, a third party, and this control panel's "External AI Buyer" button all reach the exact same trust boundary. See <code>examples/ai_buyer.py</code> for a standalone reference client that discovers the catalog and transacts without ever touching Aalok's UI.</div>
    </div>`;
}

function renderScenarioList() {
  els.body.innerHTML = `
    <p class="qb-demo-intro">Each button calls a real backend endpoint through the exact same authorization + policy pipeline as the live app — nothing here is mocked at the UI layer.</p>
    ${aiBuyerPipelineHtml()}
    <div class="qb-demo-grid">
      ${SCENARIOS.map((s) => `<button class="qb-btn qb-btn-secondary qb-demo-scenario-btn" data-key="${s.key}">${escapeHtml(s.label)}</button>`).join("")}
    </div>
    <div id="qb-demo-result" class="qb-demo-result"></div>
  `;

  const resultEl = els.body.querySelector("#qb-demo-result");
  els.body.querySelectorAll(".qb-demo-scenario-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const scenario = SCENARIOS.find((s) => s.key === btn.dataset.key);
      if (!scenario) return;
      els.body.querySelectorAll(".qb-demo-scenario-btn").forEach((b) => { b.disabled = true; });
      resultEl.innerHTML = `<div class="qb-note info"><span class="qb-spinner"></span> Running ${escapeHtml(scenario.label)}&hellip;</div>`;
      try {
        const data = await scenario.run();
        renderResult(resultEl, scenario.label, data);
      } catch (e) {
        renderResult(resultEl, scenario.label, { error: "Request failed - is the server running?" });
      } finally {
        els.body.querySelectorAll(".qb-demo-scenario-btn").forEach((b) => { b.disabled = false; });
      }
    });
  });
}
