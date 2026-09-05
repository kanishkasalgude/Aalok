// Thin fetch wrapper over the backend API.
//
// One function per endpoint the UI actually calls. The backend's surface is
// considerably larger than this - /api/catalog/search, /api/orders (list),
// /api/payments/refunds, /api/analytics, /api/growth/experiment, /api/audit,
// /api/external/purchase and the webhook routes all still run, and are all
// still tested. They simply have no consumer-facing screen any more: the
// dashboards that used to read them were removed when Aalok collapsed into
// a single conversational surface. See README.md → "What was removed from
// the UI (and what still runs underneath)".
//
// Every call attaches X-Session-Token (Track 01 Phase 2) when one is known,
// and persists whatever session_token a response hands back - so identity
// bootstraps itself on the very first call (no token yet -> server mints
// one -> this wrapper stores it) and stays current on every call after.
import { state, setSession } from "./state.js";

async function _send(method, path, body) {
  const opts = { method, headers: {} };
  if (state.sessionToken) opts.headers["X-Session-Token"] = state.sessionToken;
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  let data;
  try { data = await res.json(); } catch { data = null; }
  return { res, data };
}

async function request(method, path, body) {
  let { res, data } = await _send(method, path, body);

  if (res.status === 401 && state.sessionToken) {
    // The stored token was rejected - most likely a dev-server restart
    // regenerated its ephemeral SESSION_SECRET (services/session/auth.py),
    // which invalidates every previously-issued token. Drop it and retry
    // ONCE with a clean slate so the server mints a fresh session instead
    // of surfacing a raw auth error mid-demo.
    state.sessionToken = null;
    state.sessionId = null;
    localStorage.removeItem("qb_session_id");
    localStorage.removeItem("qb_session_token");
    if (body && typeof body === "object" && "session_id" in body) delete body.session_id;
    ({ res, data } = await _send(method, path, body));
  }

  if (data && data.session_token) setSession(data.session_id, data.session_token);
  return { ok: res.ok, status: res.status, data };
}

const get = (path) => request("GET", path);
const post = (path, body) => request("POST", path, body);
const del = (path) => request("DELETE", path);

export const api = {
  // identity (Track 01 Phase 2) - mints a fresh session or refreshes the
  // current one's expiry if a still-valid token is already known.
  createSession: () => post("/api/session", {}),

  // environment / merchants (the merchant registry backs the authorization
  // card's merchant + category rows)
  paymentMode: () => get("/api/payment-mode"),
  merchants: () => get("/api/merchants"),

  // the agent - one call per conversational turn, running the whole
  // intent -> tools -> federated catalog -> ranking -> recommendation pipeline
  agentChat: (payload) => post("/api/agent/chat", payload),

  // cart
  createCart: (sessionId, merchantId) => post("/api/cart", { session_id: sessionId, merchant_id: merchantId }),
  getCart: (cartId) => get(`/api/cart/${cartId}`),
  addCartItem: (cartId, payload) => post(`/api/cart/${cartId}/items`, payload),
  removeCartItem: (cartId, itemId) => del(`/api/cart/${cartId}/items/${encodeURIComponent(itemId)}`),

  // checkout - authorization + policy + payment, in one server-side pass
  createOrder: (sessionId, cartId, forceFail = false) => post("/api/orders", { session_id: sessionId, cart_id: cartId, force_fail: forceFail }),
  quickAdd: (itemId, budgetOverride) => post("/api/order/quick-add", { item_id: itemId, budget_override: budgetOverride }),
  confirmOrder: (sessionId, acceptUpsell = false) => post("/api/order/confirm", { session_id: sessionId, accept_upsell: acceptUpsell }),

  // Demo Control Panel (Track 01 Phase 12) - each of these is a single call
  // into a self-contained demo route that runs through the exact same
  // OrderService.checkout() pipeline as everything else; see api/routes/orders.py.
  policyRejectionDemo: () => post("/api/demo/policy-rejection", undefined),
  successfulPurchaseDemo: () => post("/api/demo/successful-purchase", undefined),
  cartTamperingDemo: () => post("/api/demo/cart-tampering", undefined),
  expiredAuthorizationDemo: () => post("/api/demo/expired-authorization", undefined),
  unauthorizedSessionDemo: () => post("/api/demo/unauthorized-session", undefined),
  externalBuyerDemo: (payload) => post("/api/external/purchase", payload),

  // real Razorpay Test Mode result reporting (never trusted from the
  // browser alone - the server verifies the signature)
  verifyPayment: (payload) => post("/api/order/verify-payment", payload),
  reportPaymentFailed: (payload) => post("/api/order/payment-failed", payload),
};
