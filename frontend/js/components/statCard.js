export function statCard({ label, value, delta, deltaDirection, icon, tint = "teal" }) {
  const deltaHtml = delta
    ? `<div class="qb-stat-delta ${deltaDirection || ""}">${delta}</div>`
    : "";
  return `
    <div class="qb-card qb-stat">
      <div class="qb-stat-top">
        <div class="qb-stat-label">${label}</div>
        ${icon ? `<div class="qb-icon-circle sm ${tint}">${icon}</div>` : ""}
      </div>
      <div class="qb-stat-value">${value}</div>
      ${deltaHtml}
    </div>
  `;
}
