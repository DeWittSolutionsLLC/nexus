from core.plugin_manager import BasePlugin
import logging, json, threading
from pathlib import Path
from datetime import datetime, date, timedelta

logger = logging.getLogger("nexus.plugins.habit_tracker")

HABITS_FILE = Path.home() / "NexusScripts" / "habits.json"


class HabitTrackerPlugin(BasePlugin):
    name = "habit_tracker"
    icon = "✅"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        HABITS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ helpers

    def _load(self) -> dict:
        if HABITS_FILE.exists():
            try:
                return json.loads(HABITS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"habits": [], "completions": []}

    def _save(self, data: dict) -> None:
        HABITS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _find_habit(self, data: dict, name: str) -> dict | None:
        name_lower = name.lower()
        return next((h for h in data["habits"] if h["name"].lower() == name_lower), None)

    def _get_streak(self, data: dict, habit_id: str, frequency: str = "daily") -> int:
        completions = sorted(
            {c["date"] for c in data["completions"] if c["habit_id"] == habit_id},
            reverse=True,
        )
        if not completions:
            return 0
        streak = 0
        check = date.today()
        for c_date_str in completions:
            c_date = date.fromisoformat(c_date_str)
            if c_date == check:
                streak += 1
                check -= timedelta(days=1)
            elif c_date < check:
                break
        return streak

    # ------------------------------------------------------------------ actions

    def add_habit(self, params=None) -> dict:
        params = params or {}
        name = params.get("name", "").strip()
        if not name:
            return {"error": "Habit name is required."}
        data = self._load()
        if self._find_habit(data, name):
            return {"error": f"Habit '{name}' already exists."}
        habit = {
            "id": f"h_{int(datetime.now().timestamp())}",
            "name": name,
            "description": params.get("description", ""),
            "frequency": params.get("frequency", "daily"),
            "created": date.today().isoformat(),
        }
        data["habits"].append(habit)
        self._save(data)
        logger.info("Added habit: %s", name)
        return {"success": True, "message": f"Habit '{name}' added.", "habit": habit}

    def complete_habit(self, params=None) -> dict:
        params = params or {}
        name = params.get("name", "").strip()
        target_date = params.get("date", date.today().isoformat())
        if not name:
            return {"error": "Habit name is required."}
        data = self._load()
        habit = self._find_habit(data, name)
        if not habit:
            return {"error": f"Habit '{name}' not found."}
        already = any(
            c["habit_id"] == habit["id"] and c["date"] == target_date
            for c in data["completions"]
        )
        if already:
            return {"success": False, "message": f"'{name}' already marked complete for {target_date}."}
        data["completions"].append({"habit_id": habit["id"], "date": target_date})
        self._save(data)
        streak = self._get_streak(data, habit["id"])
        return {"success": True, "message": f"'{name}' marked complete! Streak: {streak} days."}

    def uncomplete_habit(self, params=None) -> dict:
        params = params or {}
        name = params.get("name", "").strip()
        target_date = date.today().isoformat()
        if not name:
            return {"error": "Habit name is required."}
        data = self._load()
        habit = self._find_habit(data, name)
        if not habit:
            return {"error": f"Habit '{name}' not found."}
        before = len(data["completions"])
        data["completions"] = [
            c for c in data["completions"]
            if not (c["habit_id"] == habit["id"] and c["date"] == target_date)
        ]
        if len(data["completions"]) == before:
            return {"success": False, "message": f"No completion found for '{name}' today."}
        self._save(data)
        return {"success": True, "message": f"Completion removed for '{name}' on {target_date}."}

    def list_habits(self, params=None) -> dict:
        data = self._load()
        today_str = date.today().isoformat()
        completed_today = {c["habit_id"] for c in data["completions"] if c["date"] == today_str}
        result = []
        for h in data["habits"]:
            result.append({
                "name": h["name"],
                "description": h["description"],
                "frequency": h["frequency"],
                "done_today": h["id"] in completed_today,
                "streak": self._get_streak(data, h["id"]),
            })
        return {"habits": result, "total": len(result)}

    def get_streak(self, params=None) -> dict:
        params = params or {}
        name = params.get("name", "").strip()
        if not name:
            return {"error": "Habit name is required."}
        data = self._load()
        habit = self._find_habit(data, name)
        if not habit:
            return {"error": f"Habit '{name}' not found."}
        streak = self._get_streak(data, habit["id"], habit.get("frequency", "daily"))
        return {"name": name, "streak": streak}

    def get_stats(self, params=None) -> dict:
        params = params or {}
        name = params.get("name", "").strip()
        if not name:
            return {"error": "Habit name is required."}
        data = self._load()
        habit = self._find_habit(data, name)
        if not habit:
            return {"error": f"Habit '{name}' not found."}
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        all_completions = [c for c in data["completions"] if c["habit_id"] == habit["id"]]
        recent = [c for c in all_completions if c["date"] >= cutoff]
        completion_rate = round(len(recent) / 30 * 100, 1)
        # longest streak
        dates = sorted({c["date"] for c in all_completions})
        longest = cur = 0
        prev = None
        for d_str in dates:
            d = date.fromisoformat(d_str)
            if prev and (d - prev).days == 1:
                cur += 1
            else:
                cur = 1
            longest = max(longest, cur)
            prev = d
        return {
            "name": name,
            "total_completions": len(all_completions),
            "last_30_days": len(recent),
            "completion_rate_30d": f"{completion_rate}%",
            "longest_streak": longest,
            "current_streak": self._get_streak(data, habit["id"]),
        }

    def delete_habit(self, params=None) -> dict:
        params = params or {}
        name = params.get("name", "").strip()
        if not name:
            return {"error": "Habit name is required."}
        data = self._load()
        habit = self._find_habit(data, name)
        if not habit:
            return {"error": f"Habit '{name}' not found."}
        data["habits"] = [h for h in data["habits"] if h["id"] != habit["id"]]
        data["completions"] = [c for c in data["completions"] if c["habit_id"] != habit["id"]]
        self._save(data)
        return {"success": True, "message": f"Habit '{name}' deleted."}

    def get_today(self, params=None) -> dict:
        data = self._load()
        today_str = date.today().isoformat()
        completed_ids = {c["habit_id"] for c in data["completions"] if c["date"] == today_str}
        done = [h["name"] for h in data["habits"] if h["id"] in completed_ids]
        pending = [h["name"] for h in data["habits"] if h["id"] not in completed_ids]
        return {
            "date": today_str,
            "done": done,
            "pending": pending,
            "completion": f"{len(done)}/{len(data['habits'])}",
        }

    def execute(self, action: str, params=None) -> dict:
        actions = {
            "add_habit": self.add_habit,
            "complete_habit": self.complete_habit,
            "uncomplete_habit": self.uncomplete_habit,
            "list_habits": self.list_habits,
            "get_streak": self.get_streak,
            "get_stats": self.get_stats,
            "delete_habit": self.delete_habit,
            "get_today": self.get_today,
        }
        if action not in actions:
            return {"error": f"Unknown action '{action}'. Available: {list(actions.keys())}"}
        try:
            return actions[action](params)
        except Exception as e:
            logger.exception("Error in action '%s'", action)
            return {"error": str(e)}
