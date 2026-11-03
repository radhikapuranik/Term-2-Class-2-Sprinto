"""Command line: `uv run outreach run domains.txt`, `uv run outreach models`, `uv run outreach check-keys`."""
import argparse
import re
import sys
from pathlib import Path

from . import db
from .agent import qualify_company
from .config import ROOT, env
from .contact import load_rules
from .writer import draft_for
from .fetcher import Fetcher
from .icp import load_icp
from .llm import Gemini, LLMDown


def read_domains(path: str) -> list[str]:
    lines = Path(path).read_text().splitlines()
    return [l.split("#")[0].strip() for l in lines if l.split("#")[0].strip()]


def cmd_run(args) -> None:
    icp, con = load_icp(), db.connect()
    llm, fetcher = Gemini(con), Fetcher(con, icp.keywords)
    if not llm.model:
        sys.exit("GEMINI_MODEL is empty. Run: uv run outreach models")
    rules = load_rules()
    for d in read_domains(args.domains)[: args.limit]:
        c = qualify_company(d, icp, con, llm, fetcher, refresh=args.refresh)
        tag = "cache" if c["cached"] else f"{c['elapsed_s']}s"
        print(f"{c['decision']:<13} {c['domain']:<28} ({tag}) {c['stop_reason'] or ''}")
        if db.effective_decision(con, c["domain"]) == "GO":
            dr = draft_for(con, c["domain"], llm, rules)
            print(f"{'':<13} draft: {dr['status']} - {dr['notes']}")


def cmd_draft(args) -> None:
    """Steps 4-6 for one company a human has approved (or to redo a draft)."""
    con = db.connect()
    d = args.domain
    if db.effective_decision(con, d) != "GO":
        db.set_override(con, d, "GO", args.reason)
        print(f"Recorded human decision: {d} -> GO ({args.reason})")
    dr = draft_for(con, d, Gemini(con), load_rules(), redraft=args.redraft)
    print(f"draft: {dr['status']} - {dr['notes']}")
    if dr["body"]:
        print(f"\nSubject: {dr['subject']}\n\n{dr['body']}")


def cmd_send(args) -> None:
    """Approve and send one draft from the terminal (same recipient lock as the review page)."""
    from .send import review
    print(review(db.connect(), args.domain, "approved", dry_run=args.dry_run))


def set_env_line(name: str, value: str) -> None:
    """Write one non-secret line into .env.local without touching (or printing) the keys."""
    p = ROOT / ".env.local"
    text = p.read_text() if p.exists() else ""
    line = f"{name}={value}"
    text = re.sub(rf"^{name}=.*$", line, text, flags=re.M) if re.search(rf"^{name}=", text, re.M) else text + line + "\n"
    p.write_text(text)


def pick_flash(names: list[str]) -> str | None:
    """Newest standard Flash model: not lite, image, audio, live, tts or experimental. Stable beats preview."""
    best = None
    for n in names:
        n = n.removeprefix("models/")
        m = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash(-preview(?:-\d\d-\d{4})?)?", n)
        if not m:
            continue
        key = (float(m.group(1)), m.group(2) is None, n)
        best = max(best, key) if best else key
    return best[2] if best else None


def cmd_models(args) -> None:
    from google import genai
    if not env("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY is empty in .env.local")
    client = genai.Client(api_key=env("GEMINI_API_KEY"))
    names = [m.name for m in client.models.list() if "generateContent" in (m.supported_actions or [])]
    flash = [n for n in names if "flash" in n]
    print("Flash models your key can use:", ", ".join(sorted(n.removeprefix("models/") for n in flash)))
    choice = pick_flash(names)
    if choice:
        set_env_line("GEMINI_MODEL", choice)
        print(f"Chosen and saved to .env.local: GEMINI_MODEL={choice}")


def cmd_check_keys(args) -> None:
    import httpx
    from pydantic import BaseModel

    class Ping(BaseModel):
        ok: bool

    con = db.connect()
    if env("GEMINI_API_KEY"):
        try:
            Gemini(con).generate_json('Return {"ok": true}', Ping, "-", "key-check")
            print("GEMINI_API_KEY: works")
        except LLMDown as e:
            print(f"GEMINI_API_KEY: does not work, check the key and GEMINI_MODEL ({e})")
    for name, url, params in [
        ("HUNTER_API_KEY", "https://api.hunter.io/v2/account", lambda k: {"api_key": k}),
    ]:
        if env(name):
            r = httpx.get(url, params=params(env(name)), timeout=10)
            print(f"{name}: " + ("works" if r.status_code == 200 else f"does not work, check the key (HTTP {r.status_code})"))
    if env("LUSHA_API_KEY"):
        r = httpx.get("https://api.lusha.com/v2/company", params={"domain": "lusha.com"},
                      headers={"api_key": env("LUSHA_API_KEY")}, timeout=10)
        print("LUSHA_API_KEY: " + ("works" if r.status_code == 200 else f"does not work, check the key (HTTP {r.status_code})"))
    if env("GMAIL_ADDRESS") and env("GMAIL_APP_PASSWORD"):
        import smtplib
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
                s.login(env("GMAIL_ADDRESS"), env("GMAIL_APP_PASSWORD"))
            print("GMAIL_APP_PASSWORD: works")
        except smtplib.SMTPException:
            print("GMAIL_APP_PASSWORD: does not work, check the 16-letter app password and GMAIL_ADDRESS")


def main() -> None:
    ap = argparse.ArgumentParser(prog="outreach")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="qualify every domain in a file")
    r.add_argument("domains", nargs="?", default="domains.txt")
    r.add_argument("--refresh", action="store_true", help="ignore cached decisions and re-research")
    r.add_argument("--limit", type=int, default=None)
    r.set_defaults(fn=cmd_run)
    dr = sub.add_parser("draft", help="find contact, pain points and email for one company (marks it GO)")
    dr.add_argument("domain")
    dr.add_argument("--reason", default="human reviewer approved from CLI")
    dr.add_argument("--redraft", action="store_true")
    dr.set_defaults(fn=cmd_draft)
    se = sub.add_parser("send", help="approve and send one draft to TEST_RECIPIENT")
    se.add_argument("domain")
    se.add_argument("--dry-run", action="store_true", help="print the email instead of sending")
    se.set_defaults(fn=cmd_send)
    sub.add_parser("models", help="pick the newest Gemini Flash model").set_defaults(fn=cmd_models)
    sub.add_parser("check-keys", help="test each key with a harmless call").set_defaults(fn=cmd_check_keys)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
