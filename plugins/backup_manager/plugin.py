"""
Backup Manager Plugin — Manages file/folder backups with zip archives and scheduling info.
Uses shutil, zipfile, and a JSON config stored in ~/NexusScripts/backup_config.json.
"""

import os
import json
import shutil
import zipfile
import logging
from datetime import datetime
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.backup_manager")

CONFIG_PATH = Path.home() / "NexusScripts" / "backup_config.json"


class BackupManagerPlugin(BasePlugin):
    name = "backup_manager"
    description = "Manages file/folder backups: zip archives, restore, and job scheduling"
    icon = "💾"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._jobs: dict = {}

    async def connect(self) -> bool:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._load_config()
        self._connected = True
        self._status_message = f"Ready — {len(self._jobs)} backup job(s) loaded"
        return True

    def _load_config(self):
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._jobs = json.load(f)
            except Exception as e:
                logger.warning("Could not load backup config: %s", e)
                self._jobs = {}
        else:
            self._jobs = {}

    def _save_config(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._jobs, f, indent=2)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "add_backup", "description": "Register a new backup job"},
            {"action": "run_backup", "description": "Run a specific backup job by name"},
            {"action": "run_all", "description": "Run all registered backup jobs"},
            {"action": "list_backups", "description": "List all jobs with last-run info"},
            {"action": "remove_backup", "description": "Remove a backup job by name"},
            {"action": "get_backup_history", "description": "List zip files for a backup job"},
            {"action": "restore_backup", "description": "Restore a specific backup zip to a path"},
        ]

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "add_backup": self._add_backup,
            "run_backup": self._run_backup,
            "run_all": self._run_all,
            "list_backups": self._list_backups,
            "remove_backup": self._remove_backup,
            "get_backup_history": self._get_backup_history,
            "restore_backup": self._restore_backup,
        }
        if action not in actions:
            return f"Unknown action: {action}. Available: {', '.join(actions)}"
        try:
            return await actions[action](params)
        except Exception as e:
            logger.error("Action %s failed: %s", action, e)
            return f"Error in {action}: {e}"

    async def _add_backup(self, params: dict) -> str:
        name = params.get("name", "").strip()
        source = params.get("source", "").strip()
        destination = params.get("destination", "").strip()
        if not name or not source or not destination:
            return "Required params: name, source, destination"
        if name in self._jobs:
            return f"Backup job '{name}' already exists. Remove it first to re-add."
        self._jobs[name] = {
            "name": name,
            "source": source,
            "destination": destination,
            "schedule": params.get("schedule", "manual"),
            "last_backup": None,
            "status": "never run",
        }
        self._save_config()
        return f"Backup job '{name}' registered: {source} -> {destination}"

    def _do_zip(self, name: str) -> tuple[str, int]:
        """Zip source to destination, return (zip_path, size_bytes)."""
        job = self._jobs[name]
        source = Path(job["source"])
        dest_dir = Path(job["destination"])
        dest_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        zip_name = f"backup_{timestamp}.zip"
        zip_path = dest_dir / zip_name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if source.is_file():
                zf.write(source, source.name)
            elif source.is_dir():
                for file in source.rglob("*"):
                    if file.is_file():
                        zf.write(file, file.relative_to(source.parent))
            else:
                raise FileNotFoundError(f"Source not found: {source}")
        return str(zip_path), zip_path.stat().st_size

    async def _run_backup(self, params: dict) -> str:
        name = params.get("name", "").strip()
        if not name:
            return "Required param: name"
        if name not in self._jobs:
            return f"No backup job named '{name}'"
        try:
            zip_path, size = self._do_zip(name)
            self._jobs[name]["last_backup"] = datetime.now().isoformat()
            self._jobs[name]["status"] = "success"
            self._save_config()
            return f"Backup '{name}' complete: {zip_path} ({size / (1024*1024):.2f} MB)"
        except Exception as e:
            self._jobs[name]["status"] = f"failed: {e}"
            self._save_config()
            return f"Backup '{name}' failed: {e}"

    async def _run_all(self, params: dict) -> str:
        if not self._jobs:
            return "No backup jobs registered"
        results = []
        for name in list(self._jobs):
            result = await self._run_backup({"name": name})
            results.append(result)
        return "\n".join(results)

    async def _list_backups(self, params: dict) -> str:
        if not self._jobs:
            return "No backup jobs registered. Use add_backup to create one."
        lines = [f"{'Name':<20} {'Source':<30} {'Last Backup':<22} {'Status'}"]
        lines.append("-" * 90)
        for job in self._jobs.values():
            last = job.get("last_backup") or "Never"
            if last != "Never":
                last = last[:19].replace("T", " ")
            lines.append(f"{job['name'][:20]:<20} {job['source'][:30]:<30} {last:<22} {job.get('status','?')}")
        return "\n".join(lines)

    async def _remove_backup(self, params: dict) -> str:
        name = params.get("name", "").strip()
        if not name:
            return "Required param: name"
        if name not in self._jobs:
            return f"No backup job named '{name}'"
        del self._jobs[name]
        self._save_config()
        return f"Backup job '{name}' removed"

    async def _get_backup_history(self, params: dict) -> str:
        name = params.get("name", "").strip()
        if not name:
            return "Required param: name"
        if name not in self._jobs:
            return f"No backup job named '{name}'"
        dest_dir = Path(self._jobs[name]["destination"])
        if not dest_dir.is_dir():
            return f"Destination directory not found: {dest_dir}"
        zips = sorted(dest_dir.glob("backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not zips:
            return f"No backup archives found in {dest_dir}"
        lines = [f"Backup history for '{name}' ({dest_dir}):"]
        for z in zips:
            size_mb = z.stat().st_size / (1024 * 1024)
            mtime = datetime.fromtimestamp(z.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"  {z.name}  —  {size_mb:.2f} MB  —  {mtime}")
        return "\n".join(lines)

    async def _restore_backup(self, params: dict) -> str:
        name = params.get("name", "").strip()
        backup_file = params.get("backup_file", "").strip()
        restore_to = params.get("restore_to", "").strip()
        if not name or not backup_file or not restore_to:
            return "Required params: name, backup_file, restore_to"
        if name not in self._jobs:
            return f"No backup job named '{name}'"
        zip_path = Path(self._jobs[name]["destination"]) / backup_file
        if not zip_path.exists():
            return f"Backup file not found: {zip_path}"
        restore_path = Path(restore_to)
        restore_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(restore_path)
        return f"Restored '{backup_file}' to {restore_path}"
