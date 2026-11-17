import { api, empty, fmt, html, icon, info, render, term } from "../lib.js";
import { countUp, reveal } from "../motion.js";

const METHODS = [["http", "HTML"], ["browser", "Browser"], ["rss", "News feed"], ["api", "API"]];

const mix = (m) => {
  const total = Object.values(m).reduce((a, b) => a + b, 0);
  if (!total) return html`<span class="muted">—</span>`;
  const label = METHODS.filter(([k]) => m[k]).map(([k, l]) => `${l} ${m[k]}`).join(", ");
  return html`<span class="mix" role="img" aria-label="${label}" data-tip="${label}">${METHODS.filter(([k]) => m[k]).map(([k]) => html`<i class="${k}" style="width:${(m[k] / total) * 100}%"></i>`)}</span>`;
};

export async function render_(view) {
  const r = await api("/api/runs");
  const tot = r.runs.reduce((a, x) => ({ tokens: a.tokens + x.tokens_in + x.tokens_out, cost: a.cost + x.cost_usd, hits: a.hits + x.cache_hits }), { tokens: 0, cost: 0, hits: 0 });
  render(view, html`<div class="page">
    <header class="page-head"><div><p class="eyebrow">Runs and costs</p><h1>What each run <em>cost</em>.</h1>
      <p class="lede">Every run of the agent: how many companies, how much came from the cache, how many ${term("tokens", "tokens")} Gemini used, and how pages were read.</p></div></header>
    <div class="tiles" data-reveal>
      <div class="tile" style="background:color-mix(in srgb,var(--highlight) 22%,var(--surface))"><span class="tile-label">${term("cache", "Cache saved you")}</span><span class="tile-value" data-n="${r.cache_saved_calls}">${r.cache_saved_calls}</span><span class="tile-note">AI calls and page fetches not repeated</span></div>
      <div class="tile"><span class="tile-label">Runs</span><span class="tile-value" data-n="${r.runs.length}">${r.runs.length}</span><span class="tile-note">${tot.hits} cache hits in total</span></div>
      <div class="tile"><span class="tile-label">Tokens</span><span class="tile-value">${fmt.n(Math.round(tot.tokens / 1000))}k</span><span class="tile-note">across all runs</span></div>
      <div class="tile"><span class="tile-label">Estimated cost ${info("tokens")}</span><span class="tile-value">$${tot.cost.toFixed(2)}</span><span class="tile-note">at an assumed $${r.price.in} / $${r.price.out} per million tokens in/out</span></div>
    </div>
    <section class="section" aria-labelledby="runs-h">
      <div class="section-head"><h2 class="h2" id="runs-h">All runs</h2>
        <span class="legend"><span><i style="background:var(--ink)"></i>HTML</span><span><i style="background:var(--review)"></i>Browser (≈12× cost)</span><span><i style="background:var(--brand)"></i>News feed</span></span></div>
      ${r.runs.length ? html`<div class="table-wrap"><table class="data stack"><caption class="sr">Agent runs, newest first</caption>
        <thead><tr><th scope="col">When</th><th scope="col" class="num">Companies</th><th scope="col" class="num">Cache hits</th><th scope="col" class="num">Gemini calls</th>
          <th scope="col" class="num">Tokens</th><th scope="col">Pages read</th><th scope="col" class="num">Est. cost</th><th scope="col">Failures</th></tr></thead>
        <tbody>${r.runs.map((x) => html`<tr>
          <td data-label="When" class="full"><b>${fmt.date(x.start)}</b><div class="co-domain">${x.domains.slice(0, 3).join(", ")}${x.domains.length > 3 ? ` +${x.domains.length - 3}` : ""}</div></td>
          <td data-label="Companies" class="num tnum">${x.companies}</td>
          <td data-label="Cache hits" class="num tnum">${x.cache_hits}</td>
          <td data-label="Gemini calls" class="num tnum">${x.gemini_calls}</td>
          <td data-label="Tokens" class="num tnum">${fmt.n(x.tokens_in + x.tokens_out)}</td>
          <td data-label="Pages read">${mix(x.methods)}<div class="co-domain" style="margin-top:4px">${x.fetch_units} cost units</div></td>
          <td data-label="Est. cost" class="num tnum">$${x.cost_usd.toFixed(3)}</td>
          <td data-label="Failures" class="full">${x.failures ? html`<details><summary style="cursor:pointer;color:var(--nogo)">${x.failures} ${x.failures === 1 ? "problem" : "problems"}</summary>
            <ul style="margin:6px 0 0;padding-left:16px;font-size:12.5px" class="muted">${x.failure_samples.map((f) => html`<li>${f}</li>`)}</ul></details>` : html`<span class="muted">None</span>`}</td>
        </tr>`)}</tbody></table></div>` : empty("No runs yet.", "Run the agent from the Overview page and each run shows up here.", html`<a class="btn primary" href="/#run">${icon("play")} Run the agent</a>`)}
      <p class="muted" style="font-size:13px;margin-top:12px">A run is a stretch of agent activity with no gap longer than 15 minutes. Prices are an assumption, not a bill: edit them at the top of <code>outreach/api.py</code>.</p>
    </section>
  </div>`);
  view.querySelectorAll("[data-n]").forEach((el) => countUp(el, +el.dataset.n));
  reveal(view);
}
export { render_ as render };
