"""Step 4: find the one point of contact with Hunter.io Domain Search.

Free tier: 25 searches a month, so every search is cached forever (even across --refresh).
Only the chosen person's work name, title and work email are kept; everyone else is discarded.
"""
import re
from pathlib import Path

import httpx
import yaml

from . import db
from .config import ROOT, env, simulate

HUNTER = "https://api.hunter.io/v2/domain-search"


class HunterDown(Exception):
    pass


def load_rules(path: Path = ROOT / "outreach.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text())


def choose_contact(people: list[dict], priority: list[dict]) -> dict | None:
    """Best person by title tier, then by Hunter confidence. People without a name or title are skipped."""
    best = None
    for person in people:
        title = person.get("position") or ""
        if not (person.get("first_name") and title and person.get("value")):
            continue
        for rank, tier in enumerate(priority):
            if re.search(tier["pattern"], title, re.I):
                key = (-rank, person.get("confidence") or 0)
                if best is None or key > best[0]:
                    best = (key, tier["tier"], person)
                break
    if best is None:
        return None
    (_, conf), tier, p = best
    return {
        "first_name": p["first_name"], "last_name": p.get("last_name") or "", "title": p["position"],
        "email": p["value"], "confidence": conf, "tier": tier,
        "why": f"{p['position']} matches priority tier '{tier}' (Hunter confidence {conf}%)",
        "source": f"Hunter.io Domain Search, {len(p.get('sources') or [])} public source(s)",
    }


def find_contact(con, domain: str, priority: list[dict]) -> tuple[dict | None, str]:
    """Return (contact or None, reason). Never searches a domain twice."""
    cached = db.cached_api(con, f"hunter:{domain}")
    if cached is not None:
        return cached.get("contact"), cached.get("reason", "") + " (cached)"
    if simulate("hunter"):
        raise HunterDown("SIMULATE_FAIL=hunter")
    if not env("HUNTER_API_KEY"):
        raise HunterDown("HUNTER_API_KEY is empty in .env.local")
    try:
        r = httpx.get(HUNTER, params={"domain": domain, "api_key": env("HUNTER_API_KEY"), "limit": 10,
                                      "type": "personal", "seniority": "executive,senior"}, timeout=20)
    except httpx.HTTPError as e:
        raise HunterDown(f"Hunter unreachable: {type(e).__name__}") from e
    if r.status_code != 200:
        raise HunterDown(f"Hunter HTTP {r.status_code}")  # not cached, so a quota or outage can be retried later
    people = r.json().get("data", {}).get("emails", [])
    contact = choose_contact(people, priority)
    reason = contact["why"] if contact else f"Hunter returned {len(people)} people, none with a target title"
    db.save_api(con, f"hunter:{domain}", {"contact": contact, "reason": reason, "people_seen": len(people)})
    return contact, reason
