"""Start Outreach Desk and open it in the browser: python run_ui.py  (or: uv run python run_ui.py)"""
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = int(os.getenv("OUTREACH_PORT", "8600"))


def main() -> None:
    if not (ROOT / ".venv").exists() and shutil.which("uv") and not os.getenv("OUTREACH_NO_UV"):
        os.execvp("uv", ["uv", "run", "python", str(ROOT / "run_ui.py")])  # first run: let uv set up Python
    if not (ROOT / "node_modules" / "gsap").exists():
        if not shutil.which("npm"):
            sys.exit("Outreach Desk needs Node.js once, to install its local animation and font files: https://nodejs.org")
        print("Installing the local animation and font files (one time)...")
        subprocess.run(["npm", "install", "--silent", "--no-audit", "--no-fund"], cwd=ROOT, check=True)
    import uvicorn
    url = f"http://127.0.0.1:{PORT}"
    if not os.getenv("OUTREACH_NO_BROWSER"):
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    print(f"Outreach Desk is running at {url}  (press Ctrl+C to stop)")
    uvicorn.run("outreach.api:app", host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
