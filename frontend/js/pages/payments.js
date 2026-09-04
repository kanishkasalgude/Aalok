import { api } from "../api.js";
import { table } from "../components/table.js";
import { statusPill } from "../components/statusPill.js";
import { money, dateTime } from "../format.js";

export const paymentsPage = {
  async render(root) {
    root.innerHTML = `
      <div class="qb-content-header">
        <div><div class="qb-content-title">Payments</div><div class="qb-content-subtitle">Payment attempts and their outcomes. Aalok never collects card/UPI details itself - Razorpay's own Checkout owns payment collection.</div></div>
        <div id="pay-env"></div>
      </div>
      <div class="qb-section" id="pay-table"><div class="qb-skel qb-skel-card"></div></div>
      <div class="qb-card-header"><div class="qb-card-title">Refunds</div></div>
      <div id="refunds-table"><div class="qb-skel qb-skel-card"></div></div>
    `;

    const [modeRes, ordersRes, refundsRes] = await Promise.all([api.paymentMode(), api.listOrders(100), api.listRefunds(50)]);
    const mode = modeRes.data || {};
    document.getElementById("pay-env").innerHTML = `
      <span class="qb-pill ${mode.mode === "test" ? "success" : mode.mode === "mock" ? "warning" : "danger"}">
        <span class="qb-pill-dot"></span>${mode.mode === "test" ? "RAZORPAY TEST MODE" : mode.mode === "mock" ? "MOCK MODE" : "MISCONFIGURED"}
      </span>
    `;

    const orders = (ordersRes.data && ordersRes.data.orders) || [];
    document.getElementById("pay-table").innerHTML = table(
      [
        { key: "razorpay_order_id", label: "Razorpay Order ID", render: (r) => `<span class="qb-table-id">${r.razorpay_order_id || "—"}</span>` },
        { key: "payment_id", label: "Payment ID", render: (r) => `<span class="qb-table-id">${r.payment_id || "—"}</span>` },
        { key: "merchant_name", label: "Merchant" },
        { key: "amount", label: "Amount", num: true, render: (r) => money(r.amount, r.currency) },
        { key: "method", label: "Method", render: () => "—" },
        { key: "status", label: "Status", render: (r) => statusPill(r.status) },
        { key: "created_at", label: "Created", render: (r) => dateTime(r.created_at) },
      ],
      orders,
      { emptyTitle: "No payment attempts yet" }
    );

    const refunds = (refundsRes.data && refundsRes.data.refunds) || [];
    document.getElementById("refunds-table").innerHTML = table(
      [
        { key: "refund_id", label: "Refund ID", render: (r) => `<span class="qb-table-id">${r.refund_id}</span>` },
        { key: "internal_order_id", label: "Order", render: (r) => `<span class="qb-table-id">${r.internal_order_id.slice(0, 16)}…</span>` },
        { key: "amount", label: "Amount", num: true, render: (r) => money(r.amount) },
        { key: "reason", label: "Reason" },
        { key: "status", label: "Status", render: (r) => statusPill(r.status) },
        { key: "created_at", label: "Created", render: (r) => dateTime(r.created_at) },
      ],
      refunds,
      { emptyTitle: "No refunds issued", emptySub: "This environment hasn't processed a refund yet." }
    );
  },
};
