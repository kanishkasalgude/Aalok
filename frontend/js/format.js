// The Aalok mark: the brand's actual icon file (aalok-icon.svg), inlined
// rather than loaded as an <img> so it stays a single request-free asset
// like every other icon in this app. Flat black-on-white by design - no
// gradient, no currentColor - so a plain constant is enough; kept as a
// function only so every call site (header, chat avatar) reads the same
// `brandMark()` shape as before.
export function brandMark() {
  return `<svg viewBox="0 0 256 256" fill="none" aria-hidden="true">
  <path fill="#000" d="M128 22c-10 0-18 5-23 14L43 170c-7 13 2 29 17 29h12c7 0 13-4 17-10l39-67 39 67c4 6 10 10 17 10h12c15 0 24-16 17-29L151 36c-5-9-13-14-23-14Z"/>
  <path fill="#fff" d="M128 55 89 122l17 29 22-38 22 38 17-29-39-67Z"/>
  <path fill="#000" d="M128 91c3 9 8 14 17 17-9 3-14 8-17 17-3-9-8-14-17-17 9-3 14-8 17-17Z"/>
  <path fill="#fff" d="M74 178h108l-15 26H89l-15-26Z"/>
</svg>`;
}

export function money(amount, currency = "INR") {
  if (amount === null || amount === undefined) return "—";
  const symbol = currency === "INR" ? "₹" : currency + " ";
  const n = Number(amount);
  return symbol + n.toLocaleString("en-IN", { maximumFractionDigits: n % 1 === 0 ? 0 : 2 });
}

export function titleCase(s) {
  if (!s) return "";
  return String(s).replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// One-color line icon per category - no emoji anywhere in the product.
// Each is a 24x24 viewBox, stroke-based, sized by its container via CSS
// (.qb-icon-circle svg / .aa-chip-icon svg) rather than fixed attributes,
// so the same markup works at both the product-card and chip scale.
const CATEGORY_ICON = {
  food: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7 2v7a2 2 0 0 0 4 0V2M9 9v13M7 2v3M9 2v3M11 2v3"/><path d="M16 2c-1.6 1.5-2.2 3.2-2.2 5s2.2 3 2.2 3v12"/></svg>`,
  grocery: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h16l-1.4 10.6a2 2 0 0 1-2 1.9H7.4a2 2 0 0 1-2-1.9L4 8Z"/><path d="M8 8V6a4 4 0 0 1 8 0v2"/></svg>`,
  fashion: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 4 4 7l2 3 2-1.5V20h8V8.5L18 10l2-3-4-3-2 2h-4L8 4Z"/></svg>`,
  beauty: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 2h6M11 2v3.5M13 2v3.5"/><path d="M8 5.5h8l1 3v10.5a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V8.5l1-3Z"/></svg>`,
  electronics: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.4"/><rect x="17" y="14" width="4" height="6" rx="1.4"/></svg>`,
  jewellery: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8h12L12 20 6 8Z"/><path d="M6 8 9 3h6l3 5M9 3l3 5 3-5M6 8l6 5 6-5"/></svg>`,
  entertainment: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M10 8.5 15.5 12 10 15.5V8.5Z" fill="currentColor" stroke="none"/></svg>`,
  services: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 3.5a4.5 4.5 0 0 0-5.9 5.9L3 15l3 3 5.6-5.6a4.5 4.5 0 0 0 5.9-5.9l-3.1 3.1-2-2 3.1-3.1Z"/></svg>`,
};
const CATEGORY_ICON_FALLBACK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8 12 3l9 5v8l-9 5-9-5V8Z"/><path d="m3 8 9 5 9-5M12 13v8"/></svg>`;

export function categoryIcon(cat) {
  return CATEGORY_ICON[cat] || CATEGORY_ICON_FALLBACK;
}

// Maps each category onto one of the design system's five atmospheric
// gradient stops (mint/peach/lavender/sky/rose) - the only "colour" the
// brand uses, reused here as soft icon-plate tints since there are more
// categories (8) than gradient tokens (5).
export const CATEGORY_TINT = {
  food: "peach", grocery: "mint", fashion: "lavender", beauty: "rose",
  electronics: "sky", jewellery: "peach", entertainment: "lavender", services: "sky",
};

export function categoryTint(cat) {
  return CATEGORY_TINT[cat] || "sky";
}
