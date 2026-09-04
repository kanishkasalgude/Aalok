import { api } from "../api.js";
import { table } from "../components/table.js";
import { statusPill } from "../components/statusPill.js";
import { timeline } from "../components/timeline.js";
import { money, dateTime, titleCase } from "../format.js";

function openDetailPanel(html) {
  let panel = document.getElementById("order-detail-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "order-detail-panel";
    panel.className = "qb-drawer";
    document.body.appendChild(panel);
    const backdrop = document.createElement("div");
    backdrop.id = "order-detail-backdrop";
    backdrop.className = "qb-drawer-backdrop";
    document.body.appendChild(backdrop);
    backdrop.addEventListener("click", closeDetailPanel);
  }
  panel.innerHTML = html;
  panel.querySelector('[data-action="close-detail"]').addEventListener("click", closeDetailPanel);
  requestAnimationFrame(() => {
    panel.classList.add("open");
    document.getElementById("order-detail-backdrop").classList.add("open");
  });
}
function closeDetailPanel() {
  const panel = document.getElementById("order-detail-panel");
  const backdrop = document.getElementById("order-detail-backdrop");
  if (panel) panel.classList.remove("open");
  if (backdrop) backdrop.classList.remove("open");
}

async function showOrderDetail(orderId) {
  openDetailPanel(`
    <div class="qb-drawer-header"><div style="font-weight:700;">Order detail</div><button class="qb-drawer-close" data-action="close-detail">✕</button></div>
    <div class="qb-drawer-body qb-scroll"><div class="qb-skel qb-skel-line"></div><div class="qb-skel qb-skel-line" style="width:70%"></div></div>
  `);
  const orderRes = await api.getOrder(orderId);
  if (!orderRes.ok || orderRes.data.error) return;
  const order = orderRes.data;
  const auditRes = await api.audit(order.session_id);
  const events = (auditRes.data && auditRes.data.events) || [];

  openDetailPanel(`
    <div class="qb-drawer-header"><div style="font-weight:700;">Order detail</div><button class="qb-drawer-close" data-action="close-detail">✕</button></div>
    <div class="qb-drawer-body qb-scroll">
      <div class="qb-kv"><span class="qb-kv-label">Order ID</span><span class="qb-kv-value qb-table-id">${order.internal_order_id}</span></div>
      <div class="qb-kv"><span class="qb-kv-label">Razorpay order</span><span class="qb-kv-value qb-table-id">${order.razorpay_order_id || "—"}</span></div>
      <div class="qb-kv"><span class="qb-kv-label">Payment ID</span><span class="qb-kv-value qb-table-id">${order.payment_id || "—"}</span></div>
      <div class="qb-kv"><span class="qb-kv-label">Merchant</span><span class="qb-kv-value">${order.merchant_id}</span></div>
      <div class="qb-kv"><span class="qb-kv-label">Amount</span><span class="qb-kv-value">${money(order.amount, order.currency)}</span></div>
      <div class="qb-kv"><span class="qb-kv-label">Status</span><span class="qb-kv-value">${statusPill(order.status)}</span></div>
      <div class="qb-kv"><span class="qb-kv-label">Created</span><span class="qb-kv-value">${dateTime(order.created_at)}</span></div>
      <div class="qb-divider"></div>
      <div class="qb-card-title" style="margin-bottom:10px; font-size:13px;">Lifecycle: Intent → Authorization → Cart → Policy → Internal Order → Razorpay Order → Payment → Webhook → Final</div>
      ${timeline(events)}
    </div>
  `);
}

export const ordersPage = {
  async render(root) {
    root.innerHTML = `
      <div class="qb-content-header">
        <div><div class="qb-content-title">Orders</div><div class="qb-content-subtitle">Every internal order Aalok has created, idempotently mapped to at most one Razorpay order each.</div></div>
      </div>
      <div id="orders-table"><div class="qb-skel qb-skel-card"></div></div>
    `;
    const res = await api.listOrders(100);
    const orders = (res.data && res.data.orders) || [];
    document.getElementById("orders-table").innerHTML = table(
      [
        { key: "internal_order_id", label: "Order ID", render: (r) => `<span class="qb-table-id">${r.internal_order_id.slice(0, 16)}…</span>` },
        { key: "merchant_name", label: "Merchant" },
        { key: "category", label: "Category", render: (r) => titleCase(r.category) },
        { key: "amount", label: "Amount", num: true, render: (r) => money(r.amount, r.currency) },
        { key: "razorpay_order_id", label: "Payment", render: (r) => statusPill(r.status) },
        { key: "created_at", label: "Created", render: (r) => dateTime(r.created_at) },
        { key: "actions", label: "", render: () => `<span class="qb-btn qb-btn-ghost qb-btn-sm">View →</span>` },
      ],
      orders,
      { emptyTitle: "No orders yet", emptySub: "Complete a checkout from the AI Agent or Discover page to see it here.",
        rowClass: () => "clickable", rowAttr: (r) => `data-order-id="${r.internal_order_id}"` }
    );
    document.querySelectorAll("#orders-table tr[data-order-id]").forEach((tr) => {
      tr.addEventListener("click", () => showOrderDetail(tr.dataset.orderId));
    });
  },
};
