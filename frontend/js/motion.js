// Single point of truth for the Motion library (motion.dev - the standalone
// successor to Framer Motion's animation engine), loaded as a real ES
// module straight from a CDN - the project has no build step, so this is
// the only remaining third-party frontend dependency (Chart.js went with
// the analytics dashboard). Every file that wants JS-driven animation
// imports from here rather than the CDN URL directly, so the version only
// needs updating in one place.
export { animate, stagger, spring } from "https://cdn.jsdelivr.net/npm/motion@11/+esm";

import { animate as _animate, stagger as _stagger } from "https://cdn.jsdelivr.net/npm/motion@11/+esm";

// The single easing curve the whole UI shares, matching --qb-ease in
// tokens.css. Reverse-engineered from the reference site, which declares
// exactly one curve and uses it for every transition on the page. Note the
// second control point is 1, not 0.61: that is what gives the curve its
// fast departure and long, quiet settle.
const EASE = [0.22, 1, 0.36, 1];

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

/* ------------------------------------------------------------------
 * Cursor parallax
 *
 * Decorative art drifts toward the pointer. Two details, both taken from
 * the reference, are what separate this from a generic mouse-follow:
 *
 *   1. Each layer settles over a DIFFERENT duration (340-610ms, set by the
 *      .qb-par-N classes in effects.css). Because the layers never arrive
 *      together, the group reads as several objects with their own mass
 *      rather than one rigid sheet being dragged around.
 *
 *   2. The pointer offset is normalised against the container, not the
 *      window, so the effect stays proportional at any viewport size.
 *
 * This writes CSS custom properties only - the transition itself is CSS.
 * That keeps it cheap (no per-frame JS animation) and means the whole
 * effect degrades to "nothing happens" if this module never loads, which
 * is the same visibility guarantee the entrance helpers above make.
 * ------------------------------------------------------------------ */
export function cursorParallax(container, opts = {}) {
  if (!container) return () => {};

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const coarse = window.matchMedia("(hover: none), (pointer: coarse)").matches;
  if (reduced || coarse || window.innerWidth <= 1024) return () => {};

  const layers = [...container.querySelectorAll("[data-par]")].map((el) => ({
    el,
    // Strength in px of travel at the extreme edge of the container.
    strength: parseFloat(el.dataset.par) || 8,
    // Rotation in degrees at the extreme edge; subtle by default.
    rotate: parseFloat(el.dataset.parRotate ?? "0"),
  }));
  if (!layers.length) return () => {};

  let frame = 0;
  let pending = null;

  const apply = () => {
    frame = 0;
    if (!pending) return;
    const { nx, ny } = pending;
    for (const { el, strength, rotate } of layers) {
      el.style.setProperty("--qb-par-x", `${(nx * strength).toFixed(2)}px`);
      el.style.setProperty("--qb-par-y", `${(ny * strength).toFixed(2)}px`);
      if (rotate) el.style.setProperty("--qb-par-r", `${(nx * rotate).toFixed(2)}deg`);
    }
  };

  const onMove = (e) => {
    const r = container.getBoundingClientRect();
    if (!r.width || !r.height) return;
    // -1..1 relative to the container's centre.
    pending = {
      nx: ((e.clientX - r.left) / r.width - 0.5) * 2,
      ny: ((e.clientY - r.top) / r.height - 0.5) * 2,
    };
    if (!frame) frame = requestAnimationFrame(apply);
  };

  // Returning to rest is the same motion as arriving - the CSS transition
  // carries it - so leaving just writes zeroes.
  const onLeave = () => {
    pending = { nx: 0, ny: 0 };
    if (!frame) frame = requestAnimationFrame(apply);
  };

  container.addEventListener("pointermove", onMove, { passive: true });
  container.addEventListener("pointerleave", onLeave, { passive: true });

  return () => {
    container.removeEventListener("pointermove", onMove);
    container.removeEventListener("pointerleave", onLeave);
    if (frame) cancelAnimationFrame(frame);
    layers.forEach(({ el }) => {
      el.style.removeProperty("--qb-par-x");
      el.style.removeProperty("--qb-par-y");
      el.style.removeProperty("--qb-par-r");
    });
  };
}
