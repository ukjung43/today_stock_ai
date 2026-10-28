"""Recent headlines from publisher RSS feeds. Only titles and links are used, never article bodies."""

import calendar
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

import feedparser
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (today_stock.ai bot)"}


@dataclass
class Headline:
    title: str
    link: str
    source: str
    published: str  # ISO 8601, UTC

    def to_dict(self) -> dict:
        return asdict(self)


def fetch_headlines(feeds: list[dict], hours: int, max_items: int) -> list[Headline]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    seen: set[str] = set()
    items: list[Headline] = []
    for feed in feeds:
        try:
            resp = requests.get(feed["url"], headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[news] {feed['name']} 건너뜀: {e}")
            continue
        for entry in feedparser.parse(resp.content).entries:
            stamp = entry.get("published_parsed") or entry.get("updated_parsed")
            if not stamp:
                continue
            published = datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc)
            title = " ".join(entry.get("title", "").split())
            if published < cutoff or not title or title in seen:
                continue
            seen.add(title)
            items.append(Headline(title, entry.get("link", ""), feed["name"], published.isoformat()))
    items.sort(key=lambda h: h.published, reverse=True)
    return items[:max_items]
