import { api } from "../api.js";
import { statCard } from "../components/statCard.js";
import { mountChart, lineBarConfig, doughnutConfig } from "../components/chart.js";
import { money, pct, titleCase } from "../format.js";

export const analyticsPage = {
  async render(root) {
    root.innerHTML = `
      <div class="qb-content-header">
        <div><div class="qb-content-title">Analytics</div><div class="qb-content-subtitle">Real transaction analytics, derived from order and audit data - kept strictly separate from the synthetic growth benchmark below.</div></div>
      </div>
      <div id="an-body"><div class="qb-skel qb-skel-card"></div></div>
    `;
    const body = document.getElementById("an-body");

    const [analyticsRes, ordersRes, growthRes] = await Promise.all([api.analytics(), api.listOrders(200), api.growthExperiment()]);
    const a = analyticsRes.data;
    const s = a.summary;
    const funnel = a.agentic_funnel || {};
    const orders = (ordersRes.data && ordersRes.data.orders) || [];
    const g = growthRes.ok ? growthRes.data : null;

    const byCategory = {};
    orders.filter((o) => o.status === "captured").forEach((o) => { byCategory[o.category || "unknown"] = (byCategory[o.category || "unknown"] || 0) + o.amount; });

    body.innerHTML = `
      <div class="qb-section qb-grid qb-grid-4">
        ${statCard({ label: "AI-assisted conversion", value: pct(s.conversion_rate_pct) })}
        ${statCard({ label: "AI-attributed revenue", value: money(s.ai_assisted_revenue) })}
        ${statCard({ label: "Average order value", value: money(s.average_order_value) })}
        ${statCard({ label: "Upsell acceptance", value: pct(s.upsell_acceptance_rate_pct) })}
      </div>

      <div class="qb-section qb-grid qb-grid-main-side">
        <div class="qb-card">
          <div class="qb-card-header"><div class="qb-card-title">Conversion funnel</div></div>
          <div class="qb-chart-wrap"><canvas id="an-funnel"></canvas></div>
        </div>
        <div class="qb-card">
          <div class="qb-card-header"><div class="qb-card-title">Category performance</div><div class="qb-card-sub">Captured revenue by category</div></div>
          <div class="qb-chart-wrap"><canvas id="an-category"></canvas></div>
        </div>
      </div>

      <div class="qb-section qb-grid qb-grid-3">
        ${statCard({ label: "Policy rejection rate", value: `${funnel.policy_rejection_sessions ?? 0} sessions` })}
        ${statCard({ label: "Payment failure rate", value: `${funnel.payment_failure_sessions ?? 0} sessions` })}
        ${statCard({ label: "Payment retry sessions", value: `${funnel.payment_retry_sessions ?? 0} sessions` })}
      </div>

      <div class="qb-section">
        <div class="qb-card-header"><div class="qb-card-title">Merchant performance</div></div>
        <div class="qb-table-wrap qb-scroll">
          <table class="qb-table">
            <thead><tr><th>Merchant</th><th class="num">Orders</th><th class="num">Captured</th><th class="num">AOV</th><th class="num">Upsell %</th></tr></thead>
            <tbody>
              ${(a.merchants || []).map((m) => `<tr><td>${m.merchant_name}</td><td class="num">${m.orders}</td><td class="num">${m.captured}</td><td class="num">${money(m.average_order_value)}</td><td class="num">${pct(m.upsell_acceptance_rate_pct)}</td></tr>`).join("") || `<tr><td colspan="5" style="text-align:center; color:var(--qb-text-muted);">No merchant activity yet</td></tr>`}
            </tbody>
          </table>
        </div>
      </div>

      <div class="qb-section">
        <div class="qb-card">
          <div class="qb-card-header">
            <div><div class="qb-card-title">Growth experiment</div><div class="qb-card-sub">${g ? g.label : ""}</div></div>
            <span class="qb-badge synthetic">Synthetic benchmark</span>
          </div>
          ${g ? `
            <div class="qb-grid qb-grid-3">
              <div><div class="qb-kv-label" style="font-size:12px;">Conversion uplift</div><div style="font-size:20px; font-weight:700;">${g.uplift.conversion_rate_uplift_pct}%</div></div>
              <div><div class="qb-kv-label" style="font-size:12px;">AOV uplift</div><div style="font-size:20px; font-weight:700;">${g.uplift.aov_uplift_pct}%</div></div>
              <div><div class="qb-kv-label" style="font-size:12px;">Revenue uplift</div><div style="font-size:20px; font-weight:700;">${g.uplift.revenue_uplift_pct}%</div></div>
            </div>
            <div class="qb-divider"></div>
            <div class="qb-subtle" style="font-size:12px;">${g.assumptions.join(" ")}</div>
          ` : `<div class="qb-muted" style="font-size:13px;">Growth experiment unavailable.</div>`}
        </div>
      </div>
    `;

    if (window.Chart) {
      const funnelLabels = Object.keys(funnel.steps || {});
      mountChart(document.getElementById("an-funnel"), lineBarConfig(
        funnelLabels.map((l) => titleCase(l)),
        [{ label: "Sessions reaching step", data: funnelLabels.map((l) => funnel.steps[l]), color: "#0D9488" }]
      ));
      const catLabels = Object.keys(byCategory);
      if (catLabels.length > 0) {
        mountChart(document.getElementById("an-category"), doughnutConfig(catLabels.map(titleCase), catLabels.map((c) => byCategory[c])));
      } else {
        document.getElementById("an-category").replaceWith(Object.assign(document.createElement("div"), { className: "qb-muted", style: "font-size:13px;text-align:center;padding-top:90px;", textContent: "No captured orders yet." }));
      }
    }
  },
};
