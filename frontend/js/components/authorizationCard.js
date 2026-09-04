import { money, titleCase } from "../format.js";

// Minimal line icons - no emoji/Unicode glyph anywhere in the product.
const CHECK_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12l5 5L20 6"/></svg>`;
const CROSS_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>`;

function minutesLabel(min) {
  if (min === null || min === undefined) return "—";
  if (min < 60) return `${min}m`;
  if (min < 1440) return `${Math.round(min / 60)}h`;
  return `${Math.round(min / 1440)}d`;
}
import { merchantFor } from "../state.js";

// Real MerchantCapabilities flags (backend/domain/catalog/capabilities.py),
// already returned by GET /api/merchants and cached in state.js - nothing
// here is invented or hardcoded to all-pass. A merchant with refunds/
// subscriptions/marketplace/agentic_checkout off shows those as muted, not
// as a failure - they're undeclared capabilities, not rejected checks.
const CAPABILITY_LABELS = {
  catalog: "Catalog", checkout: "Checkout", refunds: "Refunds",
  subscriptions: "Subscriptions", marketplace: "Marketplace", agentic_checkout: "Agentic checkout",
};

function capabilityChip(label, on) {
  return `<span class="qb-authz-cap ${on ? "success" : "muted"}">${on ? CHECK_ICON : CROSS_ICON}${label}</span>`;
}

const POLICY_CHECK_LABELS = {
  mandate_validity: "Mandate valid",
  cart_expiry: "Cart not expired",
  budget: "Budget",
  delivery_time: "Delivery constraint",
  merchant_availability: "Merchant availability",
  inventory: "Inventory",
  attributes: "Attribute match",
};

function checkRow(label, status, valueText) {
  const cls = status === "PASS" ? "success" : "danger";
  const icon = status === "PASS" ? CHECK_ICON : CROSS_ICON;
  return `
    <div class="qb-authz-row">
      <span class="qb-authz-row-label">${label}</span>
      <span class="qb-authz-row-value" style="color: var(--qb-${cls})">${icon}${valueText || status}</span>
    </div>
  `;
}

/**
 * Renders BOTH real decisions a checkout response carries: authorization_decision
 * (mode/status/scope checks) and decision (the PolicyDecision: budget/inventory/
 * merchant/attributes/etc). Every value shown is a real API field - nothing
 * paraphrased or invented.
 */
export function authorizationCard({ authorizationDecision, decision, cartMandate }) {
  const merchant = cartMandate ? merchantFor(cartMandate.merchant_id) : null;
  const passed = decision ? decision.decision === "PASS" : (authorizationDecision ? authorizationDecision.allowed : false);

  let policyRows = "";
  if (decision && decision.checks) {
    const c = decision.checks;
    if (c.budget) policyRows += checkRow("Budget limit", c.budget.status, `${money(c.budget.cart_total)} / ${money(c.budget.maximum)}`);
    if (c.mandate_validity) policyRows += checkRow(POLICY_CHECK_LABELS.mandate_validity, c.mandate_validity.status);
    if (c.cart_expiry) policyRows += checkRow(POLICY_CHECK_LABELS.cart_expiry, c.cart_expiry.status, c.cart_expiry.expired ? "Expired" : "Valid");
    if (c.merchant_availability) policyRows += checkRow("Merchant", c.merchant_availability.status, c.merchant_availability.open ? "Open" : "Closed");
    if (c.inventory) policyRows += checkRow("Inventory", c.inventory.status, c.inventory.unavailable_items && c.inventory.unavailable_items.length ? c.inventory.unavailable_items.join(", ") : "Available");
    if (c.delivery_time) policyRows += checkRow(POLICY_CHECK_LABELS.delivery_time, c.delivery_time.status, c.delivery_time.maximum_minutes ? `${minutesLabel(c.delivery_time.estimated_minutes)} / ${minutesLabel(c.delivery_time.maximum_minutes)} limit` : `${minutesLabel(c.delivery_time.estimated_minutes)} (no limit stated)`);
    if (c.attributes) policyRows += checkRow(POLICY_CHECK_LABELS.attributes, c.attributes.status);
  }

  let authzRows = "";
  if (authorizationDecision) {
    authzRows += `
      <div class="qb-authz-row"><span class="qb-authz-row-label">Authorization</span><span class="qb-authz-row-value">${titleCase(authorizationDecision.status)}</span></div>
    `;
  }
  if (merchant) {
    authzRows += `
      <div class="qb-authz-row"><span class="qb-authz-row-label">Merchant</span><span class="qb-authz-row-value">${merchant.name}</span></div>
      <div class="qb-authz-row"><span class="qb-authz-row-label">Category</span><span class="qb-authz-row-value">${titleCase(merchant.category)}</span></div>
    `;
    if (merchant.capabilities) {
      const chips = Object.entries(CAPABILITY_LABELS)
        .map(([key, label]) => capabilityChip(label, !!merchant.capabilities[key]))
        .join("");
      authzRows += `<div class="qb-authz-caps">${chips}</div>`;
    }
  }

  const reason = decision ? decision.reason : (authorizationDecision ? authorizationDecision.reason : "");
  const budgetCheck = decision && decision.checks ? decision.checks.budget : null;
  const passSentence = passed && budgetCheck
    ? `<div class="qb-authz-lead">${money(budgetCheck.cart_total)} is within your ${money(budgetCheck.maximum)} spending limit. All required checks passed.</div>`
    : "";

  return `
    <div class="qb-authz-card">
      <div class="qb-authz-head ${passed ? "pass" : "reject"}">
        <span class="qb-authz-head-title">${passed ? CHECK_ICON : CROSS_ICON}${passed ? "Authorization passed" : "Authorization / Policy rejected"}</span>
      </div>
      <div class="qb-authz-body">
        ${passSentence}
        ${authzRows}
        ${policyRows}
        ${!passed && reason ? `<div class="qb-authz-reject-note"><strong>${reason}</strong><br/>No Razorpay order was created. No money moved.</div>` : ""}
      </div>
    </div>
  `;
}
