import { money, categoryEmoji, categoryTint, escapeHtml } from "../format.js";

// Renders only attribute keys that actually exist on this product - never
// invents a category-specific field the backend didn't provide.
const ATTR_KEYS_BY_CATEGORY = {
  food: ["dietary_tags", "protein_g", "carbs_g"],
  grocery: ["pack_size"],
  fashion: ["size", "color", "material"],
  beauty: ["skin_type", "volume_ml"],
  electronics: ["tech_specs", "warranty_months"],
  jewellery: ["metal", "purity", "gemstone", "weight_g"],
  entertainment: ["screen_type", "language", "showtime"],
  services: ["validity_days", "data_gb"],
};

function attrChips(product) {
  const keys = ATTR_KEYS_BY_CATEGORY[product.category] || Object.keys(product.attributes || {});
  // Bare numeric attribute values ("3", "20") aren't self-explanatory in a
  // small chip - append the real unit for the keys that have one. Purely
  // presentational; never changes what data is shown.
  const UNIT_SUFFIX = {
    warranty_months: " mo warranty", protein_g: "g protein", carbs_g: "g carbs",
    volume_ml: "ml", weight_g: "g", validity_days: " day validity", data_gb: "GB data",
  };

  const chips = [];
  for (const key of keys) {
    const val = product.attributes ? product.attributes[key] : undefined;
    if (val === undefined || val === null || val === "" || val === "n/a") continue;
    let text;
    if (Array.isArray(val)) text = val.join(", ");
    else if (typeof val === "object") text = Object.entries(val).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(", ");
    else if (typeof val === "number" && UNIT_SUFFIX[key]) text = UNIT_SUFFIX[key].startsWith(" ") ? `${val}${UNIT_SUFFIX[key]}` : `${val}${UNIT_SUFFIX[key]}`;
    else text = String(val);
    if (!text) continue;
    chips.push(`<span class="qb-badge">${escapeHtml(text)}</span>`);
  }
  return chips.join("");
}

export function productCard(product, { showMerchant = true, actionLabel = "Add to cart" } = {}) {
  const discount = product.discount ? `<span class="qb-pill success" style="margin-left:6px">${product.discount}% off</span>` : "";
  const mrp = product.mrp && product.mrp > product.price ? `<span class="qb-product-mrp">${money(product.mrp, product.currency)}</span>` : "";
  const deliveryMin = product.delivery && product.delivery.eta_min;
  const deliveryLabel = deliveryMin === 0 ? "Instant" : deliveryMin ? (deliveryMin >= 1440 ? `${Math.round(deliveryMin / 1440)}d delivery` : `${deliveryMin}m delivery`) : null;
  const availPill = product.availability
    ? `<span class="qb-pill success"><span class="qb-pill-dot"></span>In stock</span>`
    : `<span class="qb-pill danger"><span class="qb-pill-dot"></span>Unavailable</span>`;

  return `
    <div class="qb-product" data-product-id="${escapeHtml(product.product_id)}" data-merchant-id="${escapeHtml(product.merchant_id)}">
      <div class="qb-product-top">
        <div style="display:flex; gap:10px; min-width:0;">
          <div class="qb-icon-circle ${categoryTint(product.category)}">${categoryEmoji(product.category)}</div>
          <div style="min-width:0;">
            <div class="qb-product-title qb-title-accent qb-truncate" title="${escapeHtml(product.title)}">${escapeHtml(product.title)}</div>
            ${showMerchant ? `<div class="qb-product-merchant qb-truncate">${escapeHtml(product.merchant_name)} · ${escapeHtml(product.category)}</div>` : ""}
          </div>
        </div>
      </div>
      <div>
        <span class="qb-product-price">${money(product.price, product.currency)}</span>${mrp}${discount}
      </div>
      <div class="qb-product-attrs">${attrChips(product)}</div>
      <div class="qb-product-meta">
        ${availPill}
        ${deliveryLabel ? `<span>🚚 ${deliveryLabel}</span>` : ""}
      </div>
      <div class="qb-product-actions">
        <button class="qb-btn qb-btn-primary qb-btn-block qb-btn-sm" data-action="add-to-cart"
          data-product-id="${escapeHtml(product.product_id)}" data-merchant-id="${escapeHtml(product.merchant_id)}"
          ${product.availability ? "" : "disabled"}>${actionLabel}</button>
      </div>
    </div>
  `;
}
