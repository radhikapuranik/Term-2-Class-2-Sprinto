"""SQLite storage: the cache and the evidence trail for every decision."""
import json
import sqlite3
import time
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    domain TEXT PRIMARY KEY,
    name TEXT,
    profile_json TEXT,
    decision TEXT,
    reasons_json TEXT,
    processed_at REAL,
    elapsed_s REAL,
    stop_reason TEXT
);
CREATE TABLE IF NOT EXISTS pages (
    url TEXT PRIMARY KEY,
    domain TEXT,
    page_type TEXT,
    method TEXT,          -- http | browser | api | rss
    status TEXT,          -- ok | blocked | error | js_failed
    clean_text TEXT,
    raw_chars INTEGER,
    error TEXT,
    fetched_at REAL
);
CREATE TABLE IF NOT EXISTS api_cache (
    key TEXT PRIMARY KEY, -- e.g. hunter:acme.com
    response_json TEXT,
    fetched_at REAL
);
CREATE TABLE IF NOT EXISTS answers (
    domain TEXT,
    param_id TEXT,
    outcome TEXT,
    reason TEXT,
    answer_json TEXT,
    evidence_quote TEXT,
    source_url TEXT,
    attempts INTEGER,
    error TEXT,
    PRIMARY KEY (domain, param_id)
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT, purpose TEXT, model TEXT,
    tokens_in INTEGER, tokens_out INTEGER, ok INTEGER, error TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS drafts (
    domain TEXT PRIMARY KEY,
    contact_json TEXT,     -- the one point of contact (name, title, work email, confidence, why)
    pains_json TEXT,       -- two pain points, each with its evidence
    subject TEXT, body TEXT, hook TEXT,
    status TEXT,           -- draft | human_review | sent | rejected
    notes TEXT,            -- validation problems or why it needs a human
    final_subject TEXT, final_body TEXT,
    edit_ratio REAL,       -- 0 = sent as drafted, 1 = fully rewritten
    review_action TEXT,    -- approved | edited | rejected
    reject_reason TEXT,
    created_at REAL, sent_at REAL
);
CREATE TABLE IF NOT EXISTS overrides (
    domain TEXT PRIMARY KEY, decision TEXT, reason TEXT, ts REAL  -- a human's call on a HUMAN REVIEW company
);
CREATE TABLE IF NOT EXISTS loop_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT, event TEXT, ts REAL
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# --- cache: companies -------------------------------------------------------

def cached_company(con, domain: str) -> dict | None:
    """A domain counts as cached once it has a stored decision."""
    row = con.execute("SELECT * FROM companies WHERE domain=? AND decision IS NOT NULL", (domain,)).fetchone()
    return dict(row) if row else None


def clear_company(con, domain: str) -> None:
    """Used by --refresh: forget the decision and pages, keep paid API caches (Hunter, Lusha)."""
    for table in ("companies", "answers", "pages"):
        con.execute(f"DELETE FROM {table} WHERE domain=?", (domain,))
    con.execute("DELETE FROM api_cache WHERE key=?", (f"links:{domain}",))
    con.commit()


def save_company(con, domain, name, profile, decision, reasons, elapsed, stop_reason):
    con.execute(
        "INSERT OR REPLACE INTO companies VALUES (?,?,?,?,?,?,?,?)",
        (domain, name, json.dumps(profile), decision, json.dumps(reasons), time.time(), elapsed, stop_reason),
    )
    con.commit()


def save_answer(con, domain, pid, r: dict):
    con.execute(
        "INSERT OR REPLACE INTO answers VALUES (?,?,?,?,?,?,?,?,?)",
        (domain, pid, r["outcome"], r["reason"], json.dumps(r.get("answer")), r.get("quote", ""),
         r.get("url", ""), r.get("attempts", 0), r.get("error")),
    )
    con.commit()


# --- cache: pages and API responses ----------------------------------------

def cached_page(con, url: str) -> dict | None:
    row = con.execute("SELECT * FROM pages WHERE url=?", (url,)).fetchone()
    return dict(row) if row else None


def save_page(con, url, domain, page_type, method, status, clean_text, raw_chars, error=None):
    con.execute(
        "INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?,?,?,?)",
        (url, domain, page_type, method, status, clean_text, raw_chars, error, time.time()),
    )
    con.commit()


def cached_api(con, key: str):
    row = con.execute("SELECT response_json FROM api_cache WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def save_api(con, key: str, response) -> None:
    con.execute("INSERT OR REPLACE INTO api_cache VALUES (?,?,?)", (key, json.dumps(response), time.time()))
    con.commit()


# --- drafts and human decisions ------------------------------------------------

def get_draft(con, domain: str) -> dict | None:
    row = con.execute("SELECT * FROM drafts WHERE domain=?", (domain,)).fetchone()
    return dict(row) if row else None


def save_draft(con, domain, contact, pains, subject, body, hook, status, notes):
    con.execute(
        "INSERT OR REPLACE INTO drafts (domain, contact_json, pains_json, subject, body, hook, status, notes, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (domain, json.dumps(contact), json.dumps(pains), subject, body, hook, status, notes, time.time()),
    )
    con.commit()


def update_draft(con, domain, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    con.execute(f"UPDATE drafts SET {cols} WHERE domain=?", (*fields.values(), domain))
    con.commit()


def set_override(con, domain, decision, reason) -> None:
    con.execute("INSERT OR REPLACE INTO overrides VALUES (?,?,?,?)", (domain, decision, reason, time.time()))
    con.commit()


def effective_decision(con, domain) -> str | None:
    """The agent's decision, unless a human resolved a HUMAN REVIEW company."""
    o = con.execute("SELECT decision FROM overrides WHERE domain=?", (domain,)).fetchone()
    if o:
        return o[0]
    c = cached_company(con, domain)
    return c["decision"] if c else None


# --- logs -------------------------------------------------------------------

def log(con, domain: str, event: str) -> None:
    con.execute("INSERT INTO loop_log (domain, event, ts) VALUES (?,?,?)", (domain, event, time.time()))
    con.commit()


def log_llm(con, domain, purpose, model, tokens_in, tokens_out, ok, error=None):
    con.execute(
        "INSERT INTO llm_calls (domain, purpose, model, tokens_in, tokens_out, ok, error, ts) VALUES (?,?,?,?,?,?,?,?)",
        (domain, purpose, model, tokens_in, tokens_out, int(ok), error, time.time()),
    )
    con.commit()
