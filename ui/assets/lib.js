// Shared helpers: data fetching, safe HTML, formatting, icons and small reusable pieces.

export async function api(path, opts = {}) {
  const init = { headers: { "Content-Type": "application/json" }, ...opts };
  if (opts.body && typeof opts.body !== "string") init.body = JSON.stringify(opts.body);
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error("Can't reach the Outreach Desk server. Is `python run_ui.py` still running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok && res.status !== 409) throw new Error(plainError(data.detail) || `Something went wrong (HTTP ${res.status}).`);
  return data;
}
const plainError = (d) => (typeof d === "string" ? d : Array.isArray(d) ? "Some of the details are missing or not valid." : "");

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
// Tagged template: interpolations are escaped unless wrapped with raw().
export const raw = (s) => ({ __raw: String(s) });
export function html(strings, ...vals) {
  let out = "";
  strings.forEach((s, i) => {
    out += s;
    if (i < vals.length) out += flat(vals[i]);
  });
  return raw(out);
}
const flat = (v) => (v == null || v === false ? "" : Array.isArray(v) ? v.map(flat).join("") : v.__raw !== undefined ? v.__raw : esc(v));
export const render = (el, tpl) => { el.innerHTML = tpl.__raw ?? tpl; return el; };

export const fmt = {
  n: (x) => (x == null ? "—" : Number(x).toLocaleString("en-US")),
  pct: (r) => (r == null ? "—" : `${Math.round(r * 100)}%`),
  ago(ts) {
    if (!ts) return "never";
    const s = Date.now() / 1000 - ts;
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} h ago`;
    const d = Math.round(s / 86400);
    return d === 1 ? "yesterday" : `${d} days ago`;
  },
  date: (ts) => (ts ? new Date(ts * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"),
  host(u) { try { return new URL(u).host.replace(/^www\./, ""); } catch { return u || ""; } },
  initials: (s) => (s || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase(),
  words: (s) => (s || "").trim().split(/\s+/).filter(Boolean).length,
  cap: (s) => (s ? s[0].toUpperCase() + s.slice(1) : s),
};

const P = {
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  eye: '<path d="M2.5 12S6 5 12 5s9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7z"/><circle cx="12" cy="12" r="3"/>',
  plane: '<path d="M21 3 3 10.5l7 2.5 2.5 7z"/><path d="M10 13l4-4"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  back: '<path d="M19 12H5M11 18l-6-6 6-6"/>',
  play: '<path d="M7 5v14l12-7z"/>',
  stop: '<path d="M12 8v5M12 16v.01"/><circle cx="12" cy="12" r="9"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.01"/>',
  warn: '<path d="M12 3 2 20h20zM12 10v4M12 17v.01"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  doc: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
};
export const icon = (name, cls = "") => raw(`<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${P[name] || ""}</svg>`);

const DEC = {
  GO: { cls: "go", icon: "check", word: "GO" },
  "NO-GO": { cls: "nogo", icon: "x", word: "NO-GO" },
  "HUMAN REVIEW": { cls: "review", icon: "eye", word: "Human review" },
  SENT: { cls: "sent", icon: "plane", word: "Sent" },
};
export const chip = (d, extra = "") => {
  const k = DEC[d] || { cls: "", icon: "info", word: d || "—" };
  return html`<span class="chip ${k.cls} ${extra}">${icon(k.icon)}${k.word}</span>`;
};
export const OUTCOME_WORD = { qualifies: "Fits", rejects: "Rules it out", neutral: "Answered, not a fit", unanswered: "Not found", not_checked: "Not checked" };
export const outcome = (o) => html`<span class="outcome ${o}"><i aria-hidden="true"></i>${OUTCOME_WORD[o] || o}</span>`;

// ICP fit ring: seven segments, one per rule, in table order.
export function ring(fit, { size = 44, label = true, flip = "" } = {}) {
  const n = fit.length || 7, r = 15, C = 2 * Math.PI * r, gap = 2.2, seg = C / n - gap;
  const score = fit.filter((f) => f.outcome === "qualifies").length;
  const arcs = fit.map((f, i) => `<circle class="seg ${f.outcome}" cx="20" cy="20" r="${r}" stroke-dasharray="${seg} ${C - seg}" stroke-dashoffset="${-i * (C / n)}" data-seg="${i}"></circle>`).join("");
  const desc = fit.map((f) => `${f.name}: ${OUTCOME_WORD[f.outcome] || f.outcome}`).join("; ");
  return html`<span class="ring" style="--size:${size}px" role="img" aria-label="${`ICP fit ${score} of ${n}. ${desc}`}" ${flip ? raw(`data-flip-id="${esc(flip)}"`) : ""}>
    <svg viewBox="0 0 40 40">${raw(arcs)}</svg>${label ? html`<span class="ring-label" aria-hidden="true">${score}</span>` : ""}</span>`;
}

export const sourceChip = (url, kind) => {
  if (!url) return "";
  const host = fmt.host(url);
  return html`<a class="source" href="${url}" target="_blank" rel="noopener noreferrer"><span class="source-init" aria-hidden="true">${(kind || host)[0]}</span><span>${host}${new URL(url, location.href).pathname.replace(/\/$/, "")}</span><span class="sr">(opens in a new tab)</span></a>`;
};

export const TERMS = {
  icp: "ICP fit = how many of Sprinto's seven customer rules this company meets.",
  review: "Human review = the agent could not decide safely, so a person makes the call.",
  edit: "Edit % = how much of a draft the reviewer changed before sending. Under 50% means the drafts are saving time.",
  cache: "Cache hit = the company was already researched, so no new pages, AI or Hunter calls were made.",
  retries: "Retries = how many sources the agent may try for this rule before giving up.",
  confidence: "Confidence = how sure the AI was that the quote answers the question (0 to 100%).",
  hook: "Hook = the one real fact from the evidence that the email opens with.",
  dry: "Dry run = everything happens except the email actually being sent.",
  qualifyOnly: "Qualify only = research and decide, but don't spend Hunter searches or write drafts.",
  tokens: "Tokens = the amount of text sent to and from Gemini. More tokens cost more.",
  unanswered: "If unanswered = what the agent does when it can't find this fact.",
  autoReject: "Auto-reject = an answer that rules the company out on the spot.",
  sufficiency: "Sufficiency = what counts as a good enough answer.",
};
export const term = (key, text) => html`<span class="term" tabindex="0" data-tip="${TERMS[key]}">${text}</span>`;
export const info = (key) => html`<button type="button" class="info-dot" data-tip="${TERMS[key]}" aria-label="${TERMS[key]}">i</button>`;

export const skeleton = () => html`<div class="page" aria-busy="true" aria-label="Loading">
  <div class="skeleton sk-line" style="width:120px"></div><div class="skeleton sk-title"></div>
  <div class="grid"><div class="span-8"><div class="skeleton sk-block"></div></div><div class="span-4"><div class="skeleton sk-block"></div></div></div>
  <div class="skeleton sk-line"></div><div class="skeleton sk-line" style="width:70%"></div></div>`;

const EMPTY_ART = raw(`<svg viewBox="0 0 72 72" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
  <rect x="10" y="20" width="52" height="34" rx="6"/><path d="m12 23 24 17 24-17"/><circle cx="56" cy="20" r="8" fill="var(--highlight)" stroke="var(--paper)" stroke-width="3"/></svg>`);
export const empty = (title, text, action = "") => html`<div class="empty">${EMPTY_ART}<h2>${title}</h2><p>${text}</p>${action}</div>`;
export const errorState = (msg) => html`<div class="page"><div class="callout nogo" role="alert">${icon("warn")}<div><strong>That didn't load.</strong> ${msg}
  <div style="margin-top:10px"><button class="btn small" type="button" onclick="location.reload()">Try again</button></div></div></div></div>`;

// ---- toasts ------------------------------------------------------------------------------
const TOAST_ICON = { ok: "check", err: "warn", warn: "warn", info: "info" };
export function toast(text, { kind = "ok", action, onAction, ms = 5000, onExpire } = {}) {
  const box = document.querySelector(".toasts");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.setAttribute("role", kind === "err" ? "alert" : "status");
  render(el, html`${icon(TOAST_ICON[kind])}<span>${text}</span>${action ? html`<button type="button">${action}</button>` : html`<span></span>`}<i class="t-bar" aria-hidden="true"></i>`);
  box.appendChild(el);
  const bar = el.querySelector(".t-bar");
  bar.animate([{ transform: "scaleX(1)" }, { transform: "scaleX(0)" }], { duration: ms, easing: "linear", fill: "forwards" });
  el.animate([{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "none" }], { duration: 260, easing: "cubic-bezier(.22,1,.36,1)" });
  let done = false;
  const close = (expired) => {
    if (done) return;
    done = true;
    clearTimeout(timer);
    if (expired && onExpire) onExpire();
    el.animate([{ opacity: 1 }, { opacity: 0, transform: "translateY(8px)" }], { duration: 200, fill: "forwards" }).onfinish = () => el.remove();
  };
  const timer = setTimeout(() => close(true), ms);
  el.querySelector("button")?.addEventListener("click", () => { onAction?.(); close(false); });
  return { close, flush: () => close(true) };
}

// ---- tooltip (one element, follows hover and keyboard focus) --------------------------------
export function initTips() {
  const tip = document.getElementById("tip");
  const show = (t) => {
    const text = t.dataset.tip;
    if (!text) return;
    tip.textContent = text;
    tip.hidden = false;
    const r = t.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    const x = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
    const y = r.top - h - 8 < 40 ? r.bottom + 8 : r.top - h - 8;
    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
  };
  const hide = () => { tip.hidden = true; };
  for (const [on, off] of [["mouseover", "mouseout"], ["focusin", "focusout"]]) {
    document.addEventListener(on, (e) => { const t = e.target.closest?.("[data-tip]"); if (t) show(t); });
    document.addEventListener(off, (e) => { if (e.target.closest?.("[data-tip]")) hide(); });
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
  addEventListener("scroll", hide, { passive: true });
}

export async function copyText(text, btn) {
  try { await navigator.clipboard.writeText(text); } catch { /* clipboard may be blocked; still confirm visually */ }
  if (btn) {
    const old = btn.innerHTML;
    render(btn, icon("check"));
    btn.setAttribute("aria-label", "Copied");
    btn.animate([{ transform: "scale(.7)" }, { transform: "scale(1.1)" }, { transform: "scale(1)" }], { duration: 320 });
    setTimeout(() => { btn.innerHTML = old; btn.setAttribute("aria-label", "Copy quote"); }, 1400);
  }
  toast("Quote copied.", { kind: "ok", ms: 1800 });
}

export const dryRun = {
  get: () => { try { return localStorage.getItem("od-dry") === "1"; } catch { return false; } },
  set: (v) => { try { localStorage.setItem("od-dry", v ? "1" : "0"); } catch { /* private mode */ } },
};
