import { api } from "../api.js";
import { statCard } from "../components/statCard.js";
import { statusPill } from "../components/statusPill.js";
import { table } from "../components/table.js";
import { mountChart, lineBarConfig } from "../components/chart.js";
import { money, pct, dateTime, titleCase } from "../format.js";

const ACTIVITY_STEPS = new Set(["order_created", "payment_captured", "payment_failed", "policy_rejected", "refund_completed", "order_confirmed"]);

const ICO = {
  revenue: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>`,
  orders: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3h12l3 3v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>`,
  conversion: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19V9M11 19V4M18 19v-6"/></svg>`,
  aov: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M8 15h4"/></svg>`,
  success: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="9"/></svg>`,
  failures: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>`,
  refunds: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>`,
  rejections: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="M9.5 9.5l5 5M14.5 9.5l-5 5"/></svg>`,
};

function activityStatus(step, status) {
  if (step === "policy_rejected") return "rejected_by_policy";
  if (step === "payment_captured" || step === "order_confirmed") return "captured";
  if (step === "payment_failed") return "failed";
  if (step === "refund_completed") return "refunded";
  return status === "success" ? "pending" : status;
}

export const overviewPage = {
  async render(root) {
    root.innerHTML = `
      <div class="qb-content-header">
        <div><div class="qb-content-title">Overview</div><div class="qb-content-subtitle">AI-attributed commerce performance across every connected merchant, derived from real order and audit data.</div></div>
      </div>
      <div id="ov-body"><div class="qb-skel qb-skel-card"></div></div>
    `;
    const body = document.getElementById("ov-body");

    const [analyticsRes, auditRes] = await Promise.all([api.analytics(), api.audit()]);
    if (!analyticsRes.ok) { body.innerHTML = `<div class="qb-note danger">Could not load analytics.</div>`; return; }
    const a = analyticsRes.data;
    const s = a.summary;
    const funnel = a.agentic_funnel || {};
    const events = (auditRes.data && auditRes.data.events) || [];

    const successRate = (s.captured_orders + s.failed_orders) > 0
      ? (s.captured_orders / (s.captured_orders + s.failed_orders) * 100) : null;

    body.innerHTML = `
      <div class="qb-shelf">
        <div class="qb-grid qb-grid-4">
          ${statCard({ label: "AI-attributed revenue", value: money(s.ai_assisted_revenue), icon: ICO.revenue, tint: "teal" })}
          ${statCard({ label: "Orders", value: `${s.captured_orders} / ${s.total_orders}`, delta: "captured / total", icon: ICO.orders, tint: "blue" })}
          ${statCard({ label: "Conversion rate", value: pct(s.conversion_rate_pct), icon: ICO.conversion, tint: "violet" })}
          ${statCard({ label: "Average order value", value: money(s.average_order_value), icon: ICO.aov, tint: "amber" })}
        </div>
      </div>

      <div class="qb-section qb-grid qb-grid-4">
        ${statCard({ label: "Payment success rate", value: successRate === null ? "—" : pct(successRate), icon: ICO.success, tint: "green" })}
        ${statCard({ label: "Payment failures", value: s.failed_orders, icon: ICO.failures, tint: "rose" })}
        ${statCard({ label: "Refunds", value: `${a.refunds.processed_count} · ${money(a.refunds.total_amount)}`, icon: ICO.refunds, tint: "blue" })}
        ${statCard({ label: "Policy rejections", value: funnel.policy_rejection_sessions ?? 0, icon: ICO.rejections, tint: "violet" })}
      </div>

      <div class="qb-section qb-grid qb-grid-main-side">
        <div class="qb-card">
          <div class="qb-card-header">
            <div><div class="qb-card-title qb-title-accent">AI commerce performance</div><div class="qb-card-sub">Orders, captures and failures by day</div></div>
          </div>
          <div class="qb-chart-wrap"><canvas id="ov-trend-chart"></canvas></div>
        </div>
        <div class="qb-card">
          <div class="qb-card-header"><div class="qb-card-title qb-title-accent">AI commerce insights</div></div>
          <div style="display:flex; flex-direction:column; gap:10px;">
            ${(a.insights || []).map((i) => `<div class="qb-note info" style="align-items:flex-start;">${i}</div>`).join("") || `<div class="qb-muted" style="font-size:13px;">No insights yet.</div>`}
          </div>
        </div>
      </div>

      <div class="qb-section">
        <div class="qb-card-header">
          <div><div class="qb-card-title">Recent activity</div><div class="qb-card-sub">Live + seeded demo data, derived from the real audit trail</div></div>
          <span class="qb-badge">Includes demo data</span>
        </div>
        <div id="ov-activity"></div>
      </div>
    `;

    const canvas = document.getElementById("ov-trend-chart");
    const trend = a.daily_trend || [];
    if (trend.length > 0 && window.Chart) {
      mountChart(canvas, lineBarConfig(
        trend.map((r) => r.day.slice(5)),
        [
          { label: "Captured", data: trend.map((r) => r.captured), color: "#0D9488" },
          { label: "Failed", data: trend.map((r) => r.failed), color: "#DC2626" },
        ]
      ));
    } else {
      canvas.replaceWith(Object.assign(document.createElement("div"), { className: "qb-muted", style: "font-size:13px; padding-top: 90px; text-align:center;", textContent: "No order activity yet in this environment." }));
    }

    const activityRows = events.filter((e) => ACTIVITY_STEPS.has(e.step)).slice(0, 12).map((e) => {
      const detail = e.detail || {};
      const merchant = (detail.cart_mandate && detail.cart_mandate.merchant_id) || detail.merchant_id || "—";
      const amount = (detail.cart_total) || (detail.cart_mandate && detail.cart_mandate.total_amount) || (detail.payment && detail.payment.amount / 100) || null;
      return {
        order: e.session_id, merchant, category: "—", amount, step: e.step, status: e.status, created_at: e.created_at,
      };
    });

    document.getElementById("ov-activity").innerHTML = table(
      [
        { key: "order", label: "Session", render: (r) => `<span class="qb-table-id">${r.order}</span>` },
        { key: "merchant", label: "Merchant" },
        { key: "step", label: "Event", render: (r) => titleCase(r.step) },
        { key: "amount", label: "Amount", num: true, render: (r) => (r.amount ? money(r.amount) : "—") },
        { key: "status", label: "Status", render: (r) => statusPill(activityStatus(r.step, r.status)) },
        { key: "created_at", label: "Time", render: (r) => dateTime(r.created_at) },
      ],
      activityRows,
      { emptyTitle: "No activity yet", emptySub: "Try the AI Agent page to generate some." }
    );
  },
};
