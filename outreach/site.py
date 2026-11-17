"""Read-only public snapshot of the latest run, for Vercel. No keys, no buttons, prospect emails hidden."""
import json
import time
from html import escape as e

from . import db
from .config import ROOT
from .send import stats

OUT = ROOT / "site" / "index.html"
COLORS = {"GO": "go", "NO-GO": "nogo", "HUMAN REVIEW": "hr"}

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e4e4e0;--go:#1a7f37;--nogo:#b42318;--hr:#9a6700;--acc:#3b5bdb}
@media (prefers-color-scheme:dark){:root{--bg:#121214;--card:#1c1c1f;--ink:#ececec;--mute:#9a9aa0;--line:#2e2e33;--go:#4ac26b;--nogo:#ff7b72;--hr:#d4a72c;--acc:#7c95ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:28px 16px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 10px}
.mute{color:var(--mute)}.banner{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--hr);padding:10px 14px;border-radius:8px;margin:16px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile b{display:block;font-size:24px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
.pill{display:inline-block;padding:1px 9px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.go{color:var(--go)}.nogo{color:var(--nogo)}.hr{color:var(--hr)}details summary{cursor:pointer;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13.5px}td,th{text-align:left;padding:6px 8px;border-top:1px solid var(--line);vertical-align:top}
.wrap{overflow-x:auto}pre{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;font:14px/1.5 inherit;font-family:inherit}
a{color:var(--acc)}q{font-style:italic}
"""


def _answers(con, domain):
    rows = con.execute("SELECT param_id, outcome, reason, evidence_quote, source_url FROM answers WHERE domain=?", (domain,))
    body = "".join(
        f"<tr><td>{e(r['param_id'])}</td><td>{e(r['outcome'] or '')}</td><td>{e(r['reason'] or '')}</td>"
        f"<td>{'<q>' + e(r['evidence_quote']) + '</q>' if r['evidence_quote'] else ''}</td>"
        f"<td>{'<a href=\"' + e(r['source_url']) + '\">source</a>' if r['source_url'] else ''}</td></tr>" for r in rows)
    return f"<div class=wrap><table><tr><th>ICP row</th><th>Outcome</th><th>Why</th><th>Quote</th><th>URL</th></tr>{body}</table></div>"


def build(con=None) -> str:
    con = con or db.connect()
    s = stats(con)
    companies = [dict(r) for r in con.execute("SELECT * FROM companies ORDER BY decision, domain")]
    parts = [f"<h1>Sprinto cold outreach agent</h1><p class=mute>Snapshot of the latest run, "
             f"{time.strftime('%d %b %Y')}. Read-only: nothing can be sent from this page.</p>",
             "<div class=banner>Test mode: every email goes only to the builder's own address (TEST_RECIPIENT). "
             "Prospects never receive anything.</div>",
             f"<div class=tiles><div class=tile><span class=mute>Companies checked</span><b>{len(companies)}</b></div>"
             f"<div class=tile><span class=mute>Emails sent</span><b>{s['sent']}</b></div>"
             f"<div class=tile><span class=mute>Average edit %</span><b class={'nogo' if s['avg_edit_pct'] > 50 else 'go'}>"
             f"{s['avg_edit_pct']}%</b></div><div class=tile><span class=mute>Opens</span><b>n/a</b>"
             f"<span class=mute>not measured in test mode</span></div></div>",
             "<h2>Decisions</h2>"]
    for c in companies:
        human = db.effective_decision(con, c["domain"])
        extra = f" &rarr; human: <span class='pill {COLORS.get(human, '')}'>{e(human)}</span>" if human != c["decision"] else ""
        reasons = "".join(f"<li>{e(r)}</li>" for r in json.loads(c["reasons_json"] or "[]"))
        parts.append(f"<details class=card><summary>{e(c['name'] or c['domain'])} <span class=mute>({e(c['domain'])})</span> "
                     f"<span class='pill {COLORS.get(c['decision'], '')}'>{e(c['decision'])}</span>{extra}</summary>"
                     f"<ul>{reasons}</ul>{_answers(con, c['domain'])}"
                     f"<p class=mute>Stopped because: {e(c['stop_reason'] or '')} &middot; {c['elapsed_s'] or 0:.0f}s</p></details>")
    parts.append("<h2>Emails</h2>")
    for d in con.execute("SELECT * FROM drafts ORDER BY created_at"):
        c = json.loads(d["contact_json"] or "{}")
        who = f"{c.get('first_name', '')} {c.get('last_name', '')[:1]}., {c.get('title', '')}"  # no email address
        pains = "".join(f"<li>{e(p['pain'])} <span class=mute>(evidence: <q>{e(p['evidence_quote'])}</q>)</span></li>"
                        for p in json.loads(d["pains_json"] or "[]"))
        subject, body = d["final_subject"] or d["subject"], d["final_body"] or d["body"]
        sent = (f"sent {time.strftime('%d %b %Y', time.localtime(d['sent_at']))} via Resend, edit {d['edit_ratio'] * 100:.0f}%"
                if d["status"] == "sent" else d["status"])
        parts.append(f"<div class=card><b>{e(d['domain'])}</b> <span class=mute>&middot; {e(sent)}</span>"
                     f"<p>Contact: {e(who)}</p><p>Pain points:</p><ul>{pains}</ul>"
                     f"<p><b>Subject:</b> {e(subject or '')}</p><pre>{e(body or '')}</pre></div>")
    parts.append("<h2>How it decides</h2><p>Scrape public pages (robots.txt respected) &rarr; Gemini extracts each ICP "
                 "answer with a quote that must appear on the page &rarr; code applies the ICP table (Gemini never "
                 "decides) &rarr; Hunter finds one contact &rarr; two evidence-backed pain points &rarr; a short email "
                 "checked for invented facts &rarr; a human approves &rarr; Resend sends to the test inbox only.</p>")
    html = (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,"
            f"initial-scale=1'><title>Sprinto Outreach Run</title><style>{CSS}</style></head><body><main>"
            + "".join(parts) + "</main></body></html>")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    return str(OUT)
