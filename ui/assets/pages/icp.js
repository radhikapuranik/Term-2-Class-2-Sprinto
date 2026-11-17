import { api, html, info, render } from "../lib.js";
import { reveal } from "../motion.js";

const UNANSWERED = {
  reject: "Rule it out (NO-GO)",
  human_review: "Send to human review",
  skip_low_weight: "Skip it: low weight",
  proceed: "Carry on",
};
const SOURCE = { home: "Home page", google_news: "News", lusha: "Lusha", about: "About page", careers: "Careers page", security: "Security page",
  customers: "Customers page", product: "Product page", blog: "Blog", docs: "Docs", footer: "Footer" };
const WHY = {
  company_type: "Sprinto sells to software companies; anything else is out.",
  funding_stage: "Series A to C companies are big enough to need SOC 2, small enough to move fast.",
  employee_count: "50 to 200 people: past the startup stage, before a full compliance team.",
  audit_prep: "No certificates yet, or hiring for audit roles, means an audit is coming.",
  clients: "Many clients, or large ones, means security questionnaires are piling up.",
  industry: "Fintech and healthtech feel compliance pressure first. Nice to have.",
  cloud_stack: "AWS or Azure plugs straight into Sprinto's integrations. Nice to have.",
};

export async function render_(view) {
  const t = await api("/api/icp");
  const l = t.limits;
  render(view, html`<div class="page">
    <header class="page-head"><div><p class="eyebrow">ICP</p><h1>Sprinto's <em>seven</em> rules.</h1>
      <p class="lede">The agent checks these in order and stops at the first answer that rules a company out. The rules live in <code>icp.yaml</code>; the AI never decides, code does.</p></div></header>
    <div class="tiles" style="margin-bottom:32px" data-reveal>
      <div class="tile"><span class="tile-label">Pages per company</span><span class="tile-value">${l.max_fetches_per_company}</span><span class="tile-note">hard cap on fetches</span></div>
      <div class="tile"><span class="tile-label">Seconds per company</span><span class="tile-value">${l.max_seconds_per_company}</span><span class="tile-note">then it stops and reports</span></div>
      <div class="tile"><span class="tile-label">Tokens per AI call</span><span class="tile-value">${(l.max_tokens_per_call / 1000).toFixed(0)}k</span><span class="tile-note">page text is cleaned to fit</span></div>
      <div class="tile"><span class="tile-label">Bad AI answers allowed</span><span class="tile-value">${l.invalid_llm_tries}</span><span class="tile-note">then human review</span></div>
    </div>
    <div class="card">${t.parameters.map((p, i) => html`<article class="rule" data-reveal aria-labelledby="r-${p.id}">
      <span class="rule-n" aria-hidden="true">${String(i + 1).padStart(2, "0")}</span>
      <div><div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap"><h2 id="r-${p.id}">${p.name}</h2>
        <span class="chip soft">${p.weight === "hard" ? "Must pass" : "Low weight"}</span></div>
        <p class="muted" style="margin-top:4px">${WHY[p.id] || ""}</p>
        <dl class="rule-grid">
          <div><dt>Fits when</dt><dd>${p.qualifying_answer}</dd></div>
          <div><dt>Where to look</dt><dd>${p.where_to_look.map((w) => SOURCE[w] || w).join(", ")}</dd></div>
          <div><dt>Sufficiency ${info("sufficiency")}</dt><dd>${p.sufficiency}</dd></div>
          <div><dt>Retries ${info("retries")}</dt><dd class="num">${p.retries}<small>${p.retries === 1 ? "source" : "sources"} at most</small></dd></div>
          <div><dt>If unanswered ${info("unanswered")}</dt><dd>${UNANSWERED[p.if_unanswered] || p.if_unanswered}</dd></div>
          <div><dt>Auto-reject ${info("autoReject")}</dt><dd>${p.auto_reject || "Never"}</dd></div>
        </dl></div></article>`)}</div>
    <p class="muted" style="font-size:13px;margin-top:16px">Read-only here. To change a rule, edit <code>icp.yaml</code> and run the agent again with --refresh.</p>
  </div>`);
  reveal(view);
}
export { render_ as render };
