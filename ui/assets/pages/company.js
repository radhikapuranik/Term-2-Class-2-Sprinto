import { api, chip, copyText, fmt, html, icon, info, outcome, render, ring, sourceChip, term, toast } from "../lib.js";
import { animate, reveal, ringFill, shake } from "../motion.js";

const conf = (c) => (c == null ? "" : html`<span class="conf" data-tip="${"Confidence = how sure the AI was that the quote answers the question."}"><span class="conf-bar" aria-hidden="true"><i style="width:${Math.round(c * 100)}%"></i></span>${Math.round(c * 100)}% sure</span>`);

function ledgerRow(s) {
  return html`<div class="ledger-row" data-reveal>
    <div class="ledger-key"><span class="h3">${s.name}</span>${outcome(s.outcome)}<span class="ledger-rule">Rule: ${s.rule}${s.weight === "low" ? " · low weight" : ""}</span></div>
    <div class="ledger-body">
      ${s.quote ? html`<blockquote class="quote"><span class="hl" data-sweep>“${s.quote}”</span></blockquote>`
        : html`<p class="no-quote">${s.outcome === "not_checked" ? "Not checked: the agent stopped before this rule." : s.error ? `No answer: ${s.error}` : "No quote found on the pages the agent could read."}</p>`}
      <div class="ledger-meta">
        ${s.answer ? html`<span>Answer: <b style="color:var(--ink)">${s.answer}</b></span>` : ""}
        ${conf(s.confidence)}
        <span data-tip="${"Retries = how many sources the agent may try for this rule before giving up."}">${s.attempts}/${s.retries} tries used</span>
      </div>
      ${s.url || s.quote ? html`<div style="display:flex;gap:8px;align-items:center;min-width:0">${sourceChip(s.url, s.source_kind)}
        ${s.quote ? html`<button class="icon-btn" type="button" data-copy="${s.quote}" aria-label="Copy quote">${icon("copy")}</button>` : ""}</div>` : ""}
    </div></div>`;
}

function timelineItem(t) {
  if (t.kind === "fetch") {
    const bad = t.status !== "ok";
    return html`<li class="tl fetch ${bad ? "bad" : ""}"><span class="tl-node" aria-hidden="true"></span>
      <div class="tl-title">Read the ${t.page} page <span class="tag ${t.method}">${t.method === "browser" ? "Browser" : t.method === "rss" ? "News feed" : "HTML"}</span>${bad ? html`<span class="chip nogo soft">${t.status}${t.detail ? `: ${t.detail}` : ""}</span>` : ""}</div>
      <div class="tl-meta">${fmt.host(t.url)}${new URL(t.url).pathname.replace(/\/$/, "")}</div></li>`;
  }
  if (t.kind === "answer") {
    return html`<li class="tl answer ${t.outcome}"><span class="tl-node" aria-hidden="true"></span>
      <div class="tl-title">${t.param.replace(/_/g, " ")} ${outcome(t.outcome)}</div>
      <div class="tl-meta">from ${t.source.replace("google_news", "news")} · ${t.detail}${t.tokens ? ` · ${fmt.n(t.tokens)} tokens` : ""}</div></li>`;
  }
  return html`<li class="tl ${t.kind}"><span class="tl-node" aria-hidden="true"></span><div class="tl-title">${t.kind === "cache" ? "Reused from the cache" : t.kind === "stop" ? "Loop finished" : "Note"}</div>
    <div class="tl-meta">${t.detail.replace(/^loop stopped: /, "")}</div></li>`;
}

export async function render_(view, [domain], ctx) {
  const c = await api(`/api/companies/${encodeURIComponent(domain)}`);
  const eff = c.human || c.decision;
  const needsCall = c.decision === "HUMAN REVIEW" && !c.override;
  const fetches = c.timeline.filter((t) => t.kind === "fetch").length;
  const stopReason = c.stop_reason || "";
  render(view, html`<div class="page">
    <p><a href="/companies" class="btn small ghost" style="margin-left:-12px">${icon("back")} All companies</a></p>
    <header class="page-head" style="align-items:center">
      <div style="display:flex;gap:20px;align-items:center;min-width:0">
        ${ring(c.fit, { size: 84, flip: `ring-${c.domain}` })}
        <div style="min-width:0"><p class="eyebrow">${c.domain}</p><h1 style="margin-top:8px">${c.name}</h1>
          ${c.one_liner ? html`<p class="lede" style="margin-top:6px">${c.one_liner}</p>` : ""}</div>
      </div>
      <div style="display:grid;gap:8px;justify-items:end">
        <div class="chip-row">${chip(c.decision)}${c.human && c.human !== c.decision ? html`<span class="muted" style="font-size:12px">your call:</span>${chip(c.human)}` : ""}</div>
        <span class="muted" style="font-size:13px">${term("icp", `ICP fit ${c.fit_score} of 7`)} · researched ${fmt.ago(c.processed_at)}</span>
      </div>
    </header>

    ${c.stopped_early ? html`<div class="callout nogo" style="margin-bottom:24px">${icon("stop")}<div><strong>Stopped early because a rule ruled it out.</strong> ${c.reasons.find((r) => /rejects/.test(r)) || stopReason}. No more pages or AI calls were spent after that.</div></div>`
      : c.decision === "HUMAN REVIEW" ? html`<div class="callout review" style="margin-bottom:24px">${icon("eye")}<div><strong>The agent couldn't decide this one safely.</strong> ${c.reasons.filter((r) => /unanswered|neutral/.test(r)).slice(0, 2).join(" · ") || stopReason}</div></div>` : ""}
    ${c.override ? html`<div class="callout info" style="margin-bottom:24px">${icon("info")}<div><strong>Your decision: ${c.override.decision}.</strong> “${c.override.reason}” · ${fmt.ago(c.override.ts)}</div></div>` : ""}

    ${needsCall ? html`<section class="card" style="margin-bottom:24px" data-decide aria-labelledby="decide-h">
      <h2 class="h3" id="decide-h" style="font-size:16px">Your call</h2>
      <p class="muted" style="font-size:14px;margin:4px 0 12px">Read the evidence below. GO also finds the contact on Hunter (1 search) and writes a draft for review.</p>
      <div class="toolbar" style="margin:0"><label class="field" style="flex:1 1 260px"><span class="sr">Reason</span><input class="input" data-reason placeholder="Why? e.g. Series B and hiring a compliance engineer"></label>
        <button class="btn go" type="button" data-go>${icon("check")} Mark GO and draft</button><button class="btn danger" type="button" data-nogo>${icon("x")} Mark NO-GO</button></div>
    </section>` : ""}

    <div class="grid">
      <section class="card span-8" aria-labelledby="sc-h">
        <div class="card-title"><h2 class="h2" id="sc-h">ICP scorecard</h2><span class="muted" style="font-size:13px">Evidence ledger: the exact quote and where it came from</span></div>
        <div class="ledger">${c.scorecard.map(ledgerRow)}</div>
      </section>
      <aside class="span-4" style="display:grid;gap:24px;align-content:start">
        <section class="card" aria-labelledby="tl-h" data-reveal>
          <div class="card-title"><h2 class="h2" id="tl-h">Agent loop</h2><span class="muted mono" style="font-size:12px">${fetches}/8 fetches</span></div>
          ${c.timeline.length ? html`<ol class="timeline"><span class="rail-fill" aria-hidden="true"></span>${c.timeline.map(timelineItem)}</ol>` : html`<p class="muted">No steps were logged for this company.</p>`}
          ${stopReason ? html`<p class="muted" style="font-size:13px;margin-top:14px">Stopped because: ${stopReason}${c.elapsed_s ? ` · ${c.elapsed_s}s` : ""}</p>` : ""}
        </section>
        <section class="card" data-reveal aria-labelledby="cost-h"><h2 class="h3" id="cost-h">Cost of this research</h2>
          <dl class="rule-grid" style="margin-top:12px">
            <div><dt>Gemini calls</dt><dd class="num">${fmt.n(c.cost.gemini_calls)}</dd></div>
            <div><dt>${term("tokens", "Tokens")}</dt><dd class="num">${fmt.n(c.cost.tokens_in + c.cost.tokens_out)}</dd></div>
            <div><dt>Pages (HTML)</dt><dd class="num">${fmt.n(c.cost.methods.http || 0)}</dd></div>
            <div><dt>Pages (browser)</dt><dd class="num">${fmt.n(c.cost.methods.browser || 0)}</dd></div>
          </dl></section>
        ${c.draft ? html`<section class="card" data-reveal><h2 class="h3">Email draft</h2><p style="margin:8px 0 12px">“${c.draft.subject}” · ${c.draft.status === "sent" ? chip("SENT") : html`<span class="muted">${c.draft.status.replace("_", " ")}</span>`}</p>
          ${["draft", "human_review"].includes(c.draft.status) ? html`<a class="btn primary small" href="/review?d=${encodeURIComponent(c.domain)}">Review it ${icon("arrow")}</a>` : ""}</section>` : ""}
      </aside>
    </div>
  </div>`);

  // Shared-element morph from the companies table, then the rest of the motion.
  const big = view.querySelector(".page-head .ring");
  if (ctx.flip && window.Flip) window.Flip.from(ctx.flip, { targets: big, duration: 0.6, ease: "expo.out", scale: true, absolute: true });
  else ringFill(view.querySelector(".page-head"));
  animate((g) => {
    g.from(view.querySelectorAll("[data-sweep]"), { backgroundSize: "0% 100%", duration: 0.8, ease: "power2.inOut", stagger: 0.08, delay: 0.25, clearProps: "backgroundSize" });
    const items = view.querySelectorAll(".tl");
    g.from(items, { opacity: 0, x: -8, scale: 0.98, duration: 0.4, stagger: 0.06, delay: 0.2, clearProps: "all" });
    const fill = view.querySelector(".rail-fill"), tl = view.querySelector(".timeline");
    if (fill && tl) g.fromTo(fill, { height: 0 }, { height: tl.offsetHeight - 12, duration: Math.min(0.8, 0.1 * items.length), delay: 0.2, ease: "none" });
  });
  reveal(view);

  view.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => copyText(b.dataset.copy, b)));
  const box = view.querySelector("[data-decide]");
  if (box) {
    const reason = box.querySelector("[data-reason]");
    const decide = async (decision, btn) => {
      if (!reason.value.trim()) { shake(reason); reason.focus(); toast("Write a short reason first, so the decision is on record.", { kind: "warn" }); return; }
      btn.disabled = true;
      const old = btn.innerHTML;
      btn.textContent = decision === "GO" ? "Finding the contact and drafting…" : "Saving…";
      try {
        const r = await api(`/api/companies/${encodeURIComponent(domain)}/decision`, { method: "POST", body: { decision, reason: reason.value } });
        toast(decision === "GO" ? (r.draft_status === "draft" ? "Marked GO. A draft is ready to review." : `Marked GO. ${r.notes || "The draft needs attention."}`) : "Marked NO-GO.",
          { kind: "ok", action: decision === "GO" ? "Review it" : undefined, onAction: () => ctx.navigate(`/review?d=${encodeURIComponent(domain)}`) });
        ctx.navigate(location.pathname, { replace: true });
      } catch (e) {
        toast(e.message, { kind: "err", ms: 8000 }); btn.disabled = false; btn.innerHTML = old;
      }
    };
    box.querySelector("[data-go]").addEventListener("click", (e) => decide("GO", e.currentTarget));
    box.querySelector("[data-nogo]").addEventListener("click", (e) => decide("NO-GO", e.currentTarget));
  }
}
export { render_ as render };
