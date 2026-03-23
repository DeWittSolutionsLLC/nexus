"""
Project Manager Plugin — Web development project tracking.
Manages clients, projects, timelines, and logged hours.
All stored locally as JSON.
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.project_manager")

PROJECTS_FILE = "memory/projects.json"

STATUS_ICONS = {
    "planning":    "🔵",
    "in_progress": "🟡",
    "review":      "🟠",
    "complete":    "🟢",
    "paused":      "⚪",
    "cancelled":   "🔴",
}


class ProjectManagerPlugin(BasePlugin):
    name = "project_manager"
    description = "Track web dev projects — clients, deadlines, hours, and revenue"
    icon = "🚀"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.projects: list[dict] = []
        self._load()

    def _load(self):
        path = Path(PROJECTS_FILE)
        if path.exists():
            try:
                self.projects = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Could not load projects: {e}")
                self.projects = []

    def _save(self):
        path = Path(PROJECTS_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.projects, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    async def connect(self) -> bool:
        self._connected = True
        active = sum(1 for p in self.projects if p.get("status") == "in_progress")
        self._status_message = f"{len(self.projects)} projects, {active} active"
        return True

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "add_project":     self._add_project,
            "list_projects":   self._list_projects,
            "update_status":   self._update_status,
            "log_hours":       self._log_hours,
            "get_project":     self._get_project,
            "get_summary":     self._get_summary,
            "get_overdue":     self._get_overdue,
            "delete_project":  self._delete_project,
            "update_project":  self._update_project,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown project action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "add_project",    "description": "Add a new web development project",                   "params": ["name", "client", "deadline", "rate", "estimated_hours", "description"]},
            {"action": "list_projects",  "description": "List all projects with status and progress",          "params": ["status_filter"]},
            {"action": "update_status",  "description": "Update a project status (planning/in_progress/review/complete/paused)", "params": ["name", "status"]},
            {"action": "log_hours",      "description": "Log worked hours against a project",                  "params": ["name", "hours", "note"]},
            {"action": "get_project",    "description": "Get full details for a specific project",             "params": ["name"]},
            {"action": "get_summary",    "description": "Get revenue summary across all projects",             "params": []},
            {"action": "get_overdue",    "description": "List projects past their deadline",                   "params": []},
            {"action": "update_project", "description": "Update any field on a project",                      "params": ["name", "field", "value"]},
        ]

    async def _add_project(self, params: dict) -> str:
        name = params.get("name", "").strip()
        if not name:
            return "⚠️ Project name is required, sir."
        if any(p["name"].lower() == name.lower() for p in self.projects):
            return f"⚠️ A project named '{name}' already exists."

        project = {
            "id":               len(self.projects) + 1,
            "name":             name,
            "client":           params.get("client", ""),
            "description":      params.get("description", ""),
            "status":           "planning",
            "start_date":       date.today().isoformat(),
            "deadline":         params.get("deadline", ""),
            "hourly_rate":      float(params.get("rate", 0) or 0),
            "estimated_hours":  float(params.get("estimated_hours", 0) or 0),
            "logged_hours":     0.0,
            "technologies":     [],
            "notes":            "",
            "invoiced":         False,
            "paid":             False,
            "created":          datetime.now().isoformat(),
            "time_log":         [],
        }
        self.projects.append(project)
        self._save()

        rate_str = f" @ £{project['hourly_rate']:.2f}/hr" if project["hourly_rate"] else ""
        est_str = f"  Est: {project['estimated_hours']}h" if project["estimated_hours"] else ""
        deadline_str = f"  Deadline: {project['deadline']}" if project["deadline"] else ""

        return (
            f"🚀 Project added, sir.\n\n"
            f"  Name:   {name}\n"
            f"  Client: {project['client'] or 'TBD'}{rate_str}\n"
            f"{est_str}{deadline_str}"
        )

    async def _list_projects(self, params: dict) -> str:
        if not self.projects:
            return "📋 No projects on record, sir. Say 'add project' to get started."

        status_filter = params.get("status_filter", "").lower()
        projects = [p for p in self.projects if not status_filter or p.get("status") == status_filter]

        if not projects:
            return f"No projects with status '{status_filter}'."

        lines = [f"🚀 PROJECTS ({len(projects)} shown)\n{'─'*60}"]

        for p in sorted(projects, key=lambda x: (x.get("status") != "in_progress", x.get("deadline", "9999"))):
            icon = STATUS_ICONS.get(p.get("status", "planning"), "⚪")
            name = p["name"]
            client = p.get("client", "")
            deadline = p.get("deadline", "")
            logged = p.get("logged_hours", 0)
            estimated = p.get("estimated_hours", 0)
            rate = p.get("hourly_rate", 0)
            earned = logged * rate if rate else 0

            client_str = f"  [{client}]" if client else ""
            deadline_str = f"  Due: {deadline}" if deadline else ""
            hours_str = f"  {logged:.1f}h"
            if estimated:
                pct = min(100, logged / estimated * 100)
                hours_str += f"/{estimated:.0f}h ({pct:.0f}%)"
            earned_str = f"  £{earned:.0f}" if earned else ""

            lines.append(f"\n{icon} {name}{client_str}{deadline_str}{hours_str}{earned_str}")

        return "\n".join(lines)

    async def _update_status(self, params: dict) -> str:
        name = params.get("name", "")
        new_status = params.get("status", "").lower()
        valid = list(STATUS_ICONS.keys())

        if new_status not in valid:
            return f"⚠️ Invalid status. Choose from: {', '.join(valid)}"

        project = self._find(name)
        if not project:
            return f"⚠️ Project '{name}' not found, sir."

        old = project["status"]
        project["status"] = new_status
        if new_status == "complete" and not project.get("completed_date"):
            project["completed_date"] = date.today().isoformat()
        self._save()

        icon = STATUS_ICONS.get(new_status, "⚪")
        return f"{icon} '{project['name']}' updated from {old} → {new_status}."

    async def _log_hours(self, params: dict) -> str:
        name = params.get("name", "")
        hours = float(params.get("hours", 0) or 0)
        note = params.get("note", "")

        if hours <= 0:
            return "⚠️ Please specify hours to log, sir."

        project = self._find(name)
        if not project:
            return f"⚠️ Project '{name}' not found, sir."

        project["logged_hours"] = round(project.get("logged_hours", 0) + hours, 2)
        project.setdefault("time_log", []).append({
            "hours": hours,
            "note": note,
            "date": date.today().isoformat(),
        })
        self._save()

        total = project["logged_hours"]
        rate = project.get("hourly_rate", 0)
        earned = total * rate if rate else 0
        earned_str = f"  Total earned: £{earned:.2f}" if earned else ""

        return (
            f"⏱️ Logged {hours}h on '{project['name']}'\n"
            f"  Total hours: {total:.1f}h{earned_str}"
        )

    async def _get_project(self, params: dict) -> str:
        name = params.get("name", "")
        project = self._find(name)
        if not project:
            return f"⚠️ Project '{name}' not found, sir."

        rate = project.get("hourly_rate", 0)
        logged = project.get("logged_hours", 0)
        estimated = project.get("estimated_hours", 0)
        earned = logged * rate if rate else 0

        lines = [
            f"🚀 {project['name']}",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"  Client:    {project.get('client', 'N/A')}",
            f"  Status:    {STATUS_ICONS.get(project['status'],'⚪')} {project['status']}",
            f"  Started:   {project.get('start_date', 'N/A')}",
            f"  Deadline:  {project.get('deadline', 'None set')}",
        ]
        if project.get("description"):
            lines.append(f"  Desc:      {project['description']}")
        if rate:
            lines.append(f"  Rate:      £{rate:.2f}/hr")
        lines.append(f"  Hours:     {logged:.1f}h logged")
        if estimated:
            pct = min(100, logged / estimated * 100)
            lines.append(f"             {estimated:.0f}h estimated  ({pct:.0f}% complete)")
        if earned:
            lines.append(f"  Earned:    £{earned:.2f}")
            lines.append(f"  Invoiced:  {'Yes' if project.get('invoiced') else 'No'}")
            lines.append(f"  Paid:      {'Yes' if project.get('paid') else 'No'}")
        if project.get("notes"):
            lines.append(f"  Notes:     {project['notes']}")

        return "\n".join(lines)

    async def _get_summary(self, params: dict) -> str:
        if not self.projects:
            return "No projects on record yet, sir."

        total_earned = 0
        total_hours = 0
        by_status: dict = {}
        unpaid = 0

        for p in self.projects:
            status = p.get("status", "planning")
            by_status[status] = by_status.get(status, 0) + 1
            logged = p.get("logged_hours", 0)
            rate = p.get("hourly_rate", 0)
            earned = logged * rate if rate else 0
            total_earned += earned
            total_hours += logged
            if earned and not p.get("paid"):
                unpaid += earned

        lines = [
            "💼 PROJECT SUMMARY\n━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"  Total projects: {len(self.projects)}",
        ]
        for status, count in sorted(by_status.items()):
            lines.append(f"  {STATUS_ICONS.get(status,'⚪')} {status}: {count}")

        lines.append(f"\n  Total hours logged: {total_hours:.1f}h")
        if total_earned:
            lines.append(f"  Total earned:       £{total_earned:.2f}")
            lines.append(f"  Outstanding:        £{unpaid:.2f}")

        return "\n".join(lines)

    async def _get_overdue(self, params: dict) -> str:
        today = date.today().isoformat()
        overdue = [
            p for p in self.projects
            if p.get("deadline") and p["deadline"] < today
            and p.get("status") not in ("complete", "cancelled")
        ]
        if not overdue:
            return "✅ No overdue projects, sir. All deadlines are on track."

        lines = [f"⚠️ OVERDUE PROJECTS ({len(overdue)})\n━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        for p in sorted(overdue, key=lambda x: x.get("deadline", "")):
            lines.append(f"\n  🔴 {p['name']}")
            lines.append(f"     Client:   {p.get('client', 'N/A')}")
            lines.append(f"     Deadline: {p['deadline']}")
            lines.append(f"     Status:   {p.get('status')}")
        return "\n".join(lines)

    async def _delete_project(self, params: dict) -> str:
        name = params.get("name", "")
        project = self._find(name)
        if not project:
            return f"⚠️ Project '{name}' not found, sir."
        self.projects.remove(project)
        self._save()
        return f"🗑️ Project '{project['name']}' removed."

    async def _update_project(self, params: dict) -> str:
        name = params.get("name", "")
        field = params.get("field", "")
        value = params.get("value", "")
        project = self._find(name)
        if not project:
            return f"⚠️ Project '{name}' not found, sir."
        if not field:
            return "⚠️ Please specify which field to update."
        project[field] = value
        self._save()
        return f"✅ '{project['name']}' — {field} updated to '{value}'."

    def _find(self, name: str) -> dict | None:
        """Find project by name (case-insensitive, partial match)."""
        name_lower = name.lower()
        # Exact match first
        for p in self.projects:
            if p["name"].lower() == name_lower:
                return p
        # Partial match
        for p in self.projects:
            if name_lower in p["name"].lower():
                return p
        return None

    def get_all_projects(self) -> list[dict]:
        return self.projects
