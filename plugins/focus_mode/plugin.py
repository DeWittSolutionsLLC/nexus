from core.plugin_manager import BasePlugin
import logging
import json
import threading
import time
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("nexus.plugins.focus_mode")

HOSTS_PATH = Path("C:/Windows/System32/drivers/etc/hosts")
HOSTS_MARKER = "# nexus-focus-block"
SESSIONS_PATH = Path.home() / "NexusScripts" / "focus_sessions.json"


class FocusModePlugin(BasePlugin):
    name = "focus_mode"
    description = "Enables distraction-free focus sessions with a countdown timer and optional site blocking."
    icon = "🎯"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._timer: threading.Timer | None = None
        self._session_start: float | None = None
        self._session_duration: int = 0
        self._current_task: str = ""
        self._active = False
        self._sessions: list[dict] = []

    async def connect(self) -> bool:
        try:
            SESSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
            if SESSIONS_PATH.exists():
                with open(SESSIONS_PATH, "r", encoding="utf-8") as f:
                    self._sessions = json.load(f)
            self._connected = True
            self._status_message = "Ready"
            return True
        except Exception as e:
            logger.error(f"connect failed: {e}")
            self._connected = False
            self._status_message = f"Error: {e}"
            return False

    def _save_sessions(self):
        try:
            with open(SESSIONS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._sessions, f, indent=2)
        except Exception as e:
            logger.error(f"save_sessions failed: {e}")

    def _on_focus_end(self):
        logger.info("Focus session ended.")
        elapsed = time.time() - (self._session_start or time.time())
        self._sessions.append({
            "task": self._current_task,
            "start": datetime.fromtimestamp(self._session_start).isoformat() if self._session_start else "",
            "duration_minutes": self._session_duration,
            "completed": True,
        })
        self._save_sessions()
        self._active = False
        self._timer = None
        self._status_message = f"Session complete: {self._current_task}"

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "start_focus":
                return self._start_focus(int(params.get("duration_minutes", 25)), str(params.get("task", "Focus")))
            elif action == "stop_focus":
                return self._stop_focus()
            elif action == "get_status":
                return self._get_status()
            elif action == "list_sessions":
                return self._list_sessions(int(params.get("limit", 10)))
            elif action == "block_site":
                return self._block_site(str(params.get("domain", "")))
            elif action == "unblock_site":
                return self._unblock_site(str(params.get("domain", "")))
            elif action == "list_blocked":
                return self._list_blocked()
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"execute({action}) error: {e}")
            return f"Error executing {action}: {e}"

    def _start_focus(self, duration_minutes: int, task: str) -> str:
        if self._active:
            return f"Focus session already active: '{self._current_task}'. Stop it first."
        self._session_start = time.time()
        self._session_duration = duration_minutes
        self._current_task = task
        self._active = True
        self._timer = threading.Timer(duration_minutes * 60, self._on_focus_end)
        self._timer.daemon = True
        self._timer.start()
        self._status_message = f"Focusing: {task}"
        return f"Focus session started. Task: '{task}' | Duration: {duration_minutes} min. Stay focused!"

    def _stop_focus(self) -> str:
        if not self._active:
            return "No active focus session."
        if self._timer:
            self._timer.cancel()
            self._timer = None
        elapsed = round((time.time() - (self._session_start or time.time())) / 60, 1)
        self._sessions.append({
            "task": self._current_task,
            "start": datetime.fromtimestamp(self._session_start).isoformat() if self._session_start else "",
            "duration_minutes": self._session_duration,
            "completed": False,
            "elapsed_minutes": elapsed,
        })
        self._save_sessions()
        self._active = False
        self._status_message = "Ready"
        return f"Focus session stopped after {elapsed} min. Task was: '{self._current_task}'."

    def _get_status(self) -> str:
        if not self._active:
            return "No active focus session."
        elapsed = (time.time() - (self._session_start or time.time())) / 60
        remaining = max(0, self._session_duration - elapsed)
        return (f"Focus session active.\nTask: {self._current_task}\n"
                f"Elapsed: {elapsed:.1f} min | Remaining: {remaining:.1f} min")

    def _list_sessions(self, limit: int) -> str:
        if not self._sessions:
            return "No focus sessions recorded."
        recent = self._sessions[-limit:]
        lines = [f"Last {len(recent)} focus sessions:"]
        for s in reversed(recent):
            status = "completed" if s.get("completed") else f"stopped at {s.get('elapsed_minutes', '?')} min"
            lines.append(f"  [{s.get('start', '')[:16]}] {s.get('task')} — {s.get('duration_minutes')} min ({status})")
        return "\n".join(lines)

    def _block_site(self, domain: str) -> str:
        if not domain:
            return "No domain specified."
        try:
            with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            entry = f"127.0.0.1 {domain} {HOSTS_MARKER}"
            if domain in content:
                return f"{domain} is already blocked."
            with open(HOSTS_PATH, "a", encoding="utf-8") as f:
                f.write(f"\n{entry}\n")
            return f"Blocked: {domain}"
        except PermissionError:
            return "Permission denied. Run Nexus as administrator to block sites."
        except Exception as e:
            return f"Failed to block {domain}: {e}"

    def _unblock_site(self, domain: str) -> str:
        if not domain:
            return "No domain specified."
        try:
            with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = [l for l in lines if domain not in l or HOSTS_MARKER not in l]
            if len(new_lines) == len(lines):
                return f"{domain} was not blocked."
            with open(HOSTS_PATH, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            return f"Unblocked: {domain}"
        except PermissionError:
            return "Permission denied. Run Nexus as administrator to unblock sites."
        except Exception as e:
            return f"Failed to unblock {domain}: {e}"

    def _list_blocked(self) -> str:
        try:
            with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            blocked = [l.strip() for l in lines if HOSTS_MARKER in l]
            if not blocked:
                return "No sites are currently blocked by Nexus."
            return "Blocked sites:\n" + "\n".join(f"  {l}" for l in blocked)
        except Exception as e:
            return f"Failed to read hosts file: {e}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "start_focus", "description": "Start a focus session. Params: duration_minutes (int), task (str)."},
            {"action": "stop_focus", "description": "Stop the current focus session early."},
            {"action": "get_status", "description": "Get current focus session status and time remaining."},
            {"action": "list_sessions", "description": "List past focus sessions. Param: limit (int)."},
            {"action": "block_site", "description": "Block a distracting site via hosts file. Param: domain (str)."},
            {"action": "unblock_site", "description": "Unblock a previously blocked site. Param: domain (str)."},
            {"action": "list_blocked", "description": "List all sites currently blocked by Nexus."},
        ]
