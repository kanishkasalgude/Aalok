// Thin fetch wrapper over the backend API. One function per endpoint the
// UI actually calls - never fabricates data client-side; every function
// here maps directly to a real backend route (see ARCHITECTURE.md).

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
const patch = (path, body) => request("PATCH", path, body);
const del = (path) => request("DELETE", path);

export const api = {
  // environment / merchants
  paymentMode: () => get("/api/payment-mode"),
  merchants: () => get("/api/merchants"),

  // catalog
  searchCatalog: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") qs.set(k, v); });
    return get(`/api/catalog/search?${qs.toString()}`);
  },
  getProduct: (id, merchantId) => get(`/api/catalog/products/${encodeURIComponent(id)}${merchantId ? `?merchant_id=${encodeURIComponent(merchantId)}` : ""}`),
  complements: (id, merchantId) => get(`/api/catalog/${encodeURIComponent(id)}/complements${merchantId ? `?merchant_id=${encodeURIComponent(merchantId)}` : ""}`),
  substitutes: (id, merchantId) => get(`/api/catalog/${encodeURIComponent(id)}/substitutes${merchantId ? `?merchant_id=${encodeURIComponent(merchantId)}` : ""}`),

  // agent
  agentChat: (payload) => post("/api/agent/chat", payload),

  // cart
  createCart: (sessionId, merchantId) => post("/api/cart", { session_id: sessionId, merchant_id: merchantId }),
  getCart: (cartId) => get(`/api/cart/${cartId}`),
  addCartItem: (cartId, payload) => post(`/api/cart/${cartId}/items`, payload),
  modifyCartItem: (cartId, itemId, quantity) => patch(`/api/cart/${cartId}/items/${encodeURIComponent(itemId)}`, { quantity }),
  removeCartItem: (cartId, itemId) => del(`/api/cart/${cartId}/items/${encodeURIComponent(itemId)}`),

  // checkout / orders
  validateCheckout: (sessionId, cartId) => post("/api/checkout/validate", { session_id: sessionId, cart_id: cartId }),
  createOrder: (sessionId, cartId, forceFail = false) => post("/api/orders", { session_id: sessionId, cart_id: cartId, force_fail: forceFail }),
  getOrder: (id) => get(`/api/orders/${id}`),
  listOrders: (limit = 100) => get(`/api/orders?limit=${limit}`),
  confirmOrder: (sessionId, acceptUpsell, forceFail) => post("/api/order/confirm", { session_id: sessionId, accept_upsell: acceptUpsell, force_fail: forceFail }),
  policyRejectionDemo: () => post("/api/demo/policy-rejection", undefined),

  // payments
  verifyPayment: (payload) => post("/api/order/verify-payment", payload),
  reportPaymentFailed: (payload) => post("/api/order/payment-failed", payload),
  listRefunds: (limit = 100) => get(`/api/payments/refunds?limit=${limit}`),

  // analytics / audit
  analytics: () => get("/api/analytics"),
  growthExperiment: () => get("/api/growth/experiment"),
  audit: (sessionId) => get(`/api/audit${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`),
};
