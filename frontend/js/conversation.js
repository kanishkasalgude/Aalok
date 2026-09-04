/* ============================================================
   The conversation. This IS the product.

   Discovery, comparison, recommendation and the policy explanation all
   happen inside this thread - there is no Discover page, no Merchants
   page, no Orders page. Every turn is one POST /api/agent/chat, which runs
   the full pipeline underneath: intent parsing, the AI tool layer, the
   federated catalog gateway across all 16 merchant adapters, ranking, and
   the grounded recommendation. The UI's job is only to show what came
   back.
   ============================================================ */
import { api } from "./api.js";
import { state } from "./state.js";
import { productCard } from "./components/productCard.js";
import { authorizationCard } from "./components/authorizationCard.js";
import { micButtonHtml, wireVoiceButton, SEND_ICON } from "./components/composer.js";
import { escapeHtml, brandMark } from "./format.js";
import { speak, stopSpeaking } from "./voice.js";
import { fadeInUp, staggerIn, tapBounce } from "./motion.js";

/** Turns, oldest first. The whole thread re-renders from this array. */
let thread = [];
let busy = false;
let teardownVoice = null;

export function isConversationEmpty() {
  return thread.length === 0;
}

export function resetConversation() {
  stopSpeaking();
  thread = [];
}

/* ---------------- rendering ---------------- */

function turnHtml(msg) {
  if (msg.role === "user") {
    return `<div class="qb-msg user"><div class="qb-msg-bubble">${escapeHtml(msg.text)}</div></div>`;
  }
  const body = msg.html ? msg.text : escapeHtml(msg.text);
  const products = (msg.candidates || []).length
    ? `<div class="qb-product-grid">${msg.candidates.slice(0, 6).map((p) => productCard(p)).join("")}</div>`
    : "";
  const attachment = msg.attachment ? `<div class="qb-msg-attachment">${msg.attachment}</div>` : "";
  return `
    <div class="qb-msg ai">
      <div class="qb-msg-avatar" aria-hidden="true">${brandMark()}</div>
      <div class="qb-msg-bubble">${body}</div>
    </div>
    ${attachment}
    ${products}
  `;
}

function renderThread({ animateLastTurn = true } = {}) {
  const threadEl = document.getElementById("aa-thread");
  if (!threadEl) return;

  threadEl.innerHTML = thread.map(turnHtml).join("");
  threadEl.scrollTop = threadEl.scrollHeight;

  if (!animateLastTurn) return;
  // The thread is rebuilt wholesale on every turn (the simplest correct
  // approach for an array-driven render), so only animate what just
  // arrived - the trailing 1-3 nodes - never the whole history again.
  [...threadEl.children].slice(-3).forEach((el) => {
    if (el.classList.contains("qb-product-grid")) staggerIn(el.querySelectorAll(".qb-product"));
    else fadeInUp(el, { duration: 0.24 });
  });
}

/** Adds a turn and repaints. Exported so the checkout flow can record its
 *  outcome in the conversation - the thread is the product's record of
 *  what happened, even after the cart drawer is closed. */
export function pushTurn(msg) {
  thread.push(msg);
  renderThread();
}

function setBusy(next) {
  busy = next;
  const input = document.getElementById("aa-input");
  const send = document.getElementById("aa-send");
  const mic = document.getElementById("aa-mic");
  if (input) input.disabled = next;
  if (send) send.disabled = next;
  if (mic) mic.disabled = next;
  if (!next && input) input.focus({ preventScroll: true });
}

/* ---------------- sending ---------------- */

const THINKING = `<span class="aa-thinking" aria-hidden="true"><span></span><span></span><span></span></span> <span class="qb-muted">Searching across connected merchants&hellip;</span>`;

/**
 * One turn. `viaVoice` only changes whether the reply is READ BACK - the
 * request itself is byte-identical to a typed one.
 */
export async function sendMessage(text, { viaVoice = false } = {}) {
  const message = (text || "").trim();
  if (!message || busy) return;

  stopSpeaking();
  thread.push({ role: "user", text: message });
  thread.push({ role: "ai", text: THINKING, html: true, pending: true });
  renderThread();

  const input = document.getElementById("aa-input");
  if (input) input.value = "";
  setBusy(true);

  let res;
  try {
    res = await api.agentChat({ session_id: state.sessionId, message });
  } catch {
    res = { ok: false };
  }

  thread.pop(); // drop the thinking turn
  if (!res.ok || !res.data) {
    thread.push({ role: "ai", text: "I couldn't reach the commerce agent just then. Try that again in a moment." });
  } else {
    const d = res.data;
    thread.push({ role: "ai", text: d.reply, candidates: d.candidates || [] });
    // Voice in, voice out. The reply text names the match count, the top
    // pick, its merchant and its price - reading the grid aloud would be
    // unusable, and the cards are already on screen.
    if (viaVoice) speak(d.reply);
  }

  setBusy(false);
  renderThread();
}

/* ---------------- the policy-rejection demo ---------------- */

/* Aalok's deterministic gate is its strongest claim, and a shopper will
   almost never trip it by accident - so there is one honest way to see it
   fire, kept as a small footnote link rather than an "Audit" destination.
   It runs the REAL POST /api/demo/policy-rejection: a genuinely over-budget
   cart through the same OrderService.checkout() every other purchase uses.
   The REJECT is a real gate, not a canned response. */
export async function runPolicyRejectionDemo() {
  if (busy) return;
  thread.push({ role: "user", text: "Show me what happens when a cart breaks my spending mandate." });
  thread.push({ role: "ai", text: THINKING, html: true, pending: true });
  renderThread();
  setBusy(true);

  let res;
  try { res = await api.policyRejectionDemo(); } catch { res = { ok: false }; }

  thread.pop();
  const d = (res && res.data) || {};
  if (!d.decision && !d.cart_mandate) {
    thread.push({ role: "ai", text: "The policy demo endpoint didn't respond. Is the backend still running?" });
  } else {
    thread.push({
      role: "ai",
      text: "Here's a cart proposed at &#8377;218 against a &#8377;180 ceiling. The Commerce Policy Engine rejected it "
          + "<strong>before</strong> any Razorpay call was made — this gate is deterministic Python, never an LLM decision.",
      html: true,
      attachment: authorizationCard({ authorizationDecision: null, decision: d.decision, cartMandate: d.cart_mandate }),
    });
  }
  setBusy(false);
  renderThread();
}

/* ---------------- mounting ---------------- */

export function mountConversation(root) {
  root.innerHTML = `
    <div class="aa-conv">
      <div class="aa-thread qb-scroll" id="aa-thread" role="log" aria-live="polite" aria-label="Conversation with Aalok"></div>
      <div class="aa-composer-wrap">
        <form class="aa-composer" id="aa-composer">
          <input id="aa-input" type="text" autocomplete="off" placeholder="Message Aalok&hellip;" aria-label="Message Aalok" />
          ${micButtonHtml("aa-mic")}
          <button class="aa-send" id="aa-send" type="submit" aria-label="Send">${SEND_ICON}</button>
        </form>
        <div class="aa-listening-hint" id="aa-listening-hint" aria-live="polite"></div>
        <div class="aa-footnote">
          Grounded in real catalog data and gated by a deterministic policy engine before anything is charged ·
          <button type="button" class="aa-linkbtn" id="aa-policy-demo">see the policy engine reject a cart</button>
        </div>
      </div>
    </div>
  `;

  renderThread({ animateLastTurn: false });

  const input = document.getElementById("aa-input");
  const micBtn = document.getElementById("aa-mic");

  document.getElementById("aa-composer").addEventListener("submit", (e) => {
    e.preventDefault();
    tapBounce(document.getElementById("aa-send"));
    sendMessage(input.value);
  });

  document.getElementById("aa-policy-demo").addEventListener("click", runPolicyRejectionDemo);

  if (teardownVoice) teardownVoice();
  teardownVoice = wireVoiceButton({
    micBtn,
    input,
    hintEl: document.getElementById("aa-listening-hint"),
    onSubmit: sendMessage,
  });

  input.focus({ preventScroll: true });
}
