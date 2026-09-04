export function emptyState({ icon = "🗂️", title, sub = "" }) {
  return `
    <div class="qb-empty">
      <div class="qb-empty-icon">${icon}</div>
      <div class="qb-empty-title">${title}</div>
      ${sub ? `<div class="qb-empty-sub">${sub}</div>` : ""}
    </div>
  `;
}
