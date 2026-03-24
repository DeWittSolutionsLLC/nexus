"""
Hotkey Daemon Plugin — Global keyboard shortcuts that work even when minimized.

Default bindings:
  Win+Space  → Voice activate JARVIS
  Win+S      → Screenshot + describe screen
  Win+B      → Morning briefing
  Win+T      → Time tracker toggle
  Win+P      → Quick status

All bindings configurable. Uses 'keyboard' library for global hooks.
"""

import asyncio
import logging
import threading
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.hotkey_daemon")


class HotkeyDaemonPlugin(BasePlugin):
    name = "hotkey_daemon"
    description = "Global hotkeys — control JARVIS from anywhere on your system"
    icon = "⌨️"

    _DEFAULT_BINDINGS = {
        "win+space": {"plugin": "voice",         "action": "listen",         "params": {}, "description": "Voice activate JARVIS"},
        "win+s":     {"plugin": "vision_ai",     "action": "describe_screen","params": {}, "description": "Screenshot + describe screen"},
        "win+b":     {"plugin": "proactive",     "action": "morning_briefing","params": {}, "description": "Morning briefing"},
        "win+t":     {"plugin": "time_tracker",  "action": "get_today",      "params": {}, "description": "Today's time summary"},
        "win+p":     {"plugin": "proactive",     "action": "quick_status",   "params": {}, "description": "Quick status"},
        "win+c":     {"plugin": "system_monitor","action": "get_stats",      "params": {}, "description": "System stats"},
    }

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._plugin_manager = None
        self._chat_callback = None    # set externally to show output in UI
        self._bindings: dict[str, dict] = dict(self._DEFAULT_BINDINGS)
        self._registered: list[str] = []
        self._active = False

    def set_plugin_manager(self, pm):
        self._plugin_manager = pm

    def set_chat_callback(self, cb):
        """cb(text: str) — called when a hotkey fires and we have output."""
        self._chat_callback = cb

    async def connect(self) -> bool:
        loop = asyncio.get_event_loop()

        def _check():
            try:
                import keyboard  # noqa: F401
                return True
            except ImportError:
                return False

        try:
            ok = await asyncio.wait_for(loop.run_in_executor(None, _check), timeout=5.0)
            if not ok:
                self._status_message = "keyboard library not installed (pip install keyboard)"
                return False
            # Start the daemon
            threading.Thread(target=self._start_daemon, daemon=True).start()
            self._connected = True
            self._status_message = f"{len(self._bindings)} hotkeys active"
            return True
        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            return False

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "list_hotkeys":     self._list_hotkeys,
            "register_hotkey":  self._register_hotkey,
            "unregister_hotkey":self._unregister_hotkey,
            "show_bindings":    self._list_hotkeys,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "list_hotkeys",     "description": "List all registered global hotkeys", "params": []},
            {"action": "register_hotkey",  "description": "Register a new global hotkey", "params": ["hotkey", "plugin", "action", "description"]},
            {"action": "unregister_hotkey","description": "Unregister a hotkey", "params": ["hotkey"]},
        ]

    # ── Daemon ────────────────────────────────────────────────────────────────

    def _start_daemon(self):
        try:
            import keyboard
            self._active = True
            for hotkey, binding in self._bindings.items():
                self._safe_register(hotkey, binding)
            logger.info(f"Hotkey daemon active — {len(self._bindings)} bindings registered")
            # Keep thread alive
            import time
            while self._active:
                time.sleep(1)
        except Exception as e:
            logger.error(f"Hotkey daemon error: {e}")

    def _safe_register(self, hotkey: str, binding: dict):
        try:
            import keyboard
            keyboard.add_hotkey(hotkey, lambda b=binding: self._fire(b))
            self._registered.append(hotkey)
            logger.debug(f"Registered hotkey: {hotkey} → {binding['plugin']}.{binding['action']}")
        except Exception as e:
            logger.warning(f"Could not register hotkey '{hotkey}': {e}")

    def _fire(self, binding: dict):
        """Called in keyboard hook thread — schedule execution on asyncio loop."""
        plugin_name = binding.get("plugin", "")
        action = binding.get("action", "")
        params = binding.get("params", {})
        desc = binding.get("description", f"{plugin_name}.{action}")

        logger.info(f"Hotkey fired: {desc}")

        if not self._plugin_manager:
            return

        async def _exec():
            plugin = self._plugin_manager.get_plugin(plugin_name)
            if not plugin:
                result = f"❌ Plugin '{plugin_name}' not available."
            else:
                try:
                    result = await plugin.execute(action, params)
                except Exception as e:
                    result = f"❌ Error: {e}"
            if self._chat_callback:
                self._chat_callback(f"[Hotkey: {desc}]\n\n{result}")

        try:
            import asyncio
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(_exec(), loop)
        except Exception as e:
            logger.error(f"Hotkey execution error: {e}")

    # ── Management ────────────────────────────────────────────────────────────

    async def _list_hotkeys(self, params: dict) -> str:
        lines = ["⌨️ Global Hotkeys:\n"]
        for hotkey, binding in self._bindings.items():
            status = "✓" if hotkey in self._registered else "✗"
            lines.append(f"  {status} {hotkey:<15}  →  {binding['description']}")
        lines.append(f"\n💡 These work system-wide, even when Nexus is minimized.")
        return "\n".join(lines)

    async def _register_hotkey(self, params: dict) -> str:
        hotkey = params.get("hotkey", "").lower().strip()
        plugin_name = params.get("plugin", "")
        action = params.get("action", "")
        description = params.get("description", f"{plugin_name}.{action}")

        if not hotkey or not plugin_name or not action:
            return "❌ Need hotkey, plugin, and action."

        binding = {"plugin": plugin_name, "action": action, "params": {}, "description": description}
        self._bindings[hotkey] = binding
        self._safe_register(hotkey, binding)
        return f"✅ Hotkey '{hotkey}' → {description} registered, sir."

    async def _unregister_hotkey(self, params: dict) -> str:
        hotkey = params.get("hotkey", "").lower().strip()
        if hotkey not in self._bindings:
            return f"❌ Hotkey '{hotkey}' not found."
        try:
            import keyboard
            keyboard.remove_hotkey(hotkey)
        except Exception:
            pass
        del self._bindings[hotkey]
        if hotkey in self._registered:
            self._registered.remove(hotkey)
        return f"✅ Hotkey '{hotkey}' unregistered."
