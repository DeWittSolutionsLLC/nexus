from core.plugin_manager import BasePlugin
import logging, json, uuid, requests
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("nexus.plugins.dream_journal")

JOURNAL_FILE = Path.home() / "NexusScripts" / "dream_journal.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"


def _ollama(prompt: str) -> str:
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=60)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"[Ollama error: {e}]"


def _load() -> list:
    if JOURNAL_FILE.exists():
        try:
            return json.loads(JOURNAL_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(data: list):
    JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class DreamJournalPlugin(BasePlugin):
    name = "dream_journal"
    description = "Record and analyze dreams with Jungian AI analysis, symbolism, and theme tracking."
    icon = "🌙"

    async def connect(self) -> bool:
        JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._connected = True
        self._status_message = "Ready"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "add_dream", "description": "Record a dream with optional title, mood, and lucidity flag", "params": ["content", "title", "mood", "lucid"]},
            {"action": "analyze_dream", "description": "AI Jungian analysis of a dream by id or content", "params": ["id", "content"]},
            {"action": "list_dreams", "description": "List recent dreams with titles and dates", "params": ["limit"]},
            {"action": "get_dream", "description": "Get full dream entry by id or date", "params": ["id", "date"]},
            {"action": "find_themes", "description": "Search dreams by recurring theme", "params": ["theme"]},
            {"action": "get_stats", "description": "Dream journal statistics", "params": []},
            {"action": "delete_dream", "description": "Delete a dream by id", "params": ["id"]},
        ]

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "add_dream":
                return await self._add_dream(params)
            elif action == "analyze_dream":
                return await self._analyze_dream(params)
            elif action == "list_dreams":
                return await self._list_dreams(params)
            elif action == "get_dream":
                return await self._get_dream(params)
            elif action == "find_themes":
                return await self._find_themes(params)
            elif action == "get_stats":
                return await self._get_stats(params)
            elif action == "delete_dream":
                return await self._delete_dream(params)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.exception("DreamJournal error")
            return f"Error in dream_journal.{action}: {e}"

    async def _add_dream(self, params: dict) -> str:
        content = params.get("content", "").strip()
        if not content:
            return "No dream content provided."
        title = params.get("title", "").strip()
        mood = params.get("mood", "").strip()
        lucid = bool(params.get("lucid", False))

        ai_prompt = (
            f"Analyze this dream briefly from a Jungian perspective. Identify 3-5 themes (as a comma-separated list first), "
            f"then give a short analysis of symbols and archetypes.\n\nDream: {content}"
        )
        ai_response = _ollama(ai_prompt)

        themes = []
        lines = ai_response.splitlines()
        if lines:
            first_line = lines[0]
            if "," in first_line and len(first_line) < 200:
                themes = [t.strip().lower() for t in first_line.split(",") if t.strip()]

        if not title:
            title_prompt = f"Generate a short, evocative 4-6 word title for this dream. Reply with only the title.\n\nDream: {content}"
            title = _ollama(title_prompt)

        entry = {
            "id": str(uuid.uuid4())[:8],
            "date": datetime.now().isoformat(),
            "title": title,
            "content": content,
            "mood": mood or "unspecified",
            "themes": themes,
            "ai_analysis": ai_response,
            "lucid": lucid,
        }
        data = _load()
        data.append(entry)
        _save(data)
        return (
            f"Dream recorded (ID: {entry['id']})\n"
            f"Title: {entry['title']}\n"
            f"Themes: {', '.join(entry['themes']) or 'none detected'}\n"
            f"Lucid: {lucid}\n\n"
            f"AI Analysis:\n{ai_response}"
        )

    async def _analyze_dream(self, params: dict) -> str:
        dream_id = params.get("id", "").strip()
        content = params.get("content", "").strip()
        if dream_id:
            data = _load()
            entry = next((d for d in data if d["id"] == dream_id), None)
            if not entry:
                return f"No dream found with ID: {dream_id}"
            content = entry["content"]
            title = entry.get("title", "Dream")
        elif not content:
            return "Provide either an id or content to analyze."
        else:
            title = "Dream"

        prompt = (
            f"Perform a detailed Jungian analysis of the following dream. Cover:\n"
            f"1. Major symbols and their archetypal meanings\n"
            f"2. Shadow, anima/animus, or Self archetypes present\n"
            f"3. Possible psychological interpretation\n"
            f"4. Potential messages from the unconscious\n"
            f"5. Any recurring motifs worth noting\n\n"
            f"Dream: {content}"
        )
        analysis = _ollama(prompt)
        return f"Deep Analysis of '{title}':\n\n{analysis}"

    async def _list_dreams(self, params: dict) -> str:
        limit = int(params.get("limit", 10))
        data = _load()
        if not data:
            return "No dreams recorded yet."
        recent = sorted(data, key=lambda d: d["date"], reverse=True)[:limit]
        lines = [f"Recent Dreams ({len(recent)} of {len(data)} total):"]
        for d in recent:
            date_str = d["date"][:10]
            lucid_tag = " [LUCID]" if d.get("lucid") else ""
            lines.append(f"  [{d['id']}] {date_str} — {d['title']}{lucid_tag} | Mood: {d.get('mood','?')} | Themes: {', '.join(d.get('themes',[]))}")
        return "\n".join(lines)

    async def _get_dream(self, params: dict) -> str:
        dream_id = params.get("id", "").strip()
        date_str = params.get("date", "").strip()
        data = _load()
        entry = None
        if dream_id:
            entry = next((d for d in data if d["id"] == dream_id), None)
        elif date_str:
            entry = next((d for d in data if d["date"].startswith(date_str)), None)
        if not entry:
            return "Dream not found."
        return (
            f"Dream ID: {entry['id']}\n"
            f"Date: {entry['date'][:16]}\n"
            f"Title: {entry['title']}\n"
            f"Mood: {entry.get('mood','unspecified')}\n"
            f"Lucid: {entry.get('lucid', False)}\n"
            f"Themes: {', '.join(entry.get('themes',[]))}\n\n"
            f"Content:\n{entry['content']}\n\n"
            f"AI Analysis:\n{entry.get('ai_analysis','Not analyzed yet.')}"
        )

    async def _find_themes(self, params: dict) -> str:
        theme = params.get("theme", "").lower().strip()
        if not theme:
            return "No theme provided."
        data = _load()
        matches = [d for d in data if theme in [t.lower() for t in d.get("themes", [])] or theme in d["content"].lower()]
        if not matches:
            return f"No dreams found containing theme: '{theme}'"
        lines = [f"Dreams matching theme '{theme}' ({len(matches)} found):"]
        for d in sorted(matches, key=lambda x: x["date"], reverse=True):
            lines.append(f"  [{d['id']}] {d['date'][:10]} — {d['title']}")
        return "\n".join(lines)

    async def _get_stats(self, params: dict) -> str:
        data = _load()
        if not data:
            return "No dreams recorded yet."
        lucid_count = sum(1 for d in data if d.get("lucid"))
        theme_counts: dict = {}
        mood_counts: dict = {}
        for d in data:
            for t in d.get("themes", []):
                theme_counts[t] = theme_counts.get(t, 0) + 1
            mood = d.get("mood", "unspecified")
            mood_counts[mood] = mood_counts.get(mood, 0) + 1
        top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        mood_dist = ", ".join(f"{m}: {c}" for m, c in sorted(mood_counts.items(), key=lambda x: x[1], reverse=True))
        theme_str = ", ".join(f"{t} ({c})" for t, c in top_themes) or "none"
        return (
            f"Dream Journal Statistics:\n"
            f"  Total dreams: {len(data)}\n"
            f"  Lucid dreams: {lucid_count}\n"
            f"  Top themes: {theme_str}\n"
            f"  Mood distribution: {mood_dist}"
        )

    async def _delete_dream(self, params: dict) -> str:
        dream_id = params.get("id", "").strip()
        if not dream_id:
            return "No id provided."
        data = _load()
        new_data = [d for d in data if d["id"] != dream_id]
        if len(new_data) == len(data):
            return f"No dream found with ID: {dream_id}"
        _save(new_data)
        return f"Dream {dream_id} deleted."
