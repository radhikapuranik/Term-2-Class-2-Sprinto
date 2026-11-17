import { api, chip, empty, fmt, html, icon, info, raw, render, term, toast } from "../lib.js";
import { animate, countUp, drawPath, heroLines, reveal } from "../motion.js";

function heroSentence(s) {
  if (s.drafts_to_review) {
    const n = s.drafts_to_review;
    return { mark: `${n} ${n === 1 ? "email is" : "emails are"}`, rest: "ready for your review.", sub: "Each one is written from evidence on the company's own site. Nothing goes out until you approve it.", cta: ["/review", "Open the review queue"] };
  }
  if (s.companies_to_decide) {
    const n = s.companies_to_decide;
    return { mark: `${n} ${n === 1 ? "company needs" : "companies need"}`, rest: "your call.", sub: "The agent couldn't decide these safely. Read the evidence and mark them GO or NO-GO.", cta: ["/companies?filter=review", "See who needs a decision"] };
  }
  if (!s.funnel[0].count) return { mark: "No companies", rest: "yet.", sub: "Paste a few company domains below and run the agent.", cta: null };
  return { mark: "All caught up.", rest: "Nice work.", sub: "Every draft has been reviewed. Run the agent on new domains whenever you're ready.", cta: null };
}

function funnelSvg(stages) {
  const W = 700, H = 170, pad = 24, max = Math.max(1, ...stages.map((s) => s.count));
  const pts = stages.map((s, i) => [pad + (i * (W - 2 * pad)) / (stages.length - 1), 18 + (1 - s.count / max) * (H - 50)]);
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], mx = (x0 + x1) / 2;
    d += ` C${mx},${y0} ${mx},${y1} ${x1},${y1}`;
  }
  const area = `${d} L${pts.at(-1)[0]},${H} L${pts[0][0]},${H} Z`;
  const drops = pts.map(([x, y]) => `<line class="f-drop" x1="${x}" y1="${y}" x2="${x}" y2="${H}"/>`).join("");
  const dots = pts.map(([x, y]) => `<circle class="f-dot" cx="${x}" cy="${y}" r="6"/>`).join("");
  const desc = stages.map((s) => `${s.label}: ${s.count}`).join(", ");
  return raw(`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Pipeline funnel. ${desc}"><path class="f-area" d="${area}"/>${drops}<path class="f-line" d="${d}"/>${dots}</svg>`);
}

const STEP_RE = /^(fetched|cache hit|loop stopped)/;
function stepText(t) {
  return t.replace(/https?:\/\/(www\.)?/, "").replace(/ via (\w+): ok\s*$/, " ($1)").replace(/\s+/g, " ").trim();
}

export async function render_(view, _params, ctx) {
  const s = await api("/api/summary");
  const h = heroSentence(s);
  const st = s.stats;
  render(view, html`<div class="page">
    <section class="hero" aria-labelledby="hero-h">
      <p class="eyebrow">Overview · last run ${fmt.ago(s.last_run_at)}</p>
      <h1 id="hero-h"><span class="line"><span><span class="mark">${h.mark}<svg viewBox="0 0 300 20" preserveAspectRatio="none" aria-hidden="true"><path d="M4 13 C 70 6, 150 16, 296 9"/></svg></span></span></span><span class="line"><span>${h.rest}</span></span></h1>
      <p class="hero-sub">${h.sub}</p>
      ${h.cta ? html`<div class="hero-actions"><a class="btn primary big" href="${h.cta[0]}">${h.cta[1]} ${icon("arrow")}</a><a class="btn big" href="#run">Run the agent</a></div>` : ""}
    </section>

    <div class="tiles" data-reveal>
      <div class="tile"><span class="tile-label">${chip("GO")}</span><span class="tile-value" data-count="${s.decisions.GO}">${s.decisions.GO}</span><span class="tile-note">the agent said fit</span></div>
      <div class="tile"><span class="tile-label">${chip("HUMAN REVIEW")} ${info("review")}</span><span class="tile-value" data-count="${s.decisions["HUMAN REVIEW"]}">${s.decisions["HUMAN REVIEW"]}</span><span class="tile-note">${s.companies_to_decide} still need your call</span></div>
      <div class="tile"><span class="tile-label">${chip("NO-GO")}</span><span class="tile-value" data-count="${s.decisions["NO-GO"]}">${s.decisions["NO-GO"]}</span><span class="tile-note">ruled out, with a reason</span></div>
      <div class="tile"><span class="tile-label">${chip("SENT")}</span><span class="tile-value" data-count="${st.sent}">${st.sent}</span><span class="tile-note">to your test inbox only</span></div>
      <div class="tile"><span class="tile-label">${term("edit", "Average edit %")}</span><span class="tile-value" style="color:${st.avg_edit_pct > 50 ? "var(--nogo)" : "var(--go)"}" data-count="${Math.round(st.avg_edit_pct)}" data-suffix="%">${Math.round(st.avg_edit_pct)}%</span><span class="tile-note">${st.avg_edit_pct > 50 ? "Above 50%: drafts need too much work" : "Under 50%: drafts are saving time"}</span></div>
    </div>

    <section class="section card" data-reveal aria-labelledby="funnel-h">
      <div class="card-title"><h2 class="h2" id="funnel-h">From domain to inbox</h2><a class="btn small ghost" href="/companies">All companies ${icon("arrow")}</a></div>
      ${s.funnel[0].count ? html`<div class="funnel">${funnelSvg(s.funnel)}
        <div class="funnel-labels">${s.funnel.map((f) => html`<div><b data-count="${f.count}">${f.count}</b><span>${f.label}</span></div>`)}</div></div>`
        : empty("No companies yet.", "Paste some domains below and run the agent. The funnel fills in as it works.")}
    </section>

    <section class="section grid" id="run" aria-labelledby="run-h">
      <div class="card span-7 run-panel" data-reveal>
        <div><h2 class="h2" id="run-h">Run the agent</h2><p class="muted" style="margin-top:6px">Paste company domains, one per line. Companies already researched come straight from the cache.</p></div>
        <form class="run-panel" data-run-form>
          <div class="field"><label for="domains">Domains</label>
            <textarea id="domains" class="textarea mono" rows="5" placeholder="acme.com&#10;ledgerly.io" spellcheck="false"></textarea></div>
          <div class="toolbar" style="margin:0">
            <span class="btn small file-btn">${icon("upload")} Upload .txt or .csv<input type="file" accept=".txt,.csv,text/plain,text/csv" aria-label="Upload a list of domains"></span>
            <label class="check"><input type="checkbox" name="qualify_only"> <span>Dry run: ${term("qualifyOnly", "qualify only")} (no Hunter searches, no drafts)</span></label>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><button class="btn primary" type="submit" data-run-btn>${icon("play")} Run agent</button>
            <span class="muted" data-run-status style="font-size:13px">${s.running.length ? "A run is in progress." : "Ready."}</span></div>
        </form>
        <div class="run-progress" aria-hidden="true"><i data-run-bar></i></div>
        <ol class="stream" data-stream aria-live="polite" aria-label="Agent steps"></ol>
      </div>
      <div class="card span-5" data-reveal>
        <h2 class="h2">What happens</h2>
        <ol class="prose" style="padding-left:20px;margin-top:12px;font-size:14.5px">
          <li>Reads each company's public pages (never LinkedIn, never logins), one request a second.</li>
          <li>Gemini answers one ICP question at a time and must quote the page.</li>
          <li>Code applies Sprinto's seven rules: ${chip("GO")} ${chip("NO-GO")} or ${chip("HUMAN REVIEW")}</li>
          <li>For GO companies: Hunter finds one person, and a short email is drafted.</li>
          <li>You review every email. It only ever goes to your own test address.</li>
        </ol>
      </div>
    </section>
  </div>`);

  heroLines(view);
  const hl = view.querySelector(".mark path");
  if (hl) drawPath(hl, { duration: 0.7, delay: 0.35 });
  view.querySelectorAll("[data-count]").forEach((el) => countUp(el, +el.dataset.count, { suffix: el.dataset.suffix || "" }));
  const line = view.querySelector(".f-line");
  if (line) {
    drawPath(line, { duration: 0.8, delay: 0.2 });
    animate((g) => g.from(view.querySelectorAll(".f-dot"), { scale: 0, transformOrigin: "50% 50%", stagger: 0.08, delay: 0.3, duration: 0.4, clearProps: "all" }));
  }
  reveal(view);
  wireRun(view, ctx);
}

function wireRun(view, ctx) {
  const form = view.querySelector("[data-run-form]");
  const ta = view.querySelector("#domains");
  const list = view.querySelector("[data-stream]");
  const bar = view.querySelector("[data-run-bar]");
  const status = view.querySelector("[data-run-status]");
  const btn = view.querySelector("[data-run-btn]");
  view.querySelector('input[type="file"]').addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    ta.value = (await f.text()).split(/\r?\n/).map((l) => l.split(",")[0].trim()).filter(Boolean).join("\n");
    toast(`Loaded ${fmt.words(ta.value)} domains from ${f.name}.`, { kind: "info", ms: 2500 });
  });

  const add = (label, text, cls = "") => {
    const li = document.createElement("li");
    li.className = cls;
    li.innerHTML = `<b>${label}</b><span></span>`;
    list.appendChild(li);
    const span = li.lastChild;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || text.length > 140) span.textContent = text;
    else { let i = 0; const t = setInterval(() => { span.textContent = text.slice(0, (i += 3)); if (i >= text.length) clearInterval(t); }, 12); }
    list.scrollTop = list.scrollHeight;
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const domains = ta.value.split(/\n/).map((l) => l.trim()).filter(Boolean);
    if (!domains.length) { toast("Add at least one domain, like acme.com.", { kind: "warn" }); ta.focus(); return; }
    btn.disabled = true;
    list.innerHTML = "";
    bar.style.width = "4%";
    let run;
    try {
      run = await api("/api/runs", { method: "POST", body: { domains, qualify_only: form.qualify_only.checked } });
    } catch (err) {
      toast(err.message, { kind: "err" }); btn.disabled = false; bar.style.width = "0"; return;
    }
    status.textContent = `Running on ${run.domains.length} ${run.domains.length === 1 ? "company" : "companies"}…`;
    let done = 0;
    const es = new EventSource(`/api/runs/${run.id}/stream`);
    ctx.cleanup.push(() => es.close());
    es.addEventListener("step", (m) => {
      const d = JSON.parse(m.data);
      add(d.domain.split(".")[0], stepText(d.text), STEP_RE.test(d.text) ? "" : "");
    });
    es.addEventListener("result", (m) => {
      const r = JSON.parse(m.data);
      done += 1;
      bar.style.width = `${Math.max(4, (done / run.domains.length) * 100)}%`;
      add("→", `${r.domain}: ${r.decision}${r.cached ? " (from cache)" : ""}${r.draft ? `, draft ${r.draft}` : ""}`, "result");
    });
    es.addEventListener("done", (m) => {
      es.close();
      const d = JSON.parse(m.data);
      btn.disabled = false;
      bar.style.width = "100%";
      if (d.error) {
        add("!", `Stopped: ${d.error}`, "err");
        status.textContent = "The run stopped early.";
        toast(`The run stopped: ${d.error}`, { kind: "err", ms: 8000 });
      } else {
        status.textContent = `Done. ${d.results.length} ${d.results.length === 1 ? "company" : "companies"} processed.`;
        toast("Run finished. The companies list is up to date.", { kind: "ok", action: "View companies", onAction: () => ctx.navigate("/companies") });
      }
      ctx.refreshCounts();
    });
    es.onerror = () => { if (es.readyState === EventSource.CLOSED) btn.disabled = false; };
  });
}
export { render_ as render };
