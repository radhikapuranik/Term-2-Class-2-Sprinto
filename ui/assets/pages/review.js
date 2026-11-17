import { api, chip, dryRun, empty, esc, fmt, html, icon, info, raw, render, ring, sourceChip, term, toast } from "../lib.js";
import { animate, burst, motionOK, shake } from "../motion.js";

const UNDO_MS = window.__UNDO_MS ?? 8000; // tests shorten the undo window

function hookBody(body, hook) {
  let out = esc(body);
  if (hook && hook.length > 3) {
    const h = esc(hook);
    out = out.split(h).join(`<mark data-tip="The hook: a real fact from the evidence">${h}</mark>`);
  }
  return raw(out);
}

export async function render_(view, _p, ctx) {
  const [queue, summary] = await Promise.all([api("/api/review"), api("/api/summary")]);
  const want = new URLSearchParams(location.search).get("d");
  const st = { queue, i: Math.max(0, queue.findIndex((d) => d.domain === want)), mode: "view", pending: null, lastReject: null };
  const recipient = ctx.meta?.test_recipient || "TEST_RECIPIENT";

  render(view, html`<div class="page">
    <header class="page-head"><div><p class="eyebrow">Review</p><h1>Read it, then <em>send</em> it.</h1>
      <p class="lede">Nothing leaves without your approval, and it only ever goes to your own test inbox. ${term("edit", "Edit %")} shows how much you changed.</p></div>
      <label class="check" style="align-self:center"><input type="checkbox" data-dry ${dryRun.get() ? "checked" : ""}><span>${term("dry", "Dry run")}: don't really send</span></label>
    </header>
    ${summary.companies_to_decide ? html`<div class="callout review" style="margin-bottom:24px">${icon("eye")}<div><strong>${summary.companies_to_decide} ${summary.companies_to_decide === 1 ? "company needs" : "companies need"} your GO or NO-GO first.</strong>
      <a href="/companies?filter=review">See them</a>. A GO writes a new draft that appears here.</div></div>` : ""}
    <div data-desk></div>
  </div>`);
  const desk = view.querySelector("[data-desk]");
  view.querySelector("[data-dry]").addEventListener("change", (e) => {
    dryRun.set(e.target.checked);
    toast(e.target.checked ? "Dry run on: approving won't send anything." : "Dry run off: approving sends to your test inbox.", { kind: "info", ms: 2500 });
  });

  const cur = () => st.queue[st.i];

  function draw({ focusQueue = false } = {}) {
    st.mode = "view";
    if (!st.queue.length) {
      render(desk, empty("Inbox zero.", "Every draft has been reviewed. Run the agent on new domains, or mark a Human review company as GO.",
        html`<a class="btn primary" href="/#run">Run the agent</a>`));
      ctx.refreshCounts();
      return;
    }
    st.i = Math.min(st.i, st.queue.length - 1);
    const d = cur();
    const c = d.contact || {};
    const who = `${c.first_name || ""} ${c.last_name || ""}`.trim() || "Unknown";
    const hookSrc = (d.pains || []).find((p) => p.evidence_quote && d.hook && p.evidence_quote.includes(d.hook)) || (d.evidence || []).find((e) => e.evidence_quote?.includes(d.hook || "§"));
    render(desk, html`<div class="review-layout">
      <nav class="queue" aria-label="Drafts to review (${st.queue.length})">
        ${st.queue.map((q, i) => html`<button type="button" class="queue-item" data-i="${i}" aria-current="${i === st.i}">
          ${ring(q.fit || [], { size: 36 })}<span><span class="qi-name">${q.company}</span><span class="qi-sub">${q.contact?.first_name || "No contact"} · ${q.subject || "No draft"}</span></span></button>`)}
        <p class="kbd-help" aria-hidden="true"><span><span class="kbd">J</span>/<span class="kbd">K</span> move</span><span><span class="kbd">A</span> approve</span><span><span class="kbd">E</span> edit</span><span><span class="kbd">X</span> reject</span><span><span class="kbd">U</span> undo</span></p>
      </nav>
      <div class="desk">
        <article class="mail" data-mail aria-labelledby="mail-subject">
          <div class="mail-head">
            <div class="mail-row"><span>From</span><span>Sprinto Outreach (test)</span></div>
            <div class="mail-row"><span>To</span><span class="name-chip" data-tip="The recipient is locked to TEST_RECIPIENT in code. Prospects never receive anything."><span class="avatar" style="background:var(--highlight);color:#12131A">${icon("lock")}</span>Your test inbox <span class="mono muted" style="font-size:12px">${recipient}</span></span></div>
            <div class="mail-row"><span>For</span><span class="name-chip"><span class="avatar">${fmt.initials(who)}</span>${who}<span class="muted" style="font-weight:400">· ${c.title || ""}</span></span></div>
          </div>
          ${d.status === "human_review" ? html`<div class="callout review" style="margin:16px 20px 0">${icon("warn")}<div><strong>Needs attention:</strong> ${d.notes}</div></div>` : ""}
          <div data-mail-main>
            <h2 class="mail-subject" id="mail-subject">${d.subject || "No subject"}</h2>
            <div class="mail-body">${hookBody(d.body || "No draft body yet.", d.hook)}</div>
          </div>
          <div class="mail-actions" data-actions>
            <button class="btn go big" type="button" data-approve ${d.body ? "" : "disabled"}>${icon("plane")} Approve and send <kbd>A</kbd></button>
            <button class="btn" type="button" data-edit>${icon("edit")} Edit <kbd>E</kbd></button>
            <button class="btn danger" type="button" data-reject>${icon("x")} Reject <kbd>X</kbd></button>
          </div>
          <div data-reject-box hidden></div>
          <p class="callout info static-only" style="margin:16px 20px">${icon("lock")}<span>Read-only snapshot: approving, editing and rejecting happen on the laptop.</span></p>
        </article>
        <aside class="side" aria-label="Why this email">
          <section class="card"><div class="person"><span class="avatar">${fmt.initials(who)}</span><div><strong>${who}</strong><div class="muted" style="font-size:13.5px">${c.title || "Title unknown"}</div></div></div>
            ${c.why ? html`<p style="font-size:13.5px;margin-top:12px"><span class="muted">Why this person:</span> ${c.why}${c.confidence ? html` <span class="mono muted" style="font-size:12px">· Hunter ${c.confidence}%</span>` : ""}</p>` : ""}
            <p style="margin-top:12px;display:flex;gap:10px;align-items:center">${ring(d.fit || [], { size: 30, label: false })}<a href="/companies/${encodeURIComponent(d.domain)}" style="font-size:13.5px">${d.company}: ICP evidence</a></p></section>
          <section class="card"><h3 class="h3" style="margin-bottom:12px">Two pain points ${info("hook")}</h3>
            ${(d.pains || []).map((p, i) => html`<div class="pain"><span class="pain-n">PAIN ${i + 1}</span><p style="font-size:14px">${p.pain}</p>
              ${p.evidence_quote ? html`<blockquote>“${p.evidence_quote}”</blockquote>` : ""}${sourceChip(p.url)}</div>`)}</section>
          ${d.hook ? html`<section class="card"><h3 class="h3">Hook source</h3><p style="margin-top:8px"><mark class="hl">${d.hook}</mark></p>
            ${hookSrc ? html`<p style="margin-top:8px">${sourceChip(hookSrc.url || hookSrc.source_url)}</p>` : ""}</section>` : ""}
        </aside>
      </div></div>`);
    wire();
    if (focusQueue) desk.querySelector(`.queue-item[data-i="${st.i}"]`)?.focus();
    history.replaceState({}, "", `/review?d=${encodeURIComponent(d.domain)}`);
    animate((g) => g.from(desk.querySelector("[data-mail]"), { y: 12, opacity: 0, duration: 0.4, clearProps: "all" }));
  }

  function wire() {
    desk.querySelectorAll(".queue-item").forEach((b) => b.addEventListener("click", () => { st.i = +b.dataset.i; draw(); }));
    desk.querySelector("[data-approve]").addEventListener("click", (e) => approve(e.currentTarget));
    desk.querySelector("[data-edit]").addEventListener("click", startEdit);
    desk.querySelector("[data-reject]").addEventListener("click", startReject);
  }

  // ---- edit mode with a live edit % meter -------------------------------------------------
  function startEdit() {
    const d = cur();
    if (!d || st.mode === "edit") return;
    st.mode = "edit";
    const main = desk.querySelector("[data-mail-main]");
    render(main, html`<div class="mail-edit">
      <label class="field"><span class="label">Subject <span class="mono" data-words></span></span><input class="input" data-subj value="${d.subject || ""}"></label>
      <label class="field"><span class="label">Body</span><textarea class="textarea" data-body>${d.body || ""}</textarea></label></div>`);
    render(desk.querySelector("[data-actions]"), html`
      <button class="btn primary big" type="button" data-send-edit>${icon("plane")} Send edited</button>
      <button class="btn" type="button" data-cancel>Cancel <kbd>Esc</kbd></button><span class="spacer"></span>
      <div class="meter" role="meter" aria-label="Edit percent" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" data-meter>
        <div class="meter-top"><span>${term("edit", "Edit %")}</span><b data-pct>0%</b></div><div class="meter-bar"><i data-bar></i></div></div>`);
    const subj = desk.querySelector("[data-subj]"), body = desk.querySelector("[data-body]");
    const words = desk.querySelector("[data-words]");
    let t;
    const measure = () => {
      const n = fmt.words(subj.value);
      words.textContent = `${n}/7 words`;
      words.style.color = n > 7 ? "var(--nogo)" : "";
      clearTimeout(t);
      t = setTimeout(async () => {
        try {
          const r = await api("/api/edit-ratio", { method: "POST", body: { original: `${d.original_subject}\n${d.original_body}`, final: `${subj.value}\n${body.value}` } });
          const pct = Math.round(r.edit_ratio * 100);
          desk.querySelector("[data-pct]").textContent = `${pct}%`;
          const bar = desk.querySelector("[data-bar]");
          bar.style.width = `${Math.min(100, pct)}%`;
          bar.classList.toggle("over", pct > 50);
          desk.querySelector("[data-meter]").setAttribute("aria-valuenow", pct);
        } catch { /* the meter just pauses */ }
      }, 120);
    };
    subj.addEventListener("input", measure);
    body.addEventListener("input", measure);
    measure();
    body.focus();
    body.setSelectionRange(0, 0);
    desk.querySelector("[data-cancel]").addEventListener("click", () => draw());
    desk.querySelector("[data-send-edit]").addEventListener("click", (e) => {
      if (fmt.words(subj.value) > 7) { shake(subj); toast("Keep the subject under 8 words.", { kind: "warn" }); subj.focus(); return; }
      if (!body.value.trim()) { shake(body); toast("The email body is empty.", { kind: "warn" }); return; }
      queueSend(e.currentTarget, { action: "edited", subject: subj.value, body: body.value });
    });
  }

  // ---- reject with a reason --------------------------------------------------------------------
  function startReject() {
    if (!cur() || st.mode === "reject") return;
    st.mode = "reject";
    const box = desk.querySelector("[data-reject-box]");
    box.hidden = false;
    render(box, html`<div class="reject-box"><label class="sr" for="rr">Reason for rejecting</label>
      <input id="rr" class="input" data-reason placeholder="Why? e.g. wrong person, weak hook" autocomplete="off">
      <button class="btn danger" type="button" data-confirm>Reject draft</button><button class="btn ghost" type="button" data-cancel-r>Cancel</button></div>`);
    const input = box.querySelector("[data-reason]");
    input.focus();
    const go = async () => {
      if (!input.value.trim()) { shake(input); input.focus(); return; }
      const d = cur();
      try {
        await api(`/api/review/${encodeURIComponent(d.domain)}/reject`, { method: "POST", body: { reason: input.value } });
      } catch (e) { toast(e.message, { kind: "err" }); return; }
      const card = desk.querySelector("[data-mail]");
      shake(card);
      card.classList.add("dim");
      await leave(card, -1);
      st.queue.splice(st.i, 1);
      st.lastReject = { item: d, index: st.i, until: Date.now() + UNDO_MS };
      draw();
      toast(`Rejected the ${d.company} draft.`, { kind: "warn", action: "Undo", ms: UNDO_MS, onAction: undo });
    };
    box.querySelector("[data-confirm]").addEventListener("click", go);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); if (e.key === "Escape") draw(); });
    box.querySelector("[data-cancel-r]").addEventListener("click", () => draw());
  }

  async function leave(card, dir = 1) {
    if (!motionOK()) return;
    await card.animate([{ transform: "none", opacity: 1 }, { transform: `translateX(${dir * 48}px)`, opacity: 0 }], { duration: 320, easing: "cubic-bezier(.22,1,.36,1)", fill: "forwards" }).finished;
  }

  // ---- approve: the card leaves, the send waits 8 seconds so Undo is real ----------------------
  function approve(btn) {
    const d = cur();
    if (!d?.body) return;
    queueSend(btn, { action: "approved" });
  }

  async function queueSend(btn, payload) {
    if (st.pending) st.pending.toast.flush(); // only one send waits at a time
    const d = cur();
    const dry = dryRun.get();
    burst(btn);
    await leave(desk.querySelector("[data-mail]"));
    const index = st.i;
    st.queue.splice(index, 1);
    const pending = { item: d, index, body: { ...payload, dry_run: dry } };
    st.pending = pending;
    draw();
    pending.toast = toast(dry ? `Dry run for ${d.company} in 8 s.` : `Sending ${d.company} to your test inbox in 8 s.`, {
      kind: "ok", action: "Undo", ms: UNDO_MS, onAction: undo, onExpire: () => send(pending),
    });
  }

  async function send(p, { keepalive = false } = {}) {
    if (st.pending === p) st.pending = null;
    const url = `/api/review/${encodeURIComponent(p.item.domain)}/send`;
    if (keepalive) { fetch(url, { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" }, body: JSON.stringify(p.body) }); return; }
    try {
      const r = await api(url, { method: "POST", body: p.body });
      if (r.result === "sent") toast(`Sent to your test inbox. Edit ${fmt.pct(r.draft?.edit_ratio)}.`, { kind: "ok" });
      else if (r.result === "dry_run") toast("Dry run: nothing was sent. The draft is back in the queue.", { kind: "info" });
      else toast(`Not sent: ${r.message}`, { kind: "err", ms: 10000 });
      if (r.result !== "sent") { st.queue = await api("/api/review"); if (st.mode === "view") draw(); }
    } catch (e) {
      toast(`Not sent: ${e.message}`, { kind: "err", ms: 10000 });
      st.queue.splice(Math.min(p.index, st.queue.length), 0, p.item);
      draw();
    }
    ctx.refreshCounts();
  }

  async function undo() {
    if (st.pending) {
      const p = st.pending;
      st.pending = null;
      p.toast.close();
      st.queue.splice(Math.min(p.index, st.queue.length), 0, p.item);
      st.i = Math.min(p.index, st.queue.length - 1);
      draw();
      toast("Undone. Nothing was sent.", { kind: "info", ms: 2500 });
      return;
    }
    const r = st.lastReject;
    if (r && Date.now() < r.until) {
      st.lastReject = null;
      try { await api(`/api/review/${encodeURIComponent(r.item.domain)}/undo-reject`, { method: "POST" }); } catch (e) { toast(e.message, { kind: "err" }); return; }
      st.queue.splice(Math.min(r.index, st.queue.length), 0, r.item);
      st.i = Math.min(r.index, st.queue.length - 1);
      draw();
      toast("Rejection undone.", { kind: "info", ms: 2500 });
    }
  }

  // ---- keyboard ---------------------------------------------------------------------------------
  const onKey = (e) => {
    const typing = e.target.closest?.("input, textarea, select");
    if (e.key === "Escape" && st.mode !== "view") { e.preventDefault(); draw(); return; }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && st.mode === "edit") desk.querySelector("[data-send-edit]")?.click();
      return;
    }
    const k = e.key.toLowerCase();
    if (k === "j" || k === "k") {
      if (!st.queue.length) return;
      st.i = (st.i + (k === "j" ? 1 : -1) + st.queue.length) % st.queue.length;
      draw({ focusQueue: true });
    } else if (k === "a" && st.mode === "view") desk.querySelector("[data-approve]")?.click();
    else if (k === "e") { e.preventDefault(); startEdit(); }
    else if (k === "x") { e.preventDefault(); startReject(); }
    else if (k === "u") undo();
    else return;
    e.preventDefault();
  };
  document.addEventListener("keydown", onKey);
  // Leaving the page or closing the tab: a waiting send goes out now (the person already approved it).
  const flushOnUnload = () => { if (st.pending) send(st.pending, { keepalive: true }); };
  addEventListener("pagehide", flushOnUnload);
  ctx.cleanup.push(() => {
    document.removeEventListener("keydown", onKey);
    removeEventListener("pagehide", flushOnUnload);
    if (st.pending) { const p = st.pending; p.toast.close(); send(p); }
  });
  draw();
}
export { render_ as render };
