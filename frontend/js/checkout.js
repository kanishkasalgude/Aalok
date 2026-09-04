// Real Razorpay Checkout.js integration - ported from the pre-redesign
// app.js verbatim in behavior. Aalok never re-implements payment
// collection UI (spec Phase 12): this loads Razorpay's OWN real widget
// script and only ever reports the result back through
// /api/order/verify-payment (signature-verified server-side) or
// /api/order/payment-failed - never trusting the browser callback alone.
import { api } from "./api.js";

let checkoutScriptPromise = null;

function ensureCheckoutScript() {
  if (window.Razorpay) return Promise.resolve();
  if (checkoutScriptPromise) return checkoutScriptPromise;
  checkoutScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not load Razorpay Checkout.js"));
    document.head.appendChild(script);
  });
  return checkoutScriptPromise;
}

/**
 * Opens the REAL Razorpay Test Mode Checkout widget for an order the
 * backend already created (checkout.order_id/key_id/amount/currency from
 * OrderService.checkout's "checkout" field). Resolves with
 * {kind: "verified"|"failed"|"dismissed", data?, ok?}.
 */
export async function openRazorpayCheckout(sessionId, checkout) {
  await ensureCheckoutScript();
  return new Promise((resolve) => {
    const options = {
      key: checkout.key_id, amount: checkout.amount, currency: checkout.currency,
      name: "Aalok", description: checkout.description, order_id: checkout.order_id,
      theme: { color: "#0D9488" },
      handler: async function (response) {
        const res = await api.verifyPayment({
          session_id: sessionId, razorpay_payment_id: response.razorpay_payment_id,
          razorpay_order_id: response.razorpay_order_id, razorpay_signature: response.razorpay_signature,
        });
        resolve({ kind: "verified", data: res.data, ok: res.ok });
      },
      modal: { ondismiss: function () { resolve({ kind: "dismissed" }); } },
    };
    const rzp = new window.Razorpay(options);
    rzp.on("payment.failed", async function (response) {
      const res = await api.reportPaymentFailed({
        session_id: sessionId, razorpay_order_id: checkout.order_id,
        error_code: response.error && response.error.code,
        error_description: response.error && response.error.description,
      });
      resolve({ kind: "failed", data: res.data });
    });
    rzp.open();
  });
}
