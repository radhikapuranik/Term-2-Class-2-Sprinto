import { api, chip, empty, fmt, html, icon, raw, render, term } from "../lib.js";
import { animate, countUp, reveal } from "../motion.js";

function gauge(pct) {
  const cx = 200, cy = 200, r = 160;
  const pt = (p) => { const a = Math.PI * (1 - p / 100); return [cx + r * Math.cos(a), cy - r * Math.sin(a)]; };
  const [x0, y0] = pt(0), [x50, y50] = pt(50), [x100, y100] = pt(100);
  const [t1x, t1y] = [cx, cy - r - 18], [t2x, t2y] = [cx, cy - r + 18];
  const angle = Math.min(100, pct) * 1.8;
  return raw(`<svg viewBox="0 0 400 230" role="img" aria-label="Average edit percent: ${pct}%. Goal: under 50%.">
    <path class="g-track" d="M${x0},${y0} A${r},${r} 0 0 1 ${x100},${y100}"/>
    <path class="g-good" d="M${x0},${y0} A${r},${r} 0 0 1 ${x50},${y50}"/>
    <path class="g-bad" d="M${x50},${y50} A${r},${r} 0 0 1 ${x100},${y100}"/>
    <line class="g-tick" x1="${t1x}" y1="${t1y}" x2="${t2x}" y2="${t2y}"/>
    <text x="${cx}" y="${cy - r - 26}" text-anchor="middle">50%</text>
    <text x="${x0}" y="${cy + 26}" text-anchor="middle">0%</text><text x="${x100}" y="${cy + 26}" text-anchor="middle">100%</text>
    <g data-needle data-angle="${angle}" transform="rotate(${angle} ${cx} ${cy})">
      <line class="g-needle" x1="${cx}" y1="${cy}" x2="${cx - r + 26}" y2="${cy}"/></g>
    <circle class="g-hub" cx="${cx}" cy="${cy}" r="9"/></svg>`);
}

export async function render_(view) {
  const q = await api("/api/quality");
  const s = q.stats, pct = Math.round(s.avg_edit_pct);
  const over = pct > 50;
  const sent = q.history.filter((h) => h.review_action !== "rejected");
  render(view, html`<div class="page">
    <header class="page-head"><div><p class="eyebrow">Quality</p><h1>Are the drafts <em>good</em>?</h1>
      <p class="lede">The honest measure: how much a person has to change each draft before sending it. Under 50% means the agent is saving time.</p></div></header>
    <div class="grid">
      <section class="card span-7" aria-labelledby="g-h">
        <div class="card-title"><h2 class="h2" id="g-h">Average ${term("edit", "edit %")}</h2>${s.sent ? (over ? html`<span class="chip nogo">${icon("warn")}Over the line</span>` : html`<span class="chip go">${icon("check")}Under 50%</span>`) : ""}</div>
        <div class="gauge">${gauge(pct)}<div class="gauge-value"><b data-pct style="color:${over ? "var(--nogo)" : "var(--go)"}">${pct}%</b>
          <p class="muted">${s.sent ? (over ? "Reviewers rewrite more than half of each draft. The drafts aren't saving time yet." : "Reviewers change little before sending. The drafts are doing their job.") : "No emails sent yet. The gauge fills in after your first approval."}</p></div></div>
      </section>
      <div class="span-5" style="display:grid;gap:24px;align-content:start">
        <div class="tiles" data-reveal>
          <div class="tile"><span class="tile-label">${chip("SENT")}</span><span class="tile-value" data-n="${s.sent}">${s.sent}</span><span class="tile-note">to your test inbox</span></div>
          <div class="tile"><span class="tile-label">Rejected</span><span class="tile-value" data-n="${q.rejected}">${q.rejected}</span><span class="tile-note">with a reason on record</span></div>
        </div>
        <div class="callout info" data-reveal>${icon("info")}<div><strong>Opens: not measured in test mode.</strong> Resend can only track opens on your own verified domain. The free test sender (onboarding@resend.dev) can't, so this page never guesses.</div></div>
      </div>
    </div>
    <section class="section card" aria-labelledby="h-h" data-reveal>
      <div class="card-title"><h2 class="h2" id="h-h">Edit % per draft</h2><span class="legend"><span><i style="background:var(--go)"></i>Under 50%</span><span><i style="background:var(--nogo)"></i>Over 50%</span><span><i style="background:var(--ink);width:2px"></i>50% line</span></span></div>
      ${q.history.length ? html`<div class="bars" role="list">${q.history.map((h) => html`<div class="bar-row" role="listitem">
        <a href="/companies/${encodeURIComponent(h.domain)}">${h.name || h.domain}</a>
        ${h.review_action === "rejected" ? html`<span class="muted" style="font-size:13px">Rejected: “${h.reject_reason}”</span><span></span>`
          : html`<span class="bar-track" aria-hidden="true"><i class="${h.edit_ratio > 0.5 ? "over" : ""}" style="width:${Math.max(1.5, h.edit_ratio * 100)}%"></i></span>
            <span class="num" style="text-align:right">${fmt.pct(h.edit_ratio)}</span>`}</div>`)}</div>`
        : empty("Nothing reviewed yet.", "Approve, edit or reject a draft on the Review page and it shows up here.", html`<a class="btn primary" href="/review">Open review</a>`)}
      ${sent.length ? html`<p class="muted" style="font-size:13px;margin-top:16px">${sent.length} sent ${sent.length === 1 ? "email" : "emails"} · edit % = 1 − similarity between the draft and what was sent (subject + body).</p>` : ""}
    </section>
  </div>`);
  view.querySelectorAll("[data-n]").forEach((el) => countUp(el, +el.dataset.n));
  countUp(view.querySelector("[data-pct]"), pct, { suffix: "%" });
  animate((g) => {
    const n = view.querySelector("[data-needle]");
    g.fromTo(n, { rotation: 0, svgOrigin: "200 200" }, { rotation: +n.dataset.angle, svgOrigin: "200 200", duration: 0.8, ease: "back.out(1.4)", delay: 0.15 });
    g.from(view.querySelectorAll(".bar-track i"), { width: 0, duration: 0.7, stagger: 0.05, delay: 0.2 });
  });
  reveal(view);
}
export { render_ as render };
