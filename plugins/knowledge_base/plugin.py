"""
Knowledge Base Plugin — Personal notes and facts store with tagging and search.
"""

import json
import uuid
import logging
from pathlib import Path
from datetime import datetime
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.knowledge_base")

KB_FILE = Path.home() / "NexusScripts" / "knowledge_base.json"


def _load_kb() -> list[dict]:
    if not KB_FILE.exists():
        return []
    try:
        data = json.loads(KB_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Failed to load knowledge base: {e}")
        return []


def _save_kb(notes: list[dict]):
    try:
        KB_FILE.parent.mkdir(parents=True, exist_ok=True)
        KB_FILE.write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save knowledge base: {e}")


class KnowledgeBasePlugin(BasePlugin):
    name = "knowledge_base"
    description = "Personal knowledge base for notes, facts, and code snippets with tags and full-text search"
    icon = "📚"

    async def connect(self) -> bool:
        KB_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not KB_FILE.exists():
            _save_kb([])
        notes = _load_kb()
        self._connected = True
        self._status_message = f"Ready ({len(notes)} notes)"
        return True

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "add_note": self._add_note,
            "get_note": self._get_note,
            "search": self._search,
            "list_notes": self._list_notes,
            "update_note": self._update_note,
            "delete_note": self._delete_note,
            "get_stats": self._get_stats,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown action: {action}. Available: {', '.join(actions)}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "add_note", "description": "Add a new note or fact to the knowledge base", "params": ["title", "content", "tags (list)"]},
            {"action": "get_note", "description": "Retrieve a note by ID or title", "params": ["id or title"]},
            {"action": "search", "description": "Full-text search across all notes", "params": ["query"]},
            {"action": "list_notes", "description": "List all notes, optionally filtered by tag", "params": ["tag (optional)"]},
            {"action": "update_note", "description": "Update the content of an existing note", "params": ["id", "content"]},
            {"action": "delete_note", "description": "Delete a note by ID", "params": ["id"]},
            {"action": "get_stats", "description": "Get statistics about the knowledge base", "params": []},
        ]

    async def _add_note(self, params: dict) -> str:
        title = params.get("title", "").strip()
        content = params.get("content", "").strip()
        tags = params.get("tags", [])
        if not title or not content:
            return "Please provide both 'title' and 'content'."
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        notes = _load_kb()
        note_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        note = {
            "id": note_id,
            "title": title,
            "content": content,
            "tags": tags,
            "created": now,
            "updated": now,
        }
        notes.append(note)
        _save_kb(notes)
        tag_str = f" [tags: {', '.join(tags)}]" if tags else ""
        return f"Note saved. ID: {note_id}\nTitle: {title}{tag_str}"

    async def _get_note(self, params: dict) -> str:
        query = str(params.get("id", params.get("title", ""))).strip()
        if not query:
            return "Please provide an 'id' or 'title' to retrieve."
        notes = _load_kb()
        # Try exact ID match first
        note = next((n for n in notes if n["id"] == query), None)
        # Try case-insensitive title match
        if not note:
            ql = query.lower()
            note = next((n for n in notes if n["title"].lower() == ql), None)
        # Try partial title match
        if not note:
            ql = query.lower()
            note = next((n for n in notes if ql in n["title"].lower()), None)
        if not note:
            return f"No note found matching: {query}"
        return self._format_note(note)

    async def _search(self, params: dict) -> str:
        query = params.get("query", "").strip().lower()
        if not query:
            return "Please provide a search query."
        notes = _load_kb()
        matches = []
        for note in notes:
            searchable = (
                note["title"].lower() + " " +
                note["content"].lower() + " " +
                " ".join(note.get("tags", [])).lower()
            )
            if query in searchable:
                matches.append(note)

        if not matches:
            return f"No notes found matching: {query}"
        lines = [f"Found {len(matches)} note(s) matching '{query}':\n"]
        for note in matches[:10]:
            tags = f" [{', '.join(note['tags'])}]" if note.get("tags") else ""
            preview = note["content"][:100].replace("\n", " ")
            lines.append(f"  [{note['id']}] {note['title']}{tags}")
            lines.append(f"    {preview}...")
        return "\n".join(lines)

    async def _list_notes(self, params: dict) -> str:
        tag_filter = params.get("tag", "").strip().lower()
        notes = _load_kb()
        if tag_filter:
            notes = [n for n in notes if tag_filter in [t.lower() for t in n.get("tags", [])]]
        if not notes:
            msg = f"No notes with tag '{tag_filter}'." if tag_filter else "Knowledge base is empty."
            return msg

        lines = [f"Notes{f' tagged [{tag_filter}]' if tag_filter else ''} ({len(notes)} total):\n"]
        for note in sorted(notes, key=lambda n: n["updated"], reverse=True)[:30]:
            tags = f" [{', '.join(note['tags'])}]" if note.get("tags") else ""
            updated = note["updated"][:10]
            lines.append(f"  [{note['id']}] {note['title']}{tags}  ({updated})")
        return "\n".join(lines)

    async def _update_note(self, params: dict) -> str:
        note_id = params.get("id", "").strip()
        content = params.get("content", "").strip()
        if not note_id or not content:
            return "Please provide 'id' and 'content'."
        notes = _load_kb()
        for note in notes:
            if note["id"] == note_id:
                note["content"] = content
                note["updated"] = datetime.now().isoformat()
                _save_kb(notes)
                return f"Note [{note_id}] '{note['title']}' updated."
        return f"Note not found: {note_id}"

    async def _delete_note(self, params: dict) -> str:
        note_id = params.get("id", "").strip()
        if not note_id:
            return "Please provide the note 'id' to delete."
        notes = _load_kb()
        original_len = len(notes)
        notes = [n for n in notes if n["id"] != note_id]
        if len(notes) == original_len:
            return f"Note not found: {note_id}"
        _save_kb(notes)
        return f"Note [{note_id}] deleted. ({len(notes)} notes remaining)"

    async def _get_stats(self, params: dict) -> str:
        notes = _load_kb()
        if not notes:
            return "Knowledge base is empty."
        all_tags: dict[str, int] = {}
        for note in notes:
            for tag in note.get("tags", []):
                all_tags[tag] = all_tags.get(tag, 0) + 1

        top_tags = sorted(all_tags.items(), key=lambda x: -x[1])[:10]
        tag_lines = ", ".join(f"{t} ({c})" for t, c in top_tags) or "none"
        oldest = min(notes, key=lambda n: n["created"])["created"][:10]
        newest = max(notes, key=lambda n: n["updated"])["updated"][:10]
        total_chars = sum(len(n["content"]) for n in notes)

        return (
            f"Knowledge Base Statistics:\n"
            f"  Total notes:   {len(notes)}\n"
            f"  Unique tags:   {len(all_tags)}\n"
            f"  Total content: {total_chars:,} characters\n"
            f"  Oldest note:   {oldest}\n"
            f"  Last updated:  {newest}\n"
            f"  Top tags:      {tag_lines}"
        )

    @staticmethod
    def _format_note(note: dict) -> str:
        tags = f"\nTags: {', '.join(note['tags'])}" if note.get("tags") else ""
        return (
            f"[{note['id']}] {note['title']}\n"
            f"Created: {note['created'][:16]}  |  Updated: {note['updated'][:16]}"
            f"{tags}\n"
            f"{'─' * 40}\n"
            f"{note['content']}"
        )
