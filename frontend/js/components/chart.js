// Thin Chart.js wrapper (Chart.js loaded via CDN in index.html). Restrained
// palette matching the design tokens; no 3D/gradient chart styling.
const PALETTE = {
  accent: "#0D9488",
  accentSoft: "rgba(13,148,136,0.12)",
  success: "#16A34A",
  danger: "#DC2626",
  warning: "#D97706",
  info: "#2563EB",
  grid: "#E2E8F0",
  text: "#64748B",
};

const registry = new Map();

export function mountChart(canvasEl, config) {
  if (!window.Chart) return null;
  const existing = registry.get(canvasEl);
  if (existing) existing.destroy();
  const chart = new window.Chart(canvasEl.getContext("2d"), config);
  registry.set(canvasEl, chart);
  return chart;
}

export function lineBarConfig(labels, datasets) {
  return {
    type: "bar",
    data: { labels, datasets: datasets.map((d) => ({
      label: d.label, data: d.data, backgroundColor: d.color || PALETTE.accentSoft,
      borderColor: d.color || PALETTE.accent, borderWidth: d.type === "line" ? 2 : 0,
      type: d.type || "bar", borderRadius: 3, maxBarThickness: 22,
      tension: 0.35, pointRadius: 0, fill: d.type === "line" ? false : undefined,
    })) },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: datasets.length > 1, position: "top", align: "end", labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, font: { size: 11 }, color: PALETTE.text } } },
      scales: {
        x: { grid: { display: false }, ticks: { color: PALETTE.text, font: { size: 11 } } },
        y: { grid: { color: PALETTE.grid }, ticks: { color: PALETTE.text, font: { size: 11 } }, beginAtZero: true },
      },
    },
  };
}

export function doughnutConfig(labels, data) {
  const colors = [PALETTE.accent, PALETTE.info, PALETTE.warning, PALETTE.success, PALETTE.danger, "#7C3AED", "#DB2777", "#0891B2"];
  return {
    type: "doughnut",
    data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "68%",
      plugins: { legend: { position: "right", labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, font: { size: 11 }, color: PALETTE.text } } },
    },
  };
}

export { PALETTE };
