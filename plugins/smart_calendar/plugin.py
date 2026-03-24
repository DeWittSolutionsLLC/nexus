from core.plugin_manager import BasePlugin
import logging, json, threading, re, uuid
from pathlib import Path
from datetime import datetime, date, timedelta

logger = logging.getLogger("nexus.plugins.smart_calendar")

CAL_FILE = Path.home() / "NexusScripts" / "calendar.json"
REMINDER_INTERVAL = 60  # seconds between reminder checks


class SmartCalendarPlugin(BasePlugin):
    name = "smart_calendar"
    description = "Local calendar with AI-powered scheduling and reminders"
    icon = "📅"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        CAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._reminder_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._pending_reminders: set[str] = set()
        self._start_reminder_thread()

    # ------------------------------------------------------------------ helpers

    def _load(self) -> list:
        if CAL_FILE.exists():
            try:
                return json.loads(CAL_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self, events: list) -> None:
        CAL_FILE.write_text(json.dumps(events, indent=2), encoding="utf-8")

    def _event_datetime(self, event: dict) -> datetime | None:
        try:
            return datetime.strptime(f"{event['date']} {event['time']}", "%Y-%m-%d %H:%M")
        except Exception:
            return None

    def _start_reminder_thread(self) -> None:
        self._stop_event.clear()
        self._reminder_thread = threading.Thread(target=self._reminder_loop, daemon=True)
        self._reminder_thread.start()

    def _reminder_loop(self) -> None:
        while not self._stop_event.wait(REMINDER_INTERVAL):
            try:
                self._check_reminders()
            except Exception as e:
                logger.error("Reminder check error: %s", e)

    def _check_reminders(self) -> None:
        events = self._load()
        now = datetime.now()
        for event in events:
            ev_dt = self._event_datetime(event)
            if not ev_dt:
                continue
            remind_at = ev_dt - timedelta(minutes=event.get("reminder_minutes", 15))
            eid = event["id"]
            if remind_at <= now <= ev_dt and eid not in self._pending_reminders:
                self._pending_reminders.add(eid)
                logger.info("REMINDER: '%s' at %s", event["title"], event["time"])
                self._notify(event)

    def _notify(self, event: dict) -> None:
        msg = f"{event['title']} at {event['time']}"
        try:
            import plyer
            plyer.notification.notify(title="Nexus Calendar", message=msg, timeout=10)
        except Exception:
            logger.info("NOTIFICATION: %s", msg)

    # ------------------------------------------------------------------ actions

    def add_event(self, params=None) -> dict:
        params = params or {}
        title = params.get("title", "").strip()
        ev_date = params.get("date", "").strip()
        ev_time = params.get("time", "").strip()
        if not title or not ev_date or not ev_time:
            return {"error": "title, date (YYYY-MM-DD), and time (HH:MM) are required."}
        event = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "date": ev_date,
            "time": ev_time,
            "duration_minutes": int(params.get("duration_minutes", 60)),
            "description": params.get("description", ""),
            "reminder_minutes": int(params.get("reminder_minutes", 15)),
            "recurring": params.get("recurring", "none"),
        }
        events = self._load()
        events.append(event)
        events.sort(key=lambda e: (e["date"], e["time"]))
        self._save(events)
        logger.info("Event added: %s on %s at %s", title, ev_date, ev_time)
        return {"success": True, "message": f"Event '{title}' added.", "event": event}

    def list_events(self, params=None) -> dict:
        params = params or {}
        days_ahead = int(params.get("days_ahead", 7))
        start = params.get("date", date.today().isoformat())
        end = (date.fromisoformat(start) + timedelta(days=days_ahead)).isoformat()
        events = [e for e in self._load() if start <= e["date"] <= end]
        return {"events": events, "count": len(events), "range": f"{start} to {end}"}

    def get_today(self, params=None) -> dict:
        today_str = date.today().isoformat()
        events = [e for e in self._load() if e["date"] == today_str]
        events.sort(key=lambda e: e["time"])
        return {"date": today_str, "events": events, "count": len(events)}

    def delete_event(self, params=None) -> dict:
        params = params or {}
        eid = params.get("id", "").strip()
        title = params.get("title", "").strip()
        events = self._load()
        before = len(events)
        if eid:
            events = [e for e in events if e["id"] != eid]
        elif title:
            events = [e for e in events if e["title"].lower() != title.lower()]
        else:
            return {"error": "Provide id or title to delete."}
        if len(events) == before:
            return {"error": "Event not found."}
        self._save(events)
        return {"success": True, "message": "Event deleted."}

    def find_free_time(self, params=None) -> dict:
        params = params or {}
        target_date = params.get("date", date.today().isoformat())
        duration = int(params.get("duration_minutes", 60))
        events = sorted(
            [e for e in self._load() if e["date"] == target_date],
            key=lambda e: e["time"],
        )
        day_start = datetime.strptime(f"{target_date} 08:00", "%Y-%m-%d %H:%M")
        day_end = datetime.strptime(f"{target_date} 20:00", "%Y-%m-%d %H:%M")
        busy = []
        for e in events:
            start = datetime.strptime(f"{e['date']} {e['time']}", "%Y-%m-%d %H:%M")
            end = start + timedelta(minutes=e.get("duration_minutes", 60))
            busy.append((start, end))
        free_slots = []
        cursor = day_start
        for b_start, b_end in sorted(busy):
            if (b_start - cursor).total_seconds() >= duration * 60:
                free_slots.append({"start": cursor.strftime("%H:%M"), "end": b_start.strftime("%H:%M")})
            cursor = max(cursor, b_end)
        if (day_end - cursor).total_seconds() >= duration * 60:
            free_slots.append({"start": cursor.strftime("%H:%M"), "end": day_end.strftime("%H:%M")})
        return {"date": target_date, "duration_needed": duration, "free_slots": free_slots}

    def get_upcoming_reminders(self, params=None) -> dict:
        now = datetime.now()
        cutoff = now + timedelta(minutes=30)
        upcoming = []
        for e in self._load():
            ev_dt = self._event_datetime(e)
            if ev_dt and now <= ev_dt <= cutoff:
                mins = int((ev_dt - now).total_seconds() / 60)
                upcoming.append({**e, "minutes_until": mins})
        return {"upcoming": upcoming, "count": len(upcoming)}

    def update_event(self, params=None) -> dict:
        params = params or {}
        eid = params.get("id", "").strip()
        if not eid:
            return {"error": "Event id is required."}
        events = self._load()
        for event in events:
            if event["id"] == eid:
                for key in ["title", "date", "time", "duration_minutes", "description", "reminder_minutes", "recurring"]:
                    if key in params:
                        event[key] = params[key]
                events.sort(key=lambda e: (e["date"], e["time"]))
                self._save(events)
                return {"success": True, "message": "Event updated.", "event": event}
        return {"error": f"Event '{eid}' not found."}

    def parse_and_add(self, params=None) -> dict:
        params = params or {}
        text = params.get("natural_language", "").strip()
        if not text:
            return {"error": "natural_language text is required."}
        today = date.today()
        ev_date = today.isoformat()
        ev_time = "09:00"
        duration = 60
        # date parsing
        if "tomorrow" in text.lower():
            ev_date = (today + timedelta(days=1)).isoformat()
        elif "today" in text.lower():
            ev_date = today.isoformat()
        else:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
            if m:
                ev_date = m.group(1)
        # time parsing
        m = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text, re.IGNORECASE)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            meridiem = (m.group(3) or "").lower()
            if meridiem == "pm" and hour != 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
            ev_time = f"{hour:02d}:{minute:02d}"
        # duration parsing
        m = re.search(r"for\s+(\d+)\s*(hour|hr|minute|min)", text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            unit = m.group(2).lower()
            duration = val * 60 if "hour" in unit or "hr" in unit else val
        # title: strip time/date phrases
        title = re.sub(r"\b(tomorrow|today|at\s+\d[\d:]*\s*(?:am|pm)?|for\s+\d+\s*(?:hour|hr|minute|min)s?)\b", "", text, flags=re.IGNORECASE).strip(" ,")
        title = title or "Event"
        return self.add_event({"title": title, "date": ev_date, "time": ev_time, "duration_minutes": duration})

    async def execute(self, action: str, params: dict) -> str:
        if params is None:
            params = {}
        actions = {
            "add_event": self.add_event,
            "list_events": self.list_events,
            "get_today": self.get_today,
            "delete_event": self.delete_event,
            "find_free_time": self.find_free_time,
            "get_upcoming_reminders": self.get_upcoming_reminders,
            "update_event": self.update_event,
            "parse_and_add": self.parse_and_add,
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
            {"action": "add_event",              "description": "Add a new calendar event"},
            {"action": "list_events",            "description": "List upcoming events"},
            {"action": "get_today",              "description": "Show today's full schedule"},
            {"action": "delete_event",           "description": "Delete an event by title or id"},
            {"action": "find_free_time",         "description": "Find a free slot of given duration"},
            {"action": "get_upcoming_reminders", "description": "Events starting in the next 30 minutes"},
            {"action": "update_event",           "description": "Update an existing event"},
            {"action": "parse_and_add",          "description": "Add event from natural language description"},
        ]

    def shutdown(self) -> None:
        self._stop_event.set()
