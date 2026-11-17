"""Read-only public snapshot of Outreach Desk, for Vercel: the same pages and design, fed by saved JSON.

No keys, no server, nothing can be sent or run. Prospect email addresses are already stripped by the API;
here last names are shortened to an initial too. Run: uv run outreach site, then vercel deploy site --prod
"""
import json
import shutil

from fastapi.testclient import TestClient

from .api import NODE, UI, app
from . import db
from .config import ROOT

OUT = ROOT / "site"
ROUTES = ["/companies", "/companies/:domain", "/review", "/quality", "/icp", "/runs", "/about"]
FONTS = {"instrument-serif": NODE / "@fontsource" / "instrument-serif" / "files",
         "inter": NODE / "@fontsource-variable" / "inter" / "files",
         "jetbrains-mono": NODE / "@fontsource-variable" / "jetbrains-mono" / "files"}


def _short_names(obj):
    """Keep only the initial of any contact's last name in the public copy."""
    if isinstance(obj, dict):
        if "last_name" in obj and obj.get("last_name"):
            obj = obj | {"last_name": obj["last_name"][0] + "."}
        return {k: _short_names(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_short_names(v) for v in obj]
    return obj


def build() -> str:
    for p in OUT.iterdir() if OUT.exists() else []:
        if p.name not in (".vercel", ".gitignore"):
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    OUT.mkdir(exist_ok=True)
    shutil.copytree(UI / "assets", OUT / "assets")
    for name in ("gsap.min.js", "ScrollTrigger.min.js", "Flip.min.js"):
        (OUT / "vendor" / "gsap").mkdir(parents=True, exist_ok=True)
        shutil.copy(NODE / "gsap" / "dist" / name, OUT / "vendor" / "gsap" / name)
    for family, src in FONTS.items():
        dst = OUT / "vendor" / "fonts" / family
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.glob("*latin-*normal.woff2"):
            shutil.copy(f, dst / f.name)
        for f in src.glob("*latin-400-italic.woff2"):
            shutil.copy(f, dst / f.name)

    client = TestClient(app)
    con = db.connect()
    names = [(c.get("first_name") or "", c.get("last_name") or "") for c in
             (json.loads(r["contact_json"] or "{}") for r in con.execute("SELECT contact_json FROM drafts"))]
    names = [(f, l) for f, l in names if f and l]
    paths = ["/api/meta", "/api/summary", "/api/companies", "/api/review", "/api/quality", "/api/icp", "/api/runs"]
    companies = client.get("/api/companies").json()
    paths += [f"/api/companies/{c['domain']}" for c in companies]
    for p in paths:
        data = _short_names(client.get(p).json())
        if p == "/api/summary":
            data["running"] = []
        dst = OUT / "data" / f"{p.lstrip('/')}.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data)
        for first, last in names:  # full names inside sentences (e.g. pain points) too
            text = text.replace(f"{first} {last}", f"{first} {last[0]}.")
        dst.write_text(text)

    page = (UI / "index.html").read_text().replace(
        "<script>\n", "<script>\n  window.OD_STATIC = true; document.documentElement.classList.add('static');\n", 1)
    (OUT / "index.html").write_text(page)
    (OUT / "404.html").write_text(page)
    rewrites = [{"source": r.replace(":domain", ":domain"), "destination": "/index.html"} for r in ROUTES]
    (OUT / "vercel.json").write_text(json.dumps({"rewrites": rewrites, "trailingSlash": False}, indent=2))
    return str(OUT)
