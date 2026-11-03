"""Contact choice, Hunter caching, the email validator, and degrade-to-human-review."""
import pytest

from outreach import db
from outreach.contact import choose_contact, find_contact, load_rules
from outreach.llm import Gemini, LLMDown
from outreach.writer import Email, Pain, Pains, draft_for, validate_email

RULES = load_rules()
PRIO = RULES["contact_priority"]


def person(first, title, conf=90):
    return {"first_name": first, "last_name": "X", "position": title, "value": f"{first.lower()}@acme.com",
            "confidence": conf, "sources": [{}]}


def test_contact_priority_order():
    people = [person("Ceo", "Co-Founder & CEO"), person("Vp", "VP Engineering"), person("Cto", "CTO", 70),
              person("Sec", "Head of Information Security", 60), person("Mkt", "VP Marketing", 99)]
    assert choose_contact(people, PRIO)["first_name"] == "Sec"
    assert choose_contact(people[:3], PRIO)["first_name"] == "Cto"
    assert choose_contact(people[:2], PRIO)["first_name"] == "Vp"
    assert choose_contact([people[4]], PRIO) is None


def test_hunter_is_never_searched_twice(tmp_path, monkeypatch):
    con = db.connect(tmp_path / "t.db")
    db.save_api(con, "hunter:acme.com", {"contact": None, "reason": "nobody"})
    monkeypatch.setenv("SIMULATE_FAIL", "hunter")  # a live call would now raise
    contact, why = find_contact(con, "acme.com", PRIO)
    assert contact is None and "(cached)" in why


EV = '[E1] (audit_prep, https://acme.com/careers) finding: hiring | quote: "Compliance Manager (SOC 2 / ISO 27001)"\n' \
     '[E2] (clients, https://acme.com/customers) finding: 300 | quote: "Trusted by 300+ finance teams"'
FACTS = " ".join(RULES["sprinto_facts"])


def check(body, subject="Your SOC 2 hire", hook="Compliance Manager (SOC 2 / ISO 27001)"):
    return validate_email(subject, body, hook, "Priya", "Acme", EV, FACTS, 110, 7)


GOOD = "Hi Priya, I saw Acme is hiring a Compliance Manager to own SOC 2 and ISO 27001. " \
       "Sprinto has AI-powered audit prep that keeps evidence current. Worth a short chat?"


def test_validator_accepts_a_good_email():
    assert check(GOOD) == []


@pytest.mark.parametrize("body,expect", [
    (GOOD.replace("Priya", "there"), "by name"),
    (GOOD + " Hi [First Name].", "placeholder"),
    (GOOD.replace("to own", "after your 40M raise to own"), "number '40'"),
    (GOOD.replace("Sprinto has", "Like Stripe, Sprinto has"), "'Stripe'"),
    ("Hi Priya, Sprinto has AI-powered audit prep. Worth a short chat?", "mention the hook"),
    (GOOD + " word" * 120, "words, limit"),
])
def test_validator_catches(body, expect):
    assert any(expect in p for p in check(body)), check(body)


def test_subject_length_and_hook_must_be_real():
    assert any("subject" in p for p in check(GOOD, subject="A very long subject line that goes on and on"))
    assert any("hook_quote" in p for p in check(GOOD, hook="raised a Series C"))


class FakeWriter(Gemini):
    def __init__(self, con, down=False):
        super().__init__(con, model="fake")
        self.down = down

    def generate_json(self, prompt, schema, domain, purpose):
        if self.down:
            raise LLMDown("fake outage")
        if schema is Pains:
            return Pains(pains=[Pain(pain="SOC 2 audit coming", why_it_matters_to_this_role="owns it", evidence_id="E1",
                                     evidence_quote="Compliance Manager"),
                                Pain(pain="Enterprise reviews", why_it_matters_to_this_role="sales", evidence_id="E2",
                                     evidence_quote="Trusted by 300+")])
        return Email(subject="Your SOC 2 hire", body=GOOD, hook_evidence_id="E1",
                     hook_quote="Compliance Manager (SOC 2 / ISO 27001)")


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.delenv("SIMULATE_FAIL", raising=False)
    con = db.connect(tmp_path / "t.db")
    db.save_company(con, "acme.com", "Acme", {}, "GO", [], 1, "")
    for pid, q in [("audit_prep", "Compliance Manager (SOC 2 / ISO 27001)"), ("clients", "Trusted by 300+ finance teams")]:
        db.save_answer(con, "acme.com", pid, {"outcome": "qualifies", "reason": "r", "quote": q, "url": "https://acme.com/x"})
    db.save_api(con, "hunter:acme.com", {"contact": choose_contact([person("Priya", "CTO")], PRIO), "reason": "cto"})
    return con


def test_draft_passes_and_names_person(con):
    d = draft_for(con, "acme.com", FakeWriter(con), RULES)
    assert d["status"] == "draft" and d["body"].startswith("Hi Priya") and d["body"].endswith("Radhika, Sprinto")


def test_gemini_down_degrades_to_human_review(con):
    d = draft_for(con, "acme.com", FakeWriter(con, down=True), RULES)
    assert d["status"] == "human_review" and "Gemini unavailable" in d["notes"]


def test_hunter_down_degrades_to_human_review(con, monkeypatch):
    con.execute("DELETE FROM api_cache")
    monkeypatch.setenv("SIMULATE_FAIL", "hunter")
    d = draft_for(con, "acme.com", FakeWriter(con), RULES)
    assert d["status"] == "human_review" and "Contact lookup failed" in d["notes"]
