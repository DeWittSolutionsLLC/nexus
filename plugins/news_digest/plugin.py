"""
News Digest Plugin — Fetches RSS feeds and summarizes headlines with Ollama.
"""

import json
import logging
import requests
from pathlib import Path
from datetime import datetime
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.news_digest")

DIGEST_FILE = Path.home() / "NexusScripts" / "news_digests.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

DEFAULT_FEEDS = {
    "BBC News": "http://feeds.bbci.co.uk/news/rss.xml",
    "Reuters": "https://feeds.reuters.com/reuters/topNews",
    "Hacker News": "https://hnrss.org/frontpage",
    "TechCrunch": "https://techcrunch.com/feed/",
}


def _ollama(prompt: str, timeout: int = 60) -> str:
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        return resp.json().get("response", "").strip()
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return f"[Ollama unavailable: {e}]"


class NewsDigestPlugin(BasePlugin):
    name = "news_digest"
    description = "Fetches RSS news feeds and delivers AI-summarized digests"
    icon = "📰"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._use_feedparser = False
        self._feeds: dict = {}

    async def connect(self) -> bool:
        # Load persisted feed list or initialize defaults
        DIGEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        if DIGEST_FILE.exists():
            try:
                data = json.loads(DIGEST_FILE.read_text(encoding="utf-8"))
                self._feeds = data.get("feeds", dict(DEFAULT_FEEDS))
            except Exception:
                self._feeds = dict(DEFAULT_FEEDS)
        else:
            self._feeds = dict(DEFAULT_FEEDS)
            self._save_state([])

        # Try feedparser first, fall back to requests+xml
        try:
            import feedparser  # noqa: F401
            self._use_feedparser = True
            logger.info("Using feedparser for RSS parsing")
        except ImportError:
            self._use_feedparser = False
            logger.info("feedparser not available, using requests+xml.etree")

        self._connected = True
        self._status_message = f"Ready ({len(self._feeds)} feeds)"
        return True

    def _save_state(self, digests: list):
        try:
            existing = {}
            if DIGEST_FILE.exists():
                existing = json.loads(DIGEST_FILE.read_text(encoding="utf-8"))
            existing["feeds"] = self._feeds
            if digests:
                existing.setdefault("digests", [])
                existing["digests"] = (digests + existing.get("digests", []))[:50]
            DIGEST_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def _fetch_feed(self, url: str) -> list[dict]:
        """Fetch an RSS feed and return list of {title, link, summary, published}."""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NexusNews/1.0)"}
        if self._use_feedparser:
            import feedparser
            try:
                feed = feedparser.parse(url)
                items = []
                for entry in feed.entries[:20]:
                    items.append({
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", ""),
                        "published": entry.get("published", ""),
                    })
                return items
            except Exception as e:
                logger.error(f"feedparser error for {url}: {e}")
                return []
        else:
            import xml.etree.ElementTree as ET
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                items = []
                # RSS 2.0
                for item in root.findall(".//item")[:20]:
                    title = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    desc = item.findtext("description", "").strip()
                    pub = item.findtext("pubDate", "").strip()
                    if title:
                        items.append({"title": title, "link": link, "summary": desc, "published": pub})
                # Atom
                if not items:
                    for entry in root.findall(".//atom:entry", ns)[:20]:
                        title = entry.findtext("atom:title", "", ns).strip()
                        link_el = entry.find("atom:link", ns)
                        link = link_el.get("href", "") if link_el is not None else ""
                        summary = entry.findtext("atom:summary", "", ns).strip()
                        pub = entry.findtext("atom:updated", "", ns).strip()
                        if title:
                            items.append({"title": title, "link": link, "summary": summary, "published": pub})
                return items
            except Exception as e:
                logger.error(f"XML parse error for {url}: {e}")
                return []

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "get_digest": self._get_digest,
            "add_feed": self._add_feed,
            "list_feeds": self._list_feeds,
            "remove_feed": self._remove_feed,
            "get_headlines": self._get_headlines,
            "search_news": self._search_news,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown action: {action}. Available: {', '.join(actions)}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "get_digest", "description": "Fetch and AI-summarize top news headlines", "params": ["topic (optional)", "count (default 10)"]},
            {"action": "add_feed", "description": "Add a new RSS feed", "params": ["url", "name"]},
            {"action": "list_feeds", "description": "List all configured RSS feeds", "params": []},
            {"action": "remove_feed", "description": "Remove an RSS feed by name", "params": ["name"]},
            {"action": "get_headlines", "description": "Get raw list of latest headlines without AI summary", "params": ["count (default 20)"]},
            {"action": "search_news", "description": "Search headlines for a keyword", "params": ["keyword"]},
        ]

    async def _get_digest(self, params: dict) -> str:
        topic = params.get("topic", "").strip()
        count = int(params.get("count", 10))
        all_items = []
        for name, url in self._feeds.items():
            items = self._fetch_feed(url)
            for item in items:
                item["source"] = name
                all_items.append(item)

        if not all_items:
            return "Could not fetch any news items. Check feed URLs or network connection."

        if topic:
            tl = topic.lower()
            filtered = [i for i in all_items if tl in i["title"].lower() or tl in i["summary"].lower()]
            all_items = filtered if filtered else all_items

        selected = all_items[:count]
        headlines_text = "\n".join(
            f"- [{i['source']}] {i['title']}: {i['summary'][:120]}" for i in selected
        )
        prompt = (
            f"You are a news analyst. Summarize the following headlines into a concise daily digest"
            f"{f' focused on {topic}' if topic else ''}. Group by theme and highlight key takeaways:\n\n"
            f"{headlines_text}"
        )
        summary = _ollama(prompt, timeout=90)
        digest_entry = {
            "timestamp": datetime.now().isoformat(),
            "topic": topic or "general",
            "count": len(selected),
            "summary": summary,
        }
        self._save_state([digest_entry])
        return f"News Digest ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n{'=' * 50}\n{summary}"

    async def _add_feed(self, params: dict) -> str:
        url = params.get("url", "").strip()
        name = params.get("name", "").strip()
        if not url or not name:
            return "Please provide both 'url' and 'name'."
        self._feeds[name] = url
        self._save_state([])
        return f"Feed added: {name} → {url}"

    async def _list_feeds(self, params: dict) -> str:
        if not self._feeds:
            return "No feeds configured."
        lines = ["Configured RSS Feeds:\n"]
        for name, url in self._feeds.items():
            lines.append(f"  {name}: {url}")
        return "\n".join(lines)

    async def _remove_feed(self, params: dict) -> str:
        name = params.get("name", "").strip()
        if name not in self._feeds:
            return f"Feed not found: {name}. Use list_feeds to see available feeds."
        del self._feeds[name]
        self._save_state([])
        return f"Feed removed: {name}"

    async def _get_headlines(self, params: dict) -> str:
        count = int(params.get("count", 20))
        all_items = []
        for name, url in self._feeds.items():
            items = self._fetch_feed(url)
            for item in items:
                item["source"] = name
                all_items.append(item)

        if not all_items:
            return "No headlines fetched. Check feeds with list_feeds."

        lines = [f"Latest Headlines ({datetime.now().strftime('%H:%M')}):\n"]
        for item in all_items[:count]:
            lines.append(f"  [{item['source']}] {item['title']}")
            if item.get("link"):
                lines.append(f"    {item['link']}")
        return "\n".join(lines)

    async def _search_news(self, params: dict) -> str:
        keyword = params.get("keyword", "").strip().lower()
        if not keyword:
            return "Please provide a keyword to search."
        all_items = []
        for name, url in self._feeds.items():
            items = self._fetch_feed(url)
            for item in items:
                item["source"] = name
                all_items.append(item)

        matches = [
            i for i in all_items
            if keyword in i["title"].lower() or keyword in i["summary"].lower()
        ]
        if not matches:
            return f"No headlines found matching: {keyword}"
        lines = [f"Headlines matching '{keyword}':\n"]
        for item in matches[:15]:
            lines.append(f"  [{item['source']}] {item['title']}")
            if item.get("link"):
                lines.append(f"    {item['link']}")
        return "\n".join(lines)
