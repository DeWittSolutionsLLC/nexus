"""
Task Automator Plugin — Define named macros that chain multiple plugin actions.

"Every morning at 9: check weather + email + projects then brief me"
→ Saved as a macro. Run with one phrase or on a schedule.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.task_automator")

MACROS_FILE = Path.home() / "NexusScripts" / "macros.json"


class TaskAutomatorPlugin(BasePlugin):
    name = "task_automator"
    description = "Define and run multi-step automation macros across all plugins"
    icon = "🤖"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._plugin_manager = None   # set externally after init
        self._macros: dict[str, dict] = {}
        self._load_macros()

    def set_plugin_manager(self, pm):
        self._plugin_manager = pm

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = f"{len(self._macros)} macros loaded"
        return True

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "create_macro": self._create_macro,
            "run_macro":    self._run_macro,
            "list_macros":  self._list_macros,
            "delete_macro": self._delete_macro,
            "show_macro":   self._show_macro,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "create_macro", "description": "Create a named multi-step automation macro", "params": ["name", "description", "steps"]},
            {"action": "run_macro",    "description": "Run a saved macro by name", "params": ["name"]},
            {"action": "list_macros",  "description": "List all saved macros", "params": []},
            {"action": "delete_macro", "description": "Delete a macro", "params": ["name"]},
            {"action": "show_macro",   "description": "Show the steps of a macro", "params": ["name"]},
        ]

    # ── Built-in macros shipped with Nexus ───────────────────────────────────

    _BUILT_INS = {
        "morning_routine": {
            "description": "Full morning briefing — weather, email, projects, urgent items",
            "steps": [
                {"plugin": "weather_eye",    "action": "get_weather",        "params": {}},
                {"plugin": "email",          "action": "check_inbox",        "params": {}},
                {"plugin": "project_manager","action": "get_overdue",        "params": {}},
                {"plugin": "proactive",      "action": "morning_briefing",   "params": {}},
            ],
        },
        "end_of_day": {
            "description": "End-of-day wrap-up — project summary, invoice check, recap",
            "steps": [
                {"plugin": "project_manager","action": "get_summary",        "params": {}},
                {"plugin": "invoice_system", "action": "get_summary",        "params": {}},
                {"plugin": "proactive",      "action": "end_of_day",         "params": {}},
            ],
        },
        "system_check": {
            "description": "Full system health check — CPU, RAM, disk, uptime",
            "steps": [
                {"plugin": "system_monitor", "action": "get_full_report",    "params": {}},
                {"plugin": "uptime_monitor", "action": "check_all",          "params": {}},
            ],
        },
        "client_update": {
            "description": "Check all client-facing services — email, projects, invoices",
            "steps": [
                {"plugin": "email",          "action": "check_inbox",        "params": {}},
                {"plugin": "project_manager","action": "list_projects",      "params": {}},
                {"plugin": "invoice_system", "action": "list_invoices",      "params": {}},
            ],
        },
    }

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _create_macro(self, params: dict) -> str:
        name = params.get("name", "").strip().lower().replace(" ", "_")
        description = params.get("description", "Custom macro")
        steps = params.get("steps", [])

        if not name:
            return "❌ Please provide a name for the macro."
        if not steps:
            return (
                "❌ Please provide steps. Example:\n"
                '  steps: [{"plugin":"weather_eye","action":"get_weather","params":{}}, ...]'
            )

        self._macros[name] = {
            "description": description,
            "steps": steps,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "run_count": 0,
        }
        self._save_macros()

        step_list = "\n".join(f"  {i+1}. {s['plugin']} → {s['action']}" for i, s in enumerate(steps))
        return f"✅ Macro '{name}' saved, sir.\n\nSteps:\n{step_list}\n\nSay 'run macro {name}' to execute it."

    async def _run_macro(self, params: dict) -> str:
        name = params.get("name", "").strip().lower().replace(" ", "_")

        # Check user macros then built-ins
        macro = self._macros.get(name) or self._BUILT_INS.get(name)
        if not macro:
            available = list(self._macros.keys()) + list(self._BUILT_INS.keys())
            return f"❌ Macro '{name}' not found.\n\nAvailable: {', '.join(available)}"

        if not self._plugin_manager:
            return "❌ Plugin manager not connected — cannot execute macro steps."

        steps = macro["steps"]
        results = [f"🤖 Running macro: {name}\n"]

        for i, step in enumerate(steps):
            plugin_name = step.get("plugin", "")
            action = step.get("action", "")
            step_params = step.get("params", {})

            plugin = self._plugin_manager.get_plugin(plugin_name)
            if not plugin:
                results.append(f"  ⚠️  Step {i+1}: plugin '{plugin_name}' not found — skipping")
                continue

            results.append(f"\n━━ Step {i+1}: {plugin_name} → {action} ━━")
            try:
                out = await plugin.execute(action, step_params)
                results.append(out)
            except Exception as e:
                results.append(f"  ❌ Error: {e}")

            await asyncio.sleep(0.1)   # small gap between steps

        # Update run count
        if name in self._macros:
            self._macros[name]["run_count"] = self._macros[name].get("run_count", 0) + 1
            self._macros[name]["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            self._save_macros()

        return "\n".join(results)

    async def _list_macros(self, params: dict) -> str:
        lines = ["🤖 Available Macros:\n"]
        lines.append("── Built-in ──")
        for name, data in self._BUILT_INS.items():
            lines.append(f"  • {name}  —  {data['description']}")
        if self._macros:
            lines.append("\n── Custom ──")
            for name, data in self._macros.items():
                runs = data.get("run_count", 0)
                lines.append(f"  • {name}  —  {data['description']}  (run {runs}×)")
        lines.append(f"\nSay 'run macro <name>' to execute any macro.")
        return "\n".join(lines)

    async def _show_macro(self, params: dict) -> str:
        name = params.get("name", "").strip().lower().replace(" ", "_")
        macro = self._macros.get(name) or self._BUILT_INS.get(name)
        if not macro:
            return f"❌ Macro '{name}' not found."
        lines = [f"🤖 Macro: {name}", f"   {macro['description']}\n", "Steps:"]
        for i, step in enumerate(macro["steps"]):
            p = json.dumps(step.get("params", {})) if step.get("params") else "{}"
            lines.append(f"  {i+1}. [{step['plugin']}] {step['action']}  params={p}")
        return "\n".join(lines)

    async def _delete_macro(self, params: dict) -> str:
        name = params.get("name", "").strip().lower().replace(" ", "_")
        if name in self._BUILT_INS:
            return f"❌ '{name}' is a built-in macro and cannot be deleted."
        if name not in self._macros:
            return f"❌ Macro '{name}' not found."
        del self._macros[name]
        self._save_macros()
        return f"🗑️ Macro '{name}' deleted."

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_macros(self):
        MACROS_FILE.parent.mkdir(exist_ok=True)
        if MACROS_FILE.exists():
            try:
                self._macros = json.loads(MACROS_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._macros = {}

    def _save_macros(self):
        try:
            MACROS_FILE.write_text(json.dumps(self._macros, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save macros: {e}")
