/* ============================================================
   Aalok - one surface.

   The app has exactly two states, and they are the same conversation at
   two moments: the landing (an empty thread, dressed as a hero) and the
   conversation (that thread, once it has something in it). Everything else
   the shopper needs - the cart, the authorization receipt, the payment
   result - arrives in the drawer, in the context of the transaction it
   belongs to.

   There is no router, because there is nowhere else to go.
   ============================================================ */
import { api } from "./api.js";
import { state, setMerchants } from "./state.js";
import { mountCartDrawer, addToCart, openCartDrawer, closeCartDrawer, onCartCountChange } from "./components/cartDrawer.js";
import { mountDemoPanel, openDemoPanel, closeDemoPanel } from "./components/demoPanel.js";
import { micButtonHtml, wireVoiceButton, SEND_ICON } from "./components/composer.js";
import { mountConversation, sendMessage, isConversationEmpty, resetConversation } from "./conversation.js";
import { categoryIcon, escapeHtml, brandMark } from "./format.js";
import { cursorParallax, tapBounce } from "./motion.js";

/* A handful of openers, spanning enough categories to make the point that
   Aalok is not a food-delivery app. Deliberately phrased the way someone
   would actually say them out loud, since the microphone is right there. */
const SUGGESTIONS = [
  { key: "fashion", text: "Find me running shoes under ₹3000" },
  { key: "food", text: "Dinner for two under ₹500" },
  { key: "electronics", text: "Wireless headphones under ₹5000" },
  { key: "beauty", text: "Skincare for oily skin under ₹2000" },
  { key: "grocery", text: "Build a breakfast basket under ₹1000" },
];

const CART_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="20" r="1.4"/><circle cx="18" cy="20" r="1.4"/><path d="M2 3h3l2.4 12.1a2 2 0 0 0 2 1.6h8.3a2 2 0 0 0 2-1.6L21.5 7H6"/></svg>`;
const DEMO_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 20h8M9 9l3 2-3 2V9Z" fill="currentColor" stroke="none"/></svg>`;

let teardownParallax = null;
let teardownLandingVoice = null;

/* ---------------- shell ---------------- */

function renderShell() {
  document.getElementById("qb-app").innerHTML = `
    <div class="aa-app">
      <header class="aa-header" id="aa-header">
        <button class="aa-brand" id="aa-brand" type="button" title="Start a new conversation">
          <span class="aa-brand-mark" aria-hidden="true">${brandMark()}</span>
          <span class="aa-brand-name">Aalok</span>
        </button>
        <span class="aa-header-spacer"></span>
        <button class="aa-cart-btn" id="aa-demo-btn" type="button" aria-label="Open demo control panel" title="Demo Control Panel">
          ${DEMO_ICON}<span class="label">Demo</span>
        </button>
        <button class="aa-cart-btn" id="aa-cart-btn" type="button" aria-label="Open cart">
          ${CART_ICON}<span class="label">Cart</span>
          <span class="aa-cart-count" id="aa-cart-count" hidden>0</span>
        </button>
      </header>
      <main class="aa-main" id="aa-main"></main>
    </div>
  `;

  document.getElementById("aa-cart-btn").addEventListener("click", (e) => {
    tapBounce(e.currentTarget);
    closeDemoPanel();
    openCartDrawer();
  });

  document.getElementById("aa-demo-btn").addEventListener("click", (e) => {
    tapBounce(e.currentTarget);
    closeCartDrawer();
    openDemoPanel();
  });

  // The wordmark is the way back to a blank slate - the only "navigation"
  // in the product, and it goes to the one place there is.
  document.getElementById("aa-brand").addEventListener("click", () => {
    resetConversation();
    showLanding();
  });
}

/* ---------------- landing ---------------- */

/* The hero's decorative layers - soft, heavily blurred atmospheric blooms
   in the reference's five gradient stops, drifting toward the cursor.
   Each gets its own data-par strength and a .qb-par-N class, and the two
   are deliberately mismatched: the nearest blooms travel furthest AND
   settle fastest, which is what sells them as sitting at different depths.
   No data-par-rotate here - a blurred circle looks identical rotated, so
   there is nothing for that wiring to show on this shape. */
const HERO_ART = `
  <div class="aa-hero-art" aria-hidden="true">
    <div class="aa-hero-grid qb-par qb-par-2" data-par="5"></div>
    <div class="aa-hero-bloom s4 qb-par qb-par-5" data-par="10"></div>
    <div class="aa-hero-bloom s1 qb-par qb-par-1" data-par="16"></div>
    <div class="aa-hero-bloom s5 qb-par qb-par-6" data-par="9"></div>
    <div class="aa-hero-bloom s2 qb-par qb-par-3" data-par="13"></div>
    <div class="aa-hero-bloom s3 qb-par qb-par-4" data-par="11"></div>
  </div>`;

function showLanding() {
  teardown();
  const main = document.getElementById("aa-main");
  main.innerHTML = `
    <section class="aa-hero" id="aa-hero">
      ${HERO_ART}
      <div class="aa-hero-inner">
        <h1>AI proposes.<br/>Aalok authorizes.</h1>
        <div class="aa-hero-pipeline"><span>AI PROPOSES</span><span class="aa-hero-pipeline-arrow">&rarr;</span><span>AALOK AUTHORIZES</span><span class="aa-hero-pipeline-arrow">&rarr;</span><span>RAZORPAY EXECUTES</span></div>
        <form class="aa-ask" id="aa-ask">
          <input id="aa-ask-input" type="text" autocomplete="off" placeholder="Ask for anything, in plain language&hellip;" aria-label="Ask Aalok" />
          ${micButtonHtml("aa-ask-mic")}
          <button class="aa-send" type="submit" aria-label="Ask Aalok">${SEND_ICON}</button>
        </form>
        <div class="aa-listening-hint" id="aa-ask-hint" aria-live="polite"></div>
        <div class="aa-suggest">
          <span class="aa-suggest-label">Or start with one of these</span>
          ${SUGGESTIONS.map((s) => `
            <button class="aa-chip" type="button" data-prompt="${escapeHtml(s.text)}">
              <span class="aa-chip-icon" aria-hidden="true">${categoryIcon(s.key)}</span>${escapeHtml(s.text)}
            </button>`).join("")}
        </div>
      </div>
    </section>
  `;

  const input = document.getElementById("aa-ask-input");
  bindResponsivePlaceholder(input);

  document.getElementById("aa-ask").addEventListener("submit", (e) => {
    e.preventDefault();
    ask(input.value);
  });

  main.querySelectorAll(".aa-chip[data-prompt]").forEach((chip) => {
    chip.addEventListener("click", () => ask(chip.dataset.prompt));
  });

  teardownLandingVoice = wireVoiceButton({
    micBtn: document.getElementById("aa-ask-mic"),
    input,
    hintEl: document.getElementById("aa-ask-hint"),
    // A spoken opener goes straight through - same path, and the reply
    // gets read back because the turn arrived by voice.
    onSubmit: (text, opts) => ask(text, opts),
  });

  // Pointer parallax returns a no-op teardown on touch, coarse pointers,
  // narrow viewports and prefers-reduced-motion, so this is unconditional.
  teardownParallax = cursorParallax(document.getElementById("aa-hero"));

  input.focus({ preventScroll: true });
}

/* The ask field shares its width with a microphone and a send button, so on
   a phone the full placeholder truncates mid-word ("Ask for anything, in
   pla"). Shorten it there.

   This LISTENS rather than reading the media query once, for two reasons:
   a rotation or a resized window should correct itself, and - the case that
   actually bit during development - a tab painting while its pane is hidden
   reports innerWidth 0, which matches every max-width query and would
   otherwise lock the phone wording in permanently on a desktop. */
function bindResponsivePlaceholder(input) {
  const narrow = window.matchMedia("(max-width: 560px)");
  const apply = () => {
    input.placeholder = narrow.matches ? "Ask for anything…" : "Ask for anything, in plain language…";
  };
  apply();
  narrow.addEventListener("change", apply);
}

/** The landing's one job: hand the question to the conversation. */
function ask(text, opts = {}) {
  if (!text || !text.trim()) return;
  showConversation();
  sendMessage(text, opts);
}

/* ---------------- conversation ---------------- */

function showConversation() {
  teardown();
  mountConversation(document.getElementById("aa-main"));
}

function teardown() {
  if (teardownParallax) { teardownParallax(); teardownParallax = null; }
  if (teardownLandingVoice) { teardownLandingVoice(); teardownLandingVoice = null; }
}

/* ---------------- header state ---------------- */

async function loadPaymentMode() {
  let mode = {};
  try {
    const res = await api.paymentMode();
    mode = res.data || {};
  } catch { /* leave it unknown */ }
  state.paymentMode = mode;
}

function updateCartCount(count) {
  const el = document.getElementById("aa-cart-count");
  if (!el) return;
  el.hidden = count === 0;
  if (count === 0) return;
  el.textContent = count;
  el.classList.remove("bumped");
  // Force a reflow so the animation restarts on every increment, not just
  // the first - without this the class is re-added within the same frame
  // and the browser never sees it change.
  void el.offsetWidth;
  el.classList.add("bumped");
}

/* Add-to-cart buttons are rendered inside agent replies, which are rebuilt
   on every turn - so the handler is delegated from the body once rather
   than rebound per card. */
function wireGlobalActions() {
  document.body.addEventListener("click", (e) => {
    const btn = e.target.closest('[data-action="add-to-cart"]');
    if (btn && !btn.disabled) {
      tapBounce(btn);
      addToCart(btn.dataset.productId, btn.dataset.merchantId);
    }
  });

  const header = document.getElementById("aa-header");
  document.addEventListener("scroll", () => {
    header.classList.toggle("scrolled", window.scrollY > 4);
  }, { passive: true });
}

/* ---------------- boot ---------------- */

async function boot() {
  renderShell();
  wireGlobalActions();
  mountCartDrawer();
  mountDemoPanel();
  onCartCountChange(updateCartCount);
  loadPaymentMode();

  // Establishes (or refreshes) this browser's signed session identity
  // (Track 01 Phase 2) - fire-and-forget like the other boot calls below:
  // even the very first chat/cart call before this resolves still works,
  // since the server mints a session on any request with no token and
  // api.js persists whatever it hands back.
  api.createSession();

  // The merchant registry backs the authorization card's merchant/category
  // rows, so it has to be in hand before the first checkout - but it must
  // never block first paint.
  api.merchants().then((res) => { if (res.ok) setMerchants(res.data.merchants || []); });

  if (isConversationEmpty()) showLanding();
  else showConversation();
}

boot();
