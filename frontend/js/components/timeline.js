import { dateTime, titleCase } from "../format.js";

// Maps real audit event step names (domain/audit/events.py) to the 9-stage
// lifecycle a reviewer wants to see: Intent -> Authorization -> Cart ->
// Policy -> Internal Order -> Razorpay Order -> Payment -> Webhook -> Final.
// No stage is invented - a stage simply doesn't render if that step never
// happened for this session (e.g. a rejected cart never reaches "Razorpay Order").
const STEP_LABELS = {
  intent_captured: "Intent captured",
  authorization_created: "Authorization created",
  authorization_checked: "Authorization checked",
  authorization_expired: "Authorization expired",
  authorization_revoked: "Authorization revoked",
  catalog_search: "Catalog searched",
  recommendation_generated: "Recommendation generated",
  cart_created: "Cart locked",
  cart_modified: "Cart modified",
  policy_evaluated: "Policy evaluated",
  policy_passed: "Policy passed",
  policy_rejected: "Policy rejected",
  order_created: "Internal + Razorpay order created",
  order_reused: "Order reused (retry - no duplicate)",
  awaiting_checkout: "Awaiting Razorpay Checkout",
  payment_attempted: "Payment attempted",
  payment_captured: "Payment captured",
  payment_failed: "Payment failed",
  payment_verification_failed: "Signature verification failed",
  payment_retry: "Payment retry",
  webhook_received: "Webhook received",
  order_confirmed: "Order confirmed",
  recovery: "Retry available",
  refund_requested: "Refund requested",
  refund_completed: "Refund completed",
  payment_provider_error: "Payment provider error",
  razorpay_api_error: "Razorpay API error",
};

function dotClass(status) {
  if (status === "success") return "success";
  if (status === "pending") return "pending";
  return "failed";
}

export function timeline(events) {
  if (!events || events.length === 0) {
    return `<div class="qb-muted" style="font-size:13px;">No audit events for this session yet.</div>`;
  }
  const items = events.map((e) => {
    const label = STEP_LABELS[e.step] || titleCase(e.step);
    const icon = e.status === "success" ? "✓" : e.status === "pending" ? "…" : "✕";
    let detailLine = "";
    if (e.detail) {
      if (e.detail.reason) detailLine = e.detail.reason;
      else if (e.detail.note) detailLine = e.detail.note;
      else if (e.detail.checks_summary) detailLine = Object.entries(e.detail.checks_summary).map(([k, v]) => `${k}: ${v}`).join(" · ");
    }
    return `
      <div class="qb-timeline-item">
        <div class="qb-timeline-rail">
          <div class="qb-timeline-dot ${dotClass(e.status)}">${icon}</div>
          <div class="qb-timeline-line"></div>
        </div>
        <div class="qb-timeline-content">
          <div class="qb-timeline-label">${label}</div>
          <div class="qb-timeline-ts">${dateTime(e.created_at)}</div>
          ${detailLine ? `<div class="qb-timeline-detail">${detailLine}</div>` : ""}
        </div>
      </div>
    `;
  }).join("");
  return `<div class="qb-timeline">${items}</div>`;
}
