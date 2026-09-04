import { api } from "../api.js";
import { state } from "../state.js";
import { productCard } from "../components/productCard.js";
import { authorizationCard } from "../components/authorizationCard.js";
import { escapeHtml, categoryEmoji } from "../format.js";
import { fadeInUp, staggerIn, tapBounce } from "../motion.js";

// A dedicated AI commerce workspace, deliberately separate from the
// Merchants page (a plain data table further down the sidebar) - this is
// Aalok's own conversational surface, laid out like the chat product
// most people already use daily (centered scrolling thread, plain
// full-width assistant turns, a pill composer pinned to the bottom), so it
// reads immediately as a real integrated AI agent rather than a form
// bolted onto a dashboard.
const EXAMPLES = [
  { category: "Food", key: "food", text: "Find dinner under ₹500" },
  { category: "Grocery", key: "grocery", text: "Build a breakfast basket under ₹1000" },
  { category: "Fashion", key: "fashion", text: "Find running shoes under ₹5000" },
  { category: "Beauty", key: "beauty", text: "Skincare for oily skin under ₹2000" },
  { category: "Electronics", key: "electronics", text: "Wireless headphones under ₹5000" },
  { category: "Jewellery", key: "jewellery", text: "Show me a gold jewellery option under ₹10000" },
  { category: "Entertainment", key: "entertainment", text: "Find something to watch tonight" },
  { category: "Services", key: "services", text: "I need a home cleaning service" },
];

const SEND_ICON = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5"/><path d="M6 11l6-6 6 6"/></svg>`;
const ARROW_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M13 6l6 6-6 6"/></svg>`;

let thread = [];

function starterGridHtml() {
  return `
    <div class="qb-chat-empty">
      <div class="qb-hero-band">
        <div class="qb-chat-empty-mark">QB</div>
        <div class="qb-chat-empty-title">What are you shopping for?</div>
        <div class="qb-chat-empty-sub">Ask in plain language, across any category. I search every connected merchant, explain why my top pick fits, and never charge anything without your confirmation.</div>
      </div>
      <div class="qb-starter-grid">
        ${EXAMPLES.map((ex) => `
          <div class="qb-starter-card" data-example="${escapeHtml(ex.text)}" role="button" tabindex="0">
            <div class="qb-starter-preview">
              <div class="qb-starter-mock">
                <span class="qb-starter-mock-emoji">${categoryEmoji(ex.key)}</span>
                <span class="qb-starter-mock-text">"${escapeHtml(ex.text)}"</span>
              </div>
            </div>
            <div class="qb-starter-body">
              <span class="cat">${ex.category}</span>
              <span class="txt qb-title-accent">${escapeHtml(ex.text)}</span>
              <span class="qb-starter-action">${ARROW_ICON} Try this prompt</span>
            </div>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function renderThread() {
  const threadEl = document.getElementById("agent-thread");
  if (!threadEl) return;

  if (thread.length === 0) {
    threadEl.innerHTML = starterGridHtml();
    wireStarterCards();
    staggerIn(threadEl.querySelectorAll(".qb-starter-card"));
    return;
  }

  threadEl.innerHTML = thread.map((msg) => {
    if (msg.role === "user") {
      return `
        <div class="qb-msg user">
          <div class="qb-msg-bubble">${escapeHtml(msg.text)}</div>
        </div>
      `;
    }
    const productsHtml = (msg.candidates || []).slice(0, 6).map((p) => productCard(p)).join("");
    return `
      <div class="qb-msg ai">
        <div class="qb-msg-avatar">QB</div>
        <div class="qb-msg-bubble">${msg.html ? msg.text : escapeHtml(msg.text)}</div>
      </div>
      ${msg.candidates && msg.candidates.length ? `<div class="qb-product-grid">${productsHtml}</div>` : ""}
    `;
  }).join("");
  threadEl.scrollTop = threadEl.scrollHeight;

  // The whole thread is rebuilt from `thread` on every turn (simplest
  // correct approach for this array-driven render), so only animate the
  // turn that just arrived - the last 1-2 DOM children (the AI/user bubble,
  // plus its product grid if one followed) - not the entire history again.
  const children = [...threadEl.children];
  const justArrived = children.slice(-2);
  justArrived.forEach((el) => {
    if (el.classList.contains("qb-product-grid")) staggerIn(el.querySelectorAll(".qb-product"));
    else fadeInUp(el, { duration: 0.24 });
  });
}

function wireStarterCards() {
  document.querySelectorAll(".qb-starter-card[data-example]").forEach((card) => {
    card.addEventListener("click", () => sendMessage(card.dataset.example));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sendMessage(card.dataset.example); }
    });
  });
}

async function sendMessage(text) {
  if (!text.trim()) return;
  thread.push({ role: "user", text });
  renderThread();

  const input = document.getElementById("agent-input");
  const sendBtn = document.getElementById("agent-send");
  input.value = "";
  input.disabled = true; sendBtn.disabled = true;
  thread.push({ role: "ai", text: `<span class="qb-spinner"></span> Searching across connected merchants…`, html: true, candidates: [] });
  renderThread();

  const res = await api.agentChat({ session_id: state.sessionId, message: text });
  thread.pop();
  if (!res.ok) {
    thread.push({ role: "ai", text: "Something went wrong reaching the AI commerce agent.", candidates: [] });
  } else {
    const d = res.data;
    thread.push({ role: "ai", text: d.reply, candidates: d.candidates || [] });
  }
  input.disabled = false; sendBtn.disabled = false;
  renderThread();
  input.focus({ preventScroll: true });
}

async function runRejectionDemo() {
  thread.push({ role: "user", text: "Run the policy rejection demo (Masala Dosa + Filter Coffee, ₹218 against a ₹180 ceiling)" });
  thread.push({ role: "ai", text: `<span class="qb-spinner"></span> Proposing a deliberately over-budget cart…`, html: true, candidates: [] });
  renderThread();
  const res = await api.policyRejectionDemo();
  thread.pop();
  const d = res.data || {};
  thread.push({
    role: "ai",
    text: `This cart was rejected before any Razorpay call was made — the Commerce Policy Engine is deterministic, never an LLM decision:<div style="margin-top:10px;">${authorizationCard({ authorizationDecision: null, decision: d.decision, cartMandate: d.cart_mandate })}</div>`,
    html: true, candidates: [],
  });
  renderThread();
}

export const agentPage = {
  async render(root) {
    root.innerHTML = `
      <div class="qb-content-header">
        <div>
          <div class="qb-content-title">AI Commerce Agent</div>
          <div class="qb-content-subtitle">Find, compare and purchase across merchants using natural language.</div>
        </div>
      </div>
      <div class="qb-agent-shell">
        <div class="qb-chat-thread qb-scroll" id="agent-thread"></div>
        <div class="qb-chat-composer-wrap">
          <div class="qb-chat-composer">
            <input id="agent-input" type="text" placeholder="Message Aalok AI…" autocomplete="off" />
            <button class="qb-chat-send-btn" id="agent-send" aria-label="Send">${SEND_ICON}</button>
          </div>
          <div class="qb-chat-footnote">
            Grounded in real catalog data, checked by a deterministic policy engine before anything is charged ·
            <a href="#" id="agent-rejection-demo">run the policy-rejection demo</a>
          </div>
        </div>
      </div>
    `;

    renderThread();

    document.getElementById("agent-send").addEventListener("click", (e) => { tapBounce(e.currentTarget); sendMessage(document.getElementById("agent-input").value); });
    document.getElementById("agent-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(e.target.value); });
    document.getElementById("agent-rejection-demo").addEventListener("click", (e) => { e.preventDefault(); runRejectionDemo(); });
    // preventScroll: focusing the composer must not scroll the outer page -
    // the composer is already pinned in view; scrolling would shove page
    // content under the sticky topbar.
    document.getElementById("agent-input").focus({ preventScroll: true });
  },
};
