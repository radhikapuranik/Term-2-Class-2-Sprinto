"""Polite page fetching: robots.txt, one request per second per host, HTML first, browser fallback.

Every fetched page is cleaned and cached in SQLite, so a page is never fetched twice.
"""
import re
import threading
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from . import db
from .cleaner import clean_html, needs_js
from .config import USER_AGENT, simulate

SLOW_HOSTS = {"api.gdeltproject.org": 5}  # GDELT asks for one request every 5 seconds
LOGIN_PATH = re.compile(r"login|log-in|signin|sign-in|signup|sign-up|/auth|/account|linkedin\.com", re.I)


def normalize_domain(d: str) -> str:
    d = d.strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    return d.removeprefix("www.")


def same_site(url: str, domain: str) -> bool:
    host = urlparse(url).hostname or ""
    return host == domain or host.endswith("." + domain)


class Fetcher:
    def __init__(self, con, keywords: list[str], transport: httpx.BaseTransport | None = None):
        self.con = con
        self.keywords = keywords
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=10,
                                   transport=transport)
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}
        self._lock = threading.Lock()
        self.min_gap = 1.0  # seconds between requests to the same host

    # --- politeness -----------------------------------------------------------

    def _wait_turn(self, host: str) -> None:
        with self._lock:
            need = self.min_gap * SLOW_HOSTS.get(host, 1)
            gap = time.time() - self._last_hit.get(host, 0)
            if gap < need:
                time.sleep(need - gap)
            self._last_hit[host] = time.time()

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                self._wait_turn(p.netloc)
                r = self.client.get(base + "/robots.txt", timeout=5)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])  # no robots.txt reachable: allowed by convention
            self._robots[base] = rp
        return self._robots[base].can_fetch(USER_AGENT, url)

    def get(self, url: str, timeout: float = 10) -> httpx.Response:
        self._wait_turn(urlparse(url).netloc)
        return self.client.get(url, timeout=max(2.0, min(10.0, timeout)))

    # --- pages ------------------------------------------------------------------

    def fetch_page(self, domain: str, page_type: str, url: str, time_left: float = 30) -> tuple[dict, bool, str]:
        """Return (page, was_network_fetch, raw_html). page['status'] is ok | blocked | error | js_failed."""
        cached = db.cached_page(self.con, url)
        if cached:
            return cached, False, ""

        def done(status, text="", method="http", raw=0, error=None, html=""):
            db.save_page(self.con, url, domain, page_type, method, status, text, raw, error)
            return db.cached_page(self.con, url), True, html

        if LOGIN_PATH.search(url):
            return done("blocked", error="login-gated page, skipped by rule")
        if simulate("blocked"):
            return done("blocked", error="SIMULATE_FAIL=blocked")
        if not self.allowed(url):
            return done("blocked", error="robots.txt disallows this page")
        try:
            r = self.get(url, timeout=time_left)
        except httpx.HTTPError as e:
            return done("error", error=f"{type(e).__name__}")
        if r.status_code in (401, 403, 429):
            return done("blocked", error=f"HTTP {r.status_code}")
        if r.status_code >= 400:
            return done("error", error=f"HTTP {r.status_code}")
        if not same_site(str(r.url), domain):
            return done("error", error=f"redirected off-site to {r.url.host}")
        html, method = r.text, "http"
        if 'type="password"' in html and "login" in str(r.url).lower():
            return done("blocked", error="login page")
        if simulate("js") or needs_js(html):
            html, err = self._render(url, time_left)
            method = "browser"
            if err:
                return done("js_failed", method=method, error=err)
        text = clean_html(html, self.keywords)
        return done("ok", text, method, len(html), html=html)

    def _render(self, url: str, time_left: float) -> tuple[str, str | None]:
        """Playwright fallback for JavaScript-only pages. 10-15x more expensive than plain HTML."""
        if simulate("js"):
            return "", "JavaScript-only page and browser fallback failed (SIMULATE_FAIL=js)"
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(user_agent=USER_AGENT)
                self._wait_turn(urlparse(url).netloc)
                page.goto(url, timeout=int(max(3, min(15, time_left)) * 1000), wait_until="networkidle")
                html = page.content()
                browser.close()
            return html, None
        except Exception as e:  # browser missing, timeout, crash: degrade, never crash the run
            return "", f"browser fallback failed: {type(e).__name__}"

    # --- link discovery ---------------------------------------------------------

    @staticmethod
    def discover_links(html: str, base_url: str, domain: str, pages: dict) -> dict[str, str]:
        """Map page types (about, security, careers...) to links found on the homepage."""
        soup = BeautifulSoup(html, "lxml")
        best: dict[str, tuple[int, int, str]] = {}
        for a in soup.find_all("a", href=True):
            url = urljoin(base_url, a["href"]).split("#")[0].split("?")[0]
            if not same_site(url, domain) or LOGIN_PATH.search(url):
                continue
            parsed = urlparse(url)
            segs = [x for x in parsed.path.lower().split("/") if x]
            first = segs[0] if segs else ""
            host_word = parsed.hostname.split(".")[0]  # e.g. trust.acme.com
            text = a.get_text(" ", strip=True).lower()
            for ptype, spec in pages.items():
                for w in spec.link_words:
                    # strong: /careers, /about-us or careers.acme.com; weak: short menu label "Careers"
                    if first.startswith(w) or host_word.startswith(w):
                        score = 2
                    elif len(text.split()) <= 3 and text.startswith(w):
                        score = 1
                    else:
                        continue
                    cand = (score, -len(segs), url)
                    if ptype not in best or cand[:2] > best[ptype][:2]:
                        best[ptype] = cand
        return {k: v[2] for k, v in best.items()}
