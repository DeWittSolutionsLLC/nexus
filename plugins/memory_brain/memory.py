"""
Memory Brain — Persistent local memory system.

Stores and retrieves:
  - Contact info (names, emails, phone numbers, relationships)
  - User preferences (communication style, working hours, priorities)
  - Conversation context (recent topics, ongoing tasks)
  - Learned patterns (who you email most, typical responses, schedules)

All stored as local JSON files — nothing leaves your machine.
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("nexus.memory")


class MemoryBrain:
    """
    Local persistent memory with fast fuzzy search.
    Data lives in nexus/memory/ as JSON files.
    """

    def __init__(self, memory_dir: str = "memory"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Memory stores
        self.contacts: dict = {}          # name → {email, phone, relationship, notes}
        self.preferences: dict = {}       # key → value
        self.facts: list[dict] = []       # [{fact, source, timestamp}]
        self.interaction_log: list = []   # Recent interactions for context
        self.tasks: list[dict] = []       # Active tasks/reminders
        self.patterns: dict = {}          # Learned behavioral patterns

        self._load_all()

    # ── Core Operations ───────────────────────────────────────

    def remember_contact(self, name: str, **kwargs):
        """Store or update contact info."""
        name_key = name.lower().strip()
        if name_key not in self.contacts:
            self.contacts[name_key] = {"name": name, "added": datetime.now().isoformat()}
        self.contacts[name_key].update(kwargs)
        self._save("contacts")
        logger.info(f"Remembered contact: {name}")

    def get_contact(self, name: str) -> Optional[dict]:
        """Find a contact by name (fuzzy match)."""
        name_lower = name.lower().strip()

        # Exact match
        if name_lower in self.contacts:
            return self.contacts[name_lower]

        # Fuzzy match
        try:
            from rapidfuzz import fuzz
            best_match = None
            best_score = 0
            for key, contact in self.contacts.items():
                score = fuzz.partial_ratio(name_lower, key)
                if score > best_score and score > 70:
                    best_score = score
                    best_match = contact
            return best_match
        except ImportError:
            # Fallback: substring match
            for key, contact in self.contacts.items():
                if name_lower in key or key in name_lower:
                    return contact
        return None

    def remember_preference(self, key: str, value):
        """Store a user preference."""
        self.preferences[key] = {
            "value": value,
            "updated": datetime.now().isoformat(),
        }
        self._save("preferences")

    def get_preference(self, key: str, default=None):
        """Get a stored preference."""
        pref = self.preferences.get(key)
        return pref["value"] if pref else default

    def remember_fact(self, fact: str, source: str = "user"):
        """Store a general fact or piece of information."""
        self.facts.append({
            "fact": fact,
            "source": source,
            "timestamp": datetime.now().isoformat(),
        })
        # Keep last 500 facts
        if len(self.facts) > 500:
            self.facts = self.facts[-500:]
        self._save("facts")

    def search_facts(self, query: str, limit: int = 5) -> list[dict]:
        """Search stored facts by keyword."""
        query_lower = query.lower()
        results = []
        for fact in reversed(self.facts):
            if query_lower in fact["fact"].lower():
                results.append(fact)
                if len(results) >= limit:
                    break
        return results

    def log_interaction(self, user_msg: str, bot_response: str, plugin_used: str = None):
        """Log a conversation interaction for context building."""
        self.interaction_log.append({
            "user": user_msg,
            "bot": bot_response[:200],
            "plugin": plugin_used,
            "timestamp": datetime.now().isoformat(),
        })
        # Keep last 100 interactions
        if len(self.interaction_log) > 100:
            self.interaction_log = self.interaction_log[-100:]
        self._save("interaction_log")

    # ── Task Management ───────────────────────────────────────

    def add_task(self, title: str, due: str = None, priority: str = "normal", tags: list = None) -> dict:
        """Create a tracked task."""
        task = {
            "id": len(self.tasks) + 1,
            "title": title,
            "due": due,
            "priority": priority,
            "tags": tags or [],
            "status": "open",
            "created": datetime.now().isoformat(),
        }
        self.tasks.append(task)
        self._save("tasks")
        return task

    def complete_task(self, task_id: int) -> bool:
        for task in self.tasks:
            if task["id"] == task_id:
                task["status"] = "done"
                task["completed"] = datetime.now().isoformat()
                self._save("tasks")
                return True
        return False

    def get_open_tasks(self) -> list[dict]:
        return [t for t in self.tasks if t["status"] == "open"]

    def get_due_soon(self, hours: int = 24) -> list[dict]:
        """Get tasks due within the next N hours."""
        cutoff = (datetime.now() + timedelta(hours=hours)).isoformat()
        return [
            t for t in self.tasks
            if t["status"] == "open" and t.get("due") and t["due"] <= cutoff
        ]

    # ── Context Building (for AI) ─────────────────────────────

    def get_context_summary(self) -> str:
        """Build a context string for the AI about what it knows about the user."""
        parts = []

        # Preferences
        if self.preferences:
            pref_lines = [f"  {k}: {v['value']}" for k, v in list(self.preferences.items())[:10]]
            parts.append("User preferences:\n" + "\n".join(pref_lines))

        # Recent contacts
        if self.contacts:
            contact_list = list(self.contacts.values())[:10]
            c_lines = [f"  {c['name']}: {c.get('relationship', '')} {c.get('email', '')}" for c in contact_list]
            parts.append("Known contacts:\n" + "\n".join(c_lines))

        # Open tasks
        open_tasks = self.get_open_tasks()
        if open_tasks:
            t_lines = [f"  [{t['priority']}] {t['title']}" + (f" (due: {t['due']})" if t.get('due') else "") for t in open_tasks[:8]]
            parts.append("Open tasks:\n" + "\n".join(t_lines))

        # Recent facts
        if self.facts:
            recent = self.facts[-5:]
            f_lines = [f"  - {f['fact']}" for f in recent]
            parts.append("Recent notes:\n" + "\n".join(f_lines))

        return "\n\n".join(parts) if parts else "No stored context yet."

    # ── Persistence ───────────────────────────────────────────

    def _save(self, store_name: str):
        """Save a specific store to disk."""
        data = getattr(self, store_name, None)
        if data is not None:
            path = self.memory_dir / f"{store_name}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def _load_all(self):
        """Load all stores from disk."""
        for store in ["contacts", "preferences", "facts", "interaction_log", "tasks", "patterns"]:
            path = self.memory_dir / f"{store}.json"
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        setattr(self, store, json.load(f))
                    logger.debug(f"Loaded memory store: {store}")
                except Exception as e:
                    logger.warning(f"Failed to load {store}: {e}")

    def _save_all(self):
        for store in ["contacts", "preferences", "facts", "interaction_log", "tasks", "patterns"]:
            self._save(store)
