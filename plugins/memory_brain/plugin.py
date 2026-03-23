"""
Memory Brain Plugin — Persistent memory so Nexus remembers you.
"""

import logging
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.memory")


class MemoryPlugin(BasePlugin):
    name = "memory"
    description = "Persistent memory - contacts, preferences, tasks, notes"
    icon = "🧠"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.brain = None

    async def connect(self) -> bool:
        try:
            from plugins.memory_brain.memory import MemoryBrain
            self.brain = MemoryBrain(self.config.get("memory_dir", "memory"))
            contact_count = len(self.brain.contacts)
            task_count = len(self.brain.get_open_tasks())
            self._connected = True
            self._status_message = f"{contact_count} contacts, {task_count} tasks"
            return True
        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self.brain:
            return "Memory not initialized"

        actions = {
            "remember_contact": self._remember_contact,
            "find_contact": self._find_contact,
            "remember": self._remember_fact,
            "recall": self._recall,
            "set_preference": self._set_preference,
            "add_task": self._add_task,
            "list_tasks": self._list_tasks,
            "complete_task": self._complete_task,
            "get_context": self._get_context,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown memory action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "remember_contact", "description": "Store contact info (name, email, phone, relationship)", "params": ["name", "email", "phone", "relationship"]},
            {"action": "find_contact", "description": "Look up a contact by name", "params": ["name"]},
            {"action": "remember", "description": "Remember a fact or note", "params": ["fact"]},
            {"action": "recall", "description": "Search stored facts and notes", "params": ["query"]},
            {"action": "set_preference", "description": "Set a user preference", "params": ["key", "value"]},
            {"action": "add_task", "description": "Create a task or reminder", "params": ["title", "due", "priority"]},
            {"action": "list_tasks", "description": "Show open tasks", "params": []},
            {"action": "complete_task", "description": "Mark a task as done", "params": ["task_id"]},
            {"action": "get_context", "description": "Get summary of everything Nexus knows about the user", "params": []},
        ]

    async def _remember_contact(self, params: dict) -> str:
        name = params.get("name", "")
        if not name:
            return "Need a name to store a contact."
        kwargs = {k: v for k, v in params.items() if k != "name" and v}
        self.brain.remember_contact(name, **kwargs)
        return f"🧠 Remembered contact: {name}"

    async def _find_contact(self, params: dict) -> str:
        name = params.get("name", "")
        contact = self.brain.get_contact(name)
        if not contact:
            return f"No contact found for '{name}'"
        lines = [f"👤 {contact.get('name', name)}"]
        for k, v in contact.items():
            if k not in ("name", "added") and v:
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    async def _remember_fact(self, params: dict) -> str:
        fact = params.get("fact", "")
        if not fact:
            return "What should I remember?"
        self.brain.remember_fact(fact, source="user")
        return f"🧠 Noted: {fact}"

    async def _recall(self, params: dict) -> str:
        query = params.get("query", "")
        results = self.brain.search_facts(query)
        if not results:
            return f"Nothing stored about '{query}'"
        lines = [f"  - {r['fact']} ({r['timestamp'][:10]})" for r in results]
        return f"🧠 What I know about '{query}':\n\n" + "\n".join(lines)

    async def _set_preference(self, params: dict) -> str:
        key = params.get("key", "")
        value = params.get("value", "")
        if not key:
            return "Need a preference name."
        self.brain.remember_preference(key, value)
        return f"🧠 Preference saved: {key} = {value}"

    async def _add_task(self, params: dict) -> str:
        title = params.get("title", "")
        if not title:
            return "What's the task?"
        task = self.brain.add_task(
            title, due=params.get("due"), priority=params.get("priority", "normal")
        )
        return f"✅ Task #{task['id']}: {title}" + (f" (due: {task['due']})" if task.get("due") else "")

    async def _list_tasks(self, params: dict) -> str:
        tasks = self.brain.get_open_tasks()
        if not tasks:
            return "No open tasks!"
        lines = []
        for t in tasks:
            pri = {"high": "🔴", "normal": "🟡", "low": "🟢"}.get(t["priority"], "⚪")
            due = f" (due: {t['due']})" if t.get("due") else ""
            lines.append(f"  {pri} #{t['id']} {t['title']}{due}")
        return f"📋 Open tasks ({len(tasks)}):\n\n" + "\n".join(lines)

    async def _complete_task(self, params: dict) -> str:
        task_id = int(params.get("task_id", 0))
        if self.brain.complete_task(task_id):
            return f"✅ Task #{task_id} marked as done!"
        return f"Task #{task_id} not found."

    async def _get_context(self, params: dict) -> str:
        return self.brain.get_context_summary()
