"""Load the ICP table from icp.yaml and apply its rules to extracted answers.

Gemini only extracts answers. Every qualify / reject / unanswered rule lives here and in icp.yaml.
"""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from .config import ICP_PATH

Outcome = Literal["qualifies", "rejects", "neutral", "unanswered"]


class Parameter(BaseModel):
    id: str
    name: str
    qualifying_answer: str
    where_to_look: list[str]
    sufficiency: str
    retries: int
    if_unanswered: Literal["reject", "human_review", "skip_low_weight", "proceed"]
    auto_reject: str | None = None
    weight: Literal["hard", "low"]
    kind: Literal["category", "range", "audit", "clients", "cloud"]
    ask: str
    keywords: list[str] = []
    allowed: list[str] = []
    qualify_values: list[str] = []
    reject_values: list[str] = []
    qualify_range: tuple[int, int] | None = None
    required_certs: list[str] = []
    min_page_chars: int = 0
    min_clients: int = 0
    qualify_items: list[str] = []


class Limits(BaseModel):
    max_fetches_per_company: int
    max_seconds_per_company: int
    max_tokens_per_call: int
    invalid_llm_tries: int


class PageType(BaseModel):
    paths: list[str]
    link_words: list[str]


class ICP(BaseModel):
    limits: Limits
    keywords: list[str]
    parameters: list[Parameter]
    pages: dict[str, PageType]

    def param(self, pid: str) -> Parameter:
        return next(p for p in self.parameters if p.id == pid)


def load_icp(path: Path = ICP_PATH) -> ICP:
    return ICP.model_validate(yaml.safe_load(Path(path).read_text()))


class Answer(BaseModel):
    """What Gemini extracted for one parameter (already quote-checked)."""
    value: str | None = None
    number_min: int | None = None
    number_max: int | None = None
    items: list[str] = []
    evidence_quote: str = ""
    confidence: float = 0.0
    page_chars: int = 0  # length of the cleaned page the answer came from


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def evaluate(p: Parameter, a: Answer) -> tuple[Outcome, str]:
    """Apply one ICP row to one answer. Returns (outcome, plain-English reason)."""
    if p.kind == "category":
        if a.value in p.reject_values:
            return "rejects", f"{a.value} matches auto-reject rule '{p.auto_reject}'"
        if a.value in p.qualify_values:
            return "qualifies", f"{a.value} matches '{p.qualifying_answer}'"
        if a.value in p.allowed:
            return "neutral", f"{a.value} is not '{p.qualifying_answer}'"
        return "unanswered", "no usable value"

    if p.kind == "range":
        lo, hi = a.number_min, a.number_max if a.number_max is not None else a.number_min
        if lo is None:
            return "unanswered", "no number found"
        qlo, qhi = p.qualify_range
        if qlo <= lo and hi <= qhi:
            return "qualifies", f"{lo}-{hi} is inside {qlo}-{qhi}"
        if hi < qlo or lo > qhi:
            return "rejects", f"{lo}-{hi} is clearly outside {qlo}-{qhi}"
        return "neutral", f"{lo}-{hi} overlaps {qlo}-{qhi} but is not inside it"

    if p.kind == "audit":
        if a.value == "hiring_audit_role":
            return "qualifies", "hiring for an audit or compliance role"
        found = {_norm(c) for c in a.items}
        required = [c for c in p.required_certs if _norm(c) in found]
        if len(required) == len(p.required_certs):
            return "rejects", f"already shows {', '.join(p.required_certs)}"
        if not a.items:
            if a.page_chars >= p.min_page_chars:
                return "qualifies", f"page checked ({a.page_chars} chars) and no certs found"
            return "unanswered", f"page too thin to trust 'no certs' ({a.page_chars} chars)"
        return "neutral", f"shows some certs ({', '.join(a.items)}), not all of {', '.join(p.required_certs)}"

    if p.kind == "clients":
        if a.number_min is not None and a.number_min > p.min_clients:
            return "qualifies", f"claims {a.number_min} clients (> {p.min_clients})"
        if a.value == "enterprise_clients":
            return "qualifies", f"enterprise logos: {', '.join(a.items[:5])}"
        if a.items or a.number_min is not None:
            return "neutral", "clients found but under the bar"
        return "unanswered", "no clients found"

    if p.kind == "cloud":
        hits = [c for c in p.qualify_items if _norm(c) in {_norm(i) for i in a.items}]
        if hits:
            return "qualifies", f"uses {', '.join(hits)}"
        if a.items:
            return "neutral", f"uses {', '.join(a.items)}, not {' or '.join(p.qualify_items)}"
        return "unanswered", "no cloud named"

    raise ValueError(p.kind)


Decision = Literal["GO", "NO-GO", "HUMAN REVIEW"]


def decide(icp: ICP, results: dict[str, dict]) -> tuple[Decision, list[str]]:
    """Turn per-parameter results into GO / NO-GO / HUMAN REVIEW.

    results[pid] = {"outcome": Outcome, "reason": str, "error": str | None}
    """
    reasons, review = [], []
    for p in icp.parameters:
        r = results.get(p.id, {"outcome": "unanswered", "reason": "not checked", "error": None})
        line = f"{p.name}: {r['outcome']} - {r['reason']}"
        reasons.append(line)
        if r["outcome"] == "rejects":
            return "NO-GO", reasons + [f"Auto-reject on {p.name}"]
        if r["outcome"] == "unanswered":
            if r.get("error") and p.weight == "hard":
                review.append(f"{p.name} not answered because of a system problem: {r['error']}")
            elif p.if_unanswered == "reject":
                return "NO-GO", reasons + [f"{p.name} unanswered, table says reject"]
            elif p.if_unanswered == "human_review":
                review.append(f"{p.name} unanswered")
        elif r["outcome"] == "neutral" and p.weight == "hard":
            review.append(f"{p.name} answered but not qualifying")
    if review:
        return "HUMAN REVIEW", reasons + review
    return "GO", reasons
