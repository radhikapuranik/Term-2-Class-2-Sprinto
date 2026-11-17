"""Step 7: the review gate's actions and sending via Resend, locked to TEST_RECIPIENT."""
import difflib
import html
import json
import time

from . import db
from .config import env
from .resend_mail import SENDER, SendFailed, send

MAX_SUBJECT_WORDS = 7  # "under 8 words"


class RecipientLocked(Exception):
    """Raised for any attempt to send to someone other than TEST_RECIPIENT."""


def locked_recipient() -> str:
    to = env("TEST_RECIPIENT")
    if not to or "@" not in to:
        raise RecipientLocked("TEST_RECIPIENT is empty in .env.local, so nothing can be sent")
    return to


def to_html(body: str) -> str:
    """Plain-text body as simple HTML: one <p> per paragraph, line breaks kept, text escaped."""
    paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    return "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paras)


def send_email(to: str, subject: str, body: str, intended_for: str = "", dry_run: bool = False) -> str:
    """Send one email (HTML + plain text). Refuses any address that is not TEST_RECIPIENT.
    Returns Resend's email id, or "dry-run"."""
    allowed = locked_recipient()
    if to.strip().lower() != allowed.strip().lower():
        raise RecipientLocked(f"refused: emails may only go to TEST_RECIPIENT, not {to}")
    if len(subject.split()) > MAX_SUBJECT_WORDS:
        raise SendFailed(f"subject has {len(subject.split())} words; it must be under 8")
    headers = {"X-Intended-For": intended_for} if intended_for else None  # the real prospect, never sent to
    if dry_run:
        print(f"--- DRY RUN (not sent) ---\nFrom: {SENDER}\nTo: {allowed}\nSubject: {subject}\n"
              f"X-Intended-For: {intended_for}\n\n{body}")
        return "dry-run"
    return send(allowed, subject, body, to_html(body), headers)


def edit_ratio(original: str, final: str) -> float:
    """Share of the draft the reviewer changed: 0.0 = untouched, 1.0 = rewritten (character-level diff)."""
    return round(1 - difflib.SequenceMatcher(None, original, final).ratio(), 3)


def review(con, domain: str, action: str, subject: str = "", body: str = "", reason: str = "",
           dry_run: bool = False) -> str:
    """Apply a reviewer action: approved | edited | rejected. Returns what happened.
    A send failure puts the draft back in HUMAN REVIEW with the reason instead of crashing."""
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
    try:
        result = send_email(locked_recipient(), subject, body, intended, dry_run)
    except SendFailed as e:
        db.update_draft(con, domain, status="human_review", notes=f"Not sent: {e}")
        return f"human review: {e}"
    if result != "dry-run":
        db.update_draft(con, domain, status="sent", review_action=action, final_subject=subject, final_body=body,
                        edit_ratio=ratio, sent_at=time.time(), resend_id=result)
        return f"sent (Resend id {result})"
    return result


def stats(con) -> dict:
    """The two tracked numbers: sends (opens not measured in test mode) and the running edit %."""
    sent = con.execute("SELECT COUNT(*), AVG(edit_ratio) FROM drafts WHERE status='sent'").fetchone()
    reviewed = con.execute("SELECT COUNT(*) FROM drafts WHERE review_action IS NOT NULL").fetchone()[0]
    return {"sent": sent[0], "avg_edit_pct": round((sent[1] or 0) * 100, 1), "reviewed": reviewed,
            "open_rate": "not measured in test mode"}
