from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import feedparser
from datetime import datetime, timezone
import time
import re

class NewsItem(BaseModel):
    headline: str
    summary: str
    url: str
    source: str
    published_at: str

app = FastAPI(
    title="Fineryx News Backend",
    version="2.0.0",
    description="Aggregated finance headlines from multiple legal RSS sources."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 15 OFFICIAL, PUBLIC, LEGAL RSS FEEDS
RSS_FEEDS = [

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

NEWS_CACHE = {"items": [], "timestamp": 0.0}
CACHE_TTL_SECONDS = 300  # 5 mins cache


def _to_iso(struct):
    if not struct:
        return None
    try:
        dt = datetime(
            struct.tm_year, struct.tm_mon, struct.tm_mday,
            struct.tm_hour, struct.tm_min, struct.tm_sec,
            tzinfo=timezone.utc
        )
        return dt.isoformat()
    except:
        return None


def _clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 400:
        return text[:397] + "..."
    return text


def fetch_news(force=False):
    now = time.time()

    if (not force 
        and NEWS_CACHE["items"] 
        and now - NEWS_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return NEWS_CACHE["items"]

    all_items = []
    seen = set()

    for feed in RSS_FEEDS:
        parsed = feedparser.parse(feed["url"])
        if parsed.bozo:
            continue

        for entry in parsed.entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()

            if not title or not link or link in seen:
                continue

            seen.add(link)

            summary = _clean(entry.get("summary") or entry.get("description") or "")
            published = None

            if entry.get("published_parsed"):
                published = _to_iso(entry["published_parsed"])
            elif entry.get("updated_parsed"):
                published = _to_iso(entry["updated_parsed"])
            else:
                published = datetime.now(timezone.utc).isoformat()

            all_items.append({
                "headline": title,
                "summary": summary,
                "url": link,
                "source": feed["name"],
                "published_at": published
            })

    all_items.sort(key=lambda x: x["published_at"], reverse=True)

    if len(all_items) > 250:
        all_items = all_items[:250]

    NEWS_CACHE["items"] = all_items
    NEWS_CACHE["timestamp"] = now
    return all_items


@app.get("/")
def root():
    return {
        "message": "Fineryx News API Live 🌐",
        "sources": len(RSS_FEEDS),
        "info": "Use /news to get aggregated headlines."
    }


@app.get("/news")
def get_news(limit: int = 0):
    items = fetch_news()
    if limit > 0:
        items = items[:limit]
    return {"count": len(items), "items": items}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "sources": len(RSS_FEEDS),
        "cached_items": len(NEWS_CACHE["items"]),
    }

