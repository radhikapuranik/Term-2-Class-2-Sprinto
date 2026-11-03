"""The agent loop, end to end, against a fake website and a fake Gemini. No network, no keys."""
import json
from pathlib import Path

import httpx
import pytest

from outreach import db
from outreach.agent import Profile, qualify_company
from outreach.cli import pick_flash
from outreach.config import simulate
from outreach.fetcher import Fetcher
from outreach.icp import load_icp
from outreach.llm import Extraction, Gemini, LLMDown, check_extraction, quote_in_text

FIX = Path(__file__).parent / "fixtures"
SITE = {
    "/": (FIX / "saas_home.html").read_text(),
    "/careers": (FIX / "careers.html").read_text(),
    "/trust": (FIX / "security.html").read_text(),
}
BING_RSS = """<?xml version="1.0"?><rss><channel><item><title>Ledgerly raises $22M Series B to automate accounts payable</title>
<pubDate>Tue, 12 Mar 2024 08:00:00 GMT</pubDate><description>The fintech startup will hire.</description></item></channel></rss>"""


def site(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    if host == "news.google.com":
        return httpx.Response(200, text="User-agent: *\nDisallow: /")
    if host == "www.bing.com":
        return httpx.Response(200, text=BING_RSS) if path != "/robots.txt" else httpx.Response(404)
    if path in SITE:
        return httpx.Response(200, html=SITE[path])
    return httpx.Response(404)


def E(answered=True, value=None, lo=None, hi=None, items=(), quote=""):
    return Extraction(answered=answered, value=value, number_min=lo, number_max=hi, items=list(items),
                      evidence_quote=quote, confidence=0.9)


GOOD = {  # param -> (text that must be on the page, extraction)
    "company_type": ("cloud software platform", E(value="saas", quote="cloud software platform")),
    "funding_stage": ("Series B", E(value="series_b", quote="raises $22M Series B")),
    "employee_count": ("team of 120", E(lo=120, hi=120, quote="team of 120 people")),
    "audit_prep": ("Security at Ledgerly", E(value="none")),
    "clients": ("Trusted by 300+", E(lo=300, quote="Trusted by 300+ finance teams")),
    "industry": ("finance teams", E(value="fintech", quote="finance teams")),
    "cloud_stack": ("AWS", E(items=["AWS"], quote="AWS (ECS, RDS, S3)")),
}


class FakeGemini(Gemini):
    def __init__(self, con, answers=None, down=False):
        super().__init__(con, model="fake-flash")
        self.answers = answers or GOOD
        self.down = down
        self.calls = []

    def generate_json(self, prompt, schema, domain, purpose):
        self.calls.append(purpose)
        if self.down or simulate("gemini"):
            raise LLMDown("fake outage")
        if schema is Profile:
            return Profile(name="Ledgerly", one_liner="AP automation", evidence_quote="Close your books three days faster")
        pid = purpose.split(":")[1]
        need, ex = self.answers[pid]
        text = prompt.split("<<<")[1]
        return ex if need in text else E(answered=False)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("SIMULATE_FAIL", raising=False)
    monkeypatch.delenv("LUSHA_API_KEY", raising=False)
    con = db.connect(tmp_path / "t.db")
    icp = load_icp()
    fetcher = Fetcher(con, icp.keywords, transport=httpx.MockTransport(site))
    fetcher.min_gap = 0
    return con, icp, fetcher


def test_full_loop_goes_with_evidence(env):
    con, icp, fetcher = env
    llm = FakeGemini(con)
    c = qualify_company("https://www.ledgerly.io/", icp, con, llm, fetcher)
    assert c["decision"] == "GO", c["reasons_json"]
    rows = {r["param_id"]: dict(r) for r in con.execute("SELECT * FROM answers WHERE domain='ledgerly.io'")}
    assert rows["funding_stage"]["source_url"].startswith("https://www.bing.com/news")  # Google News robots respected
    assert rows["employee_count"]["evidence_quote"] == "team of 120 people"
    assert "no certs found" in rows["audit_prep"]["reason"]
    assert rows["cloud_stack"]["outcome"] == "qualifies"
    methods = {r[0] for r in con.execute("SELECT method FROM pages")}
    assert methods <= {"http", "rss"}


def test_rerun_uses_cache_and_makes_no_calls(env):
    con, icp, fetcher = env
    qualify_company("ledgerly.io", icp, con, FakeGemini(con), fetcher)
    llm2 = FakeGemini(con)
    fetcher.client = None  # any network call would now crash
    c = qualify_company("ledgerly.io", icp, con, llm2, fetcher)
    assert c["cached"] and llm2.calls == []


def test_not_saas_short_circuits_early(env):
    con, icp, fetcher = env
    llm = FakeGemini(con, GOOD | {"company_type": ("cloud", E(value="not_saas", quote="cloud software platform"))})
    c = qualify_company("ledgerly.io", icp, con, llm, fetcher)
    assert c["decision"] == "NO-GO" and c["stop_reason"].startswith("short-circuit")
    assert llm.calls == ["profile", "extract:company_type"]  # no tokens spent after the reject


def test_retry_caps_and_fetch_cap(env):
    con, icp, fetcher = env
    nothing = {pid: ("zzz-never", E()) for pid in GOOD}
    llm = FakeGemini(con, nothing)
    c = qualify_company("ledgerly.io", icp, con, llm, fetcher)
    assert c["decision"] == "NO-GO"  # company type unanswered -> table says reject
    con2_icp = icp.model_copy(deep=True)
    con2_icp.parameters[0].if_unanswered = "human_review"
    con2_icp.limits.max_fetches_per_company = 3
    c = qualify_company("ledgerly.io", con2_icp, con, FakeGemini(con, nothing), fetcher, refresh=True)
    assert c["stop_reason"] == "fetch cap (3 pages) reached"
    per_param = {r[0]: r[1] for r in con.execute("SELECT param_id, attempts FROM answers")}
    for p in icp.parameters:
        assert per_param[p.id] <= p.retries


def test_invalid_twice_marks_unanswered(env):
    con, icp, fetcher = env
    bad = GOOD | {"company_type": ("", E(value="saas", quote="a quote that is not on the page"))}
    llm = FakeGemini(con, bad)
    c = qualify_company("ledgerly.io", icp, con, llm, fetcher)
    assert llm.calls.count("extract:company_type") == 2
    row = con.execute("SELECT reason FROM answers WHERE param_id='company_type'").fetchone()
    assert "invalid answers twice" in row[0]
    assert c["decision"] == "NO-GO"


@pytest.mark.parametrize("fail", ["gemini", "blocked", "js"])
def test_failures_degrade_to_human_review(env, monkeypatch, fail):
    con, icp, fetcher = env
    monkeypatch.setenv("SIMULATE_FAIL", fail)
    c = qualify_company("ledgerly.io", icp, con, FakeGemini(con), fetcher)
    assert c["decision"] == "HUMAN REVIEW", c["reasons_json"]
    assert any("system problem" in r for r in json.loads(c["reasons_json"]))


def test_evidence_quote_check():
    text = "Ledgerly raised a $22M Series B led by Accel."
    assert quote_in_text("raised a $22M  Series B", text)
    assert not quote_in_text("raised a $30M Series C", text)
    assert not quote_in_text("", text)


def test_json_validator_rejects_bad_label():
    p = load_icp().param("funding_stage")
    assert check_extraction(p, E(value="series_z", quote="Series B"), "Series B") is not None
    assert check_extraction(p, E(value="series_b", quote="Series B"), "a Series B round") is None


def test_pick_flash():
    names = ["models/gemini-2.0-flash", "models/gemini-2.5-flash", "models/gemini-2.5-flash-lite",
             "models/gemini-2.5-flash-image", "models/gemini-3.0-flash-preview", "models/gemini-2.5-pro"]
    assert pick_flash(names) == "gemini-3.0-flash-preview"
    assert pick_flash(names[:4]) == "gemini-2.5-flash"


def test_link_discovery_skips_login_and_prefers_real_sections():
    icp = load_icp()
    links = Fetcher.discover_links(SITE["/"], "https://ledgerly.io/", "ledgerly.io", icp.pages)
    assert links["about"] == "https://ledgerly.io/about-us"
    assert links["security"] in ("https://ledgerly.io/trust", "https://ledgerly.io/security")
    assert links["careers"] == "https://ledgerly.io/careers"
    assert not any("login" in u for u in links.values())
