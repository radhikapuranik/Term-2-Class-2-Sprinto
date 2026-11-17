"""Recipient lock, edit %, and the review actions."""
import json

import httpx
import pytest

from outreach import db, resend_mail
from outreach.send import RecipientLocked, edit_ratio, review, send_email, stats


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_RECIPIENT", "me@example.com")
    con = db.connect(tmp_path / "t.db")
    db.save_draft(con, "acme.com", {"first_name": "Priya", "last_name": "S", "email": "priya@acme.com", "title": "CTO"},
                  [], "Your SOC 2 hire", "Hi Priya, short note.", "hook", "draft", "ok")
    return con


def test_recipient_lock_refuses_anyone_else(con):
    with pytest.raises(RecipientLocked):
        send_email("priya@acme.com", "s", "b", dry_run=True)
    assert send_email("ME@example.com", "s", "b", dry_run=True) == "dry-run"


def test_recipient_lock_needs_test_recipient(monkeypatch):
    monkeypatch.setenv("TEST_RECIPIENT", "")
    with pytest.raises(RecipientLocked):
        send_email("", "s", "b", dry_run=True)


def test_edit_ratio():
    assert edit_ratio("same text", "same text") == 0
    assert edit_ratio("Hi Priya, short note.", "Totally different words here!") > 0.5


def test_dry_run_does_not_mark_sent(con):
    assert review(con, "acme.com", "approved", dry_run=True) == "dry-run"
    assert db.get_draft(con, "acme.com")["status"] == "draft"


def test_send_records_edit_pct(con, monkeypatch):
    monkeypatch.setattr("outreach.send.send_email", lambda *a, **k: "sent")
    review(con, "acme.com", "edited", "Your SOC 2 hire", "Hi Priya, a slightly longer short note.")
    d = db.get_draft(con, "acme.com")
    assert d["status"] == "sent" and 0 < d["edit_ratio"] < 0.5
    assert stats(con)["sent"] == 1 and stats(con)["avg_edit_pct"] > 0


def test_reject_keeps_reason(con):
    review(con, "acme.com", "rejected", reason="wrong person")
    assert db.get_draft(con, "acme.com")["reject_reason"] == "wrong person"


def _resend(status=200, body=None, seen=None):
    """A fake Resend API (httpx MockTransport): records requests, answers with status/body."""
    def handler(req):
        if seen is not None:
            seen.append(req)
        return httpx.Response(status, json=body if body is not None else {"id": "re_123"})
    return httpx.MockTransport(handler)


@pytest.fixture
def fake_resend(monkeypatch):
    """Route outreach's Resend calls through a mock; returns the list of requests made."""
    class Seen(list):
        state = {"status": 200, "body": None}
    seen = Seen()
    state = seen.state
    monkeypatch.setenv("RESEND_API_KEY", "re_test_not_real")
    real = resend_mail.send
    monkeypatch.setattr("outreach.send.send", lambda *a, **k: real(
        *a, transport=_resend(state["status"], state["body"], seen), **k))
    return seen


def test_real_send_goes_to_test_recipient_only_as_html_and_text(con, fake_resend):
    assert review(con, "acme.com", "approved") == "sent (Resend id re_123)"
    p = json.loads(fake_resend[0].content)
    assert p["to"] == ["me@example.com"] and "onboarding@resend.dev" in p["from"]
    assert p["text"] == "Hi Priya, short note." and p["html"] == "<p>Hi Priya, short note.</p>"
    assert p["headers"]["X-Intended-For"].startswith("Priya S <priya@acme.com>")  # prospect never in "to"
    assert fake_resend[0].headers["authorization"] == "Bearer re_test_not_real"
    d = db.get_draft(con, "acme.com")
    assert d["status"] == "sent" and d["resend_id"] == "re_123" and d["edit_ratio"] == 0
    with pytest.raises(RecipientLocked):
        send_email("priya@acme.com", "Hi", "Body")
    assert len(fake_resend) == 1


def test_dry_run_never_calls_resend(con, fake_resend):
    assert review(con, "acme.com", "approved", dry_run=True) == "dry-run"
    assert fake_resend == []


def test_resend_error_goes_to_human_review_not_crash(con, fake_resend):
    fake_resend.state.update(status=403, body={"message": "You can only send testing emails to your own email address"})
    out = review(con, "acme.com", "approved")
    d = db.get_draft(con, "acme.com")
    assert out.startswith("human review") and d["status"] == "human_review"
    assert "signed up to Resend with" in d["notes"] and d["resend_id"] is None


def test_resend_outage_and_missing_key_go_to_human_review(con, fake_resend, monkeypatch):
    monkeypatch.setenv("SIMULATE_FAIL", "resend")
    assert review(con, "acme.com", "approved").startswith("human review")
    monkeypatch.setenv("SIMULATE_FAIL", "")
    monkeypatch.setenv("RESEND_API_KEY", "")
    assert "RESEND_API_KEY is empty" in review(con, "acme.com", "approved")
    assert fake_resend == []


def test_long_subject_is_not_sent(con, fake_resend):
    out = review(con, "acme.com", "edited", "one two three four five six seven eight", "Hi Priya, short note.")
    assert out.startswith("human review") and fake_resend == []
