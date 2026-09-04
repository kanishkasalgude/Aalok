import { api } from "../api.js";
import { state, setCartId, cartIdFor, merchantFor } from "../state.js";
import { money, escapeHtml } from "../format.js";
import { authorizationCard } from "./authorizationCard.js";
import { openRazorpayCheckout } from "../checkout.js";

let els = {};
let activeMerchantId = null;

export function mountCartDrawer() {
  const backdrop = document.createElement("div");
  backdrop.className = "qb-drawer-backdrop";
  const drawer = document.createElement("div");
  drawer.className = "qb-drawer";
  drawer.innerHTML = `
    <div class="qb-drawer-header">
      <div style="font-weight:700; font-size:15px;">Cart</div>
      <button class="qb-drawer-close" data-action="close-cart">✕</button>
    </div>
    <div class="qb-drawer-body qb-scroll" id="qb-cart-body"></div>
    <div class="qb-drawer-footer" id="qb-cart-footer" style="display:none;"></div>
  `;
  document.body.appendChild(backdrop);
  document.body.appendChild(drawer);
  els = { backdrop, drawer, body: drawer.querySelector("#qb-cart-body"), footer: drawer.querySelector("#qb-cart-footer") };
  backdrop.addEventListener("click", closeCartDrawer);
  drawer.querySelector('[data-action="close-cart"]').addEventListener("click", closeCartDrawer);
}

export function openCartDrawer() {
  els.backdrop.classList.add("open");
  els.drawer.classList.add("open");
}
export function closeCartDrawer() {
  els.backdrop.classList.remove("open");
  els.drawer.classList.remove("open");
}

export async function addToCart(productId, merchantId, opts = {}) {
  let cartId = cartIdFor(merchantId);
  if (!cartId) {
    const res = await api.createCart(state.sessionId, merchantId);
    if (!res.ok || !res.data || res.data.error) { alert((res.data && res.data.error) || "Could not create a cart."); return; }
    cartId = res.data.cart_id;
    setCartId(merchantId, cartId);
  }
  const res = await api.addCartItem(cartId, {
    product_id: productId, merchant_id: merchantId, quantity: opts.quantity || 1, role: opts.role || "primary",
  });
  if (!res.ok || (res.data && res.data.error)) { alert((res.data && res.data.error) || "Could not add item to cart."); return; }
  activeMerchantId = merchantId;
  openCartDrawer();
  await renderActiveCart();
}

function otherCartsChips() {
  const ids = Object.keys(state.carts).filter((mid) => mid !== activeMerchantId);
  if (ids.length === 0) return "";
  const chips = ids.map((mid) => {
    const m = merchantFor(mid);
    return `<button class="qb-chip" data-action="switch-cart" data-merchant-id="${mid}">${m ? m.name : mid}</button>`;
  }).join("");
  return `
    <div class="qb-note info" style="margin-bottom:12px; flex-direction:column; align-items:flex-start; gap:6px;">
      <div>You also have items from other merchants. Aalok checks out one merchant per order.</div>
      <div class="qb-chip-group">${chips}</div>
    </div>
  `;
}

async function renderActiveCart() {
  if (!activeMerchantId) { els.body.innerHTML = `<div class="qb-muted" style="font-size:13px;">Nothing here yet.</div>`; els.footer.style.display = "none"; return; }
  const cartId = cartIdFor(activeMerchantId);
  const res = await api.getCart(cartId);
  if (!res.ok || res.data.error) { els.body.innerHTML = `<div class="qb-note danger">Could not load cart.</div>`; return; }
  const cart = res.data;
  const merchant = merchantFor(activeMerchantId);

  const lines = cart.items.map((i) => `
    <div class="qb-cart-line">
      <div>
        <div class="qb-cart-line-name">${escapeHtml(i.name)}</div>
        <div class="qb-cart-line-meta">Qty ${i.quantity} · ${i.role}</div>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <span>${money(i.unit_price * i.quantity, cart.currency)}</span>
        <button class="qb-btn qb-btn-ghost qb-btn-sm" data-action="remove-item" data-cart-id="${cart.cart_id}" data-item-id="${i.product_id}">Remove</button>
      </div>
    </div>
  `).join("");

  els.body.innerHTML = `
    ${otherCartsChips()}
    <div style="font-size:12px; color:var(--qb-text-secondary); margin-bottom:10px;">${merchant ? merchant.name : activeMerchantId}</div>
    ${lines || `<div class="qb-muted" style="font-size:13px;">No items yet.</div>`}
    <div class="qb-cart-totals">
      <div class="row"><span>Subtotal</span><span>${money(cart.subtotal, cart.currency)}</span></div>
      <div class="row"><span>Delivery</span><span>${money(cart.delivery_fee, cart.currency)}</span></div>
      <div class="row grand"><span>Total</span><span>${money(cart.total, cart.currency)}</span></div>
    </div>
    <div id="qb-cart-outcome" style="margin-top:12px;"></div>
  `;

  els.footer.style.display = "block";
  els.footer.innerHTML = `
    <button class="qb-btn qb-btn-primary qb-btn-block" data-action="checkout" ${cart.items.length === 0 ? "disabled" : ""}>Checkout</button>
  `;

  els.body.querySelectorAll('[data-action="remove-item"]').forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api.removeCartItem(btn.dataset.cartId, btn.dataset.itemId);
      await renderActiveCart();
    });
  });
  els.body.querySelectorAll('[data-action="switch-cart"]').forEach((btn) => {
    btn.addEventListener("click", async () => { activeMerchantId = btn.dataset.merchantId; await renderActiveCart(); });
  });
  els.footer.querySelector('[data-action="checkout"]').addEventListener("click", () => runCheckout(cart.cart_id));
}

async function runCheckout(cartId) {
  const outcomeEl = document.getElementById("qb-cart-outcome");
  outcomeEl.innerHTML = `<div class="qb-note info"><span class="qb-spinner"></span> Validating authorization and policy…</div>`;

  const res = await api.createOrder(state.sessionId, cartId, false);
  const data = res.data || {};
  state.lastAuditTrail = data.audit_trail || state.lastAuditTrail;

  if (data.status === "rejected_by_policy" || data.status === "rejected_by_authorization") {
    outcomeEl.innerHTML = authorizationCard({
      authorizationDecision: data.authorization_decision, decision: data.decision, cartMandate: data.cart_mandate,
    });
    return;
  }
  if (data.status === "provider_misconfigured") {
    outcomeEl.innerHTML = `<div class="qb-note danger"><strong>Payment provider misconfigured:</strong> ${escapeHtml(data.error)}</div>`;
    return;
  }
  if (data.status === "razorpay_api_error") {
    outcomeEl.innerHTML = `<div class="qb-note danger"><strong>Razorpay API call failed:</strong> ${escapeHtml(data.error)}</div>`;
    return;
  }

  const authzHtml = authorizationCard({ authorizationDecision: data.authorization_decision, decision: data.decision, cartMandate: data.cart_mandate });

  if (data.status === "success") {
    outcomeEl.innerHTML = `<div class="qb-note success">✓ Payment captured (${data.payment ? data.payment.mode : "mock"} mode). Order ${data.order.id} confirmed.</div>${authzHtml}`;
    delete state.carts[Object.keys(state.carts).find((k) => cartIdFor(k) === cartId)];
  } else if (data.status === "payment_failed") {
    outcomeEl.innerHTML = `<div class="qb-note danger"><strong>Payment failed.</strong> Order remains pending — same order will be reused on retry, no duplicate charge risk.</div>${authzHtml}`;
  } else if (data.status === "awaiting_checkout") {
    outcomeEl.innerHTML = `<div class="qb-note info">Opening Razorpay Test Mode Checkout for order <strong>${data.order.id}</strong>…</div>${authzHtml}`;
    const outcome = await openRazorpayCheckout(state.sessionId, data.checkout);
    if (outcome.kind === "verified" && outcome.ok) {
      outcomeEl.innerHTML = `<div class="qb-note success">✓ Payment captured (Test Mode, signature verified). Order ${data.order.id} confirmed.</div>${authzHtml}`;
    } else if (outcome.kind === "verified" && !outcome.ok) {
      outcomeEl.innerHTML = `<div class="qb-note danger"><strong>Signature verification failed</strong> — payment NOT marked captured.</div>${authzHtml}`;
    } else if (outcome.kind === "failed") {
      outcomeEl.innerHTML = `<div class="qb-note danger"><strong>Payment failed</strong> (Razorpay Test Mode). Order remains pending — retry with the same order, no duplicate charge.</div>${authzHtml}`;
    } else {
      outcomeEl.innerHTML = `<div class="qb-note info">Checkout closed without completing payment. Order ${data.order.id} is still pending.</div>${authzHtml}`;
    }
  } else {
    outcomeEl.innerHTML = `<div class="qb-note info">Order pending.</div>${authzHtml}`;
  }
}
