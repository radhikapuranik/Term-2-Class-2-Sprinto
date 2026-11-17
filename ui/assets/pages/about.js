import { html, icon, raw, render } from "../lib.js";
import { animate, heroLines, reveal } from "../motion.js";

const STEPS = [
  ["Scrape", "public pages", ""], ["Extract", "Gemini quotes", "ai"], ["Qualify", "code, 7 rules", ""],
  ["Contact", "Hunter, 1 person", ""], ["Pains", "2, with evidence", "ai"], ["Email", "checked draft", "ai"], ["Review", "you approve", "human"],
];

function pipeline() {
  const W = 980, nodeW = 118, gap = (W - nodeW * 7) / 6, y = 30, h = 76;
  let links = "", nodes = "";
  STEPS.forEach(([t, sub, cls], i) => {
    const x = i * (nodeW + gap);
    if (i) links += `<path class="p-link" d="M${x - gap},${y + h / 2} H${x}"/><path class="p-flow" d="M${x - gap},${y + h / 2} H${x}"/>`;
    nodes += `<g class="p-node ${cls}" data-node><rect x="${x}" y="${y}" width="${nodeW}" height="${h}" rx="12"/>
      <text class="n" x="${x + 14}" y="${y + 24}">0${i + 1}</text><text x="${x + 14}" y="${y + 46}">${t}</text><text class="sub" x="${x + 14}" y="${y + 64}">${sub}</text></g>`;
  });
  return raw(`<svg viewBox="-4 0 ${W + 8} 140" role="img" aria-label="The pipeline: ${STEPS.map((s) => s[0]).join(", then ")}. Yellow outline: AI. Green outline: a person.">${links}${nodes}
    <text x="0" y="132" style="fill:var(--muted);font:500 11px var(--mono)">YELLOW = AI WRITES OR EXTRACTS · GREEN = A PERSON DECIDES · EVERYTHING ELSE IS CODE</text></svg>`);
}

const SAFE = [
  ["Test mode, locked in code", "Every email goes to one address: your own TEST_RECIPIENT. Any other address is refused before Resend is called."],
  ["A person approves every email", "Drafts wait on the Review page. Nothing sends itself, and an approval can be undone for 8 seconds."],
  ["No LinkedIn, no logins", "Only public pages are read. Login pages and LinkedIn are never fetched."],
  ["Polite reading", "robots.txt is respected, one request per second per site, at most 8 pages per company."],
  ["Minimal personal data", "Only one contact's work name, title and work email are kept. The email address never reaches this page."],
  ["AI never decides", "Gemini extracts quotes and writes text. GO or NO-GO comes from the rules in code, with the quote and URL on record."],
];

export function render_(view) {
  render(view, html`<div class="page">
    <section class="hero"><p class="eyebrow">About</p>
      <h1><span class="line"><span>A careful assistant</span></span><span class="line"><span>for <em style="color:var(--brand)">cold outreach</em>.</span></span></h1>
      <p class="hero-sub">Outreach Desk researches companies, checks them against Sprinto's ideal customer profile, finds the one right person, and drafts a short email from real evidence. You stay in charge of what gets sent.</p></section>
    <section class="card pipeline" data-reveal aria-labelledby="p-h"><h2 class="h2" id="p-h" style="margin-bottom:16px">How it works</h2>${pipeline()}</section>
    <section class="section" aria-labelledby="s-h"><h2 class="h2" id="s-h" style="margin-bottom:16px">Safety rules</h2>
      <ul class="safety">${SAFE.map(([t, d]) => html`<li data-reveal>${icon("shield")}<div><strong>${t}</strong><p class="muted" style="font-size:13.5px;margin-top:2px">${d}</p></div></li>`)}</ul></section>
    <section class="section grid">
      <div class="card span-6" data-reveal><h2 class="h2">Assumptions</h2><ul class="prose" style="padding-left:18px;margin-top:12px;font-size:14.5px">
        <li>"Retries" means how many sources may be tried for a rule.</li>
        <li>A system failure (site blocked, AI down) never rejects a company: it goes to human review.</li>
        <li>"No certificates found" only counts when the security page itself was readable.</li>
        <li>News comes from Bing News RSS because Google News blocks feed readers.</li>
        <li>The full list is in <code>docs/ASSUMPTIONS.md</code>.</li></ul></div>
      <div class="card span-6" data-reveal><h2 class="h2">Limits</h2><ul class="prose" style="padding-left:18px;margin-top:12px;font-size:14.5px">
        <li>Without a Lusha key, headcount is usually unknown, so many companies need your call.</li>
        <li>Hunter's free tier allows 25 searches a month; results are cached forever.</li>
        <li>Sites that block automated readers can't be researched.</li>
        <li>Opens aren't measured: Resend's test sender can't track them.</li>
        <li>Costs shown are estimates from token counts and an assumed price.</li></ul></div>
    </section>
  </div>`);
  heroLines(view);
  animate((g) => {
    g.from(view.querySelectorAll("[data-node]"), { opacity: 0, y: 14, duration: 0.5, stagger: 0.09, delay: 0.2, clearProps: "all" });
    g.fromTo(view.querySelectorAll(".p-flow"), { strokeDashoffset: 28 }, { strokeDashoffset: 0, duration: 1.2, ease: "none", repeat: -1 });
  });
  reveal(view);
}
export { render_ as render };
