"""
Consolidate & Optimize Knowledge Base Plugin
Deduplicates, compacts, archives, and reports on Nexus memory stores.
All operations are local — no network access.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.kb_optimizer")

MEMORY_DIR = Path("memory")
ARCHIVE_DIR = MEMORY_DIR / "archive"

# Stores that are lists vs. dicts
LIST_STORES = {"facts", "interaction_log", "tasks"}
DICT_STORES = {"contacts", "preferences", "patterns"}
ALL_STORES = LIST_STORES | DICT_STORES


class ConsolidateOptimizeKnowledgeBasePlugin(BasePlugin):
    name = "consolidate_optimize_knowledge_base"
    description = "Deduplicates, trims, and optimizes Nexus memory stores"
    icon = "🗃️"

    async def connect(self) -> bool:
        try:
            if not MEMORY_DIR.exists():
                self._status_message = "Memory directory not found"
                return False
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            stats = self._load_stats()
            self._connected = True
            self._status_message = (
                f"{stats['facts']} facts, {stats['interactions']} interactions, "
                f"{stats['tasks']} tasks"
            )
            return True
        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            return False

    async def execute(self, action: str, params: dict) -> str:
        handlers = {
            "consolidate": self._consolidate,
            "optimize":    self._optimize,
            "report":      self._report,
            "deduplicate": self._deduplicate,
            "archive_old": self._archive_old,
        }
        handler = handlers.get(action)
        if not handler:
            return f"Unknown action '{action}'. Available: {', '.join(handlers)}"
        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"KB optimizer error in '{action}': {e}")
            return f"Error during {action}: {e}"

    def get_capabilities(self) -> list[dict]:
        return [
            {
                "action": "consolidate",
                "description": "Deduplicate facts, contacts, tasks, and interactions",
                "params": [],
            },
            {
                "action": "optimize",
                "description": "Trim oversized stores and sort tasks for fast retrieval",
                "params": [],
            },
            {
                "action": "report",
                "description": "Show knowledge base stats and health warnings",
                "params": [],
            },
            {
                "action": "deduplicate",
                "description": "Remove exact-duplicate entries from one store",
                "params": ["store"],
            },
            {
                "action": "archive_old",
                "description": "Move old completed tasks / interactions to memory/archive/",
                "params": ["days"],
            },
        ]

    # ── Persistence helpers ────────────────────────────────────

    def _load(self, store: str):
        path = MEMORY_DIR / f"{store}.json"
        if not path.exists():
            return {} if store in DICT_STORES else []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load {store}: {e}")
            return {} if store in DICT_STORES else []

    def _save(self, store: str, data) -> None:
        path = MEMORY_DIR / f"{store}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def _load_stats(self) -> dict:
        return {
            "facts":        len(self._load("facts")),
            "interactions": len(self._load("interaction_log")),
            "tasks":        len(self._load("tasks")),
            "contacts":     len(self._load("contacts")),
        }

    # ── Actions ────────────────────────────────────────────────

    async def _consolidate(self, params: dict) -> str:
        """Deduplicate all stores and merge contacts sharing an email."""
        lines = ["Knowledge base consolidation:"]
        total_removed = 0

        # --- Facts: deduplicate by normalised text ---
        facts = self._load("facts")
        seen: set = set()
        unique_facts = []
        for f in facts:
            key = f.get("fact", "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique_facts.append(f)
        removed = len(facts) - len(unique_facts)
        if removed:
            self._save("facts", unique_facts)
        lines.append(f"  Facts:        removed {removed} duplicates ({len(unique_facts)} remain)")
        total_removed += removed

        # --- Interaction log: deduplicate by (user, bot-prefix, timestamp) ---
        interactions = self._load("interaction_log")
        seen_ix: set = set()
        unique_ix = []
        for ix in interactions:
            key = (ix.get("user", ""), ix.get("bot", "")[:100], ix.get("timestamp", ""))
            if key not in seen_ix:
                seen_ix.add(key)
                unique_ix.append(ix)
        removed = len(interactions) - len(unique_ix)
        if removed:
            self._save("interaction_log", unique_ix)
        lines.append(f"  Interactions: removed {removed} duplicates ({len(unique_ix)} remain)")
        total_removed += removed

        # --- Tasks: keep newest entry per title ---
        tasks = self._load("tasks")
        title_map: dict = {}
        for t in tasks:
            title = t.get("title", "").strip().lower()
            if title not in title_map or t.get("created", "") > title_map[title].get("created", ""):
                title_map[title] = t
        unique_tasks = list(title_map.values())
        removed = len(tasks) - len(unique_tasks)
        if removed:
            self._save("tasks", unique_tasks)
        lines.append(f"  Tasks:        removed {removed} duplicates ({len(unique_tasks)} remain)")
        total_removed += removed

        # --- Contacts: merge entries that share an email address ---
        contacts = self._load("contacts")
        email_to_key: dict = {}
        merged = 0
        for key in list(contacts.keys()):
            contact = contacts.get(key)
            if contact is None:
                continue
            email = contact.get("email", "").strip().lower()
            if not email:
                continue
            if email in email_to_key:
                existing = contacts[email_to_key[email]]
                for field, value in contact.items():
                    if value and not existing.get(field):
                        existing[field] = value
                del contacts[key]
                merged += 1
            else:
                email_to_key[email] = key
        if merged:
            self._save("contacts", contacts)
        lines.append(f"  Contacts:     merged {merged} duplicates ({len(contacts)} remain)")
        total_removed += merged

        lines.append(f"\nTotal entries removed: {total_removed}")
        return "\n".join(lines)

    async def _optimize(self, params: dict) -> str:
        """Trim oversized stores, remove empty entries, sort tasks."""
        lines = ["Knowledge base optimization:"]

        # Trim interaction_log to last 100 (MemoryBrain's built-in cap)
        interactions = self._load("interaction_log")
        before = len(interactions)
        if len(interactions) > 100:
            interactions = interactions[-100:]
            self._save("interaction_log", interactions)
        lines.append(f"  Interactions: trimmed {before - len(interactions)} old entries ({len(interactions)} kept)")

        # Trim facts to last 500 (MemoryBrain's built-in cap)
        facts = self._load("facts")
        before = len(facts)
        if len(facts) > 500:
            facts = facts[-500:]
            self._save("facts", facts)
        lines.append(f"  Facts:        trimmed {before - len(facts)} old entries ({len(facts)} kept)")

        # Remove empty fact entries
        clean_facts = [f for f in self._load("facts") if f.get("fact", "").strip()]
        nulls = len(self._load("facts")) - len(clean_facts)
        if nulls:
            self._save("facts", clean_facts)
        lines.append(f"  Facts:        removed {nulls} empty entries")

        # Sort tasks: open first, then by priority, then by due date
        tasks = self._load("tasks")
        priority_order = {"high": 0, "normal": 1, "low": 2}
        tasks.sort(key=lambda t: (
            0 if t.get("status") == "open" else 1,
            priority_order.get(t.get("priority", "normal"), 1),
            t.get("due") or "9999",
        ))
        self._save("tasks", tasks)
        lines.append(f"  Tasks:        sorted {len(tasks)} entries by status/priority/due")

        return "\n".join(lines)

    async def _report(self, params: dict) -> str:
        """Print a health summary of all memory stores."""
        stats = self._load_stats()
        tasks = self._load("tasks")
        facts = self._load("facts")
        open_tasks  = [t for t in tasks if t.get("status") == "open"]
        done_tasks  = [t for t in tasks if t.get("status") == "done"]

        sources: dict = defaultdict(int)
        for f in facts:
            sources[f.get("source", "unknown")] += 1

        lines = [
            "Knowledge Base Health Report",
            "─" * 34,
            f"  Contacts:     {stats['contacts']}",
            f"  Facts:        {stats['facts']}  (by source: {dict(sources)})",
            f"  Interactions: {stats['interactions']} / 100",
            f"  Tasks open:   {len(open_tasks)}",
            f"  Tasks done:   {len(done_tasks)}",
        ]

        warnings = []
        if stats["interactions"] >= 90:
            warnings.append("⚠  Interaction log near limit — run 'optimize'")
        if stats["facts"] >= 450:
            warnings.append("⚠  Facts store near limit — run 'optimize'")
        if len(done_tasks) > 50:
            warnings.append(f"⚠  {len(done_tasks)} completed tasks accumulating — run 'archive_old'")
        if warnings:
            lines.append("")
            lines.extend(warnings)

        if ARCHIVE_DIR.exists():
            archived = list(ARCHIVE_DIR.glob("*.json"))
            if archived:
                lines.append(f"\n  Archive files: {len(archived)}")

        return "\n".join(lines)

    async def _deduplicate(self, params: dict) -> str:
        """Remove exact-duplicate entries from a single store."""
        store = params.get("store", "facts")
        if store not in ALL_STORES:
            return f"Unknown store '{store}'. Valid stores: {', '.join(sorted(ALL_STORES))}"

        data = self._load(store)
        if not isinstance(data, list):
            return f"'{store}' is a dict store — use 'consolidate' for merging"

        before = len(data)
        seen: set = set()
        unique = []
        for item in data:
            key = json.dumps(item, sort_keys=True)
            if key not in seen:
                seen.add(key)
                unique.append(item)
        removed = before - len(unique)
        if removed:
            self._save(store, unique)
        return f"Deduplicated '{store}': removed {removed} exact duplicates ({len(unique)} remain)"

    async def _archive_old(self, params: dict) -> str:
        """Move old completed tasks and old interactions to memory/archive/."""
        days = int(params.get("days", 30))
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        lines = [f"Archiving entries older than {days} days (cutoff: {cutoff[:10]}):"]

        # Completed tasks older than cutoff
        tasks = self._load("tasks")
        keep, archive = [], []
        for t in tasks:
            completed_at = t.get("completed", "")
            if t.get("status") == "done" and completed_at and completed_at < cutoff:
                archive.append(t)
            else:
                keep.append(t)
        if archive:
            self._save("tasks", keep)
            out = ARCHIVE_DIR / f"tasks_archived_{stamp}.json"
            with open(out, "w", encoding="utf-8") as f:
                json.dump(archive, f, indent=2, default=str)
        lines.append(f"  Tasks:        archived {len(archive)} completed ({len(keep)} remain)")

        # Interactions older than cutoff
        interactions = self._load("interaction_log")
        keep_ix, archive_ix = [], []
        for ix in interactions:
            if ix.get("timestamp", "9999") < cutoff:
                archive_ix.append(ix)
            else:
                keep_ix.append(ix)
        if archive_ix:
            self._save("interaction_log", keep_ix)
            out = ARCHIVE_DIR / f"interactions_archived_{stamp}.json"
            with open(out, "w", encoding="utf-8") as f:
                json.dump(archive_ix, f, indent=2, default=str)
        lines.append(f"  Interactions: archived {len(archive_ix)} old entries ({len(keep_ix)} remain)")

        return "\n".join(lines)
