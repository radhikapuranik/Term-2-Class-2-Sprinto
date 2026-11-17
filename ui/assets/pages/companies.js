import { api, chip, empty, fmt, html, icon, info, render, ring, term } from "../lib.js";
import { reveal, ringFill } from "../motion.js";

const FILTERS = [["all", "All"], ["GO", "GO"], ["review", "Human review"], ["NO-GO", "NO-GO"]];
const SORTS = { fit: (a, b) => b.fit_score - a.fit_score, name: (a, b) => a.name.localeCompare(b.name), recent: (a, b) => (b.processed_at || 0) - (a.processed_at || 0) };

const effective = (c) => c.human || c.decision;

export async function render_(view, _p, ctx) {
  const rows = await api("/api/companies");
  const qs = new URLSearchParams(location.search);
  const state = { q: qs.get("q") || "", filter: qs.get("filter") || "all", sort: qs.get("sort") || "recent" };

  render(view, html`<div class="page">
    <header class="page-head"><div><p class="eyebrow">Companies</p><h1>Who <em>fits</em>, and why.</h1>
      <p class="lede">Every company the agent has researched, with its decision and an ${term("icp", "ICP fit ring")}: one segment per rule, green when it fits.</p></div>
      <div class="legend" aria-label="Ring colours"><span><i style="background:var(--go)"></i>Fits</span><span><i style="background:var(--review)"></i>Answered, not a fit</span><span><i style="background:var(--nogo)"></i>Rules it out</span><span><i style="background:color-mix(in srgb,var(--neutral) 35%,transparent)"></i>Not found</span></div>
    </header>
    ${rows.length ? html`<div class="toolbar" role="search">
      <label class="search"><span class="sr">Search companies</span>${icon("search")}<input class="input" type="search" placeholder="Search name or domain" value="${state.q}" data-q></label>
      <div class="seg-ctl" role="group" aria-label="Filter by decision">${FILTERS.map(([k, l]) => html`<button type="button" data-filter="${k}" aria-pressed="${state.filter === k}">${l}</button>`)}</div>
      <label class="field" style="grid-auto-flow:column;align-items:center;gap:8px;margin-left:auto"><span class="label">Sort</span>
        <select class="select" data-sort style="width:auto;padding:7px 10px;border-radius:99px">
          <option value="recent">Most recent</option><option value="fit">Best ICP fit</option><option value="name">Name A–Z</option></select></label>
    </div>
    <div class="table-wrap"><table class="data stack" aria-describedby="count-note">
      <caption class="sr">Researched companies</caption>
      <thead><tr><th scope="col">Company</th><th scope="col">Decision</th><th scope="col">ICP fit ${info("icp")}</th><th scope="col">Funding</th>
        <th scope="col">Headcount</th><th scope="col">Cloud</th><th scope="col" class="num">Sources</th><th scope="col">Researched</th></tr></thead>
      <tbody data-body></tbody></table></div>
    <p class="muted" id="count-note" style="margin-top:12px;font-size:13px" aria-live="polite" data-count></p>`
    : empty("No companies yet.", "Paste some domains and run the agent.", html`<a class="btn primary" href="/#run">Run the agent</a>`)}
  </div>`);
  if (!rows.length) return;

  const body = view.querySelector("[data-body]");
  view.querySelector("[data-sort]").value = state.sort;
  const draw = () => {
    const q = state.q.toLowerCase();
    const list = rows.filter((c) => (!q || c.name.toLowerCase().includes(q) || c.domain.includes(q))
      && (state.filter === "all" || (state.filter === "review" ? effective(c) === "HUMAN REVIEW" : effective(c) === state.filter)))
      .sort(SORTS[state.sort]);
    render(body, list.length ? html`${list.map((c) => html`<tr class="clickable" data-href="/companies/${encodeURIComponent(c.domain)}">
      <td class="full" data-label="Company"><a href="/companies/${encodeURIComponent(c.domain)}" class="co-link" style="text-decoration:none"><span class="co-name">${c.name}</span><span class="co-domain">${c.domain}</span></a></td>
      <td data-label="Decision"><div class="chip-row">${chip(c.decision)}${c.human && c.human !== c.decision ? html`<span class="muted" style="font-size:12px">you:</span>${chip(c.human)}` : ""}</div></td>
      <td data-label="ICP fit"><span class="fit">${ring(c.fit, { flip: `ring-${c.domain}` })}<small>${c.fit_score}/7</small></span></td>
      <td data-label="Funding">${fmt.cap(c.funding) || html`<span class="muted">—</span>`}</td>
      <td data-label="Headcount" class="tnum">${c.headcount || html`<span class="muted" title="Not found">—</span>`}</td>
      <td data-label="Cloud">${c.cloud ? c.cloud.toUpperCase() : html`<span class="muted">—</span>`}</td>
      <td data-label="Sources" class="num tnum">${c.sources}</td>
      <td data-label="Researched" class="muted" style="font-size:13px">${fmt.ago(c.processed_at)}</td></tr>`)}`
      : html`<tr><td colspan="8" class="full"><p class="muted" style="padding:20px 0;text-align:center">No companies match. Try another search or filter.</p></td></tr>`);
    view.querySelector("[data-count]").textContent = `Showing ${list.length} of ${rows.length} companies.`;
    ringFill(body);
    const u = new URLSearchParams();
    if (state.q) u.set("q", state.q);
    if (state.filter !== "all") u.set("filter", state.filter);
    if (state.sort !== "recent") u.set("sort", state.sort);
    history.replaceState({}, "", `/companies${u.size ? `?${u}` : ""}`);
  };
  draw();
  reveal(view);

  view.querySelector("[data-q]").addEventListener("input", (e) => { state.q = e.target.value; draw(); });
  view.querySelector("[data-sort]").addEventListener("change", (e) => { state.sort = e.target.value; draw(); });
  view.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => {
    state.filter = b.dataset.filter;
    view.querySelectorAll("[data-filter]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    draw();
  }));
  // Whole row is clickable; the ring morphs into the detail page header (GSAP Flip).
  body.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-href]");
    if (!tr || e.target.closest("a") && e.metaKey) return;
    e.preventDefault();
    const r = tr.querySelector(".ring");
    if (window.Flip && r && !matchMedia("(prefers-reduced-motion: reduce)").matches) ctx.flip = window.Flip.getState(r);
    ctx.navigate(tr.dataset.href);
  });
}
export { render_ as render };
