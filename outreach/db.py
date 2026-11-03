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
