"""
Time Tracker Plugin — Passive billable hour tracking.

Polls the active window title every 30s, maps it to projects,
and accumulates time. Zero effort — just work, ask later.
"""

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.time_tracker")

TIME_LOG_FILE = Path.home() / "NexusScripts" / "time_log.json"
POLL_INTERVAL = 30   # seconds


class TimeTrackerPlugin(BasePlugin):
    name = "time_tracker"
    description = "Passive time tracking — auto-detects billable hours per project"
    icon = "⏱️"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._tracking = False
        self._poll_thread: threading.Thread | None = None
        self._sessions: list[dict] = []        # [{project, window, start, end, minutes}]
        self._project_map: dict[str, str] = {} # keyword → project name
        self._active_project: str | None = None
        self._active_since: datetime | None = None
        self._plugin_manager = None
        self._load_log()

    def set_plugin_manager(self, pm):
        self._plugin_manager = pm
        self._sync_projects_from_pm()

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = "Ready (not tracking)"
        return True

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "start_tracking":   self._start_tracking,
            "stop_tracking":    self._stop_tracking,
            "log_time":         self._log_time,
            "get_summary":      self._get_summary,
            "get_today":        self._get_today,
            "get_week":         self._get_week,
            "add_mapping":      self._add_mapping,
            "list_mappings":    self._list_mappings,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "start_tracking",  "description": "Start passive time tracking", "params": []},
            {"action": "stop_tracking",   "description": "Stop time tracking", "params": []},
            {"action": "log_time",        "description": "Manually log time to a project", "params": ["project", "minutes", "description"]},
            {"action": "get_summary",     "description": "Get time summary for all projects", "params": ["days"]},
            {"action": "get_today",       "description": "Get today's tracked time", "params": []},
            {"action": "get_week",        "description": "Get this week's tracked time", "params": []},
            {"action": "add_mapping",     "description": "Map a window title keyword to a project", "params": ["keyword", "project"]},
            {"action": "list_mappings",   "description": "Show all keyword-to-project mappings", "params": []},
        ]

    # ── Tracking ──────────────────────────────────────────────────────────────

    async def _start_tracking(self, params: dict) -> str:
        if self._tracking:
            return "⏱️ Already tracking, sir."
        self._tracking = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        self._status_message = "Tracking active"
        return (
            f"✅ Time tracking started, sir.\n\n"
            f"I'll log time automatically based on your active window.\n"
            f"Current mappings: {len(self._project_map)} keywords\n\n"
            f"Add mappings: 'map keyword AcmeCo to project AcmeCo Website'"
        )

    async def _stop_tracking(self, params: dict) -> str:
        self._tracking = False
        self._flush_active_session()
        self._status_message = "Tracking stopped"
        return "⏱️ Time tracking stopped, sir."

    def _poll_loop(self):
        while self._tracking:
            try:
                window = self._get_active_window()
                project = self._match_project(window)
                self._update_session(project, window)
            except Exception as e:
                logger.debug(f"Poll error: {e}")
            time.sleep(POLL_INTERVAL)
        self._flush_active_session()

    def _get_active_window(self) -> str:
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value.strip()
        except Exception:
            return "Unknown"

    def _match_project(self, window_title: str) -> str:
        title_lower = window_title.lower()
        for keyword, project in self._project_map.items():
            if keyword.lower() in title_lower:
                return project
        return "Untracked"

    def _update_session(self, project: str, window: str):
        now = datetime.now()
        if project != self._active_project:
            self._flush_active_session()
            if project != "Untracked":
                self._active_project = project
                self._active_since = now
        # If same project, just continue

    def _flush_active_session(self):
        if self._active_project and self._active_since:
            minutes = max(1, int((datetime.now() - self._active_since).total_seconds() / 60))
            self._sessions.append({
                "project": self._active_project,
                "date": date.today().isoformat(),
                "minutes": minutes,
                "window": self._active_project,
                "logged_at": datetime.now().isoformat(),
            })
            self._save_log()
            logger.debug(f"Flushed {minutes}m for {self._active_project}")
        self._active_project = None
        self._active_since = None

    # ── Manual log ────────────────────────────────────────────────────────────

    async def _log_time(self, params: dict) -> str:
        project = params.get("project", "General")
        minutes = int(params.get("minutes", 60))
        description = params.get("description", "")
        self._sessions.append({
            "project": project,
            "date": date.today().isoformat(),
            "minutes": minutes,
            "description": description,
            "logged_at": datetime.now().isoformat(),
        })
        self._save_log()
        hours = minutes / 60
        return f"✅ Logged {minutes}min ({hours:.1f}h) to '{project}', sir."

    # ── Reports ───────────────────────────────────────────────────────────────

    async def _get_today(self, params: dict) -> str:
        today = date.today().isoformat()
        return self._build_report([s for s in self._sessions if s.get("date") == today], "Today")

    async def _get_week(self, params: dict) -> str:
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        return self._build_report([s for s in self._sessions if s.get("date", "") >= week_ago], "This week")

    async def _get_summary(self, params: dict) -> str:
        days = int(params.get("days", 30))
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        return self._build_report([s for s in self._sessions if s.get("date", "") >= cutoff], f"Last {days} days")

    def _build_report(self, sessions: list, label: str) -> str:
        if not sessions:
            return f"⏱️ No time logged for {label.lower()}, sir."

        by_project: dict[str, int] = defaultdict(int)
        for s in sessions:
            by_project[s["project"]] += s["minutes"]

        total = sum(by_project.values())
        lines = [f"⏱️ Time Report — {label}\n"]
        for project, mins in sorted(by_project.items(), key=lambda x: -x[1]):
            h, m = divmod(mins, 60)
            bar = "█" * min(20, int(mins / max(total, 1) * 20))
            lines.append(f"  {project:<25} {bar:<20} {h}h {m:02d}m")

        total_h, total_m = divmod(total, 60)
        lines.append(f"\n  {'TOTAL':<25} {'':20} {total_h}h {total_m:02d}m")

        if self._tracking and self._active_project:
            live_mins = int((datetime.now() - self._active_since).total_seconds() / 60) if self._active_since else 0
            lines.append(f"\n  🔴 Currently tracking: {self._active_project} (+{live_mins}m live)")

        return "\n".join(lines)

    # ── Mappings ──────────────────────────────────────────────────────────────

    async def _add_mapping(self, params: dict) -> str:
        keyword = params.get("keyword", "").strip()
        project = params.get("project", "").strip()
        if not keyword or not project:
            return "❌ Need both keyword and project name."
        self._project_map[keyword] = project
        self._save_log()
        return f"✅ Window titles containing '{keyword}' will be tracked as '{project}', sir."

    async def _list_mappings(self, params: dict) -> str:
        if not self._project_map:
            return (
                "⏱️ No keyword mappings yet, sir.\n\n"
                "Add one: 'map keyword AcmeCo to project AcmeCo Website'\n"
                "I'll detect that window title and log time automatically."
            )
        lines = ["⏱️ Window → Project Mappings:\n"]
        for kw, proj in self._project_map.items():
            lines.append(f"  '{kw}'  →  {proj}")
        return "\n".join(lines)

    def _sync_projects_from_pm(self):
        """Auto-import project names as mappings."""
        if not self._plugin_manager:
            return
        pm = self._plugin_manager.get_plugin("project_manager")
        if pm and hasattr(pm, "_projects"):
            for name in pm._projects:
                if name not in self._project_map.values():
                    self._project_map[name] = name

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_log(self):
        TIME_LOG_FILE.parent.mkdir(exist_ok=True)
        if TIME_LOG_FILE.exists():
            try:
                data = json.loads(TIME_LOG_FILE.read_text(encoding="utf-8"))
                self._sessions = data.get("sessions", [])
                self._project_map = data.get("mappings", {})
            except Exception:
                pass

    def _save_log(self):
        try:
            TIME_LOG_FILE.write_text(
                json.dumps({"sessions": self._sessions[-500:], "mappings": self._project_map}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save time log: {e}")
