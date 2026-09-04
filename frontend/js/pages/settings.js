import { api } from "../api.js";
import { state } from "../state.js";

export const settingsPage = {
  async render(root) {
    const modeRes = await api.paymentMode();
    const mode = modeRes.data || {};
    root.innerHTML = `
      <div class="qb-content-header">
        <div><div class="qb-content-title">Settings</div><div class="qb-content-subtitle">Read-only environment summary. No secrets are ever shown here, and there is no in-UI way to change configuration - that stays server-side, by design.</div></div>
      </div>
      <div class="qb-card" style="max-width:520px;">
        <div class="qb-kv"><span class="qb-kv-label">Session ID</span><span class="qb-kv-value qb-table-id">${state.sessionId}</span></div>
        <div class="qb-kv"><span class="qb-kv-label">Payment provider</span><span class="qb-kv-value">${mode.provider || "—"}</span></div>
        <div class="qb-kv"><span class="qb-kv-label">Mode</span><span class="qb-kv-value">${(mode.mode || "unknown").toUpperCase()}</span></div>
        <div class="qb-kv"><span class="qb-kv-label">Webhook secret configured</span><span class="qb-kv-value">${mode.webhook_secret_configured ? "Yes" : "No"}</span></div>
        <div class="qb-divider"></div>
        <div class="qb-note ${mode.mode === "test" ? "success" : "info"}">${mode.note || (mode.mode === "test" ? "Real Razorpay Test Mode is active - Checkout.js opens a genuine test-mode payment session." : "Running in mock mode - the full flow is exercised with zero real network calls.")}</div>
      </div>
    `;
  },
};
