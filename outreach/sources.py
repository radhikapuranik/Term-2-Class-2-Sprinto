"""Free and paid data sources that are not the company website: news and Lusha."""
import json
from urllib.parse import quote_plus

import httpx

from . import db
from .config import env

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
BING_NEWS = "https://www.bing.com/news/search?q={q}&format=rss"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc?query={q}&mode=artlist&format=json&maxrecords=25&timespan=24m&sort=datedesc"


def news_url(fetcher, name: str) -> str:
    """First free news feed whose robots.txt allows us: Google News RSS, then Bing News RSS, then GDELT.

    Google News currently disallows /rss for all crawlers, so in practice this is Bing News RSS.
    """
    for feed, q in [(GOOGLE_NEWS, f'"{name}" (funding OR raises OR series)'), (BING_NEWS, f'"{name}" funding series')]:
        url = feed.format(q=quote_plus(q))
        if fetcher.allowed(url):
            return url
    return GDELT.format(q=quote_plus(f'"{name}" (funding OR raises OR series)'))


def fetch_news(fetcher, domain: str, name: str, time_left: float) -> tuple[dict, bool]:
    """Headlines as plain text lines. Cached in the pages table like any page."""
    url = news_url(fetcher, name)
    cached = db.cached_page(fetcher.con, url)
    if cached:
        return cached, False
    try:
        for attempt in range(2):  # GDELT often drops or rate-limits the first call; wait our turn once more
            try:
                r = fetcher.get(url, timeout=min(15, time_left))
                if r.status_code != 429:
                    break
            except httpx.TransportError:
                if attempt:
                    raise
        r.raise_for_status()
        if "gdelt" in url:
            arts = r.json().get("articles", []) if r.text.strip().startswith("{") else []
            lines = [f"{a['title']} ({a.get('domain', '')}, {a.get('seendate', '')[:8]})" for a in arts]
        else:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "xml")
            lines = [f"{i.title.text} ({i.pubDate.text[:16] if i.pubDate else ''}): "
                     f"{BeautifulSoup(i.description.text, 'lxml').get_text(' ') if i.description else ''}"
                     for i in soup.find_all("item")[:20]]
        status, text, err = ("ok", "\n".join(lines), None) if lines else ("error", "", "no news articles found")
    except (httpx.HTTPError, ValueError, KeyError) as e:
        status, text, err = "error", "", f"news fetch failed: {type(e).__name__}"
    db.save_page(fetcher.con, url, domain, "google_news", "rss", status, text, len(text), err)
    return db.cached_page(fetcher.con, url), True


def fetch_lusha(con, domain: str) -> dict | None:
    """Lusha company enrichment. Returns None when no key is set (source skipped, no attempt used)."""
    if not env("LUSHA_API_KEY"):
        return None
    url = f"https://api.lusha.com/v2/company?domain={domain}"
    data = db.cached_api(con, f"lusha:{domain}")
    if data is None:
        try:
            r = httpx.get(url, headers={"api_key": env("LUSHA_API_KEY")}, timeout=15)
            data = r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}
        except (httpx.HTTPError, ValueError) as e:
            data = {"error": type(e).__name__}
        if "error" not in data:
            db.save_api(con, f"lusha:{domain}", data)
    if "error" in data:
        return {"url": url, "status": "error", "clean_text": "", "error": f"Lusha: {data['error']}", "method": "api"}
    return {"url": url, "status": "ok", "clean_text": json.dumps(data, indent=1)[:20000], "error": None, "method": "api"}
