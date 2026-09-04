export function money(amount, currency = "INR") {
  if (amount === null || amount === undefined) return "—";
  const symbol = currency === "INR" ? "₹" : currency + " ";
  const n = Number(amount);
  return symbol + n.toLocaleString("en-IN", { maximumFractionDigits: n % 1 === 0 ? 0 : 2 });
}

export function paise(amountPaise, currency = "INR") {
  return money((amountPaise || 0) / 100, currency);
}

export function pct(n, digits = 1) {
  if (n === null || n === undefined) return "—";
  return `${Number(n).toFixed(digits)}%`;
}

export function dateTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

export function timeAgo(iso) {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function titleCase(s) {
  if (!s) return "";
  return String(s).replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export const CATEGORY_EMOJI = {
  food: "🍽️", grocery: "🛒", fashion: "👕", beauty: "💄",
  electronics: "🎧", jewellery: "💎", entertainment: "🎬", services: "🔧",
};

export function categoryEmoji(cat) {
  return CATEGORY_EMOJI[cat] || "📦";
}

export const CATEGORY_TINT = {
  food: "amber", grocery: "green", fashion: "violet", beauty: "rose",
  electronics: "blue", jewellery: "amber", entertainment: "violet", services: "teal",
};

export function categoryTint(cat) {
  return CATEGORY_TINT[cat] || "teal";
}
