from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime, timezone
import time
import re
import asyncio
import feedparser
import httpx

class NewsItem(BaseModel):
    headline: str
    summary: str
    url: str
    source: str
    published_at: str

app = FastAPI(
    title="Fineryx News Backend",
    version="3.0.0",
    description="Aggregated finance headlines from multiple legal RSS sources (async + cached)."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 15 OFFICIAL, PUBLIC, LEGAL RSS FEEDS
RSS_FEEDS: List[Dict[str, str]] = [
    # INDIA
    {"name": "Moneycontrol",
     "url": "http://www.moneycontrol.com/rss/latestnews.xml"},

    {"name": "Economic Times",
     "url": "https://economictimes.indiatimes.com/rssfeedsdefault.cms"},

    {"name": "BusinessLine",
     "url": "https://www.thehindubusinessline.com/feeder/default.rss"},

    {"name": "Business Standard",
     "url": "https://www.business-standard.com/rss/latest.rss"},

    {"name": "LiveMint Companies",
     "url": "https://www.livemint.com/rss/companies"},

    {"name": "Zee Business",
     "url": "https://www.zeebiz.com/latest.xml"},

    {"name": "NDTV Business",
     "url": "https://feeds.feedburner.com/ndtvprofit-latest"},

    {"name": "Hindustan Times Business",
     "url": "https://www.hindustantimes.com/feeds/rss/business/rssfeed.xml"},

    # GLOBAL
    {"name": "BBC Business",
     "url": "http://feeds.bbci.co.uk/news/business/rss.xml"},

    {"name": "Reuters Business",
     "url": "http://feeds.reuters.com/reuters/businessNews"},

    {"name": "CNBC",
     "url": "https://www.cnbc.com/id/10001147/device/rss/rss.html"},

    {"name": "MarketWatch",
     "url": "https://www.marketwatch.com/rss/topstories"},

    {"name": "Yahoo Finance",
     "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=yhoo&region=US&lang=en-US"},

    {"name": "CNN Money",
     "url": "http://rss.cnn.com/rss/money_latest.rss"},

    {"name": "Al Jazeera Business",
     "url": "https://www.aljazeera.com/xml/rss/all.xml"},
]

# In-memory cache
NEWS_CACHE: Dict[str, Any] = {"items": [], "timestamp": 0.0}
CACHE_TTL_SECONDS = 300  # 5 mins cache
FEED_TIMEOUT_SECONDS = 8.0  # per-feed HTTP timeout
MAX_ITEMS = 250  # max total news items returned


def _to_iso(struct) -> str | None:
    if not struct:
        return None
    try:
        dt = datetime(
            struct.tm_year, struct.tm_mon, struct.tm_mday,
            struct.tm_hour, struct.tm_min, struct.tm_sec,
            tzinfo=timezone.utc
        )
        return dt.isoformat()
    except Exception:
        return None


def _clean(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 400:
        return text[:397] + "..."
    return text


async def _fetch_single_feed(client: httpx.AsyncClient, feed: Dict[str, str]) -> list[Dict[str, Any]]:
    """Fetch and parse one RSS feed with timeout + bozo check."""
    name = feed["name"]
    url = feed["url"]
    items: list[Dict[str, Any]] = []

    try:
        resp = await client.get(url, timeout=FEED_TIMEOUT_SECONDS)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)

        if parsed.bozo:
            # malformed feed, skip
            return []

        for entry in parsed.entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()

            if not title or not link:
                continue

            summary = _clean(entry.get("summary") or entry.get("description") or "")
            published = None

            if entry.get("published_parsed"):
                published = _to_iso(entry["published_parsed"])
            elif entry.get("updated_parsed"):
                published = _to_iso(entry["updated_parsed"])
            else:
                published = datetime.now(timezone.utc).isoformat()

            items.append({
                "headline": title,
                "summary": summary,
                "url": link,
                "source": name,
                "published_at": published
            })

        return items

    except Exception as e:
        # Log error in server logs, but don't break the whole aggregator
        print(f"[FEED ERROR] {name}: {e}")
        return []


async def fetch_news(force: bool = False) -> list[Dict[str, Any]]:
    """Fetch aggregated news with caching + async RSS fetch."""
    now = time.time()

    # Serve from cache if still fresh
    if (not force
        and NEWS_CACHE["items"]
        and now - NEWS_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return NEWS_CACHE["items"]

    all_items: list[Dict[str, Any]] = []
    seen_links: set[str] = set()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            _fetch_single_feed(client, feed)
            for feed in RSS_FEEDS
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten & dedupe
    for result in results:
        if isinstance(result, Exception):
            # already logged inside _fetch_single_feed
            continue
        for item in result:
            link = item.get("url")
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            all_items.append(item)

    # Sort newest first
    all_items.sort(key=lambda x: x["published_at"], reverse=True)

    # Limit total count
    if len(all_items) > MAX_ITEMS:
        all_items = all_items[:MAX_ITEMS]

    # Update cache
    NEWS_CACHE["items"] = all_items
    NEWS_CACHE["timestamp"] = now

    return all_items


@app.get("/")
def root():
    return {
        "message": "Fineryx News API Live 🌐",
        "sources": len(RSS_FEEDS),
        "info": "Use /news to get aggregated headlines.",
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
    }


@app.get("/news")
async def get_news(limit: int = 0, force: bool = False):
    """
    Get aggregated news.
    - limit: optional max number of items to return (0 = no extra limit)
    - force: if true, bypass cache and refetch (use carefully)
    """
    items = await fetch_news(force=force)

    if limit > 0:
        items = items[:limit]

    return {"count": len(items), "items": items}


@app.get("/health")
def health():
    """Lightweight health endpoint for uptime checks."""
    return {
        "status": "ok",
        "sources": len(RSS_FEEDS),
        "cached_items": len(NEWS_CACHE["items"]),
        "cache_age_seconds": time.time() - NEWS_CACHE["timestamp"] if NEWS_CACHE["timestamp"] else None,
    }
