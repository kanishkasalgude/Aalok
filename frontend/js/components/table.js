import { emptyState } from "./emptyState.js";

// columns: [{ key, label, num?, render?(row) }]
export function table(columns, rows, { emptyTitle = "Nothing here yet", emptySub = "", rowClass = () => "", rowAttr = () => "" } = {}) {
  if (!rows || rows.length === 0) {
    return `<div class="qb-card">${emptyState({ title: emptyTitle, sub: emptySub })}</div>`;
  }
  const head = columns.map((c) => `<th class="${c.num ? "num" : ""}">${c.label}</th>`).join("");
  const body = rows.map((row) => {
    const cells = columns.map((c) => {
      const val = c.render ? c.render(row) : (row[c.key] ?? "—");
      return `<td class="${c.num ? "num" : ""}">${val}</td>`;
    }).join("");
    return `<tr class="${rowClass(row)}" ${rowAttr(row)}>${cells}</tr>`;
  }).join("");
  return `
    <div class="qb-table-wrap qb-scroll">
      <table class="qb-table">
        <thead><tr>${head}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}
