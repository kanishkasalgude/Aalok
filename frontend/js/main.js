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
  overview: `<svg class="qb-nav-icon animated-icon" viewBox="0 0 24 24"><g class="icon-group-1"><rect x="2" y="2" width="9" height="9" fill="currentColor" opacity="0.7"/></g><g class="icon-group-2"><rect x="13" y="2" width="9" height="9" fill="currentColor" opacity="0.9"/></g><g class="icon-group-3"><rect x="13" y="13" width="9" height="9" fill="currentColor" opacity="0.8"/></g><g class="icon-group-4"><rect x="2" y="13" width="9" height="9" fill="currentColor" opacity="0.85"/></g></svg>`,
  agent: `<svg class="qb-nav-icon animated-icon" viewBox="0 0 24 24"><g class="icon-head"><circle cx="12" cy="6" r="3" fill="currentColor"/></g><g class="icon-body"><path d="M12 9v5M8 13c0 2 2.2 3.5 4 3.5s4-1.5 4-3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></g></svg>`,
  discover: `<svg class="qb-nav-icon animated-icon" viewBox="0 0 24 24"><g class="icon-circle"><circle cx="9" cy="9" r="6" fill="none" stroke="currentColor" stroke-width="2"/></g><g class="icon-line"><line x1="15" y1="15" x2="20" y2="20" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></g></svg>`,
  merchants: `<svg class="qb-nav-icon animated-icon" viewBox="0 0 24 24"><g class="icon-roof"><polygon points="12,3 4,10 20,10" fill="currentColor"/></g><g class="icon-walls"><rect x="4" y="10" width="16" height="10" fill="none" stroke="currentColor" stroke-width="2"/></g><g class="icon-door"><rect x="10" y="14" width="4" height="6" fill="currentColor"/></g></svg>`,
  orders: `<svg class="qb-nav-icon animated-icon" viewBox="0 0 24 24"><g class="icon-document"><path d="M5 2h12v18H5V2" fill="none" stroke="currentColor" stroke-width="2"/></g><g class="icon-lines"><line x1="8" y1="8" x2="14" y2="8" stroke="currentColor" stroke-width="1.5"/><line x1="8" y1="12" x2="14" y2="12" stroke="currentColor" stroke-width="1.5"/><line x1="8" y1="16" x2="11" y2="16" stroke="currentColor" stroke-width="1.5"/></g></svg>`,
  payments: `<svg class="qb-nav-icon animated-icon" viewBox="0 0 24 24"><g class="icon-card"><rect x="1" y="6" width="22" height="12" rx="1" fill="none" stroke="currentColor" stroke-width="2"/></g><g class="icon-stripe"><line x1="1" y1="10" x2="23" y2="10" stroke="currentColor" stroke-width="2"/></g></svg>`,
  analytics: `<svg class="qb-nav-icon animated-icon" viewBox="0 0 24 24"><g class="icon-bar-1"><rect x="2" y="12" width="4" height="9" fill="currentColor"/></g><g class="icon-bar-2"><rect x="10" y="5" width="4" height="16" fill="currentColor"/></g><g class="icon-bar-3"><rect x="18" y="9" width="4" height="12" fill="currentColor"/></g></svg>`,
  audit: `<svg class="qb-nav-icon animated-icon" viewBox="0 0 24 24"><g class="icon-document"><path d="M4 2h14v18H4V2" fill="none" stroke="currentColor" stroke-width="2"/></g><g class="icon-text"><line x1="7" y1="8" x2="15" y2="8" stroke="currentColor" stroke-width="1.5"/><line x1="7" y1="12" x2="15" y2="12" stroke="currentColor" stroke-width="1.5"/><line x1="7" y1="16" x2="12" y2="16" stroke="currentColor" stroke-width="1.5"/></g></svg>`,
  settings: `<svg class="qb-nav-icon animated-icon" viewBox="0 0 24 24"><g class="icon-center"><circle cx="12" cy="12" r="3" fill="currentColor"/></g><g class="icon-gear"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="2,2"/><path d="M12 2v2M12 20v2M22 12h-2M2 12h2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></g></svg>`,
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
