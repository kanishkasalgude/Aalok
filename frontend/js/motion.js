// Single point of truth for the Motion library (motion.dev - the standalone
// successor to Framer Motion's animation engine), loaded as a real ES
// module straight from a CDN (same "no build step" approach already used
// for Chart.js). Every file that wants JS-driven animation imports from
// here instead of the CDN URL directly, so the version only needs
// updating in one place.
export { animate, stagger, spring } from "https://cdn.jsdelivr.net/npm/motion@11/+esm";

import { animate as _animate, stagger as _stagger } from "https://cdn.jsdelivr.net/npm/motion@11/+esm";

const EASE = [0.22, 0.61, 0.36, 1];

// SAFETY PRINCIPLE, verified the hard way against this project's own dev
// tooling: a staggered/delayed animate() call can get stuck indefinitely
// (observed directly: items left permanently at opacity:0, and separately,
// animating `transform` on a flex/height:calc layout container collapsed
// its width to 0) when a tab is backgrounded/throttled or otherwise stalls
// - the same class of failure a slow device, a blocked CDN request, or
// background-tab throttling could trigger for a real visitor. So content
// visibility must NEVER depend on a JS animation completing. Entrance
// motion here therefore only ever animates `transform` (a slide into
// place) and never `opacity` - CSS's own default (opacity: 1, fully
// visible) governs at all times; Motion, when it works, is purely a
// cosmetic slide layered on top, never a gate.
function clearInlineTransform(target) {
  const list = target instanceof NodeList || Array.isArray(target) ? target : [target];
  list.forEach((el) => { el.style.transform = ""; });
}

function withCleanup(controls, target, timeoutMs) {
  let settled = false;
  const finish = () => {
    if (settled) return;
    settled = true;
    try { controls && controls.stop && controls.stop(); } catch { /* already stopped */ }
    clearInlineTransform(target);
  };
  try {
    const finished = controls && controls.finished;
    if (finished && typeof finished.then === "function") finished.then(finish).catch(finish);
  } catch { /* some builds throw accessing .finished before the animation starts */ }
  setTimeout(finish, timeoutMs);
  return controls;
}

/** Slides a single element up into place - content stays visible throughout;
 * only `transform` is animated, never `opacity`. */
export function fadeInUp(el, opts = {}) {
  const controls = _animate(el, { transform: ["translateY(10px)", "translateY(0px)"] },
    { duration: 0.32, easing: EASE, ...opts });
  return withCleanup(controls, el, 1200);
}

/** Cascading slide-in for a NodeList/array of elements - a real stagger,
 * not a hand-rolled nth-child animation-delay table. Same visibility
 * guarantee as fadeInUp: only `transform` moves, content is never hidden. */
export function staggerIn(els, opts = {}) {
  const list = els instanceof NodeList || Array.isArray(els) ? els : [els];
  if (!list.length) return;
  const controls = _animate(list, { transform: ["translateY(10px)", "translateY(0px)"] },
    { duration: 0.32, delay: _stagger(0.045), easing: EASE, ...opts });
  return withCleanup(controls, list, 1200 + list.length * 80);
}

/** A quick, satisfying tap-confirm bounce for buttons (add-to-cart, send).
 * User-gesture-triggered and never below scale(0.92), so even a stuck
 * animation leaves the button fully visible and usable. */
export function tapBounce(el) {
  const controls = _animate(el, { transform: ["scale(1)", "scale(0.92)", "scale(1)"] }, { duration: 0.28, easing: EASE });
  return withCleanup(controls, el, 800);
}
