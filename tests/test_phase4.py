"""Recipient lock, edit %, and the review actions."""
import pytest

from outreach import db
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


def test_real_send_goes_through_gmail_api_to_test_recipient_only(monkeypatch):
    monkeypatch.setenv("TEST_RECIPIENT", "me@example.com")
    sent = []
    monkeypatch.setattr("outreach.send.send_raw", lambda raw: sent.append(raw) or "id1")
    assert send_email("me@example.com", "Hi", "Body", intended_for="Priya <priya@acme.com>") == "sent"
    assert b"To: me@example.com" in sent[0] and b"priya@acme.com" in sent[0]  # prospect only in X-Intended-For
    assert b"\nTo: priya" not in sent[0]
    with pytest.raises(RecipientLocked):
        send_email("priya@acme.com", "Hi", "Body")
    assert len(sent) == 1


def test_gmail_not_connected_is_a_clear_error(monkeypatch, tmp_path):
    from outreach import gmail
    monkeypatch.setattr(gmail, "TOKEN_FILE", tmp_path / "none.json")
    with pytest.raises(gmail.GmailNotReady):
        gmail.credentials()
