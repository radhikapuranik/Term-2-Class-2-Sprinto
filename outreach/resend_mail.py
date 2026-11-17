"""Sending through Resend's HTTPS API with RESEND_API_KEY. The key is only ever put in a request header."""
import httpx

from .config import env, simulate

API = "https://api.resend.com"
SENDER = "Sprinto Outreach (test) <onboarding@resend.dev>"  # Resend's shared test sender


class SendFailed(Exception):
    """Resend refused or could not be reached. The draft goes back to HUMAN REVIEW."""


def _explain(status: int, body: dict) -> str:
    """Turn a Resend error into plain words (never includes the key)."""
    msg = str(body.get("message", ""))
    if status == 403 and ("own email" in msg or "verify a domain" in msg or "testing emails" in msg):
        return ("Resend's free test sender can only deliver to the address you signed up to Resend with. "
                f"Set TEST_RECIPIENT in .env.local to that exact address. Resend said: {msg.split('. ')[0]}")
    if status in (401, 403):
        return "Resend did not accept RESEND_API_KEY. Check the key in .env.local (it starts with re_)."
    if status == 422:
        return f"Resend rejected the email's contents: {msg}"
    if status == 429:
        return "Resend's rate limit was hit. Wait a minute and approve again."
    return f"Resend returned HTTP {status}: {msg}"


def send(to: str, subject: str, text: str, html: str, headers: dict | None = None,
         transport: httpx.BaseTransport | None = None) -> str:
    """Send one email. Returns Resend's email id. Raises SendFailed with an easy explanation."""
    key = env("RESEND_API_KEY")
    if simulate("resend"):
        raise SendFailed("simulated Resend outage (SIMULATE_FAIL=resend)")
    if not key:
        raise SendFailed("RESEND_API_KEY is empty in .env.local, so nothing can be sent")
    payload = {"from": SENDER, "to": [to], "subject": subject, "text": text, "html": html}
    if headers:
        payload["headers"] = headers
    try:
        with httpx.Client(transport=transport, timeout=20) as c:
            r = c.post(f"{API}/emails", json=payload, headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as e:
        raise SendFailed(f"could not reach Resend ({type(e).__name__})") from None
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code != 200:
        raise SendFailed(_explain(r.status_code, body))
    return body.get("id", "")


def check_key(transport: httpx.BaseTransport | None = None) -> str:
    """Harmless key check (lists domains, sends nothing). A send-only key counts as working."""
    with httpx.Client(transport=transport, timeout=10) as c:
        r = c.get(f"{API}/domains", headers={"Authorization": f"Bearer {env('RESEND_API_KEY')}"})
    if r.status_code == 200 or (r.status_code == 401 and "restricted" in r.text):
        return "works"
    return f"does not work, check the key (HTTP {r.status_code})"
