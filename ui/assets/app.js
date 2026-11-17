// Router and app shell. Each page is a lazily loaded module exporting render(view, params, ctx).
import { api, errorState, initTips, render, skeleton } from "./lib.js";
import { gsapReady, initFeedback, pageIn, pageOut } from "./motion.js";

const ROUTES = [
  [/^\/$/, "overview", "Overview"],
  [/^\/companies\/?$/, "companies", "Companies"],
  [/^\/companies\/([^/]+)\/?$/, "company", "Company"],
  [/^\/review\/?$/, "review", "Review"],
  [/^\/quality\/?$/, "quality", "Quality"],
  [/^\/icp\/?$/, "icp", "ICP"],
  [/^\/runs\/?$/, "runs", "Runs and costs"],
  [/^\/about\/?$/, "about", "About"],
];
const view = document.getElementById("view");
const ctx = { meta: null, flip: null, cleanup: [] };
let first = true;

function match(path) {
  for (const [re, page, title] of ROUTES) {
    const m = path.match(re);
    if (m) return { page, title, params: m.slice(1).map(decodeURIComponent) };
  }
  return { page: "notfound", title: "Not found", params: [] };
}

export async function navigate(url, { replace = false } = {}) {
  if (url === location.pathname + location.search && !replace) return;
  history[replace ? "replaceState" : "pushState"]({}, "", url);
  await route();
}
ctx.navigate = navigate;

async function route() {
  ctx.cleanup.splice(0).forEach((fn) => { try { fn(); } catch { /* page already gone */ } });
  const { page, title, params } = match(location.pathname);
  document.title = `${title} · Outreach Desk`;
  document.querySelectorAll("[data-nav]").forEach((a) => {
    const n = a.dataset.nav;
    const on = n === "/" ? location.pathname === "/" : location.pathname.startsWith(n);
    on ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current");
  });
  if (!first && !ctx.flip) await pageOut(view);
  render(view, skeleton());
  try {
    const mod = await import(`./pages/${page}.js`);
    await mod.render(view, params, ctx);
  } catch (e) {
    render(view, errorState(e.message || "Please try again."));
  }
  if (!first) {
    if (!ctx.flip) pageIn(view);
    view.focus({ preventScroll: true });
    scrollTo({ top: 0, behavior: "instant" });
  }
  ctx.flip = null;
  first = false;
  refreshCounts();
}

export async function refreshCounts() {
  try {
    const s = await api("/api/summary");
    const el = document.querySelector("[data-review-count]");
    el.hidden = !s.drafts_to_review;
    el.textContent = s.drafts_to_review;
    el.setAttribute("aria-label", `${s.drafts_to_review} drafts to review`);
  } catch { /* the page shows its own error */ }
}
ctx.refreshCounts = refreshCounts;

// Links: same-origin, data-link or plain internal anchors, open in place.
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href]");
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || a.target === "_blank") return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  e.preventDefault();
  navigate(url.pathname + url.search);
});
addEventListener("popstate", route);

// Theme toggle: follows the system until the person picks one.
function themeLabel() {
  const t = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  document.querySelectorAll("[data-theme-label]").forEach((l) => { l.textContent = t === "dark" ? "Dark theme" : "Light theme"; });
  return t;
}
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-theme-toggle]")) return;
  const next = themeLabel() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("od-theme", next); } catch { /* private mode */ }
  themeLabel();
});
themeLabel();

initTips();
initFeedback();
api("/api/meta").then((m) => {
  ctx.meta = m;
  document.querySelectorAll("[data-recipient]").forEach((s) => { s.textContent = m.test_recipient ? ` (${m.test_recipient})` : ""; });
}).catch(() => {});
route();
requestIdleCallback?.(() => gsapReady()) ?? setTimeout(gsapReady, 400);
