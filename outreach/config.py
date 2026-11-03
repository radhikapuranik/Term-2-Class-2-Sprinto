"""Settings from .env.local. Keys are read here and never printed."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.local")

DB_PATH = Path(os.getenv("OUTREACH_DB", ROOT / "data" / "outreach.db"))
ICP_PATH = ROOT / "icp.yaml"
USER_AGENT = "SprintoOutreachResearch/0.1 (student project; polite crawler)"


def env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def simulate(kind: str) -> bool:
    """SIMULATE_FAIL=gemini,hunter,blocked,js turns on failure simulation."""
    return kind in {s.strip().lower() for s in env("SIMULATE_FAIL").split(",") if s.strip()}
