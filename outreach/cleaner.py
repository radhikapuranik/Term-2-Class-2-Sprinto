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
    badges = [img.get("alt", "") for img in soup.find_all("img") if _has_keyword(img.get("alt", ""), keywords)]
    footer_keep = []
    for f in soup.find_all("footer"):
        footer_keep += [l for l in _lines(f.get_text("\n")) if _has_keyword(l, keywords)]
        f.decompose()
    for tag in soup(DROP_TAGS):
        tag.decompose()
    for el in soup.find_all(attrs={"class": BANNER}) + soup.find_all(attrs={"id": BANNER}):
        if not el.decomposed:
            el.decompose()
    body = soup.body or soup
    parts = [title] + _lines(body.get_text("\n")) + [f"[badge] {b}" for b in badges] + [f"[footer] {l}" for l in footer_keep]
    return "\n".join(_lines("\n".join(parts)))


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
    """A page is JavaScript-only when its raw HTML carries almost no visible text.

    Server-rendered Next.js pages also have __NEXT_DATA__, so markers alone are not enough:
    we fall back to the browser only when the text is missing.
    """
    chars = visible_text_chars(html)
    if chars < 150:
        return True
    return chars < min_chars and bool(JS_MARKERS.search(html))
