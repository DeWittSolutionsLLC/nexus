"""
Proactive Agent Plugin — Nexus doesn't just respond, it anticipates.

Features:
  - Morning briefing: summarizes emails, messages, tasks, schedule
  - Smart alerts: notifies you of urgent items
  - Auto-triage: categorizes incoming messages by priority
  - End-of-day recap: what you accomplished, what's left
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.proactive")


class ProactivePlugin(BasePlugin):
    name = "proactive"
    description = "Proactive briefings, alerts, and auto-triage"
    icon = "📡"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._plugin_manager = None  # Set externally after init

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = "Proactive mode active"
        return True

    def set_plugin_manager(self, pm):
        """Give the proactive agent access to other plugins."""
        self._plugin_manager = pm

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "morning_briefing": self._morning_briefing,
            "check_urgent": self._check_urgent,
            "end_of_day": self._end_of_day,
            "quick_status": self._quick_status,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown proactive action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "morning_briefing", "description": "Full morning briefing - emails, messages, tasks, schedule", "params": []},
            {"action": "check_urgent", "description": "Check for anything urgent across all platforms", "params": []},
            {"action": "end_of_day", "description": "End of day recap and tomorrow prep", "params": []},
            {"action": "quick_status", "description": "Quick 30-second status across everything", "params": []},
        ]

    async def _gather_from_plugin(self, plugin_name: str, action: str, params: dict = None) -> str:
        """Safely try to get data from another plugin."""
        if not self._plugin_manager:
            return ""
        plugin = self._plugin_manager.get_plugin(plugin_name)
        if not plugin or not plugin.is_connected:
            return f"[{plugin_name}: not connected]"
        try:
            return await plugin.execute(action, params or {})
        except Exception as e:
            return f"[{plugin_name}: error - {str(e)[:50]}]"

    async def _morning_briefing(self, params: dict) -> str:
        """Comprehensive morning briefing — all sources fetched in parallel."""
        now = datetime.now()
        greeting = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"
        day_name = now.strftime("%A, %B %d")

        # Fetch all sources simultaneously instead of one by one
        email_data, wa_data, dc_data, gh_data, task_data, proj_data, weather_data = await asyncio.gather(
            self._gather_from_plugin("email",          "check_inbox",        {"max_results": "5"}),
            self._gather_from_plugin("whatsapp",       "list_chats",         {"limit": "5"}),
            self._gather_from_plugin("discord",        "check_dms",          {"limit": "5"}),
            self._gather_from_plugin("github",         "check_notifications", {}),
            self._gather_from_plugin("memory",         "list_tasks",         {}),
            self._gather_from_plugin("project_manager","get_summary",        {}),
            self._gather_from_plugin("weather_eye",    "get_weather",        {}),
        )

        sections = [f"{'='*50}", f"{greeting}! Here's your briefing for {day_name}.", f"{'='*50}"]

        if email_data   and "not connected" not in email_data:   sections.append(f"\n📧 EMAIL\n{email_data}")
        if wa_data      and "not connected" not in wa_data:      sections.append(f"\n💬 WHATSAPP\n{wa_data}")
        if dc_data      and "not connected" not in dc_data:      sections.append(f"\n🎮 DISCORD\n{dc_data}")
        if gh_data      and "not connected" not in gh_data:      sections.append(f"\n🐙 GITHUB\n{gh_data}")
        if task_data    and "not connected" not in task_data:    sections.append(f"\n📋 TASKS\n{task_data}")
        if proj_data    and "not connected" not in proj_data:    sections.append(f"\n🚀 PROJECTS\n{proj_data}")
        if weather_data and "not connected" not in weather_data: sections.append(f"\n🌤️ WEATHER\n{weather_data}")

        sections.append(f"\n{'='*50}")
        sections.append("How would you like to start your day?")

        return "\n".join(sections)

    async def _check_urgent(self, params: dict) -> str:
        """Quick scan for anything urgent — all sources checked in parallel."""
        email_data, wa_data, task_data = await asyncio.gather(
            self._gather_from_plugin("email",    "check_inbox", {"max_results": "5"}),
            self._gather_from_plugin("whatsapp", "list_chats",  {"limit": "5"}),
            self._gather_from_plugin("memory",   "list_tasks",  {}),
        )

        urgent_items = []
        if email_data and "unread" in email_data.lower():
            urgent_items.append(f"📧 {email_data.split(chr(10))[0]}")
        if wa_data and "🔵" in wa_data:
            for line in [l.strip() for l in wa_data.split("\n") if "🔵" in l][:3]:
                urgent_items.append(f"💬 {line}")
        if task_data and "🔴" in task_data:
            for line in [l.strip() for l in task_data.split("\n") if "🔴" in l][:3]:
                urgent_items.append(f"📋 {line}")

        if not urgent_items:
            return "✅ All clear! Nothing urgent across your platforms."
        return "🚨 Items needing attention:\n\n" + "\n".join(urgent_items)

    async def _end_of_day(self, params: dict) -> str:
        """End-of-day recap — fetched in parallel."""
        task_data, urgent = await asyncio.gather(
            self._gather_from_plugin("memory", "list_tasks", {}),
            self._check_urgent({}),
        )
        sections = ["📊 END OF DAY RECAP", "=" * 40]
        if task_data:
            sections.append(f"\n📋 Task Status:\n{task_data}")
        if "All clear" not in urgent:
            sections.append(f"\n⚠️ Still pending:\n{urgent}")
        else:
            sections.append("\n✅ All caught up across platforms!")
        sections.append(f"\n{'='*40}")
        sections.append("Want me to set any tasks for tomorrow?")
        return "\n".join(sections)

    async def _quick_status(self, params: dict) -> str:
        """30-second status check."""
        lines = ["⚡ Quick Status:"]

        # Just check what's connected and has activity
        if self._plugin_manager:
            for name, plugin in self._plugin_manager.plugins.items():
                if name in ("proactive", "voice", "screen", "memory", "file_manager"):
                    continue
                status = "🟢" if plugin.is_connected else "🔴"
                lines.append(f"  {status} {plugin.icon} {plugin.name}: {plugin.status}")

        # Task count
        task_data = await self._gather_from_plugin("memory", "list_tasks")
        if task_data and "No open tasks" not in task_data:
            task_count = task_data.count("#")
            lines.append(f"  📋 {task_count} open tasks")

        return "\n".join(lines)
