import { money, titleCase } from "../format.js";

function minutesLabel(min) {
  if (min === null || min === undefined) return "—";
  if (min < 60) return `${min}m`;
  if (min < 1440) return `${Math.round(min / 60)}h`;
  return `${Math.round(min / 1440)}d`;
}
import { merchantFor } from "../state.js";

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
  const icon = status === "PASS" ? "✓" : "✕";
  return `
    <div class="qb-authz-row">
      <span class="qb-authz-row-label">${label}</span>
      <span class="qb-authz-row-value" style="color: var(--qb-${cls})">${icon} ${valueText || status}</span>
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
  }

  const reason = decision ? decision.reason : (authorizationDecision ? authorizationDecision.reason : "");

  return `
    <div class="qb-authz-card">
      <div class="qb-authz-head ${passed ? "pass" : "reject"}">
        <span class="qb-authz-head-title">${passed ? "✓ Authorization passed" : "✕ Authorization / Policy rejected"}</span>
      </div>
      <div class="qb-authz-body">
        ${authzRows}
        ${policyRows}
        ${!passed && reason ? `<div class="qb-authz-reject-note"><strong>${reason}</strong><br/>No Razorpay order was created. No money moved.</div>` : ""}
      </div>
    </div>
  `;
}
