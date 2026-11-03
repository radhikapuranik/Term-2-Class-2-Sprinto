"""Gemini Flash wrapper. Gemini only extracts, explains and writes; it never decides GO / NO-GO.

All output is JSON with an enforced schema, validated by pydantic, and every evidence quote
must appear in the text we supplied.
"""
import re
import unicodedata

from pydantic import BaseModel, ValidationError

from . import db
from .config import env, simulate
from .icp import Answer, Parameter


class LLMDown(Exception):
    """Gemini could not be reached (no key, outage, quota, or SIMULATE_FAIL=gemini)."""


class Extraction(BaseModel):
    """Schema Gemini must fill for one ICP parameter. No defaults: Gemini's schema format dislikes them."""
    answered: bool
    value: str | None
    number_min: int | None
    number_max: int | None
    items: list[str]
    evidence_quote: str
    confidence: float


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[‐-―]", "-", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_in_text(quote: str, text: str) -> bool:
    """The evidence check: the quote must be a real substring of the supplied text."""
    q = _norm(quote).strip(" .\"'")
    return len(q) >= 4 and q in _norm(text)


class Gemini:
    def __init__(self, con, model: str | None = None):
        self.con = con
        self.model = model or env("GEMINI_MODEL")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai
            if not env("GEMINI_API_KEY"):
                raise LLMDown("GEMINI_API_KEY is empty in .env.local")
            self._client = genai.Client(api_key=env("GEMINI_API_KEY"))
        return self._client

    def generate_json(self, prompt: str, schema: type[BaseModel], domain: str, purpose: str):
        """Call Gemini with an enforced JSON schema. Raises LLMDown or ValidationError."""
        if simulate("gemini"):
            raise LLMDown("SIMULATE_FAIL=gemini")
        from google.genai import types
        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema=schema, temperature=0.2),
            )
        except LLMDown:
            raise
        except Exception as e:
            db.log_llm(self.con, domain, purpose, self.model, 0, 0, False, type(e).__name__)
            raise LLMDown(f"Gemini error: {type(e).__name__}") from e
        u = resp.usage_metadata
        tin, tout = (u.prompt_token_count or 0, u.candidates_token_count or 0) if u else (0, 0)
        try:
            obj = schema.model_validate_json(resp.text or "")
        except ValidationError:
            db.log_llm(self.con, domain, purpose, self.model, tin, tout, False, "invalid JSON")
            raise
        db.log_llm(self.con, domain, purpose, self.model, tin, tout, True)
        return obj


PROMPT = """You extract one fact for B2B sales research about the company at {domain}.
Answer ONLY from the TEXT below (taken from {source}). Do not use outside knowledge. Do not guess.

QUESTION ({name}): {ask}
Allowed labels for "value": {allowed}

Rules:
- evidence_quote: copy one short phrase or sentence WORD FOR WORD from TEXT that supports your answer.
- If TEXT does not answer the question, set answered=false, value=null and evidence_quote="".
- Make sure facts are about {domain} itself, not another company with a similar name.
- confidence: 0 to 1.
{retry_note}
TEXT:
<<<
{text}
>>>"""

CERT_PATTERNS = {"SOC 2": r"soc\s?-?\s?2", "ISO 27001": r"iso\s?/?\s?(iec\s?)?27001", "GDPR": r"\bgdpr\b",
                 "HIPAA": r"\bhipaa\b"}


def check_extraction(p: Parameter, ex: Extraction, text: str) -> str | None:
    """Return why an extraction is invalid, or None if it is fine."""
    if not ex.answered:
        return None
    if p.allowed and ex.value not in p.allowed and p.kind == "category":
        return f'value "{ex.value}" is not one of {p.allowed}'
    absence = p.kind == "audit" and not ex.items and ex.value != "hiring_audit_role"
    if not absence and not quote_in_text(ex.evidence_quote, text):
        return "evidence_quote does not appear in TEXT word for word"
    return None


def extract_param(llm: Gemini, p: Parameter, text: str, source: str, domain: str,
                  tries: int) -> tuple[Answer | None, int, str | None]:
    """Ask Gemini about one parameter. Returns (answer or None, invalid_count, last_problem).

    Raises LLMDown when Gemini is unreachable.
    """
    invalid, note, problem = 0, "", None
    for _ in range(tries):
        prompt = PROMPT.format(domain=domain, source=source, name=p.name, ask=p.ask,
                               allowed=p.allowed or "free text, or null", retry_note=note, text=text)
        try:
            ex = llm.generate_json(prompt, Extraction, domain, f"extract:{p.id}")
            problem = check_extraction(p, ex, text)
        except ValidationError:
            problem = "output was not valid JSON for the schema"
        if problem is None:
            break
        invalid += 1
        note = f"\nYour previous answer was rejected because: {problem}. Fix it.\n"
    else:
        return None, invalid, problem
    if not ex.answered:
        return None, invalid, None
    items = list(ex.items)
    if p.kind == "audit":  # code double-checks certs so a missed badge never reads as "no certs"
        for cert, pat in CERT_PATTERNS.items():
            if re.search(pat, text, re.I) and cert not in items and _claims(text, pat):
                items.append(cert)
    return Answer(value=ex.value, number_min=ex.number_min, number_max=ex.number_max, items=items,
                  evidence_quote=ex.evidence_quote, confidence=ex.confidence, page_chars=len(text)), invalid, None


def _claims(text: str, pat: str) -> bool:
    """A cert mention counts as held only if it is not in a job ad ('own our first SOC 2 audit')."""
    for line in text.splitlines():
        if re.search(pat, line, re.I) and not re.search(r"first|achieve|working towards|own our|lead our|prepare", line, re.I):
            return True
    return False
