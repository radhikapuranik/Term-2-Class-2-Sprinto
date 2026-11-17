"""Seed data for the Outreach Desk API and browser tests (fictional companies, no network)."""
import time

from outreach import db

PARAMS = ["company_type", "funding_stage", "employee_count", "audit_prep", "clients", "industry", "cloud_stack"]


def answer(outcome, quote="", url="", value=None, conf=0.9, attempts=1):
    a = {"value": value, "number_min": None, "number_max": None, "items": [], "evidence_quote": quote,
         "confidence": conf, "page_chars": 900, "source_kind": "home", "certs_unnamed": False} if quote else None
    return {"outcome": outcome, "reason": f"{outcome} ({value})", "answer": a, "quote": quote, "url": url, "attempts": attempts}


def seed(con) -> None:
    go = {"company_type": answer("qualifies", "Ledgerly is a cloud platform for finance teams", "https://ledgerly.test/", "saas"),
          "funding_stage": answer("qualifies", "Ledgerly raised a $20M Series B", "https://news.test/ledgerly", "series_b"),
          "employee_count": answer("unanswered", attempts=3),
          "audit_prep": answer("qualifies", "Senior Compliance Engineer", "https://ledgerly.test/careers", "hiring_audit_role"),
          "clients": answer("qualifies", "Trusted by 300 finance teams", "https://ledgerly.test/customers", "enterprise_clients"),
          "industry": answer("qualifies", "Ledgerly is a cloud platform for finance teams", "https://ledgerly.test/", "fintech"),
          "cloud_stack": answer("qualifies", "Runs on AWS", "https://docs.ledgerly.test/", "aws")}
    db.save_company(con, "ledgerly.test", "Ledgerly", {"one_liner": "Close-the-books software for finance teams."},
                    "HUMAN REVIEW", ["Employee count: unanswered"], 21.5, "every parameter answered or out of retries")
    for pid, a in go.items():
        db.save_answer(con, "ledgerly.test", pid, a)
    db.set_override(con, "ledgerly.test", "GO", "Series B and hiring for compliance")
    db.save_company(con, "bigco.test", "BigCo", {"one_liner": "Enterprise CRM."}, "NO-GO",
                    ["Employee count: rejects - 900 is above 200"], 9.0, "auto-reject on Employee count")
    db.save_answer(con, "bigco.test", "company_type", answer("qualifies", "BigCo CRM platform", "https://bigco.test/", "saas"))
    db.save_answer(con, "bigco.test", "employee_count", answer("rejects", "900 employees worldwide", "https://bigco.test/about", "900"))
    db.save_company(con, "quiet.test", "Quiet", {}, "HUMAN REVIEW", ["Company type: unanswered - HTTP 403"], 3.0, "site blocked")
    for d in ("ledgerly.test", "bigco.test", "quiet.test"):
        db.log(con, d, f"fetched home https://{d}/ via http: ok ")
    db.log(con, "ledgerly.test", "company_type from home: qualifies (saas matches 'SaaS (hard filter)')")
    db.log(con, "ledgerly.test", "loop stopped: every parameter answered or out of retries")
    db.log_llm(con, "ledgerly.test", "extract:company_type", "m", 1200, 80, True)
    db.save_page(con, "https://ledgerly.test/", "ledgerly.test", "home", "http", "ok", "text", 5000)
    contact = {"first_name": "Priya", "last_name": "Shah", "title": "Head of Security", "email": "priya@ledgerly.test",
               "confidence": 92, "why": "security title ranks first", "source": "Hunter"}
    pains = [{"pain": "Audit prep pulls engineers off the roadmap", "why_it_matters_to_this_role": "She owns the audit",
              "evidence_quote": "Senior Compliance Engineer", "url": "https://ledgerly.test/careers"},
             {"pain": "Enterprise buyers ask for SOC 2", "why_it_matters_to_this_role": "Deals stall on questionnaires",
              "evidence_quote": "Trusted by 300 finance teams", "url": "https://ledgerly.test/customers"}]
    db.save_draft(con, "ledgerly.test", contact, pains, "Your compliance engineer hire",
                  "Hi Priya,\n\nSaw Ledgerly is hiring a Senior Compliance Engineer. Worth a short chat?", "Senior Compliance Engineer",
                  "draft", "ok")
    db.save_company(con, "second.test", "Second", {}, "GO", [], 5.0, "done")
    db.save_draft(con, "second.test", dict(contact, first_name="Sam", email="sam@second.test"), pains, "Quick audit question",
                  "Hi Sam,\n\nNoticed Second is growing fast. Worth a short chat?", "growing", "draft", "ok")
    con.execute("UPDATE drafts SET created_at=? WHERE domain='second.test'", (time.time() + 1,))
    con.commit()
