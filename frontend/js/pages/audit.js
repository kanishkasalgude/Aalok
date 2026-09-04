import { api } from "../api.js";
import { table } from "../components/table.js";
import { titleCase, dateTime } from "../format.js";

let allEvents = [];

function applyFilters() {
  const typeFilter = document.getElementById("aud-type").value;
  const sessionFilter = document.getElementById("aud-session").value.trim().toLowerCase();
  const filtered = allEvents.filter((e) => {
    if (typeFilter && e.step !== typeFilter) return false;
    if (sessionFilter && !e.session_id.toLowerCase().includes(sessionFilter)) return false;
    return true;
  });
  renderTable(filtered);
}

function summarize(detail) {
  if (!detail) return "—";
  if (detail.reason) return detail.reason;
  if (detail.note) return detail.note;
  if (detail.error) return detail.error;
  if (detail.cart_total !== undefined) return `Cart total: ${detail.cart_total}`;
  const keys = Object.keys(detail).slice(0, 2);
  return keys.map((k) => `${k}: ${JSON.stringify(detail[k]).slice(0, 40)}`).join(", ");
}

function renderTable(events) {
  document.getElementById("audit-table").innerHTML = table(
    [
      { key: "created_at", label: "Time", render: (r) => dateTime(r.created_at) },
      { key: "step", label: "Event type", render: (r) => titleCase(r.step) },
      { key: "session_id", label: "Session", render: (r) => `<span class="qb-table-id">${r.session_id}</span>` },
      { key: "status", label: "Result" },
      { key: "detail", label: "Detail", render: (r) => `<span class="qb-truncate" style="display:inline-block;max-width:340px;">${summarize(r.detail)}</span>` },
    ],
    events,
    { emptyTitle: "No matching events" }
  );
}

export const auditPage = {
  async render(root) {
    root.innerHTML = `
      <div class="qb-content-header">
        <div><div class="qb-content-title">Audit Trail</div><div class="qb-content-subtitle">Every commerce-relevant decision this platform has made, timestamped. Never shows API keys, webhook secrets, or LLM chain-of-thought - the backend never writes them here in the first place.</div></div>
      </div>
      <div class="qb-filter-bar">
        <select class="qb-select" id="aud-type"><option value="">All event types</option></select>
        <input class="qb-input" id="aud-session" placeholder="Filter by session id…" style="min-width:220px;" />
      </div>
      <div id="audit-table"><div class="qb-skel qb-skel-card"></div></div>
    `;

    const res = await api.audit();
    allEvents = (res.data && res.data.events) || [];
    const types = [...new Set(allEvents.map((e) => e.step))].sort();
    const typeSelect = document.getElementById("aud-type");
    typeSelect.innerHTML += types.map((t) => `<option value="${t}">${titleCase(t)}</option>`).join("");

    typeSelect.addEventListener("change", applyFilters);
    document.getElementById("aud-session").addEventListener("input", applyFilters);
    renderTable(allEvents);
  },
};
