"""Steps 1-3: scrape, extract, and qualify one company with a capped agent loop."""
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

from pydantic import BaseModel

from . import db
from .cleaner import focus
from .fetcher import Fetcher, normalize_domain
from .icp import ICP, decide, evaluate
from .llm import Gemini, LLMDown, extract_param, quote_in_text
from .sources import fetch_lusha, fetch_news


class Profile(BaseModel):
    name: str
    one_liner: str
    evidence_quote: str


PROFILE_PROMPT = """From the TEXT of the homepage of {domain}, give the company's short brand name and one plain
sentence (max 25 words) on what it sells and to whom. evidence_quote: copy a phrase from TEXT word for word.
TEXT:
<<<
{text}
>>>"""


@dataclass
class ParamState:
    attempts: int = 0
    tried: set = field(default_factory=set)
    invalid: int = 0
    result: dict | None = None      # final qualifies / rejects
    neutral: dict | None = None     # best non-qualifying answer so far
    errors: list = field(default_factory=list)
    gave_up: str | None = None


class CapReached(Exception):
    pass


class Run:
    """One company's qualification run, with its hard caps."""

    def __init__(self, domain, icp: ICP, con, llm: Gemini, fetcher: Fetcher):
        self.domain, self.icp, self.con, self.llm, self.fetcher = domain, icp, con, llm, fetcher
        self.start = time.time()
        self.fetches = 0
        self.sources: dict[str, dict | None] = {}
        self.links: dict[str, str] = db.cached_api(con, f"links:{domain}") or {}
        self.name = domain.split(".")[0].capitalize()
        self.stop_reason = ""

    def log(self, event: str) -> None:
        db.log(self.con, self.domain, event)

    def time_left(self) -> float:
        return self.icp.limits.max_seconds_per_company - (time.time() - self.start)

    # --- getting a source (page, news or Lusha) ----------------------------------

    def source(self, kind: str) -> dict | None:
        """Return a page dict, or None when the source is not available (e.g. no Lusha key)."""
        if kind in self.sources:
            return self.sources[kind]
        if self.time_left() <= 0:
            raise CapReached(f"time cap ({self.icp.limits.max_seconds_per_company}s) reached")
        if kind == "lusha":
            page = fetch_lusha(self.con, self.domain)
        elif kind == "google_news":
            self._need_fetch()
            page, net = fetch_news(self.fetcher, self.domain, self.name, self.time_left())
            self.fetches += net
        else:
            url = self.links.get(kind) or urljoin(f"https://{self.domain}", self.icp.pages[kind].paths[0])
            self._need_fetch(url)
            page, net, html = self.fetcher.fetch_page(self.domain, kind, url, self.time_left())
            self.fetches += net
            if kind == "home" and html:
                self.links = Fetcher.discover_links(html, page["url"], self.domain, self.icp.pages)
                db.save_api(self.con, f"links:{self.domain}", self.links)
            if net:
                self.log(f"fetched {kind} {url} via {page['method']}: {page['status']} {page['error'] or ''}")
        self.sources[kind] = page
        return page

    def _need_fetch(self, url: str | None = None) -> None:
        if url and db.cached_page(self.con, url):
            return
        if self.fetches >= self.icp.limits.max_fetches_per_company:
            raise CapReached(f"fetch cap ({self.icp.limits.max_fetches_per_company} pages) reached")

    # --- step 2: profile ------------------------------------------------------------

    def profile(self) -> dict:
        home = self.source("home")
        if not home or home["status"] != "ok":
            return {"name": self.name, "one_liner": "", "evidence_quote": ""}
        title = home["clean_text"].splitlines()[0] if home["clean_text"] else ""
        try:
            text = focus(home["clean_text"], self.icp.keywords, 2000)
            p = self.llm.generate_json(PROFILE_PROMPT.format(domain=self.domain, text=text), Profile, self.domain, "profile")
            if quote_in_text(p.evidence_quote, text):
                self.name = p.name or self.name
                return p.model_dump()
        except (LLMDown, ValueError):
            pass
        return {"name": self.name, "one_liner": title, "evidence_quote": title}

    # --- step 3: the loop -------------------------------------------------------

    def qualify(self) -> tuple[str, list[str], dict]:
        params = self.icp.parameters
        state = {p.id: ParamState() for p in params}
        gemini_down = None
        try:
            prof = self.profile()
            while True:
                if self.time_left() <= 0:
                    raise CapReached(f"time cap ({self.icp.limits.max_seconds_per_company}s) reached")
                todo = None
                for p in params:  # table order: hard filters first, so rejects stop spending early
                    s = state[p.id]
                    if s.result or s.gave_up or s.attempts >= p.retries:
                        continue
                    nxt = next((k for k in p.where_to_look if k not in s.tried), None)
                    if nxt is None:
                        continue
                    todo = (p, s, nxt)
                    break
                if todo is None:
                    self.stop_reason = "every parameter answered or out of retries"
                    break
                p, s, kind = todo
                s.tried.add(kind)
                page = self.source(kind)
                if page is None:  # source not configured, try the next one without using an attempt
                    continue
                s.attempts += 1
                if page["status"] != "ok":
                    s.errors.append(f"{kind}: {page['error']}")
                    continue
                text = focus(page["clean_text"], p.keywords + self.icp.keywords, self.icp.limits.max_tokens_per_call)
                left = self.icp.limits.invalid_llm_tries - s.invalid
                ans, bad, problem = extract_param(self.llm, p, text, page["url"], self.domain, left)
                s.invalid += bad
                if s.invalid >= self.icp.limits.invalid_llm_tries:
                    s.gave_up = f"Gemini gave invalid answers twice ({problem})"
                    self.log(f"{p.id}: {s.gave_up}")
                    continue
                if ans is None:
                    continue
                outcome, reason = evaluate(p, ans)
                rec = {"outcome": outcome, "reason": reason, "answer": ans.model_dump(), "quote": ans.evidence_quote,
                       "url": page["url"], "attempts": s.attempts, "error": None}
                self.log(f"{p.id} from {kind}: {outcome} ({reason})")
                if outcome in ("qualifies", "rejects"):
                    s.result = rec
                    if outcome == "rejects" and p.auto_reject:
                        self.stop_reason = f"short-circuit: {p.name} {reason}"
                        break
                elif outcome == "neutral":
                    s.neutral = rec
        except CapReached as e:
            self.stop_reason = str(e)
        except LLMDown as e:
            gemini_down = str(e)
            self.stop_reason = f"Gemini unavailable: {e}"
        self.log(f"loop stopped: {self.stop_reason}")

        results = {}
        for p in params:
            s = state[p.id]
            r = s.result or s.neutral
            if r is None:
                why = s.gave_up or (f"tried {s.attempts} of {p.retries} sources" if s.attempts else "no source tried")
                err = gemini_down or ("; ".join(s.errors) if s.errors and len(s.errors) == s.attempts else None)
                if self.stop_reason.startswith(("fetch cap", "time cap")) and s.attempts < p.retries:
                    why += f", stopped by {self.stop_reason}"
                r = {"outcome": "unanswered", "reason": why + (f" ({err})" if err else ""), "answer": None,
                     "quote": "", "url": "", "attempts": s.attempts, "error": err}
            results[p.id] = r
            db.save_answer(self.con, self.domain, p.id, r)
        decision, reasons = decide(self.icp, results)
        if self.stop_reason.startswith("short-circuit"):
            decision = "NO-GO"
        return decision, reasons, prof


def qualify_company(domain: str, icp: ICP, con, llm: Gemini, fetcher: Fetcher, refresh: bool = False) -> dict:
    """Cache first, then run the loop. Never raises for one bad company."""
    domain = normalize_domain(domain)
    if not refresh and (hit := db.cached_company(con, domain)):
        db.log(con, domain, "cache hit: reused stored decision, no new fetches or Gemini calls")
        return hit | {"cached": True}
    db.clear_company(con, domain)
    run = Run(domain, icp, con, llm, fetcher)
    try:
        decision, reasons, prof = run.qualify()
    except Exception as e:  # last line of defence: one company must never crash the batch
        decision, reasons, prof = "HUMAN REVIEW", [f"Unexpected error: {type(e).__name__}: {e}"], {"name": run.name}
        run.stop_reason = "crashed safely"
    elapsed = round(time.time() - run.start, 1)
    db.save_company(con, domain, prof.get("name", run.name), prof, decision, reasons, elapsed, run.stop_reason)
    return db.cached_company(con, domain) | {"cached": False}
