"""Outreach Desk: a thin JSON layer over the existing functions, plus the static front end.

Nothing here decides, scrapes or writes emails: it reads the same SQLite database and calls the same
functions the CLI uses (qualify_company, draft_for, review). Run: python run_ui.py
"""
import asyncio
import json
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db
from .agent import qualify_company
from .config import ROOT, env
from .contact import load_rules
from .icp import load_icp
from .send import RecipientLocked, edit_ratio, review, stats
from .writer import draft_for

UI = ROOT / "ui"
NODE = ROOT / "node_modules"
ROUTES = re.compile(r"^/(companies(/[^/]+)?|review|quality|icp|runs|about)?/?$")
# Assumed Gemini Flash list prices (USD per million tokens). An estimate only: edit if your price differs.
PRICE_IN, PRICE_OUT = 0.30, 2.50
BROWSER_COST_UNITS = 12  # a Playwright page costs 10 to 15 times a plain HTML fetch

app = FastAPI(title="Outreach Desk", docs_url=None, redoc_url=None)
RUNS: dict[str, dict] = {}  # runs started from the UI in this session


def con():
    return db.connect(app.state.db_path) if hasattr(app.state, "db_path") else db.connect()


def _j(s, default=None):
    try:
        return json.loads(s) if s else default
    except ValueError:
        return default


def _mask(addr: str) -> str:
    if "@" not in addr:
        return ""
    user, host = addr.split("@", 1)
    return f"{user[:2]}…@{host}"


# --- read models --------------------------------------------------------------------------

def _fit(c, domain: str, params) -> list[dict]:
    rows = {r["param_id"]: dict(r) for r in c.execute("SELECT * FROM answers WHERE domain=?", (domain,))}
    return [{"id": p.id, "name": p.name, "outcome": rows.get(p.id, {}).get("outcome") or "not_checked"} for p in params]


def _answer_value(c, domain, pid):
    r = c.execute("SELECT answer_json, outcome FROM answers WHERE domain=? AND param_id=?", (domain, pid)).fetchone()
    a = _j(r["answer_json"]) if r else None
    if not a:
        return None
    if a.get("number_min") is not None or a.get("number_max") is not None:
        lo, hi = a.get("number_min"), a.get("number_max")
        return f"{lo}" if lo == hi or hi is None else f"{lo or '?'}–{hi}"
    v = a.get("value")
    return v.replace("_", " ") if isinstance(v, str) else v


def company_row(c, row, params) -> dict:
    d = row["domain"]
    draft = db.get_draft(c, d)
    fit = _fit(c, d, params)
    pages = c.execute("SELECT COUNT(*) FROM pages WHERE domain=? AND status='ok'", (d,)).fetchone()[0]
    return {
        "domain": d, "name": row["name"] or d, "decision": row["decision"],
        "human": db.effective_decision(c, d), "fit": fit,
        "fit_score": sum(f["outcome"] == "qualifies" for f in fit),
        "funding": _answer_value(c, d, "funding_stage"), "headcount": _answer_value(c, d, "employee_count"),
        "cloud": _answer_value(c, d, "cloud_stack"), "sources": pages,
        "processed_at": row["processed_at"], "elapsed_s": row["elapsed_s"], "stop_reason": row["stop_reason"],
        "draft_status": draft["status"] if draft else None,
        "one_liner": (_j(row["profile_json"], {}) or {}).get("one_liner"),
    }


@app.get("/api/meta")
def meta():
    return {"test_recipient": _mask(env("TEST_RECIPIENT")), "sender": "Sprinto Outreach (test) <onboarding@resend.dev>",
            "model": env("GEMINI_MODEL") or None, "hunter": bool(env("HUNTER_API_KEY")),
            "lusha": bool(env("LUSHA_API_KEY")), "resend": bool(env("RESEND_API_KEY"))}


@app.get("/api/summary")
def summary():
    c, params = con(), load_icp().parameters
    comps = [dict(r) for r in c.execute("SELECT * FROM companies")]
    drafts = [dict(r) for r in c.execute("SELECT * FROM drafts")]
    human = {x["domain"]: db.effective_decision(c, x["domain"]) for x in comps}
    scraped = sum(1 for x in comps if c.execute("SELECT 1 FROM pages WHERE domain=? AND status='ok'", (x["domain"],)).fetchone())
    funnel = [
        {"key": "domains", "label": "Domains", "count": len(comps)},
        {"key": "scraped", "label": "Scraped", "count": scraped},
        {"key": "qualified", "label": "Qualified", "count": sum(v == "GO" for v in human.values())},
        {"key": "contact", "label": "Contact found", "count": sum(1 for d in drafts if _j(d["contact_json"]))},
        {"key": "drafted", "label": "Drafted", "count": sum(1 for d in drafts if d["body"])},
        {"key": "approved", "label": "Approved", "count": sum(1 for d in drafts if d["review_action"] in ("approved", "edited"))},
        {"key": "sent", "label": "Sent", "count": sum(1 for d in drafts if d["status"] == "sent")},
    ]
    to_review = sum(1 for d in drafts if d["status"] in ("draft", "human_review"))
    needs_call = sum(1 for x in comps if x["decision"] == "HUMAN REVIEW" and human[x["domain"]] == "HUMAN REVIEW")
    last = max((x["processed_at"] or 0 for x in comps), default=0)
    decisions = {k: sum(1 for x in comps if x["decision"] == k) for k in ("GO", "NO-GO", "HUMAN REVIEW")}
    return {"funnel": funnel, "drafts_to_review": to_review, "companies_to_decide": needs_call,
            "decisions": decisions, "last_run_at": last or None, "stats": stats(c),
            "running": [r["id"] for r in RUNS.values() if not r["done"]], "params": len(params)}


@app.get("/api/companies")
def companies():
    c, params = con(), load_icp().parameters
    return [company_row(c, r, params) for r in c.execute("SELECT * FROM companies ORDER BY processed_at DESC")]


def _timeline(c, domain: str) -> list[dict]:
    """The agent loop for the latest research run of this domain (cache hits are shown as one step)."""
    rows = [dict(r) for r in c.execute("SELECT id, event, ts FROM loop_log WHERE domain=? ORDER BY id", (domain,))]
    start = 0
    for i, r in enumerate(rows):  # latest run starts at the last fresh "fetched home" before the stop line
        if r["event"].startswith("fetched home") or r["event"].startswith("homepage"):
            start = i
    run = rows[start:] if rows else []
    if rows and rows[-1]["event"].startswith("cache hit"):
        run = [r for r in run if not r["event"].startswith("cache hit")] + [rows[-1]]
    tokens = {r["purpose"]: (r["tokens_in"] or 0) + (r["tokens_out"] or 0)
              for r in c.execute("SELECT purpose, SUM(tokens_in) tokens_in, SUM(tokens_out) tokens_out FROM llm_calls "
                                 "WHERE domain=? GROUP BY purpose", (domain,))}
    out = []
    for r in run:
        e = r["event"]
        m = re.match(r"fetched (\w+) (\S+) via (\w+): (\w+)\s*(.*)", e)
        if m:
            out.append({"kind": "fetch", "page": m[1], "url": m[2], "method": m[3], "status": m[4],
                        "detail": m[5].strip(), "ts": r["ts"]})
            continue
        m = re.match(r"(\w+) from (\w+): (\w+) \((.*)\)$", e)
        if m:
            out.append({"kind": "answer", "param": m[1], "source": m[2], "outcome": m[3], "detail": m[4],
                        "tokens": tokens.get(f"extract:{m[1]}"), "ts": r["ts"]})
            continue
        kind = "cache" if e.startswith("cache hit") else "stop" if e.startswith("loop stopped") else "note"
        out.append({"kind": kind, "detail": e, "ts": r["ts"]})
    return out


@app.get("/api/companies/{domain}")
def company(domain: str):
    c, icp = con(), load_icp()
    row = c.execute("SELECT * FROM companies WHERE domain=?", (domain,)).fetchone()
    if not row:
        raise HTTPException(404, f"No company called {domain} yet. Run the agent on it first.")
    answers = {r["param_id"]: dict(r) for r in c.execute("SELECT * FROM answers WHERE domain=?", (domain,))}
    scorecard = []
    for p in icp.parameters:
        a = answers.get(p.id, {})
        aj = _j(a.get("answer_json"), {}) or {}
        scorecard.append({"id": p.id, "name": p.name, "rule": p.qualifying_answer, "weight": p.weight,
                          "outcome": a.get("outcome") or "not_checked", "reason": a.get("reason"),
                          "answer": _answer_value(c, domain, p.id), "confidence": aj.get("confidence"),
                          "attempts": a.get("attempts") or 0, "retries": p.retries,
                          "quote": a.get("evidence_quote"), "url": a.get("source_url"), "source_kind": aj.get("source_kind"),
                          "error": a.get("error")})
    override = c.execute("SELECT decision, reason, ts FROM overrides WHERE domain=?", (domain,)).fetchone()
    tok = c.execute("SELECT COUNT(*), COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0) FROM llm_calls WHERE domain=?",
                    (domain,)).fetchone()
    meth = dict(c.execute("SELECT method, COUNT(*) FROM pages WHERE domain=? GROUP BY method", (domain,)).fetchall())
    stopped_early = row["decision"] == "NO-GO" and any(s["outcome"] == "rejects" for s in scorecard)
    return company_row(c, row, icp.parameters) | {
        "profile": _j(row["profile_json"], {}), "reasons": _j(row["reasons_json"], []), "scorecard": scorecard,
        "override": dict(override) if override else None, "timeline": _timeline(c, domain),
        "stopped_early": stopped_early, "draft": _draft_out(c, domain),
        "cost": {"gemini_calls": tok[0], "tokens_in": tok[1], "tokens_out": tok[2], "methods": meth}}


class Decision(BaseModel):
    decision: str
    reason: str


@app.post("/api/companies/{domain}/decision")
def decide(domain: str, body: Decision):
    """A person's GO / NO-GO on a HUMAN REVIEW company. GO also finds the contact and drafts (same as the CLI)."""
    if body.decision not in ("GO", "NO-GO") or not body.reason.strip():
        raise HTTPException(400, "Pick GO or NO-GO and write a short reason.")
    c = con()
    db.set_override(c, domain, body.decision, body.reason.strip())
    if body.decision == "GO":
        from .llm import Gemini
        dr = draft_for(c, domain, Gemini(c), load_rules())
        return {"ok": True, "draft_status": dr["status"], "notes": dr["notes"]}
    return {"ok": True}


# --- review -------------------------------------------------------------------------------

def _draft_out(c, domain: str) -> dict | None:
    d = db.get_draft(c, domain)
    if not d:
        return None
    comp = db.cached_company(c, domain) or {}
    contact = _j(d["contact_json"], {}) or {}
    contact.pop("email", None)  # the prospect's address never reaches the browser; sends go to TEST_RECIPIENT
    return {"domain": domain, "company": comp.get("name") or domain, "status": d["status"], "notes": d["notes"],
            "subject": d["final_subject"] or d["subject"], "body": d["final_body"] or d["body"],
            "original_subject": d["subject"], "original_body": d["body"], "hook": d["hook"],
            "contact": contact, "pains": _j(d["pains_json"], []), "review_action": d["review_action"],
            "edit_ratio": d["edit_ratio"], "reject_reason": d["reject_reason"], "sent_at": d["sent_at"],
            "resend_id": d["resend_id"], "created_at": d["created_at"]}


@app.get("/api/review")
def review_queue():
    c, params = con(), load_icp().parameters
    out = []
    for r in c.execute("SELECT domain FROM drafts WHERE status IN ('draft','human_review') ORDER BY created_at"):
        d = _draft_out(c, r["domain"])
        row = c.execute("SELECT * FROM companies WHERE domain=?", (r["domain"],)).fetchone()
        d["fit"] = _fit(c, r["domain"], params)
        d["decision"] = row["decision"] if row else None
        d["evidence"] = [dict(a) for a in c.execute(
            "SELECT param_id, outcome, evidence_quote, source_url FROM answers WHERE domain=? AND outcome='qualifies'",
            (r["domain"],))]
        out.append(d)
    return out


class SendBody(BaseModel):
    action: str = "approved"  # approved | edited
    subject: str = ""
    body: str = ""
    dry_run: bool = False


@app.post("/api/review/{domain}/send")
def send(domain: str, b: SendBody):
    c = con()
    if b.action not in ("approved", "edited"):
        raise HTTPException(400, "action must be approved or edited")
    if not db.get_draft(c, domain):
        raise HTTPException(404, "No draft for that company.")
    try:
        result = review(c, domain, b.action, b.subject, b.body, dry_run=b.dry_run)
    except RecipientLocked as e:
        return JSONResponse({"ok": False, "result": "locked", "message": str(e)}, status_code=409)
    if result.startswith("human review"):
        return {"ok": False, "result": "human_review", "message": result.split(": ", 1)[1]}
    return {"ok": True, "result": "dry_run" if result == "dry-run" else "sent", "message": result,
            "draft": _draft_out(c, domain)}


class RejectBody(BaseModel):
    reason: str


@app.post("/api/review/{domain}/reject")
def reject(domain: str, b: RejectBody):
    c = con()
    if not b.reason.strip():
        raise HTTPException(400, "Write a short reason so the next draft can be better.")
    if not db.get_draft(c, domain):
        raise HTTPException(404, "No draft for that company.")
    review(c, domain, "rejected", reason=b.reason.strip())
    return {"ok": True}


@app.post("/api/review/{domain}/undo-reject")
def undo_reject(domain: str):
    c = con()
    d = db.get_draft(c, domain)
    if not d or d["status"] != "rejected":
        raise HTTPException(409, "Only a rejected draft can be brought back.")
    db.update_draft(c, domain, status="draft", review_action=None, reject_reason=None)
    return {"ok": True}


class Ratio(BaseModel):
    original: str
    final: str


@app.post("/api/edit-ratio")
def ratio(b: Ratio):
    return {"edit_ratio": edit_ratio(b.original, b.final)}  # the same formula the send records


@app.get("/api/quality")
def quality():
    c = con()
    hist = [dict(r) for r in c.execute(
        "SELECT d.domain, c.name, d.status, d.review_action, d.edit_ratio, d.sent_at, d.reject_reason "
        "FROM drafts d LEFT JOIN companies c USING(domain) WHERE d.review_action IS NOT NULL ORDER BY d.sent_at")]
    return {"stats": stats(c), "history": hist,
            "rejected": sum(1 for h in hist if h["review_action"] == "rejected")}


@app.get("/api/icp")
def icp_table():
    icp = load_icp()
    return {"limits": icp.limits.model_dump(), "parameters": [
        {k: getattr(p, k) for k in ("id", "name", "qualifying_answer", "where_to_look", "sufficiency", "retries",
                                     "if_unanswered", "auto_reject", "weight")} for p in icp.parameters]}


# --- runs ---------------------------------------------------------------------------------

def _segments(c) -> list[dict]:
    """Group the loop log into runs: a gap of more than 15 minutes starts a new run."""
    rows = [dict(r) for r in c.execute("SELECT domain, event, ts FROM loop_log ORDER BY id")]
    segs, cur = [], None
    for r in rows:
        if not cur or r["ts"] - cur["end"] > 900:
            cur = {"start": r["ts"], "end": r["ts"], "events": []}
            segs.append(cur)
        cur["end"] = r["ts"]
        cur["events"].append(r)
    return segs


@app.get("/api/runs")
def runs():
    c = con()
    out = []
    for s in reversed(_segments(c)):
        ev = s["events"]
        domains = sorted({e["domain"] for e in ev if e["domain"]})
        hits = [e["domain"] for e in ev if e["event"].startswith("cache hit")]
        methods = {}
        for e in ev:
            m = re.match(r"fetched \w+ \S+ via (\w+)", e["event"])
            if m:
                methods[m[1]] = methods.get(m[1], 0) + 1
        t = c.execute("SELECT COUNT(*), COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0) FROM llm_calls "
                      "WHERE ts BETWEEN ? AND ? AND purpose != 'key-check'", (s["start"] - 1, s["end"] + 120)).fetchone()
        failures = [e for e in ev if re.search(r": (blocked|error|js_failed)|ReadTimeout|crashed|LLMDown|unavailable", e["event"])]
        out.append({"start": s["start"], "end": s["end"], "companies": len(domains), "domains": domains,
                    "cache_hits": len(hits), "gemini_calls": t[0], "tokens_in": t[1], "tokens_out": t[2],
                    "methods": methods, "failures": len(failures),
                    "failure_samples": [f"{f['domain']}: {f['event']}" for f in failures[:4]],
                    "cost_usd": round(t[1] / 1e6 * PRICE_IN + t[2] / 1e6 * PRICE_OUT, 4),
                    "fetch_units": sum(n * (BROWSER_COST_UNITS if k == "browser" else 1) for k, n in methods.items())})
    saved = 0
    for r in c.execute("SELECT domain, COUNT(*) n FROM loop_log WHERE event LIKE 'cache hit%' GROUP BY domain"):
        per = c.execute("SELECT COUNT(*) FROM llm_calls WHERE domain=? AND (purpose LIKE 'extract:%' OR purpose='profile')",
                        (r["domain"],)).fetchone()[0]
        pages = c.execute("SELECT COUNT(*) FROM pages WHERE domain=?", (r["domain"],)).fetchone()[0]
        saved += r["n"] * (per + pages)
    return {"runs": out, "cache_saved_calls": saved, "price": {"in": PRICE_IN, "out": PRICE_OUT}}


class RunBody(BaseModel):
    domains: list[str]
    qualify_only: bool = False


def _run_worker(run: dict, db_path):
    """The same loop as `outreach run`: qualify each domain, draft the GO ones (unless qualify_only)."""
    from .fetcher import Fetcher
    from .llm import Gemini
    c = db.connect(db_path) if db_path else db.connect()
    try:
        icp = load_icp()
        llm, fetcher, rules = Gemini(c), Fetcher(c, icp.keywords), load_rules()
        if not llm.model:
            raise RuntimeError("GEMINI_MODEL is empty. Run: uv run outreach models")
        for d in run["domains"]:
            run["current"] = d
            res = qualify_company(d, icp, c, llm, fetcher)
            item = {"domain": res["domain"], "decision": res["decision"], "cached": res.get("cached", False),
                    "stop_reason": res.get("stop_reason")}
            if not run["qualify_only"] and db.effective_decision(c, res["domain"]) == "GO":
                run["events"].append({"type": "step", "domain": res["domain"], "text": "finding the contact and writing the draft"})
                dr = draft_for(c, res["domain"], llm, rules)
                item["draft"] = dr["status"]
            run["results"].append(item)
            run["events"].append({"type": "result", **item})
    except Exception as e:  # shown to the person in plain words, never as a stack trace
        run["error"] = str(e) or type(e).__name__
    finally:
        run["done"] = True
        run["current"] = None


def _clean_domains(raw: list[str]) -> list[str]:
    out = []
    for line in raw:
        for part in re.split(r"[\s,;]+", line):
            p = re.sub(r"^https?://", "", part.strip().lower()).split("/")[0].removeprefix("www.")
            if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", p) and p not in out:
                out.append(p)
    return out


@app.post("/api/runs")
def start_run(b: RunBody):
    domains = _clean_domains(b.domains)
    if not domains:
        raise HTTPException(400, "Add at least one domain, like acme.com.")
    if any(not r["done"] for r in RUNS.values()):
        raise HTTPException(409, "A run is already going. Wait for it to finish.")
    rid = uuid.uuid4().hex[:8]
    c = con()
    start_id = c.execute("SELECT COALESCE(MAX(id),0) FROM loop_log").fetchone()[0]
    run = {"id": rid, "domains": domains[:25], "qualify_only": b.qualify_only, "events": [], "results": [],
           "done": False, "error": None, "current": None, "start_id": start_id, "started": time.time()}
    RUNS[rid] = run
    threading.Thread(target=_run_worker, args=(run, getattr(app.state, "db_path", None)), daemon=True).start()
    return {"id": rid, "domains": run["domains"]}


@app.get("/api/runs/{rid}/stream")
async def run_stream(rid: str, request: Request):
    """Server-sent events: each agent step from the loop log, then each result, then 'done'."""
    run = RUNS.get(rid)
    if not run:
        raise HTTPException(404, "That run is not known (the server may have restarted).")

    async def gen():
        last_id, sent = run["start_id"], 0
        yield f"event: start\ndata: {json.dumps({'domains': run['domains']})}\n\n"
        c = con()
        while True:
            if await request.is_disconnected():
                return
            rows = c.execute("SELECT id, domain, event FROM loop_log WHERE id>? ORDER BY id", (last_id,)).fetchall()
            for r in rows:
                last_id = r["id"]
                if r["domain"] in run["domains"]:
                    yield f"event: step\ndata: {json.dumps({'domain': r['domain'], 'text': r['event']})}\n\n"
            while sent < len(run["events"]):
                ev = run["events"][sent]
                sent += 1
                yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
            if run["done"] and not rows:
                yield f"event: done\ndata: {json.dumps({'error': run['error'], 'results': run['results']})}\n\n"
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# --- static front end ---------------------------------------------------------------------

app.mount("/vendor/gsap", StaticFiles(directory=NODE / "gsap" / "dist", check_dir=False), name="gsap")
app.mount("/vendor/fonts/instrument-serif", StaticFiles(directory=NODE / "@fontsource" / "instrument-serif" / "files", check_dir=False))
app.mount("/vendor/fonts/inter", StaticFiles(directory=NODE / "@fontsource-variable" / "inter" / "files", check_dir=False))
app.mount("/vendor/fonts/jetbrains-mono", StaticFiles(directory=NODE / "@fontsource-variable" / "jetbrains-mono" / "files", check_dir=False))
app.mount("/assets", StaticFiles(directory=UI / "assets", check_dir=False), name="assets")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith("/api/"):
        detail = getattr(exc, "detail", "Not found")
        return JSONResponse({"detail": detail}, status_code=404)
    return FileResponse(UI / "index.html", status_code=404)  # the designed 404 page


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if ROUTES.match("/" + path):
        return FileResponse(UI / "index.html", headers={"Cache-Control": "no-cache"})
    raise HTTPException(404)
