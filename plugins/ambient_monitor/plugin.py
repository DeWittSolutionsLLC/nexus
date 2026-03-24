from core.plugin_manager import BasePlugin
import logging
import json
import threading
import time
import ctypes
import ctypes.wintypes
from pathlib import Path
from datetime import datetime, date

logger = logging.getLogger("nexus.plugins.ambient_monitor")


class AmbientMonitorPlugin(BasePlugin):
    name = "ambient_monitor"
    description = "Passively monitors system activity: active window, idle time, and screen time per day."
    icon = "👁"

    LOG_PATH = Path.home() / "NexusScripts" / "ambient_log.json"
    POLL_INTERVAL = 30

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._log: list[dict] = []
        self._current_window = ""
        self._window_start = time.time()

    async def connect(self) -> bool:
        try:
            self.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            if self.LOG_PATH.exists():
                with open(self.LOG_PATH, "r", encoding="utf-8") as f:
                    self._log = json.load(f)
            self._start_thread()
            self._connected = True
            self._status_message = "Monitoring"
            return True
        except Exception as e:
            logger.error(f"connect failed: {e}")
            self._connected = False
            self._status_message = f"Error: {e}"
            return False

    def _get_active_window_title(self) -> str:
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""

    def _get_idle_seconds(self) -> float:
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return millis / 1000.0
        except Exception:
            return 0.0

    def _save_log(self):
        try:
            with open(self.LOG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._log[-5000:], f, indent=2)
        except Exception as e:
            logger.error(f"save_log failed: {e}")

    def _poll(self):
        while not self._stop_event.is_set():
            title = self._get_active_window_title()
            now = time.time()
            if title != self._current_window:
                if self._current_window:
                    entry = {
                        "timestamp": datetime.fromtimestamp(self._window_start).isoformat(),
                        "window": self._current_window,
                        "duration_s": round(now - self._window_start, 1),
                    }
                    self._log.append(entry)
                    self._save_log()
                self._current_window = title
                self._window_start = now
            self._stop_event.wait(self.POLL_INTERVAL)

    def _start_thread(self):
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._poll, daemon=True, name="ambient_monitor")
        self._monitor_thread.start()

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "get_activity":
                return self._get_activity(int(params.get("minutes", 60)))
            elif action == "get_screen_time":
                return self._get_screen_time()
            elif action == "get_idle_time":
                idle = self._get_idle_seconds()
                return f"Current idle time: {idle:.1f} seconds ({idle/60:.1f} minutes)."
            elif action == "get_top_apps":
                return self._get_top_apps(int(params.get("top_n", 5)))
            elif action == "stop_monitoring":
                self._stop_event.set()
                self._status_message = "Stopped"
                return "Ambient monitoring stopped."
            elif action == "start_monitoring":
                if not self._monitor_thread or not self._monitor_thread.is_alive():
                    self._start_thread()
                    self._status_message = "Monitoring"
                    return "Ambient monitoring started."
                return "Already monitoring."
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"execute({action}) error: {e}")
            return f"Error executing {action}: {e}"

    def _today_entries(self):
        today = date.today().isoformat()
        return [e for e in self._log if e.get("timestamp", "").startswith(today)]

    def _get_activity(self, minutes: int) -> str:
        cutoff = time.time() - minutes * 60
        recent = [e for e in self._log if datetime.fromisoformat(e["timestamp"]).timestamp() >= cutoff]
        if not recent:
            return f"No activity logged in the last {minutes} minutes."
        lines = [f"Activity in last {minutes} min ({len(recent)} windows):"]
        for e in recent[-10:]:
            lines.append(f"  [{e['timestamp'][11:19]}] {e['window'][:60]} — {e['duration_s']}s")
        return "\n".join(lines)

    def _get_screen_time(self) -> str:
        total = sum(e.get("duration_s", 0) for e in self._today_entries())
        hours = total / 3600
        return f"Screen time today: {hours:.2f} hours ({total:.0f} seconds)."

    def _get_top_apps(self, top_n: int) -> str:
        from collections import defaultdict
        app_time: dict[str, float] = defaultdict(float)
        for e in self._today_entries():
            app_time[e.get("window", "Unknown")[:50]] += e.get("duration_s", 0)
        sorted_apps = sorted(app_time.items(), key=lambda x: x[1], reverse=True)[:top_n]
        if not sorted_apps:
            return "No app usage data for today."
        lines = ["Top apps today:"]
        for app, secs in sorted_apps:
            lines.append(f"  {app}: {secs/60:.1f} min")
        return "\n".join(lines)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "get_activity", "description": "Summary of active windows in the last N minutes. Param: minutes (int)."},
            {"action": "get_screen_time", "description": "Total screen time logged for today in hours."},
            {"action": "get_idle_time", "description": "Current idle time in seconds since last input."},
            {"action": "get_top_apps", "description": "Most-used apps today by total time. Param: top_n (int)."},
            {"action": "stop_monitoring", "description": "Stop the background monitoring thread."},
            {"action": "start_monitoring", "description": "Start (or restart) the background monitoring thread."},
        ]
