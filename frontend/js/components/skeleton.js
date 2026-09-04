export function skeletonLines(n = 3) {
  return Array.from({ length: n }).map((_, i) =>
    `<div class="qb-skel qb-skel-line" style="width:${90 - i * 15}%"></div>`
  ).join("");
}

export function skeletonCards(n = 4) {
  return `<div class="qb-grid qb-grid-4">${Array.from({ length: n }).map(() => `<div class="qb-skel qb-skel-card"></div>`).join("")}</div>`;
}
