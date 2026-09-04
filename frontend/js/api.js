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

async function request(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  let data;
  try { data = await res.json(); } catch { data = null; }
  return { ok: res.ok, status: res.status, data };
}

const get = (path) => request("GET", path);
const post = (path, body) => request("POST", path, body);
const del = (path) => request("DELETE", path);

export const api = {
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
  policyRejectionDemo: () => post("/api/demo/policy-rejection", undefined),

  // real Razorpay Test Mode result reporting (never trusted from the
  // browser alone - the server verifies the signature)
  verifyPayment: (payload) => post("/api/order/verify-payment", payload),
  reportPaymentFailed: (payload) => post("/api/order/payment-failed", payload),
};
