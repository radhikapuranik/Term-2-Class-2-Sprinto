"""Steps 5-6: two evidence-backed pain points and a short personalised email.

Gemini writes; the code checks every draft (name, hook, length, placeholders, and that every
number or company fact is in the evidence) and retries twice before handing it to a human.
"""
import json
import re

from pydantic import BaseModel, ValidationError

from . import db
from .contact import HunterDown, find_contact
from .llm import Gemini, LLMDown, quote_in_text


class Pain(BaseModel):
    pain: str
    why_it_matters_to_this_role: str
    evidence_id: str
    evidence_quote: str


class Pains(BaseModel):
    pains: list[Pain]


class Email(BaseModel):
    subject: str
    body: str
    hook_evidence_id: str
    hook_quote: str


def evidence_bundle(con, domain: str) -> tuple[list[dict], str]:
    """Every answered ICP row with its quote and URL, numbered E1, E2..."""
    rows = con.execute("SELECT param_id, outcome, reason, evidence_quote, source_url FROM answers "
                       "WHERE domain=? AND outcome != 'unanswered' AND evidence_quote != ''", (domain,)).fetchall()
    ev = [{"id": f"E{i + 1}", "param": r[0], "finding": r[2], "quote": r[3], "url": r[4]} for i, r in enumerate(rows)]
    prof = json.loads((db.cached_company(con, domain) or {}).get("profile_json") or "{}")
    if prof.get("evidence_quote"):
        ev.append({"id": f"E{len(ev) + 1}", "param": "profile", "finding": prof.get("one_liner", ""),
                   "quote": prof["evidence_quote"], "url": f"https://{domain}/"})
    text = "\n".join(f"[{e['id']}] ({e['param']}, {e['url']}) finding: {e['finding']} | quote: \"{e['quote']}\"" for e in ev)
    return ev, text


PAINS_PROMPT = """You help Sprinto's growth lead prepare a cold email.
SPRINTO (only these facts): {facts}
PROSPECT: {company} ({domain}). {one_liner}
CONTACT: {first} {last}, {title}

EVIDENCE (the only source of truth about the prospect):
{evidence}

Give the TWO most likely compliance pain points for this person, specific to their role and to the evidence
(for example: hiring a compliance manager, enterprise customers, no SOC 2 badge yet). No generic pain points.
Each must cite one evidence_id and copy evidence_quote word for word from that evidence line's quote.
{retry_note}"""

EMAIL_PROMPT = """Write a first cold email from Sprinto to {first} {last} ({title} at {company}).
SPRINTO FACTS (the only claims you may make about Sprinto): {facts}
EVIDENCE about {company} (the only facts you may state about them):
{evidence}
PAIN POINTS: {pains}

Rules:
- Start the body with "Hi {first},". Do not write a sign-off or signature; it is added later.
- Body under {max_body} words. Subject under {max_subj_plus} words, plain, no clickbait.
- Open with ONE specific hook from the EVIDENCE (give its id in hook_evidence_id and copy its quote word for word
  into hook_quote) and refer to it clearly in the body.
- Link the hook to one pain point and at most one Sprinto fact.
- End with one clear, low-pressure ask (for example: "Worth a short chat?"). No numbers in the ask.
- No hype, no exclamation marks, no invented facts. Use only numbers that appear in EVIDENCE or SPRINTO FACTS.
{retry_note}"""

PLACEHOLDER = re.compile(r"\[[^\]]*\]|\{[^}]*\}|<[^>]+>|\bX{2,}\b|lorem ipsum|insert |your name|company name", re.I)
STOP = {"with", "that", "this", "from", "your", "have", "their", "about", "into", "they", "will", "been", "were"}
ALWAYS_OK = {"hi", "hello", "i", "i'm", "i've", "i'd", "sprinto", "soc", "iso", "gdpr", "hipaa", "pci", "dss", "aws",
             "azure", "gcp", "trust", "center", "grc", "ai", "saas", "best", "thanks", "regards", "cheers", "ps",
             "series", "ceo", "cto", "ciso", "vp", "type", "ii"}


def words(s: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][\w'’&.-]*", s)


def validate_email(subject, body, hook_quote, first_name, company, evidence_text, facts_text, max_body, max_subj) -> list[str]:
    """Problems with a draft; an empty list means it may go to the human reviewer."""
    problems = []
    if not re.search(rf"\b{re.escape(first_name)}\b", body):
        problems.append(f"does not address {first_name} by name")
    if len(words(body)) > max_body:
        problems.append(f"body is {len(words(body))} words, limit {max_body}")
    if len(words(subject)) > max_subj:
        problems.append(f"subject is {len(words(subject))} words, limit {max_subj}")
    if PLACEHOLDER.search(subject + " " + body):
        problems.append(f"placeholder text: {PLACEHOLDER.search(subject + ' ' + body).group(0)!r}")
    if not quote_in_text(hook_quote, evidence_text):
        problems.append("hook_quote is not in the evidence")
    hook_words = {w.lower() for w in words(hook_quote) if len(w) >= 4 and w.lower() not in STOP}
    if hook_words and len(hook_words & {w.lower() for w in words(body)}) < min(2, len(hook_words)):
        problems.append("the body does not clearly mention the hook")
    allowed = (evidence_text + " " + facts_text + " " + company + " " + first_name).lower()
    for num in set(re.findall(r"\d[\d,.]*\+?%?", subject + " " + body)):
        if num.rstrip(".,") not in allowed:
            problems.append(f"number {num!r} is not in the evidence")
    for sentence in re.split(r"(?<=[.!?:])\s+|\n+", subject + "\n" + body):
        for w in words(sentence)[1:]:  # skip the sentence's first word, it is capitalised anyway
            if w[0].isupper() and w.lower().strip(".'’") not in ALWAYS_OK and w.lower().strip(".'’") not in allowed:
                problems.append(f"'{w}' is a name or fact not found in the evidence")
    if "!" in body:
        problems.append("no exclamation marks")
    return problems


def _evidence_ok(pains: Pains, evidence: list[dict]) -> str | None:
    if len(pains.pains) != 2:
        return f"need exactly 2 pain points, got {len(pains.pains)}"
    by_id = {e["id"]: e for e in evidence}
    for p in pains.pains:
        if p.evidence_id not in by_id or not quote_in_text(p.evidence_quote, by_id[p.evidence_id]["quote"]):
            return f"pain '{p.pain[:40]}' does not quote evidence {p.evidence_id} word for word"
    if pains.pains[0].pain.strip().lower() == pains.pains[1].pain.strip().lower():
        return "the two pain points are the same"
    return None


def draft_for(con, domain: str, llm: Gemini, rules: dict, redraft: bool = False) -> dict:
    """Steps 4-6 for one company. Always stores a row in drafts; never raises for one company."""
    existing = db.get_draft(con, domain)
    if existing and not redraft:
        return existing
    company = db.cached_company(con, domain)
    name = company["name"] if company else domain
    prof = json.loads((company or {}).get("profile_json") or "{}")
    cfg = rules["email"]
    facts = " ".join(rules["sprinto_facts"])

    def stop(notes, contact=None, pains=None, subject="", body="", hook=""):
        db.save_draft(con, domain, contact, pains, subject, body, hook, "human_review", notes)
        return db.get_draft(con, domain)

    try:
        contact, why = find_contact(con, domain, rules["contact_priority"])
    except HunterDown as e:
        return stop(f"Contact lookup failed: {e}")
    if contact is None:
        return stop(f"No point of contact: {why}")

    evidence, ev_text = evidence_bundle(con, domain)
    if not evidence:
        return stop("No evidence quotes to write from", contact)
    base = dict(facts=facts, company=name, domain=domain, one_liner=prof.get("one_liner", ""),
                first=contact["first_name"], last=contact["last_name"], title=contact["title"], evidence=ev_text)
    try:
        pains, note, problem = None, "", None
        for _ in range(cfg["retries"] + 1):
            try:
                pains = llm.generate_json(PAINS_PROMPT.format(**base, retry_note=note), Pains, domain, "pains")
                problem = _evidence_ok(pains, evidence)
            except ValidationError:
                problem = "output did not match the schema"
            if problem is None:
                break
            note = f"\nYour previous answer was rejected: {problem}. Fix it."
        if problem:
            return stop(f"Pain points failed checks twice: {problem}", contact)
        pain_list = [p.model_dump() | {"url": next(e["url"] for e in evidence if e["id"] == p.evidence_id)}
                     for p in pains.pains]

        sig = cfg["sender_signature"]
        max_body = cfg["max_words"] - len(words(sig)) - 1
        note, problems, em = "", [], None
        for _ in range(cfg["retries"] + 1):
            prompt = EMAIL_PROMPT.format(**base, pains=json.dumps([p.pain for p in pains.pains]), max_body=max_body,
                                         max_subj_plus=cfg["max_subject_words"] + 1, retry_note=note)
            try:
                em = llm.generate_json(prompt, Email, domain, "email")
                problems = validate_email(em.subject, em.body, em.hook_quote, contact["first_name"], name,
                                          ev_text, facts, max_body, cfg["max_subject_words"])
            except ValidationError:
                problems = ["output did not match the schema"]
            if not problems:
                break
            note = "\nYour previous draft was rejected: " + "; ".join(problems[:6]) + ". Rewrite it."
    except LLMDown as e:
        return stop(f"Gemini unavailable: {e}", contact)

    body = f"{em.body.strip()}\n\nBest,\n{sig}" if em else ""
    if problems:
        return stop("Email failed checks after 2 retries: " + "; ".join(problems), contact, pain_list,
                    em.subject if em else "", body, em.hook_quote if em else "")
    db.save_draft(con, domain, contact, pain_list, em.subject.strip(), body, em.hook_quote, "draft", "passed all checks")
    return db.get_draft(con, domain)
