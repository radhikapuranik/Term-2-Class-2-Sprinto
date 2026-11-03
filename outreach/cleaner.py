"""Three-layer cleaning before anything reaches Gemini.

Layer 1 (rules): drop scripts, styles, nav, header, footer, cookie banners and forms.
            Cert badges often live in the footer or in image alt text, so keyword lines from
            the footer and badge alt text are kept aside before the footer is removed.
Layer 2 (heuristics): if the page is long, keep lines near ICP keywords first.
Layer 3 (cap): cut to about max_tokens (4 characters per token).
"""
import re

from bs4 import BeautifulSoup

CHARS_PER_TOKEN = 4
DROP_TAGS = ["script", "style", "noscript", "svg", "iframe", "form", "nav", "header", "button", "template"]
BANNER = re.compile(r"cookie|consent|onetrust|cc-banner|gdpr-banner|newsletter|popup|modal", re.I)
MENU = re.compile(r"(^|[-_])(nav|navbar|navigation|menu|megamenu|mega-menu|dropdown|header)([-_]|$)", re.I)
# Cert badges are often images: alt text or file names like aicpa-logo.webp or soc2-badge.png.
BADGE = re.compile(r"aicpa|soc[-_ ]?2|iso[-_ ]?(iec[-_ ]?)?27001|gdpr|hipaa|pci[-_ ]?dss", re.I)


def _has_keyword(line: str, keywords: list[str]) -> bool:
    low = line.lower()
    return any(k.lower() in low for k in keywords)


def _lines(text: str) -> list[str]:
    out, seen = [], set()
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line and line.lower() not in seen:
            seen.add(line.lower())
            out.append(line)
    return out


def clean_html(html: str, keywords: list[str]) -> str:
    """Layer 1. Returns readable text with boilerplate removed."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    # Badge alt text (e.g. <img alt="SOC 2 Type II">) is real signal; keep it if it names a keyword.
    badges = []
    for img in soup.find_all("img"):
        alt, src = img.get("alt", ""), img.get("src", "") + " " + img.get("srcset", "")
        if BADGE.search(alt):
            badges.append(alt)
        elif m := BADGE.search(src):
            badges.append(("SOC 2 (AICPA logo)" if m.group(0).lower() == "aicpa" else m.group(0)) + " badge image")
    # Badge images inside <noscript> or lazy-load attributes are not parsed as <img>; scan image URLs too.
    for m in re.finditer(r"[\w%./-]*(aicpa|soc[-_]?2|iso[-_]?27001)[\w.-]*\.(?:png|svg|webp|jpe?g)", html, re.I):
        label = "SOC 2 (AICPA logo)" if m.group(1).lower() == "aicpa" else m.group(1)
        if f"{label} badge image" not in badges:
            badges.append(f"{label} badge image")
    footer_keep = []
    for f in soup.find_all("footer"):
        footer_keep += [l for l in _lines(f.get_text("\n")) if _has_keyword(l, keywords)]
        f.decompose()
    for tag in soup(DROP_TAGS):
        tag.decompose()
    for pat in (BANNER, MENU):
        for el in soup.find_all(attrs={"class": pat}) + soup.find_all(attrs={"id": pat}) + soup.find_all(attrs={"role": "navigation"}):
            if not el.decomposed and el.name not in ("body", "html", "main"):
                el.decompose()
    body = soup.body or soup
    parts = [title] + _lines(body.get_text("\n")) + [f"[badge] {b}" for b in badges] + [f"[footer] {l}" for l in footer_keep]
    return "\n".join(_lines("\n".join(parts)))


def body_chars(html: str, keywords: list[str]) -> int:
    """Characters of real content left after layer 1 (menus and footers removed)."""
    return len(clean_html(html, keywords))


def focus(text: str, keywords: list[str], max_tokens: int) -> str:
    """Layers 2 and 3. Keep keyword lines (plus one line either side) first, then cap."""
    budget = max_tokens * CHARS_PER_TOKEN
    if len(text) <= budget:
        return text
    lines = text.splitlines()
    keep = set(range(min(5, len(lines))))  # the title and hero lines say what the company does
    for i, line in enumerate(lines):
        if _has_keyword(line, keywords):
            keep.update({i - 1, i, i + 1})
    picked = "\n".join(lines[i] for i in sorted(keep) if 0 <= i < len(lines))
    return picked[:budget]


def visible_text_chars(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    return len(re.sub(r"\s+", " ", soup.get_text(" ")).strip())


JS_MARKERS = re.compile(r'id="(root|app|__next|__nuxt)"|enable javascript|you need to enable javascript|__NEXT_DATA__', re.I)


def needs_js(html: str, min_chars: int = 400) -> bool:
    """A page is JavaScript-only when its raw HTML carries almost no real content.

    Content is measured after menus, headers and footers are removed, because many sites
    server-render a big menu and load the actual page with JavaScript. Server-rendered Next.js
    pages also have __NEXT_DATA__, so markers alone are not enough.
    """
    chars = body_chars(html, [])
    if chars < 150:
        return True
    return chars < min_chars and bool(JS_MARKERS.search(html))
