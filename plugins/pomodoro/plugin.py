from core.plugin_manager import BasePlugin
import logging, json, threading
from pathlib import Path
from datetime import datetime, date

logger = logging.getLogger("nexus.plugins.pomodoro")

LOG_FILE = Path.home() / "NexusScripts" / "pomodoro_log.json"


class PomodoroPlugin(BasePlugin):
    name = "pomodoro"
    description = "Pomodoro focus timer with work/break cycles and session logging"
    icon = "🍅"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._timer: threading.Timer | None = None
        self._state = {
            "active": False,
            "mode": None,
            "task": "",
            "started_at": None,
            "duration_minutes": 25,
            "pomodoros_today": 0,
        }
        self._work_duration = 25
        self._break_duration = 5
        self._long_break_duration = 15
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ helpers

    def _load_log(self) -> list:
        if LOG_FILE.exists():
            try:
                return json.loads(LOG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_log(self, data: list) -> None:
        LOG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _cancel_timer(self) -> None:
        if self._timer and self._timer.is_alive():
            self._timer.cancel()
        self._timer = None

    def _on_timer_complete(self) -> None:
        mode = self._state.get("mode")
        task = self._state.get("task", "")
        if mode == "work":
            self._state["pomodoros_today"] += 1
            self._record_completion(task)
            logger.info("Pomodoro complete for task: %s", task)
            self._notify("Pomodoro complete! Time for a break.")
        else:
            logger.info("Break complete. Ready to work!")
            self._notify("Break over! Ready for the next pomodoro.")
        self._state["active"] = False
        self._state["mode"] = None

    def _notify(self, message: str) -> None:
        try:
            import plyer
            plyer.notification.notify(title="Nexus Pomodoro", message=message, timeout=10)
        except Exception:
            logger.info("NOTIFICATION: %s", message)

    def _record_completion(self, task: str) -> None:
        log = self._load_log()
        today_str = date.today().isoformat()
        entry = next((e for e in log if e.get("date") == today_str and e.get("task") == task), None)
        if entry:
            entry["completed_pomodoros"] += 1
            entry["total_minutes"] += self._state.get("duration_minutes", self._work_duration)
        else:
            log.append({
                "date": today_str,
                "task": task,
                "completed_pomodoros": 1,
                "total_minutes": self._state.get("duration_minutes", self._work_duration),
            })
        self._save_log(log)

    def _time_remaining(self) -> int | None:
        if not self._state["active"] or not self._state["started_at"]:
            return None
        elapsed = (datetime.now().timestamp() - self._state["started_at"])
        remaining = self._state["duration_minutes"] * 60 - elapsed
        return max(0, int(remaining))

    # ------------------------------------------------------------------ actions

    def start(self, params=None) -> dict:
        params = params or {}
        task = params.get("task", "Focus session")
        duration = int(params.get("duration_minutes", self._work_duration))
        if self._state["active"]:
            return {"success": False, "message": "A timer is already active. Stop it first."}
        self._cancel_timer()
        self._state.update({
            "active": True,
            "mode": "work",
            "task": task,
            "started_at": datetime.now().timestamp(),
            "duration_minutes": duration,
        })
        self._timer = threading.Timer(duration * 60, self._on_timer_complete)
        self._timer.daemon = True
        self._timer.start()
        logger.info("Pomodoro started: task=%s duration=%dmin", task, duration)
        return {"success": True, "message": f"Pomodoro started for '{task}' ({duration} min)."}

    def stop(self, params=None) -> dict:
        if not self._state["active"]:
            return {"success": False, "message": "No active timer."}
        self._cancel_timer()
        self._state["active"] = False
        self._state["mode"] = None
        logger.info("Pomodoro stopped.")
        return {"success": True, "message": "Timer stopped."}

    def get_status(self, params=None) -> dict:
        remaining = self._time_remaining()
        today_str = date.today().isoformat()
        log = self._load_log()
        pomodoros_today = sum(e["completed_pomodoros"] for e in log if e.get("date") == today_str)
        return {
            "active": self._state["active"],
            "mode": self._state.get("mode"),
            "task": self._state.get("task"),
            "time_remaining_seconds": remaining,
            "time_remaining_display": f"{remaining // 60}m {remaining % 60}s" if remaining is not None else None,
            "pomodoros_today": pomodoros_today,
        }

    def take_break(self, params=None) -> dict:
        params = params or {}
        long = params.get("long", False)
        duration = self._long_break_duration if long else self._break_duration
        if self._state["active"]:
            return {"success": False, "message": "Stop the current timer before taking a break."}
        self._state.update({
            "active": True,
            "mode": "long_break" if long else "break",
            "task": "",
            "started_at": datetime.now().timestamp(),
            "duration_minutes": duration,
        })
        self._timer = threading.Timer(duration * 60, self._on_timer_complete)
        self._timer.daemon = True
        self._timer.start()
        return {"success": True, "message": f"{'Long break' if long else 'Break'} started ({duration} min)."}

    def get_stats(self, params=None) -> dict:
        params = params or {}
        period = params.get("period", "today")
        log = self._load_log()
        today_str = date.today().isoformat()
        if period == "today":
            entries = [e for e in log if e.get("date") == today_str]
        else:
            from datetime import timedelta
            week_ago = (date.today() - timedelta(days=7)).isoformat()
            entries = [e for e in log if e.get("date", "") >= week_ago]
        total_pomodoros = sum(e.get("completed_pomodoros", 0) for e in entries)
        total_minutes = sum(e.get("total_minutes", 0) for e in entries)
        return {
            "period": period,
            "total_pomodoros": total_pomodoros,
            "total_focus_minutes": total_minutes,
            "tasks": [{"task": e["task"], "pomodoros": e["completed_pomodoros"]} for e in entries],
        }

    def set_work_duration(self, params=None) -> dict:
        params = params or {}
        minutes = int(params.get("minutes", 25))
        self._work_duration = minutes
        return {"success": True, "message": f"Work duration set to {minutes} minutes."}

    def set_break_duration(self, params=None) -> dict:
        params = params or {}
        minutes = int(params.get("minutes", 5))
        self._break_duration = minutes
        return {"success": True, "message": f"Break duration set to {minutes} minutes."}

    async def execute(self, action: str, params: dict) -> str:
        if params is None:
            params = {}
        actions = {
            "start": self.start,
            "stop": self.stop,
            "get_status": self.get_status,
            "take_break": self.take_break,
            "get_stats": self.get_stats,
            "set_work_duration": self.set_work_duration,
            "set_break_duration": self.set_break_duration,
        }
        if action not in actions:
            return f"Unknown action '{action}'. Available: {list(actions.keys())}"
        try:
            result = actions[action](params)
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.exception("Error in action '%s'", action)
            return f"Error: {e}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "start",             "description": "Start a pomodoro work timer"},
            {"action": "stop",              "description": "Stop the current timer"},
            {"action": "get_status",        "description": "Get time remaining and current task"},
            {"action": "take_break",        "description": "Start a 5 or 15 minute break"},
            {"action": "get_stats",         "description": "Pomodoros completed today or this week"},
            {"action": "set_work_duration", "description": "Change work session duration in minutes"},
            {"action": "set_break_duration","description": "Change break duration in minutes"},
        ]
