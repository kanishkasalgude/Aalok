const MAP = {
  captured: ["success", "Paid"],
  paid: ["success", "Paid"],
  success: ["success", "Paid"],
  processed: ["success", "Processed"],
  passed: ["success", "Passed"],
  pass: ["success", "Passed"],
  active: ["success", "Active"],

  pending: ["warning", "Pending"],
  created: ["warning", "Pending"],
  requires_checkout_js: ["warning", "Awaiting Checkout"],
  awaiting_checkout: ["warning", "Awaiting Checkout"],
  retrying: ["warning", "Retrying"],
  requested: ["warning", "Requested"],

  failed: ["danger", "Failed"],
  fail: ["danger", "Failed"],
  reject: ["danger", "Rejected"],
  rejected: ["danger", "Rejected"],
  rejected_by_policy: ["danger", "Policy Rejected"],
  rejected_by_authorization: ["danger", "Authorization Rejected"],
  policy_rejected: ["danger", "Policy Rejected"],
  expired: ["danger", "Expired"],
  revoked: ["danger", "Revoked"],
  cancelled: ["neutral", "Cancelled"],

  refunded: ["info", "Refunded"],
  reversed: ["info", "Reversed"],
};

export function statusPill(rawStatus, labelOverride) {
  const key = String(rawStatus || "").toLowerCase();
  const [kind, defaultLabel] = MAP[key] || ["neutral", rawStatus || "Unknown"];
  const label = labelOverride || defaultLabel;
  return `<span class="qb-pill ${kind}"><span class="qb-pill-dot"></span>${label}</span>`;
}
