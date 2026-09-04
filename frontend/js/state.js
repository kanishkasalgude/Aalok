// Shared client-side state. Deliberately thin: session id, cart ids by
// merchant, a merchants cache, and the payment-mode badge - the backend
// remains authoritative for price/inventory/authorization/policy/order/
// payment status. Nothing here is ever trusted for those decisions; it's
// only used to know WHICH backend objects (session, cart) to talk to next.
function uid() {
  return "sess-" + Math.random().toString(16).slice(2, 12);
}

export const state = {
  sessionId: localStorage.getItem("qb_session_id") || uid(),
  paymentMode: null,
  merchants: [],
  merchantsById: {},
  carts: {}, // merchant_id -> cart_id (client only tracks WHICH cart to add to; server owns contents)
};

localStorage.setItem("qb_session_id", state.sessionId);

export function setMerchants(list) {
  state.merchants = list;
  state.merchantsById = {};
  list.forEach((m) => { state.merchantsById[m.merchant_id] = m; });
}

export function merchantFor(merchantId) {
  return state.merchantsById[merchantId] || null;
}

export function cartIdFor(merchantId) {
  return state.carts[merchantId] || null;
}

export function setCartId(merchantId, cartId) {
  state.carts[merchantId] = cartId;
}
