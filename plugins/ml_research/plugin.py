"""
ML Research Plugin — fetches real papers from arXiv and summarises them.

Uses only Python stdlib: urllib, xml.etree.ElementTree, json, pathlib,
datetime, logging.  No API key required.
"""

import json
import logging
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.ml_research")

ARXIV_API = "http://export.arxiv.org/api/query"
OLLAMA_API = "http://localhost:11434/api/generate"
REPORTS_DIR = Path.home() / "NexusScripts" / "ml_research"

# arXiv Atom namespace
_NS = {"atom": "http://www.w3.org/2005/Atom",
       "opensearch": "http://a9.com/-/spec/opensearch/1.1/"}


class MLResearchPlugin(BasePlugin):
    name = "ml_research"
    description = "Fetches and summarises ML papers from arXiv"
    icon = "📚"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._ollama_model = config.get("ollama_model", "llama3.2:3b")

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = "ML Research ready"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {
                "action": "fetch_arxiv_papers",
                "description": "Fetch recent ML papers from arXiv",
                "params": ["query", "max_results"]
            },
            {
                "action": "search_conference_papers",
                "description": "Search arXiv for papers from a specific conference (NIPS/NeurIPS/ICML/ICLR)",
                "params": ["conference", "topic"]
            },
            {
                "action": "summarize_findings",
                "description": "Summarise key findings from a list of papers using the local LLM",
                "params": ["papers_json"]
            },
            {
                "action": "save_research_report",
                "description": "Save a research report as a Markdown file",
                "params": ["topic", "content"]
            },
            {
                "action": "get_saved_reports",
                "description": "List all saved research reports",
                "params": []
            }
        ]

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "fetch_arxiv_papers":
                return self._fetch_arxiv_papers(
                    query=params.get("query", "machine learning optimization neural network"),
                    max_results=int(params.get("max_results", 10))
                )
            elif action == "search_conference_papers":
                return self._search_conference_papers(
                    conference=params.get("conference", "NeurIPS"),
                    topic=params.get("topic", "deep learning")
                )
            elif action == "summarize_findings":
                return await self._summarize_findings(params.get("papers_json", "[]"))
            elif action == "save_research_report":
                return self._save_research_report(
                    topic=params.get("topic", "research"),
                    content=params.get("content", "")
                )
            elif action == "get_saved_reports":
                return self._get_saved_reports()
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"ml_research.{action} error: {e}")
            return f"Error in ml_research.{action}: {e}"

    # ── Internal helpers ──────────────────────────────────────────────────

    def _fetch_arxiv_papers(self, query: str = "machine learning optimization neural network",
                             max_results: int = 10) -> str:
        """Fetch papers from the arXiv Atom API and return JSON."""
        params = urllib.parse.urlencode({
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        })
        url = f"{ARXIV_API}?{params}"

        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                xml_data = resp.read().decode("utf-8")
        except Exception as e:
            return json.dumps({"error": f"Network error: {e}"})

        papers = self._parse_arxiv_atom(xml_data)
        return json.dumps({"query": query, "count": len(papers), "papers": papers}, indent=2,
                          ensure_ascii=False)

    def _search_conference_papers(self, conference: str = "NeurIPS",
                                   topic: str = "deep learning") -> str:
        """Search arXiv for papers associated with a major ML conference."""
        conf_map = {
            "NIPS": "NeurIPS",
            "NeurIPS": "NeurIPS",
            "ICML": "ICML",
            "ICLR": "ICLR"
        }
        conf_normalised = conf_map.get(conference.upper().strip(), conference)

        # Build a query that looks in title/abstract for the conference name + topic
        query = f'"{conf_normalised}" AND {topic}'
        params = urllib.parse.urlencode({
            "search_query": f"ti:{conf_normalised} OR abs:{conf_normalised} AND all:{topic}",
            "start": 0,
            "max_results": 15,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        })
        url = f"{ARXIV_API}?{params}"

        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                xml_data = resp.read().decode("utf-8")
        except Exception as e:
            return json.dumps({"error": f"Network error: {e}"})

        papers = self._parse_arxiv_atom(xml_data)
        return json.dumps({
            "conference": conf_normalised,
            "topic": topic,
            "count": len(papers),
            "papers": papers
        }, indent=2, ensure_ascii=False)

    def _parse_arxiv_atom(self, xml_data: str) -> list:
        """Parse arXiv Atom XML and return a list of paper dicts."""
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            return []

        papers = []
        for entry in root.findall("atom:entry", _NS):
            title_el = entry.find("atom:title", _NS)
            summary_el = entry.find("atom:summary", _NS)
            link_el = entry.find("atom:link[@rel='alternate']", _NS)
            published_el = entry.find("atom:published", _NS)

            authors = [
                a.find("atom:name", _NS).text
                for a in entry.findall("atom:author", _NS)
                if a.find("atom:name", _NS) is not None
            ]

            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
            summary = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""
            link = link_el.get("href", "") if link_el is not None else ""
            published = (published_el.text or "").strip() if published_el is not None else ""

            papers.append({
                "title": title,
                "authors": authors,
                "summary": summary[:500] + ("..." if len(summary) > 500 else ""),
                "link": link,
                "published": published
            })

        return papers

    async def _summarize_findings(self, papers_json: str) -> str:
        """Use the local Ollama LLM to summarise a batch of papers."""
        try:
            papers = json.loads(papers_json)
        except json.JSONDecodeError:
            return "Error: papers_json is not valid JSON."

        if not papers:
            return "No papers provided."

        # Build a condensed text representation
        paper_list = papers if isinstance(papers, list) else papers.get("papers", [])
        texts = []
        for i, p in enumerate(paper_list[:10], 1):
            texts.append(f"{i}. {p.get('title', 'Untitled')}\n   {p.get('summary', '')[:200]}")

        combined = "\n\n".join(texts)
        prompt = (
            "You are an ML researcher. Below are titles and abstracts of recent papers.\n"
            "Summarise the key findings and themes in 3-5 bullet points.\n\n"
            f"{combined}\n\nKey findings:"
        )

        payload = json.dumps({
            "model": self._ollama_model,
            "prompt": prompt,
            "stream": False
        }).encode("utf-8")

        req = urllib.request.Request(
            OLLAMA_API,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "No response from model.")
        except Exception as e:
            return f"LLM summarisation failed: {e}"

    def _save_research_report(self, topic: str, content: str) -> str:
        """Save a Markdown research report to disk."""
        safe_topic = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = REPORTS_DIR / f"{safe_topic}_{timestamp}.md"

        try:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            return f"Report saved to {out_path}"
        except Exception as e:
            return f"Failed to save report: {e}"

    def _get_saved_reports(self) -> str:
        """List all saved research reports."""
        if not REPORTS_DIR.exists():
            return "No reports directory found. Save a report first."

        reports = sorted(REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            return "No saved reports found."

        items = []
        for r in reports:
            size_kb = r.stat().st_size / 1024
            items.append({"name": r.name, "path": str(r), "size_kb": round(size_kb, 2)})

        return json.dumps({"count": len(items), "reports": items}, indent=2)
