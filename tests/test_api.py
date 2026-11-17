"""Outreach Desk API: reads, review actions, and the recipient lock through the API."""
import json

import pytest
from fastapi.testclient import TestClient

from outreach import api, db
from tests.ui_seed import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_RECIPIENT", "me@example.com")
    path = tmp_path / "ui.db"
    seed(db.connect(path))
    api.app.state.db_path = path
    yield TestClient(api.app)
    del api.app.state.db_path


def test_companies_and_summary(client):
    rows = {r["domain"]: r for r in client.get("/api/companies").json()}
    assert rows["ledgerly.test"]["human"] == "GO" and rows["ledgerly.test"]["fit_score"] == 6
    assert len(rows["ledgerly.test"]["fit"]) == 7 and rows["bigco.test"]["decision"] == "NO-GO"
    s = client.get("/api/summary").json()
    assert s["drafts_to_review"] == 2 and [f["key"] for f in s["funnel"]][0] == "domains"


def test_company_evidence_and_timeline(client):
    c = client.get("/api/companies/ledgerly.test").json()
    card = {s["id"]: s for s in c["scorecard"]}
    assert card["audit_prep"]["quote"] == "Senior Compliance Engineer" and card["audit_prep"]["url"].endswith("/careers")
    assert any(t["kind"] == "fetch" for t in c["timeline"]) and c["override"]["decision"] == "GO"
    assert client.get("/api/companies/bigco.test").json()["stopped_early"] is True
    assert client.get("/api/companies/nope.test").status_code == 404


def test_prospect_email_never_reaches_the_browser(client):
    q = client.get("/api/review").json()
    assert q[0]["contact"]["first_name"] == "Priya" and "email" not in q[0]["contact"]
    assert "priya@ledgerly.test" not in json.dumps(q)


def test_send_goes_through_review_and_lock(client, monkeypatch):
    sent = []
    monkeypatch.setattr("outreach.send.send", lambda to, *a, **k: sent.append(to) or "re_1")
    r = client.post("/api/review/ledgerly.test/send", json={"action": "approved", "dry_run": True}).json()
    assert r["result"] == "dry_run" and sent == []
    r = client.post("/api/review/ledgerly.test/send", json={"action": "edited", "subject": "Your compliance engineer hire",
                                                             "body": "Hi Priya,\n\nSaw the Senior Compliance Engineer role. Chat?"}).json()
    assert r["result"] == "sent" and sent == ["me@example.com"] and 0 < r["draft"]["edit_ratio"] < 1


def test_recipient_lock_enforced_through_api(client, monkeypatch):
    monkeypatch.setenv("TEST_RECIPIENT", "")
    r = client.post("/api/review/ledgerly.test/send", json={"action": "approved"})
    assert r.status_code == 409 and r.json()["result"] == "locked"
    assert db.get_draft(db.connect(api.app.state.db_path), "ledgerly.test")["status"] == "draft"


def test_resend_error_becomes_human_review(client, monkeypatch):
    from outreach.resend_mail import SendFailed

    def boom(*a, **k):
        raise SendFailed("Resend is down")
    monkeypatch.setattr("outreach.send.send", boom)
    r = client.post("/api/review/ledgerly.test/send", json={"action": "approved"}).json()
    assert r["result"] == "human_review" and "Resend is down" in r["message"]


def test_reject_and_undo(client):
    assert client.post("/api/review/ledgerly.test/reject", json={"reason": " "}).status_code == 400
    assert client.post("/api/review/ledgerly.test/reject", json={"reason": "wrong person"}).json()["ok"]
    assert len(client.get("/api/review").json()) == 1
    assert client.post("/api/review/ledgerly.test/undo-reject").json()["ok"]
    assert len(client.get("/api/review").json()) == 2


def test_edit_ratio_quality_icp_runs(client):
    assert client.post("/api/edit-ratio", json={"original": "abc", "final": "abc"}).json()["edit_ratio"] == 0
    assert client.get("/api/quality").json()["stats"]["open_rate"] == "not measured in test mode"
    assert len(client.get("/api/icp").json()["parameters"]) == 7
    runs = client.get("/api/runs").json()
    assert runs["runs"][0]["companies"] == 3


def test_human_decision_needs_reason(client):
    assert client.post("/api/companies/quiet.test/decision", json={"decision": "NO-GO", "reason": ""}).status_code == 400
    assert client.post("/api/companies/quiet.test/decision", json={"decision": "NO-GO", "reason": "blocked site"}).json()["ok"]


def test_start_run_streams_steps(client, monkeypatch):
    def fake_qualify(d, icp, con, llm, fetcher, refresh=False):
        db.log(con, d, f"fetched home https://{d}/ via http: ok ")
        db.save_company(con, d, d, {}, "NO-GO", ["x"], 1.0, "auto-reject")
        return db.cached_company(con, d) | {"cached": False}
    monkeypatch.setattr(api, "qualify_company", fake_qualify)
    monkeypatch.setattr("outreach.llm.Gemini.model", "fake", raising=False)
    r = client.post("/api/runs", json={"domains": ["https://www.alpha.test/x, beta.test"], "qualify_only": True}).json()
    assert r["domains"] == ["alpha.test", "beta.test"]
    with client.stream("GET", f"/api/runs/{r['id']}/stream") as s:
        text = "".join(s.iter_text())
    assert "event: step" in text and "alpha.test" in text and "event: done" in text


def test_spa_routes_and_404(client):
    assert client.get("/companies/ledgerly.test").status_code == 200
    assert client.get("/no-such-page").status_code == 404
    assert client.get("/api/nope").status_code == 404
