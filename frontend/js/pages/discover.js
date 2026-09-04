import { api } from "../api.js";
import { state } from "../state.js";
import { productCard } from "../components/productCard.js";
import { emptyState } from "../components/emptyState.js";
import { titleCase } from "../format.js";

const CATEGORIES = ["food", "grocery", "fashion", "beauty", "electronics", "jewellery", "entertainment", "services"];

let filters = { query: "", category: "", merchant_ids: "", max_price: "", availability_only: true, sort: "relevance" };

async function runSearch() {
  const resultsEl = document.getElementById("discover-results");
  resultsEl.innerHTML = `<div class="qb-grid qb-grid-4">${Array.from({ length: 8 }).map(() => `<div class="qb-skel qb-skel-card"></div>`).join("")}</div>`;

  const params = { query: filters.query, category: filters.category || undefined, max_price: filters.max_price || undefined, merchant_ids: filters.merchant_ids || undefined };
  const res = await api.searchCatalog(params);
  if (!res.ok) { resultsEl.innerHTML = `<div class="qb-note danger">Search failed.</div>`; return; }
  let products = res.data.results || [];
  if (filters.availability_only) products = products.filter((p) => p.availability);
  if (filters.sort === "price_asc") products = [...products].sort((a, b) => a.price - b.price);
  if (filters.sort === "price_desc") products = [...products].sort((a, b) => b.price - a.price);

  document.getElementById("discover-count").textContent = `${products.length} product${products.length === 1 ? "" : "s"}`;

  if (products.length === 0) {
    resultsEl.innerHTML = emptyState({ icon: "🔍", title: "No products match these filters", sub: "Try widening the price range or clearing a filter." });
    return;
  }
  resultsEl.innerHTML = `<div class="qb-grid qb-grid-4">${products.map((p) => productCard(p)).join("")}</div>`;
}

export const discoverPage = {
  async render(root) {
    const merchantOptions = state.merchants.map((m) => `<option value="${m.merchant_id}">${m.name}</option>`).join("");
    root.innerHTML = `
      <div class="qb-content-header">
        <div>
          <div class="qb-content-title">Discover</div>
          <div class="qb-content-subtitle">Federated search across every connected merchant and category - the same AI Commerce Discovery Gateway the agent uses.</div>
        </div>
      </div>
      <div class="qb-filter-bar">
        <input class="qb-input" id="d-query" placeholder="Search products…" style="min-width:220px;" />
        <select class="qb-select" id="d-category">
          <option value="">All categories</option>
          ${CATEGORIES.map((c) => `<option value="${c}">${titleCase(c)}</option>`).join("")}
        </select>
        <select class="qb-select" id="d-merchant">
          <option value="">All merchants</option>
          ${merchantOptions}
        </select>
        <input class="qb-input" id="d-maxprice" type="number" placeholder="Max price" style="width:120px;" />
        <select class="qb-select" id="d-sort">
          <option value="relevance">Sort: Relevance</option>
          <option value="price_asc">Price: Low to high</option>
          <option value="price_desc">Price: High to low</option>
        </select>
        <label style="display:flex; align-items:center; gap:6px; font-size:13px; color:var(--qb-text-secondary);">
          <input type="checkbox" id="d-avail" checked /> In stock only
        </label>
        <span class="qb-topbar-spacer"></span>
        <span id="discover-count" class="qb-subtle" style="font-size:13px;"></span>
      </div>
      <div id="discover-results"></div>
    `;

    const q = document.getElementById("d-query");
    const cat = document.getElementById("d-category");
    const merchant = document.getElementById("d-merchant");
    const maxPrice = document.getElementById("d-maxprice");
    const sort = document.getElementById("d-sort");
    const avail = document.getElementById("d-avail");

    let debounce;
    const trigger = () => {
      filters = { query: q.value, category: cat.value, merchant_ids: merchant.value, max_price: maxPrice.value, sort: sort.value, availability_only: avail.checked };
      runSearch();
    };
    q.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(trigger, 300); });
    [cat, merchant, maxPrice, sort, avail].forEach((el) => el.addEventListener("change", trigger));

    // support a pre-filled query from the topbar global search
    const preset = window.__qbDiscoverQuery;
    if (preset) { q.value = preset; window.__qbDiscoverQuery = null; }

    await runSearch();
  },
};
