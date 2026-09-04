/* ============================================================
   Cart + checkout, as a right-side drawer.

   This is where Aalok's trust story is told, and it is told in context -
   at the moment money is about to move, not on an "Audit" page nobody
   would open. One checkout renders, in order:

     the cart      -> what you're buying
     the outcome   -> whether it was captured, rejected, or failed
     the receipt   -> every deterministic check the Policy Engine ran

   None of that is client-side reasoning. Every row comes from the real
   POST /api/orders response: authorization_decision, decision.checks, and
   cart_mandate, produced by AuthorizationService + PolicyEngine before
   PaymentService is allowed to reach Razorpay at all.
   ============================================================ */
import { api } from "../api.js";
import { state, setCartId, cartIdFor, merchantFor } from "../state.js";
import { money, escapeHtml } from "../format.js";
import { authorizationCard } from "./authorizationCard.js";
import { openRazorpayCheckout } from "../checkout.js";
import { pushTurn } from "../conversation.js";
import { fadeInUp, tapBounce } from "../motion.js";

// Minimal line icons - no emoji anywhere in the product.
const CLOSE_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>`;
const CHECK_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12l5 5L20 6"/></svg>`;
const BAG_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h16l-1.4 10.6a2 2 0 0 1-2 1.9H7.4a2 2 0 0 1-2-1.9L4 8Z"/><path d="M8 8V6a4 4 0 0 1 8 0v2"/></svg>`;

let els = {};
let activeMerchantId = null;
let itemCountByMerchant = {};
let countListener = null;

/** main.js subscribes the header badge to this. */
export function onCartCountChange(fn) {
  countListener = fn;
  emitCount();
}

function emitCount() {
  if (!countListener) return;
  countListener(Object.values(itemCountByMerchant).reduce((a, b) => a + b, 0));
}

/* ---------------- mount / open / close ---------------- */

export function mountCartDrawer() {
  const backdrop = document.createElement("div");
  backdrop.className = "qb-drawer-backdrop";

  const drawer = document.createElement("div");
  drawer.className = "qb-drawer";
  drawer.setAttribute("role", "dialog");
  drawer.setAttribute("aria-label", "Cart");
  drawer.setAttribute("aria-modal", "true");
  drawer.innerHTML = `
    <div class="qb-drawer-header">
      <div class="qb-drawer-title">Cart</div>
      <button class="qb-drawer-close" data-action="close-cart" aria-label="Close cart">${CLOSE_ICON}</button>
    </div>
    <div class="qb-drawer-body qb-scroll" id="qb-cart-body"></div>
    <div class="qb-drawer-footer" id="qb-cart-footer" hidden></div>
  `;

  document.body.append(backdrop, drawer);
  els = { backdrop, drawer, body: drawer.querySelector("#qb-cart-body"), footer: drawer.querySelector("#qb-cart-footer") };

  backdrop.addEventListener("click", closeCartDrawer);
  drawer.querySelector('[data-action="close-cart"]').addEventListener("click", closeCartDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawer.classList.contains("open")) closeCartDrawer();
  });
}

export function openCartDrawer() {
  els.backdrop.classList.add("open");
  els.drawer.classList.add("open");
  renderActiveCart();
}

export function closeCartDrawer() {
  els.backdrop.classList.remove("open");
  els.drawer.classList.remove("open");
}

/* ---------------- cart mutation ---------------- */

export async function addToCart(productId, merchantId, opts = {}) {
  let cartId = cartIdFor(merchantId);
  if (!cartId) {
    const res = await api.createCart(state.sessionId, merchantId);
    if (!res.ok || !res.data || res.data.error) return failToast(res, "Could not start a cart with this merchant.");
    cartId = res.data.cart_id;
    setCartId(merchantId, cartId);
  }

  const res = await api.addCartItem(cartId, {
    product_id: productId, merchant_id: merchantId,
    quantity: opts.quantity || 1, role: opts.role || "primary",
  });
  if (!res.ok || (res.data && res.data.error)) return failToast(res, "Could not add that to the cart.");

  activeMerchantId = merchantId;
  openCartDrawer();
}

function failToast(res, fallback) {
  const message = (res && res.data && res.data.error) || fallback;
  pushTurn({ role: "ai", text: message });
}

/* ---------------- rendering ---------------- */

function otherCartsHtml() {
  const ids = Object.keys(state.carts).filter((id) => id !== activeMerchantId && itemCountByMerchant[id]);
  if (!ids.length) return "";
  const chips = ids.map((id) => {
    const m = merchantFor(id);
    return `<button class="aa-chip" type="button" data-action="switch-cart" data-merchant-id="${escapeHtml(id)}">${escapeHtml(m ? m.name : id)}</button>`;
  }).join("");
  return `
    <div class="qb-note neutral stacked" style="margin-bottom:16px;">
      <div>You have items from other merchants too. Aalok checks out one merchant per order, so each is authorized separately.</div>
      <div style="display:flex; flex-wrap:wrap; gap:6px;">${chips}</div>
    </div>`;
}

async function renderActiveCart() {
  if (!els.body) return;

  if (!activeMerchantId) {
    els.body.innerHTML = `
      <div class="qb-empty">
        <div class="qb-empty-icon" aria-hidden="true">${BAG_ICON}</div>
        <div class="qb-empty-title">Your cart is empty</div>
        <div class="qb-empty-sub">Ask Aalok for something and add it from the results.</div>
      </div>`;
    els.footer.hidden = true;
    return;
  }

  const cartId = cartIdFor(activeMerchantId);
  const res = await api.getCart(cartId);
  if (!res.ok || !res.data || res.data.error) {
    els.body.innerHTML = `<div class="qb-note danger">Could not load this cart.</div>`;
    els.footer.hidden = true;
    return;
  }

  const cart = res.data;
  const merchant = merchantFor(activeMerchantId);
  itemCountByMerchant[activeMerchantId] = cart.items.reduce((n, i) => n + i.quantity, 0);
  emitCount();

  const lines = cart.items.map((i) => `
    <div class="qb-cart-line">
      <div style="min-width:0;">
        <div class="qb-cart-line-name">${escapeHtml(i.name)}</div>
        <div class="qb-cart-line-meta">Qty ${i.quantity} · ${escapeHtml(i.role)}</div>
      </div>
      <div class="qb-cart-line-right">
        <span class="qb-cart-line-price">${money(i.unit_price * i.quantity, cart.currency)}</span>
        <button class="qb-btn qb-btn-ghost qb-btn-sm" data-action="remove-item"
          data-cart-id="${escapeHtml(cart.cart_id)}" data-item-id="${escapeHtml(i.product_id)}">Remove</button>
      </div>
    </div>`).join("");

  els.body.innerHTML = `
    ${otherCartsHtml()}
    <div class="qb-cart-merchant">${escapeHtml(merchant ? merchant.name : activeMerchantId)}</div>
    ${lines || `<div class="qb-empty"><div class="qb-empty-title">No items yet</div></div>`}
    <div class="qb-cart-totals">
      <div class="row"><span>Subtotal</span><span>${money(cart.subtotal, cart.currency)}</span></div>
      <div class="row"><span>Delivery</span><span>${money(cart.delivery_fee, cart.currency)}</span></div>
      <div class="row grand"><span>Total</span><span>${money(cart.total, cart.currency)}</span></div>
    </div>
    <div id="qb-cart-outcome" style="margin-top:16px;"></div>
  `;

  const empty = cart.items.length === 0;
  els.footer.hidden = false;
  els.footer.innerHTML = `
    <button class="qb-btn qb-btn-primary qb-btn-block qb-btn-lg" data-action="checkout" ${empty ? "disabled" : ""}>Checkout</button>
    ${empty ? "" : `
      <div style="text-align:center; margin-top:10px;">
        <button class="qb-btn qb-btn-ghost qb-btn-sm" data-action="checkout-fail"
          title="Runs the same checkout with force_fail, to show the retry + idempotency path">Simulate a failed payment</button>
      </div>`}
  `;

  els.body.querySelectorAll('[data-action="remove-item"]').forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      await api.removeCartItem(btn.dataset.cartId, btn.dataset.itemId);
      await renderActiveCart();
    });
  });
  els.body.querySelectorAll('[data-action="switch-cart"]').forEach((btn) => {
    btn.addEventListener("click", async () => { activeMerchantId = btn.dataset.merchantId; await renderActiveCart(); });
  });

  const checkoutBtn = els.footer.querySelector('[data-action="checkout"]');
  if (checkoutBtn) checkoutBtn.addEventListener("click", (e) => { tapBounce(e.currentTarget); runCheckout(cart.cart_id); });
  const failBtn = els.footer.querySelector('[data-action="checkout-fail"]');
  if (failBtn) failBtn.addEventListener("click", () => runCheckout(cart.cart_id, { forceFail: true }));
}

/* ---------------- checkout ---------------- */

function setFooterBusy(busy) {
  els.footer.querySelectorAll("button").forEach((b) => { b.disabled = busy; });
}

function showOutcome(html) {
  const el = document.getElementById("qb-cart-outcome");
  if (!el) return;
  el.innerHTML = html;
  fadeInUp(el, { duration: 0.24 });
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/** A retry button that re-runs the SAME cart - which is exactly what proves
 *  idempotency: OrderService keys on (cart_id, cart_version), so the retry
 *  reuses the existing InternalOrder and its Razorpay order id rather than
 *  creating a second one. */
function retryHtml(cartId) {
  return `<div style="margin-top:12px;">
    <button class="qb-btn qb-btn-primary qb-btn-block" data-action="retry" data-cart-id="${escapeHtml(cartId)}">Retry payment</button>
  </div>`;
}

function wireRetry() {
  const btn = document.querySelector('[data-action="retry"]');
  if (btn) btn.addEventListener("click", () => { tapBounce(btn); runCheckout(btn.dataset.cartId); });
}

/** The same order id coming back on a retry is the evidence, so show it. */
function orderIdNote(data) {
  const internal = data.internal_order || {};
  const rzp = internal.razorpay_order_id || (data.order && data.order.id);
  if (!rzp) return "";
  return `<div class="qb-note neutral" style="margin-top:8px; font-size:12px;">Razorpay order <strong>${escapeHtml(rzp)}</strong>${data.already_captured ? " · already captured, no new charge made" : ""}</div>`;
}

async function runCheckout(cartId, { forceFail = false } = {}) {
  setFooterBusy(true);
  showOutcome(`<div class="qb-note info"><span class="qb-spinner"></span> Checking authorization and commerce policy&hellip;</div>`);

  let res;
  try { res = await api.createOrder(state.sessionId, cartId, forceFail); }
  catch { res = { ok: false, data: null }; }

  const data = (res && res.data) || {};

  if (!res.ok && !data.status) {
    showOutcome(`<div class="qb-note danger">Couldn't reach the checkout service. The cart is untouched.</div>`);
    setFooterBusy(false);
    return;
  }

  // --- gated before any money could move -------------------------------
  if (data.status === "rejected_by_policy" || data.status === "rejected_by_authorization") {
    showOutcome(authorizationCard({
      authorizationDecision: data.authorization_decision, decision: data.decision, cartMandate: data.cart_mandate,
    }));
    pushTurn({ role: "ai", text: `That cart didn't pass the policy gate — ${data.decision ? data.decision.reason : "authorization was refused"}. Nothing was charged.` });
    setFooterBusy(false);
    return;
  }
  if (data.status === "provider_misconfigured") {
    showOutcome(`<div class="qb-note danger stacked"><strong>Payment provider misconfigured</strong><span>${escapeHtml(data.error || "")}</span></div>`);
    setFooterBusy(false);
    return;
  }
  if (data.status === "razorpay_api_error") {
    showOutcome(`<div class="qb-note danger stacked"><strong>Razorpay API call failed</strong><span>${escapeHtml(data.error || "")}</span></div>`);
    setFooterBusy(false);
    return;
  }

  // --- passed the gate: show the receipt alongside the payment result ---
  const receipt = authorizationCard({
    authorizationDecision: data.authorization_decision, decision: data.decision, cartMandate: data.cart_mandate,
  });
  const merchant = merchantFor(activeMerchantId);
  const total = data.cart_mandate ? data.cart_mandate.total_amount : null;

  if (data.status === "success") {
    showOutcome(`
      <div class="qb-note success"><span class="qb-note-icon">${CHECK_ICON}</span>Payment captured (${escapeHtml(data.payment ? data.payment.mode : "mock")} mode). Order ${escapeHtml(data.order.id)} confirmed.</div>
      ${orderIdNote(data)}
      <div style="margin-top:12px;">${receipt}</div>`);
    settleCart(cartId);
    pushTurn({
      role: "ai",
      text: `Order confirmed${merchant ? ` with ${merchant.name}` : ""}${total ? ` — ${money(total)}` : ""}. Payment captured and the authorization is recorded in the audit trail.`,
    });
  } else if (data.status === "payment_failed") {
    showOutcome(`
      <div class="qb-note danger stacked"><strong>Payment failed.</strong><span>The order stays pending — retrying reuses the same order, so there is no duplicate-charge risk.</span></div>
      ${orderIdNote(data)}
      ${retryHtml(cartId)}
      <div style="margin-top:12px;">${receipt}</div>`);
    wireRetry();
  } else if (data.status === "awaiting_checkout") {
    showOutcome(`<div class="qb-note info"><span class="qb-spinner"></span> Opening Razorpay Test Mode checkout for order ${escapeHtml(data.order.id)}&hellip;</div><div style="margin-top:12px;">${receipt}</div>`);
    const outcome = await openRazorpayCheckout(state.sessionId, data.checkout);
    if (outcome.kind === "verified" && outcome.ok) {
      showOutcome(`<div class="qb-note success"><span class="qb-note-icon">${CHECK_ICON}</span>Payment captured (Test Mode, signature verified server-side). Order ${escapeHtml(data.order.id)} confirmed.</div><div style="margin-top:12px;">${receipt}</div>`);
      settleCart(cartId);
      pushTurn({ role: "ai", text: `Order confirmed${merchant ? ` with ${merchant.name}` : ""}${total ? ` — ${money(total)}` : ""}. Razorpay signature verified server-side before anything was marked captured.` });
    } else if (outcome.kind === "verified") {
      showOutcome(`<div class="qb-note danger stacked"><strong>Signature verification failed</strong><span>The payment was NOT marked captured.</span></div><div style="margin-top:12px;">${receipt}</div>`);
    } else if (outcome.kind === "failed") {
      showOutcome(`<div class="qb-note danger stacked"><strong>Payment failed</strong><span>The order stays pending — retrying reuses the same Razorpay order.</span></div>${retryHtml(cartId)}<div style="margin-top:12px;">${receipt}</div>`);
      wireRetry();
    } else {
      showOutcome(`<div class="qb-note info">Checkout closed before payment completed. Order ${escapeHtml(data.order.id)} is still pending.</div>${retryHtml(cartId)}<div style="margin-top:12px;">${receipt}</div>`);
      wireRetry();
    }
  } else {
    showOutcome(`<div class="qb-note info">Order pending.</div><div style="margin-top:12px;">${receipt}</div>`);
  }

  setFooterBusy(false);
}

/** A captured cart is done: drop the client's pointer to it so the next
 *  add-to-cart opens a fresh one, and stop counting it in the header. */
function settleCart(cartId) {
  const merchantId = Object.keys(state.carts).find((id) => state.carts[id] === cartId);
  if (!merchantId) return;
  delete state.carts[merchantId];
  delete itemCountByMerchant[merchantId];
  if (activeMerchantId === merchantId) {
    const next = Object.keys(state.carts).find((id) => itemCountByMerchant[id]);
    activeMerchantId = next || null;
  }
  emitCount();
  if (els.footer) els.footer.hidden = true;
}
