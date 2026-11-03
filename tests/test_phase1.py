from pathlib import Path

import pytest

from outreach import db
from outreach.cleaner import clean_html, focus, needs_js
from outreach.icp import Answer, decide, evaluate, load_icp

FIX = Path(__file__).parent / "fixtures"
ICP = load_icp()


def html(name):
    return (FIX / name).read_text()


# --- ICP loading ---------------------------------------------------------------

def test_icp_loads_all_seven_rows():
    assert [p.id for p in ICP.parameters] == [
        "company_type", "funding_stage", "employee_count", "audit_prep", "clients", "industry", "cloud_stack"]
    assert ICP.param("company_type").if_unanswered == "reject"
    assert ICP.param("employee_count").retries == 3
    assert ICP.limits.max_fetches_per_company == 8


# --- per-row rules ------------------------------------------------------------

@pytest.mark.parametrize("pid,answer,outcome", [
    ("company_type", Answer(value="saas"), "qualifies"),
    ("company_type", Answer(value="not_saas"), "rejects"),
    ("funding_stage", Answer(value="series_b"), "qualifies"),
    ("funding_stage", Answer(value="seed"), "rejects"),
    ("funding_stage", Answer(value="public"), "rejects"),
    ("funding_stage", Answer(value="series_d_plus"), "neutral"),
    ("employee_count", Answer(number_min=120, number_max=120), "qualifies"),
    ("employee_count", Answer(number_min=1000, number_max=5000), "rejects"),
    ("employee_count", Answer(number_min=11, number_max=50), "neutral"),
    ("audit_prep", Answer(value="hiring_audit_role", items=["SOC 2", "ISO 27001"]), "qualifies"),
    ("audit_prep", Answer(value="none", items=["SOC 2", "ISO 27001", "GDPR"]), "rejects"),
    ("audit_prep", Answer(value="none", items=[], page_chars=900, source_kind="security"), "qualifies"),
    ("audit_prep", Answer(value="none", items=[], page_chars=900, source_kind="careers"), "unanswered"),
    ("audit_prep", Answer(value="none", page_chars=900, source_kind="security", certs_unnamed=True), "unanswered"),
    ("audit_prep", Answer(value="none", items=[], page_chars=20, source_kind="security"), "unanswered"),
    ("audit_prep", Answer(value="none", items=["SOC2"], page_chars=900), "neutral"),
    ("clients", Answer(number_min=300), "qualifies"),
    ("clients", Answer(value="enterprise_clients", items=["Siemens"]), "qualifies"),
    ("industry", Answer(value="other"), "neutral"),
    ("cloud_stack", Answer(items=["aws"]), "qualifies"),
    ("cloud_stack", Answer(items=[]), "unanswered"),
])
def test_evaluate(pid, answer, outcome):
    assert evaluate(ICP.param(pid), answer)[0] == outcome


# --- short-circuit and "if unanswered" -----------------------------------------

def r(outcome, error=None):
    return {"outcome": outcome, "reason": "x", "error": error}


def all_qualify():
    return {p.id: r("qualifies") for p in ICP.parameters}


def test_go_when_everything_qualifies():
    assert decide(ICP, all_qualify())[0] == "GO"


def test_reject_short_circuits():
    res = all_qualify() | {"company_type": r("rejects")}
    decision, reasons = decide(ICP, res)
    assert decision == "NO-GO" and reasons[-1] == "Auto-reject on Company type"
    assert len(reasons) == 2  # stopped at the first row


def test_unanswered_company_type_rejects():
    assert decide(ICP, all_qualify() | {"company_type": r("unanswered")})[0] == "NO-GO"


def test_unanswered_funding_goes_to_human_review():
    assert decide(ICP, all_qualify() | {"funding_stage": r("unanswered")})[0] == "HUMAN REVIEW"


def test_unanswered_low_weight_is_skipped():
    res = all_qualify() | {"clients": r("unanswered"), "industry": r("unanswered"), "cloud_stack": r("unanswered")}
    assert decide(ICP, res)[0] == "GO"


def test_system_error_never_auto_rejects():
    assert decide(ICP, all_qualify() | {"company_type": r("unanswered", "Gemini down")})[0] == "HUMAN REVIEW"


# --- cleaner and JavaScript detector ------------------------------------------

def test_cleaner_strips_boilerplate_and_keeps_signal():
    text = clean_html(html("saas_home.html"), ICP.keywords)
    assert "cookies" not in text.lower()
    assert "gtag" not in text and "Log in" not in text
    assert "Series B" in text and "Trusted by 300+" in text
    assert "[footer] We are GDPR compliant." in text  # footer certs survive
    assert "Privacy policy" not in text


def test_focus_keeps_keyword_lines_and_caps():
    filler = "\n".join(f"Filler line {i} about nothing much" for i in range(3000))
    text = "Title\n" + filler + "\nWe are SOC 2 Type II certified\n" + filler
    out = focus(text, ["SOC 2"], max_tokens=200)
    assert "SOC 2 Type II" in out and len(out) <= 800


def test_js_detector():
    assert not needs_js(html("saas_home.html"))
    spa = '<html><head><script src="/app.js"></script></head><body><div id="root"></div></body></html>'
    assert needs_js(spa)
    assert needs_js('<html><body><noscript>You need to enable JavaScript to run this app.</noscript><div id="app"></div></body></html>')


# --- cache ---------------------------------------------------------------------

def test_cache_roundtrip(tmp_path):
    con = db.connect(tmp_path / "t.db")
    assert db.cached_company(con, "acme.com") is None
    db.save_company(con, "acme.com", "Acme", {}, "GO", ["ok"], 1.0, "done")
    assert db.cached_company(con, "acme.com")["decision"] == "GO"
    db.save_api(con, "hunter:acme.com", {"emails": []})
    db.clear_company(con, "acme.com")
    assert db.cached_company(con, "acme.com") is None
    assert db.cached_api(con, "hunter:acme.com") == {"emails": []}  # paid lookups survive --refresh


def test_badge_image_filenames_count_as_certs():
    page = '<html><body><main><h1>Security</h1><img src="/m/aicpa-logo.webp"><img alt="ISO 27001 certified"></main></body></html>'
    text = clean_html(page, ICP.keywords)
    assert "SOC 2 (AICPA logo) badge image" in text and "ISO 27001 certified" in text


def test_server_rendered_menu_with_empty_body_needs_js():
    menu = "".join(f"<li>Menu item number {i} with words</li>" for i in range(80))
    page = f'<html><body><div class="site-nav"><ul>{menu}</ul></div><div id="__nuxt"><h1>Security</h1></div></body></html>'
    assert needs_js(page)
