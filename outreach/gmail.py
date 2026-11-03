"""Gmail API with OAuth, send-only scope. The token stays in secrets/ and is never printed."""
import base64
import json
import os
import shutil
from pathlib import Path

import httpx

from .config import ROOT

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]  # can send, cannot read your mail
SECRETS = ROOT / "secrets"
CLIENT_FILE = SECRETS / "gmail_client_secret.json"
TOKEN_FILE = SECRETS / "gmail_token.json"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class GmailNotReady(Exception):
    pass


def _write_private(path: Path, text: str) -> None:
    SECRETS.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def find_client_file() -> Path | None:
    """The OAuth client JSON: already in secrets/, or the newest client_secret_*.json in Downloads."""
    if CLIENT_FILE.exists():
        return CLIENT_FILE
    found = sorted(Path.home().glob("Downloads/client_secret_*.json"), key=lambda p: p.stat().st_mtime)
    if not found:
        return None
    SECRETS.mkdir(mode=0o700, exist_ok=True)
    shutil.move(found[-1], CLIENT_FILE)  # move, so no copy of the secret is left in Downloads
    os.chmod(CLIENT_FILE, 0o600)
    return CLIENT_FILE


def login() -> str:
    """One-time browser consent. Saves the token to secrets/gmail_token.json."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    client = find_client_file()
    if client is None:
        raise GmailNotReady("No OAuth client file. Download it from Google Cloud (Desktop app) into Downloads.")
    flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True,
                                  success_message="Done. You can close this tab and go back to Claude.")
    _write_private(TOKEN_FILE, creds.to_json())
    return "saved"


def credentials():
    """Load the token, refreshing it if expired. Raises GmailNotReady if login is needed."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not TOKEN_FILE.exists():
        raise GmailNotReady("Gmail is not connected yet. Run: uv run outreach gmail-login")
    creds = Credentials.from_authorized_user_info(json.loads(TOKEN_FILE.read_text()), SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise GmailNotReady("Gmail sign-in expired. Run: uv run outreach gmail-login") from e
        _write_private(TOKEN_FILE, creds.to_json())
    return creds


def send_raw(message_bytes: bytes) -> str:
    """Send an RFC 822 message through the Gmail API. Returns the Gmail message id."""
    creds = credentials()
    raw = base64.urlsafe_b64encode(message_bytes).decode()
    r = httpx.post(SEND_URL, json={"raw": raw}, headers={"Authorization": f"Bearer {creds.token}"}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Gmail API refused the send (HTTP {r.status_code})")
    return r.json().get("id", "")
