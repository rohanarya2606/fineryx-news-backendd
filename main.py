from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import feedparser
from typing import List, Dict
import re
from html import unescape

app = FastAPI(title="Fineryx Finance News API (RSS Edition)")

# Allow your website to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Finance RSS Feeds
RSS_FEEDS = [
    "https://www.moneycontrol.com/rss/latestnews.xml",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.businesstoday.in/rssfeeds/?id=76",
]

# Regex to remove HTML tags
TAG_RE = re.compile(r"<[^>]+>")

# Clean HTML
def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = TAG_RE.sub("", raw_html)
    text = unescape(text)
    return text.strip()

# Shorten long summaries
def trim_words(text: str, max_words: int = 40) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."

@app.get("/")
def root():
    return {
        "message": "Hello from Fineryx 🚀",
        "info": "Go to /news to see live finance headlines"
    }

# Parse an RSS feed and extract news
def parse_feed(url: str) -> List[Dict]:
    parsed = feedparser.parse(url)
    items: List[Dict] = []

    for entry in parsed.entries[:10]:  # take top 10 items
        raw_summary = entry.get("summary", "")
        clean_summary = trim_words(clean_html(raw_summary))

        item = {
            "headline": entry.get("title", ""),
            "summary": clean_summary,
            "url": entry.get("link", ""),
            "source": parsed.feed.get("title", ""),
            "published_at": entry.get("published", "") or entry.get("updated", ""),
        }
        items.append(item)

    return items

@app.get("/news")
def get_news():
    all_items: List[Dict] = []

    for feed_url in RSS_FEEDS:
        try:
            items = parse_feed(feed_url)
            all_items.extend(items)
        except Exception:
            continue

    return {"count": len(all_items), "items": all_items}
