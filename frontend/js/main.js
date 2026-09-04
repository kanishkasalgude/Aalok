import { api } from "./api.js";
import { state, setMerchants } from "./state.js";
import { registerRoute, init as initRouter, setNavUpdater, navigate } from "./router.js";
import { mountCartDrawer, addToCart, openCartDrawer } from "./components/cartDrawer.js";
import { tapBounce } from "./motion.js";

import { overviewPage } from "./pages/overview.js";
import { agentPage } from "./pages/agent.js";
import { discoverPage } from "./pages/discover.js";
import { merchantsPage } from "./pages/merchants.js";
import { ordersPage } from "./pages/orders.js";
import { paymentsPage } from "./pages/payments.js";
import { analyticsPage } from "./pages/analytics.js";
import { auditPage } from "./pages/audit.js";
import { settingsPage } from "./pages/settings.js";

const ICONS = {
  overview: `<svg class="qb-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="5" rx="1.5"/><rect x="13" y="10" width="8" height="11" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/></svg>`,
  agent: `<svg class="qb-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="8" r="3.2"/><path d="M5 20c0-3.5 3-6 7-6s7 2.5 7 6"/></svg>`,
  discover: `<svg class="qb-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.5-4.5"/></svg>`,
  merchants: `<svg class="qb-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 9l1.5-5h15L21 9"/><path d="M4 9v10h16V9"/><path d="M9 19v-6h6v6"/></svg>`,
  orders: `<svg class="qb-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 3h9l3 3v15H6z"/><path d="M9 9h6M9 13h6M9 17h4"/></svg>`,
  payments: `<svg class="qb-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2.5" y="6" width="19" height="13" rx="2"/><path d="M2.5 10.5h19"/></svg>`,
  analytics: `<svg class="qb-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20V10M12 20V4M20 20v-7"/></svg>`,
  audit: `<svg class="qb-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 4h14v16l-3-2-2 2-2-2-2 2-2-2-3 2z"/><path d="M8 9h8M8 13h8"/></svg>`,
  settings: `<svg class="qb-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.3-.9-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-.9a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.3.9 2-3.4-2-1.5c.07-.4.1-.8.1-1.2z"/></svg>`,
};

const NAV = [
  { path: "/overview", label: "Overview", icon: "overview" },
  { path: "/agent", label: "AI Agent", icon: "agent" },
  { path: "/discover", label: "Discover", icon: "discover" },
  { path: "/merchants", label: "Merchants", icon: "merchants" },
  { path: "/orders", label: "Orders", icon: "orders" },
  { path: "/payments", label: "Payments", icon: "payments" },
  { path: "/analytics", label: "Analytics", icon: "analytics" },
  { path: "/audit", label: "Audit Trail", icon: "audit" },
];

const TITLES = { "/overview": "Overview", "/agent": "AI Agent", "/discover": "Discover", "/merchants": "Merchants",
  "/orders": "Orders", "/payments": "Payments", "/analytics": "Analytics", "/audit": "Audit Trail", "/settings": "Settings" };

function renderShell() {
  document.getElementById("qb-app").innerHTML = `
    <div class="qb-shell">
      <aside class="qb-sidebar">
        <div class="qb-brand">
          <div class="qb-brand-mark">QB</div>
          <div>
            <div class="qb-brand-name">Aalok</div>
            <div class="qb-brand-tag">AI Commerce</div>
          </div>
        </div>
        <nav class="qb-nav" id="qb-nav">
          ${NAV.map((n) => `<a href="#${n.path}" class="qb-nav-item" data-path="${n.path}">${ICONS[n.icon]}<span class="qb-nav-label">${n.label}</span></a>`).join("")}
        </nav>
        <div class="qb-sidebar-footer">
          <div class="qb-env-chip" id="qb-env-chip"><div class="qb-env-dot mode-unknown"></div><span>Loading…</span></div>
          <a href="#/settings" class="qb-nav-item" data-path="/settings">${ICONS.settings}<span class="qb-nav-label">Settings</span></a>
        </div>
      </aside>
      <div class="qb-main">
        <header class="qb-topbar">
          <div class="qb-page-title" id="qb-page-title">Overview</div>
          <div class="qb-topbar-search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.5-4.5"/></svg>
            <input id="qb-global-search" type="text" placeholder="Search products across every merchant…" />
          </div>
          <span class="qb-topbar-spacer"></span>
          <div class="qb-topbar-right">
            <span class="qb-avatar">DU</span>
          </div>
        </header>
        <main class="qb-content" id="qb-content"></main>
      </div>
    </div>
  `;

  document.getElementById("qb-global-search").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.value.trim()) {
      window.__qbDiscoverQuery = e.target.value.trim();
      navigate("/discover");
    }
  });
}

function updateNav(path) {
  document.querySelectorAll(".qb-nav-item").forEach((el) => el.classList.toggle("active", el.dataset.path === path));
  document.getElementById("qb-page-title").textContent = TITLES[path] || "Aalok";
}

async function loadEnvBadge() {
  const res = await api.paymentMode();
  const mode = res.data || {};
  const chip = document.getElementById("qb-env-chip");
  const label = mode.mode === "test" ? "Razorpay Test Mode" : mode.mode === "mock" ? "Mock Mode" : "Misconfigured";
  chip.innerHTML = `<div class="qb-env-dot mode-${mode.mode}"></div><span>${label}</span>`;
  chip.title = mode.note || mode.error || "";
}

function wireGlobalActions() {
  document.body.addEventListener("click", (e) => {
    const btn = e.target.closest('[data-action="add-to-cart"]');
    if (btn && !btn.disabled) {
      tapBounce(btn);
      addToCart(btn.dataset.productId, btn.dataset.merchantId);
    }
  });
}

async function boot() {
  renderShell();
  wireGlobalActions();
  mountCartDrawer();
  loadEnvBadge();

  const merchantsRes = await api.merchants();
  if (merchantsRes.ok) setMerchants(merchantsRes.data.merchants || []);

  registerRoute("/overview", overviewPage);
  registerRoute("/agent", agentPage);
  registerRoute("/discover", discoverPage);
  registerRoute("/merchants", merchantsPage);
  registerRoute("/orders", ordersPage);
  registerRoute("/payments", paymentsPage);
  registerRoute("/analytics", analyticsPage);
  registerRoute("/audit", auditPage);
  registerRoute("/settings", settingsPage);

  setNavUpdater(updateNav);
  initRouter(document.getElementById("qb-content"));
}

boot();
