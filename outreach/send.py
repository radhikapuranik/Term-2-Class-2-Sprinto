"""Step 7: the review gate's actions and sending via the Gmail API, locked to TEST_RECIPIENT."""
import difflib
import json
import time
from email.message import EmailMessage

from . import db
from .config import env
from .gmail import send_raw


class RecipientLocked(Exception):
    """Raised for any attempt to send to someone other than TEST_RECIPIENT."""


def locked_recipient() -> str:
    to = env("TEST_RECIPIENT")
    if not to or "@" not in to:
        raise RecipientLocked("TEST_RECIPIENT is empty in .env.local, so nothing can be sent")
    return to


def send_email(to: str, subject: str, body: str, intended_for: str = "", dry_run: bool = False) -> str:
    """Send one email. Refuses any address that is not TEST_RECIPIENT (test mode is hardcoded)."""
    allowed = locked_recipient()
    if to.strip().lower() != allowed.strip().lower():
        raise RecipientLocked(f"refused: emails may only go to TEST_RECIPIENT, not {to}")
    msg = EmailMessage()
    msg["From"] = env("GMAIL_ADDRESS") or allowed
    msg["To"] = allowed
    msg["Subject"] = subject
    if intended_for:
        msg["X-Intended-For"] = intended_for  # the real prospect, recorded but never sent to
    msg.set_content(body)
    if dry_run:
        print(f"--- DRY RUN (not sent) ---\n{msg}")
        return "dry-run"
    send_raw(msg.as_bytes())  # Gmail API, OAuth send-only scope
    return "sent"


def edit_ratio(original: str, final: str) -> float:
    """Share of the draft the reviewer changed: 0.0 = untouched, 1.0 = rewritten (character-level diff)."""
    return round(1 - difflib.SequenceMatcher(None, original, final).ratio(), 3)


def review(con, domain: str, action: str, subject: str = "", body: str = "", reason: str = "",
           dry_run: bool = False) -> str:
    """Apply a reviewer action: approved | edited | rejected. Returns what happened."""
    d = db.get_draft(con, domain)
    if not d:
        raise ValueError(f"no draft for {domain}")
    if action == "rejected":
        db.update_draft(con, domain, status="rejected", review_action="rejected", reject_reason=reason)
        return "rejected"
    if action == "approved":
        subject, body = d["subject"], d["body"]
    ratio = edit_ratio(f"{d['subject']}\n{d['body']}", f"{subject}\n{body}")
    c = json.loads(d["contact_json"] or "{}")
    intended = f"{c.get('first_name', '')} {c.get('last_name', '')} <{c.get('email', '')}>, {c.get('title', '')}"
    result = send_email(locked_recipient(), subject, body, intended, dry_run)
    if result == "sent":
        db.update_draft(con, domain, status="sent", review_action=action, final_subject=subject, final_body=body,
                        edit_ratio=ratio, sent_at=time.time())
    return result


def stats(con) -> dict:
    """The two tracked numbers: sends (opens not measured in test mode) and the running edit %."""
    sent = con.execute("SELECT COUNT(*), AVG(edit_ratio) FROM drafts WHERE status='sent'").fetchone()
    reviewed = con.execute("SELECT COUNT(*) FROM drafts WHERE review_action IS NOT NULL").fetchone()[0]
    return {"sent": sent[0], "avg_edit_pct": round((sent[1] or 0) * 100, 1), "reviewed": reviewed,
            "open_rate": "not measured in test mode"}
