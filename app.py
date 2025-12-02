from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import feedparser
from transformers import pipeline
import asyncio

app = FastAPI()

# Allow your website to access this API (important)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict to https://fineryx.com
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load AI summarizer
summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")

# RSS feeds (expand later)
FEEDS = {
    "India": [
        "https://economictimes.indiatimes.com/rssfeeds/1977021501.cms",
        "https://www.moneycontrol.com/rss/latestnews.xml"
    ],
    "Global": [
        "https://www.reuters.com/finance/rss"
    ],
    "Sector": [
        "https://www.moneycontrol.com/rss/sectornews.xml"
    ]
}

def ai_summary(text):
    """Generate short AI summary"""
    try:
        result = summarizer(
            text,
            max_length=60,
            min_length=20,
            do_sample=False
        )
        return result[0]["summary_text"]
    except:
        return (text[:140] + "...").strip()

async def fetch_feed(category, url):
    feed = feedparser.parse(url)
    articles = []

    for entry in feed.entries[:5]:
        title = entry.get("title", "Untitled")
        link = entry.get("link", "")
        summary_text = entry.get("summary", entry.get("description", ""))

        summary = ai_summary(summary_text)

        articles.append({
            "title": title,
            "link": link,
            "summary": summary,
            "category": category,
            "pubDate": entry.get("published", "")
        })

    return articles

@app.get("/news")
async def get_news():
    """Fetch + summarize + return all news"""
    tasks = [
        fetch_feed(cat, url)
        for cat, urls in FEEDS.items()
        for url in urls
    ]

    results = await asyncio.gather(*tasks)

    news_list = [item for sub in results for item in sub]

    # Sort latest first
    news_list.sort(
        key=lambda x: x.get("pubDate") or "",
        reverse=True
    )

    return news_list
