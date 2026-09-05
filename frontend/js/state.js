// Shared client-side state. Deliberately thin: session id + token, cart ids
// by merchant, a merchants cache, and the payment-mode badge - the backend
// remains authoritative for price/inventory/authorization/policy/order/
// payment status. Nothing here is ever trusted for those decisions; it's
// only used to know WHICH backend objects (session, cart) to talk to next.
//
// sessionToken (Track 01 Phase 2) is what actually proves identity to the
// backend - session_id alone is just a uuid, not a secret. Neither is
// generated client-side any more: the FIRST request this client makes (with
// no token) gets a freshly minted {session_id, session_token} back from the
// server, and api.js persists it here for every subsequent call - see
// services/session/auth.py for why a client can no longer just invent or
// claim an arbitrary session_id.
export const state = {
  sessionId: localStorage.getItem("qb_session_id") || null,
  sessionToken: localStorage.getItem("qb_session_token") || null,
  paymentMode: null,
  merchants: [],
  merchantsById: {},
  carts: {}, // merchant_id -> cart_id (client only tracks WHICH cart to add to; server owns contents)
};

export function setSession(sessionId, sessionToken) {
  if (!sessionId || !sessionToken) return;
  state.sessionId = sessionId;
  state.sessionToken = sessionToken;
  localStorage.setItem("qb_session_id", sessionId);
  localStorage.setItem("qb_session_token", sessionToken);
}

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
