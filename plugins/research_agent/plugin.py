"""
Research Agent Plugin — Web research via DuckDuckGo + Ollama summarization.
"""

import os
import re
import json
import logging
import requests
from pathlib import Path
from datetime import datetime
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.research_agent")

RESEARCH_DIR = Path.home() / "NexusScripts" / "research"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"
DDG_URL = "https://html.duckduckgo.com/html/"


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


def _ddg_search(query: str, max_results: int = 10) -> list[dict]:
    """Search DuckDuckGo HTML version. Returns list of {title, url, snippet}."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NexusResearch/1.0)"}
    try:
        resp = requests.post(DDG_URL, data={"q": query}, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.error(f"DDG fetch error: {e}")
        return []

    results = []
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for r in soup.select(".result")[:max_results]:
            title_el = r.select_one(".result__title")
            url_el = r.select_one(".result__url")
            snippet_el = r.select_one(".result__snippet")
            title = title_el.get_text(strip=True) if title_el else ""
            url = url_el.get_text(strip=True) if url_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if title:
                results.append({"title": title, "url": url, "snippet": snippet})
    except ImportError:
        # Fallback: regex-based extraction
        titles = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.S)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</span>', html, re.S)
        urls = re.findall(r'class="result__url"[^>]*>(.*?)</a>', html, re.S)
        for i, title in enumerate(titles[:max_results]):
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            clean_snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
            clean_url = re.sub(r"<[^>]+>", "", urls[i]).strip() if i < len(urls) else ""
            if clean_title:
                results.append({"title": clean_title, "url": clean_url, "snippet": clean_snippet})

    return results


class ResearchAgentPlugin(BasePlugin):
    name = "research_agent"
    description = "Web research via DuckDuckGo with AI summarization and report saving"
    icon = "🔬"

    async def connect(self) -> bool:
        RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        self._connected = True
        self._status_message = "Ready"
        return True

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "research": self._research,
            "search": self._search,
            "summarize_url": self._summarize_url,
            "list_reports": self._list_reports,
            "get_report": self._get_report,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown action: {action}. Available: {', '.join(actions)}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "research", "description": "Deep research on a topic with AI summary", "params": ["topic", "depth (quick/deep)"]},
            {"action": "search", "description": "Raw DuckDuckGo search results", "params": ["query"]},
            {"action": "summarize_url", "description": "Fetch a URL and summarize its content with AI", "params": ["url"]},
            {"action": "list_reports", "description": "List all saved research reports", "params": []},
            {"action": "get_report", "description": "Read a saved research report", "params": ["filename"]},
        ]

    async def _search(self, params: dict) -> str:
        query = params.get("query", "").strip()
        if not query:
            return "Please provide a search query."
        results = _ddg_search(query, max_results=8)
        if not results:
            return f"No results found for: {query}"
        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            if r.get("url"):
                lines.append(f"   {r['url']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet']}")
            lines.append("")
        return "\n".join(lines)

    async def _research(self, params: dict) -> str:
        topic = params.get("topic", "").strip()
        depth = params.get("depth", "quick").lower()
        if not topic:
            return "Please provide a research topic."

        num_results = 5 if depth == "quick" else 10
        queries = [topic] if depth == "quick" else [topic, f"{topic} overview", f"{topic} latest"]

        all_snippets = []
        for q in queries:
            results = _ddg_search(q, max_results=num_results)
            for r in results:
                text = f"Title: {r['title']}\n{r['snippet']}"
                if text not in all_snippets:
                    all_snippets.append(text)

        if not all_snippets:
            return f"Could not find information about: {topic}"

        context = "\n\n".join(all_snippets[:15])
        prompt = (
            f"You are a research assistant. Based on the following search results, "
            f"write a comprehensive {'brief' if depth == 'quick' else 'detailed'} research report "
            f"about: {topic}\n\nSearch Results:\n{context}\n\n"
            f"Provide a well-structured report with key findings, context, and conclusions."
        )
        summary = _ollama(prompt, timeout=90)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = re.sub(r"[^\w\s-]", "", topic).strip().replace(" ", "_")[:40]
        filename = f"{timestamp}_{safe_topic}.txt"
        report_path = RESEARCH_DIR / filename
        report_content = f"RESEARCH REPORT: {topic}\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M')}\nDepth: {depth}\n\n{summary}"
        try:
            report_path.write_text(report_content, encoding="utf-8")
            saved_msg = f"\n\nReport saved: {filename}"
        except Exception as e:
            saved_msg = f"\n\n(Could not save report: {e})"

        return f"Research Report: {topic}\n{'=' * 50}\n{summary}{saved_msg}"

    async def _summarize_url(self, params: dict) -> str:
        url = params.get("url", "").strip()
        if not url:
            return "Please provide a URL."
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NexusResearch/1.0)"}
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            return f"Failed to fetch URL: {e}"

        # Strip HTML tags
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = text[:4000]  # Limit context

        prompt = f"Summarize the following webpage content concisely:\n\n{text}"
        summary = _ollama(prompt)
        return f"Summary of {url}:\n\n{summary}"

    async def _list_reports(self, params: dict) -> str:
        reports = sorted(RESEARCH_DIR.glob("*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not reports:
            return "No research reports saved yet."
        lines = ["Saved Research Reports:\n"]
        for r in reports[:20]:
            mtime = datetime.fromtimestamp(r.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"  {r.name}  ({mtime})")
        return "\n".join(lines)

    async def _get_report(self, params: dict) -> str:
        filename = params.get("filename", "").strip()
        if not filename:
            return "Please provide a filename."
        report_path = RESEARCH_DIR / filename
        if not report_path.exists():
            return f"Report not found: {filename}"
        try:
            return report_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading report: {e}"
