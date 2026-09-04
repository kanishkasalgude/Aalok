// Minimal hash router. Each route maps to a page module exposing
// `render(container)`. No framework, no build step.
import { staggerIn } from "./motion.js";

const routes = {};
let contentEl = null;
let navUpdateFn = null;

export function registerRoute(path, module) {
  routes[path] = module;
}

export function setNavUpdater(fn) {
  navUpdateFn = fn;
}

export function init(container) {
  contentEl = container;
  window.addEventListener("hashchange", handleChange);
  handleChange();
}

function currentPath() {
  const hash = window.location.hash.replace(/^#/, "") || "/overview";
  return hash.split("?")[0];
}

async function handleChange() {
  const path = currentPath();
  const mod = routes[path] || routes["/overview"];
  if (navUpdateFn) navUpdateFn(path);
  contentEl.innerHTML = '<div class="qb-skel qb-skel-card" style="margin-bottom:12px"></div><div class="qb-skel qb-skel-line" style="width:60%"></div>';
  try {
    await mod.render(contentEl);
  } catch (err) {
    console.error("Page render failed", err);
    contentEl.innerHTML = `<div class="qb-note danger">Something went wrong loading this page. Check the console for details.</div>`;
  }
  // Motion-driven reveal for the page's actual content pieces - a real
  // stagger, not a hand-rolled nth-child animation-delay table. Deliberately
  // scoped to leaf content (header, cards) rather than structural layout
  // containers: animating `transform` on a flex/height:calc container (e.g.
  // .qb-agent-shell, .qb-content itself) was verified to collapse its width
  // to 0 mid-animation in this browser - a real, reproduced layout bug, not
  // a hypothetical one. Content cards have no such dependency and are safe.
  const reveal = contentEl.querySelectorAll(":scope > .qb-content-header, :scope > .qb-section > .qb-card, :scope .qb-grid > .qb-card");
  if (reveal.length) staggerIn(reveal);
}

export function navigate(path) {
  window.location.hash = path;
}
