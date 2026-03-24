"""
Competitor Tracker Plugin — Monitor competitor websites and summarize changes via AI.
Fetches pages with requests, parses with BeautifulSoup/regex, summarizes with Ollama.
Stores data in ~/NexusScripts/competitors.json.
"""

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from core.plugin_manager import BasePlugin
import requests

logger = logging.getLogger("nexus.plugins.competitor_tracker")

COMPETITORS_FILE = Path.home() / "NexusScripts" / "competitors.json"

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    logger.info("BeautifulSoup not available — using regex for text extraction")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class CompetitorTrackerPlugin(BasePlugin):
    name = "competitor_tracker"
    description = "Track competitor websites and get AI summaries of their latest activity"
    icon = "🎯"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.competitors: list[dict] = []
        self._load()

    def _load(self):
        if COMPETITORS_FILE.exists():
            try:
                self.competitors = json.loads(COMPETITORS_FILE.read_text(encoding="utf-8"))
                if not isinstance(self.competitors, list):
                    self.competitors = []
            except Exception as e:
                logger.warning(f"Could not load competitors: {e}")
                self.competitors = []

    def _save(self):
        COMPETITORS_FILE.parent.mkdir(parents=True, exist_ok=True)
        COMPETITORS_FILE.write_text(
            json.dumps(self.competitors, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = f"{len(self.competitors)} competitors tracked"
        return True

    async def execute(self, action: str, params: dict) -> str:
        handler = {
            "add_competitor":    self._add_competitor,
            "remove_competitor": self._remove_competitor,
            "list_competitors":  self._list_competitors,
            "check_competitor":  self._check_competitor,
            "check_all":         self._check_all,
            "search_competitor": self._search_competitor,
            "get_report":        self._get_report,
        }.get(action)
        if not handler:
            return f"Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "add_competitor",    "description": "Add a competitor to track",                          "params": ["name", "url", "keywords"]},
            {"action": "remove_competitor", "description": "Remove a competitor from tracking",                  "params": ["name"]},
            {"action": "list_competitors",  "description": "List all tracked competitors",                       "params": []},
            {"action": "check_competitor",  "description": "Fetch and AI-summarize a competitor's website",      "params": ["name"]},
            {"action": "check_all",         "description": "Check all tracked competitors and summarize",        "params": []},
            {"action": "search_competitor", "description": "DuckDuckGo news search about a competitor",         "params": ["name"]},
            {"action": "get_report",        "description": "Get a comparative report of all competitors",        "params": []},
        ]

    def _find_competitor(self, name: str) -> dict | None:
        name_lower = name.lower()
        for c in self.competitors:
            if c.get("name", "").lower() == name_lower:
                return c
        for c in self.competitors:
            if name_lower in c.get("name", "").lower():
                return c
        return None

    def _extract_text(self, html: str, url: str = "") -> str:
        if HAS_BS4:
            try:
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                lines = [ln.strip() for ln in text.splitlines() if ln.strip() and len(ln.strip()) > 20]
                return "\n".join(lines[:150])
            except Exception as e:
                logger.warning(f"BeautifulSoup parse error: {e}")

        # Regex fallback
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<[^>]+>", " ", html)
        html = re.sub(r"&[a-z]+;", " ", html)
        lines = [ln.strip() for ln in html.splitlines() if ln.strip() and len(ln.strip()) > 20]
        return "\n".join(lines[:100])

    def _call_ollama(self, prompt: str) -> str:
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
                timeout=60
            )
            return resp.json().get("response", "").strip()
        except requests.exceptions.ConnectionError:
            return ""
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return ""

    def _fetch_page(self, url: str) -> tuple[str, str]:
        """Returns (extracted_text, error_message)."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            text = self._extract_text(resp.text, url)
            return text, ""
        except requests.exceptions.Timeout:
            return "", "Request timed out (15s)"
        except requests.exceptions.ConnectionError:
            return "", "Could not connect to the website"
        except requests.exceptions.HTTPError as e:
            return "", f"HTTP error {e.response.status_code}"
        except Exception as e:
            return "", str(e)

    def _summarize(self, name: str, url: str, keywords: list, page_text: str) -> str:
        kw_str = ", ".join(keywords) if keywords else "none specified"
        prompt = (
            f"You are a business analyst. Summarize what this competitor's website says "
            f"about their products, services, pricing, and positioning.\n\n"
            f"Competitor: {name}\nURL: {url}\nKeywords to watch: {kw_str}\n\n"
            f"Website content:\n{page_text[:3000]}\n\n"
            f"Provide a concise 3-5 point bullet summary covering: main offering, target audience, "
            f"pricing signals, notable features, and anything related to the keywords."
        )
        summary = self._call_ollama(prompt)
        if not summary:
            return f"Could not generate AI summary (Ollama unavailable). Page extracted {len(page_text)} characters."
        return summary

    async def _add_competitor(self, params: dict) -> str:
        name = params.get("name", "").strip()
        url = params.get("url", "").strip()
        keywords = params.get("keywords", [])
        if not name or not url:
            return "Please provide both name and url."
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        if self._find_competitor(name):
            return f"Competitor '{name}' is already being tracked."

        competitor = {
            "id":           str(uuid.uuid4())[:8],
            "name":         name,
            "url":          url,
            "keywords":     keywords,
            "last_checked": None,
            "last_summary": None,
            "added":        datetime.now().isoformat(),
        }
        self.competitors.append(competitor)
        self._save()
        kw_str = ", ".join(keywords) if keywords else "none"
        return (
            f"Competitor '{name}' added to tracking.\n"
            f"  URL:      {url}\n"
            f"  Keywords: {kw_str}\n\n"
            f"Use check_competitor to fetch and summarize their website."
        )

    async def _remove_competitor(self, params: dict) -> str:
        name = params.get("name", "").strip()
        competitor = self._find_competitor(name)
        if not competitor:
            return f"Competitor '{name}' not found."
        self.competitors.remove(competitor)
        self._save()
        return f"Competitor '{competitor['name']}' removed from tracking."

    async def _list_competitors(self, params: dict) -> str:
        if not self.competitors:
            return "No competitors being tracked yet. Use add_competitor to start."
        lines = [f"TRACKED COMPETITORS  ({len(self.competitors)})", "─" * 65]
        for c in self.competitors:
            last = c.get("last_checked", "never")
            if last and last != "never":
                last = last[:16]
            kw = ", ".join(c.get("keywords", [])) or "—"
            lines.append(f"  {c['name']:<25}  {c['url'][:30]:<30}  Checked: {last}")
            lines.append(f"    Keywords: {kw}")
            if c.get("last_summary"):
                preview = c["last_summary"][:80].replace("\n", " ")
                lines.append(f"    Summary:  {preview}...")
        return "\n".join(lines)

    async def _check_competitor(self, params: dict) -> str:
        name = params.get("name", "").strip()
        competitor = self._find_competitor(name)
        if not competitor:
            return f"Competitor '{name}' not found. Use add_competitor first."

        url = competitor["url"]
        page_text, error = self._fetch_page(url)
        if error:
            return f"Failed to fetch {url}: {error}"

        summary = self._summarize(
            competitor["name"], url,
            competitor.get("keywords", []),
            page_text
        )
        competitor["last_checked"] = datetime.now().isoformat()
        competitor["last_summary"] = summary
        self._save()

        return (
            f"COMPETITOR CHECK — {competitor['name']}\n"
            f"  URL:     {url}\n"
            f"  Checked: {competitor['last_checked'][:19]}\n"
            f"{'─'*55}\n"
            f"{summary}\n"
            f"{'─'*55}\n"
            f"Page text extracted: {len(page_text)} chars"
        )

    async def _check_all(self, params: dict) -> str:
        if not self.competitors:
            return "No competitors to check. Use add_competitor first."
        results = [f"CHECKING ALL {len(self.competitors)} COMPETITORS\n{'═'*55}"]
        for c in self.competitors:
            results.append(f"\nChecking {c['name']} ({c['url']})...")
            page_text, error = self._fetch_page(c["url"])
            if error:
                results.append(f"  FAILED: {error}")
                continue
            summary = self._summarize(c["name"], c["url"], c.get("keywords", []), page_text)
            c["last_checked"] = datetime.now().isoformat()
            c["last_summary"] = summary
            results.append(f"  {summary[:200]}...")
        self._save()
        results.append(f"\n{'═'*55}\nAll checks complete.")
        return "\n".join(results)

    async def _search_competitor(self, params: dict) -> str:
        name = params.get("name", "").strip()
        if not name:
            return "Please provide a competitor name to search."

        competitor = self._find_competitor(name)
        search_name = competitor["name"] if competitor else name

        try:
            search_url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(search_name + ' news 2026')}"
            resp = requests.get(search_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            text = self._extract_text(resp.text)
        except Exception as e:
            return f"Search failed: {e}"

        if not text:
            return f"No search results found for '{search_name}'."

        prompt = (
            f"Summarize the latest news and activity about '{search_name}' "
            f"based on these search results. Focus on product launches, funding, "
            f"partnerships, and market moves.\n\nSearch results:\n{text[:3000]}"
        )
        summary = self._call_ollama(prompt)
        if not summary:
            return f"Search results for '{search_name}':\n\n{text[:1500]}"

        return (
            f"NEWS SEARCH — {search_name}\n"
            f"{'─'*55}\n"
            f"{summary}"
        )

    async def _get_report(self, params: dict) -> str:
        if not self.competitors:
            return "No competitors tracked. Use add_competitor to get started."

        checked = [c for c in self.competitors if c.get("last_summary")]
        if not checked:
            return "No competitors have been checked yet. Run check_all first."

        summaries = "\n\n".join(
            f"COMPETITOR: {c['name']} ({c['url']})\n"
            f"Last checked: {(c.get('last_checked') or 'unknown')[:16]}\n"
            f"Summary: {c['last_summary'][:500]}"
            for c in checked
        )

        prompt = (
            f"You are a business analyst. Based on these competitor summaries, "
            f"write a concise comparative intelligence report covering:\n"
            f"1. Market positioning of each competitor\n"
            f"2. Key differentiators\n"
            f"3. Potential threats and opportunities\n"
            f"4. Recommended strategic actions\n\n"
            f"{summaries}"
        )
        report = self._call_ollama(prompt)
        if not report:
            lines = [f"COMPETITOR REPORT  ({len(checked)} competitors)\n{'═'*60}"]
            for c in checked:
                lines.append(f"\n{c['name'].upper()}  |  {c['url']}")
                lines.append(f"  {c.get('last_summary', 'No summary')[:300]}")
            lines.append(f"\n{'═'*60}\n[AI unavailable — showing raw summaries]")
            return "\n".join(lines)

        return (
            f"COMPETITOR INTELLIGENCE REPORT\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"Competitors analyzed: {len(checked)}\n"
            f"{'═'*60}\n\n"
            f"{report}"
        )
