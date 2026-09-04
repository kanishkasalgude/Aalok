import { api } from "../api.js";
import { state } from "../state.js";
import { titleCase, categoryEmoji, categoryTint } from "../format.js";

export const merchantsPage = {
  async render(root) {
    root.innerHTML = `
      <div class="qb-content-header">
        <div>
          <div class="qb-content-title">Merchants</div>
          <div class="qb-content-subtitle">Every source the AI Commerce Discovery Gateway federates. All merchants in this environment are synthetic - there is no real Swiggy/Zomato/BigBasket/Zepto integration anywhere.</div>
        </div>
      </div>
      <div id="merchants-body"><div class="qb-grid qb-grid-3">${Array.from({ length: 6 }).map(() => `<div class="qb-skel qb-skel-card"></div>`).join("")}</div></div>
    `;

    const [productsRes] = await Promise.all([api.searchCatalog({ query: "", top_k: 300 })]);
    const counts = {};
    if (productsRes.ok) {
      for (const p of (productsRes.data.results || [])) counts[p.merchant_id] = (counts[p.merchant_id] || 0) + 1;
    }

    const body = document.getElementById("merchants-body");
    const cards = state.merchants.map((m) => `
      <div class="qb-card">
        <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:8px;">
          <div style="display:flex; gap:10px;">
            <div class="qb-icon-circle sm ${categoryTint(m.category)}">${categoryEmoji(m.category)}</div>
            <div>
              <div class="qb-title-accent" style="font-weight:700; font-size:14px;">${m.name}</div>
              <div class="qb-subtle" style="font-size:12px;">${titleCase(m.category)}${m.subcategory ? " · " + titleCase(m.subcategory) : ""}</div>
            </div>
          </div>
          ${m.is_synthetic ? `<span class="qb-badge synthetic">Synthetic Merchant</span>` : ""}
        </div>
        <div class="qb-divider"></div>
        <div class="qb-kv"><span class="qb-kv-label">Products</span><span class="qb-kv-value">${counts[m.merchant_id] || 0}</span></div>
        <div class="qb-kv"><span class="qb-kv-label">Status</span><span class="qb-kv-value">${m.open ? "Open" : "Closed"}</span></div>
        <div class="qb-kv"><span class="qb-kv-label">Tier</span><span class="qb-kv-value">${titleCase(m.tier)}</span></div>
        <div class="qb-kv"><span class="qb-kv-label">Rating</span><span class="qb-kv-value">★ ${m.rating.toFixed(1)}</span></div>
        <div class="qb-divider"></div>
        <div class="qb-card-sub" style="margin-bottom:6px;">Capabilities</div>
        <div class="qb-chip-group">
          ${Object.entries(m.capabilities).map(([k, v]) => `<span class="qb-badge" style="${v ? "" : "opacity:.4;"}">${titleCase(k)}${v ? "" : " off"}</span>`).join("")}
        </div>
      </div>
    `).join("");

    body.innerHTML = `<div class="qb-shelf"><div class="qb-grid qb-grid-3">${cards}</div></div>`;
  },
};
