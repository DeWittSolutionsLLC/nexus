"""
Print Queue Plugin — Manage 3D print jobs. Pairs with CAD Engine.

Tracks jobs, estimates filament/time, opens STL in slicer,
and gives you a status overview of your print farm.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.print_queue")

QUEUE_FILE = Path.home() / "NexusScripts" / "print_queue.json"

# Common slicer executables — checked in order
SLICERS = [
    r"C:\Program Files\Bambu Studio\bambu-studio.exe",
    r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe",
    r"C:\Program Files\Ultimaker Cura\UltiMaker-Cura.exe",
    r"C:\Program Files\Creality\Creality Print\Creality Print.exe",
    r"C:\Program Files\Chitubox\CHITUBOX.exe",
]

# Rough estimate: PLA at 30mm/s, 0.2mm layer
MM3_PER_GRAM = 1.24 * 1000   # PLA density ~1.24 g/cm³


class PrintQueuePlugin(BasePlugin):
    name = "print_queue"
    description = "3D print job queue — track jobs, estimate materials, open slicer"
    icon = "🖨️"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._jobs: dict[str, dict] = {}
        self._slicer_path = config.get("slicer_path", "")
        self._filament_cost = float(config.get("filament_cost_per_kg", 20.0))
        self._load_queue()

    async def connect(self) -> bool:
        slicer = self._find_slicer()
        if slicer:
            self._status_message = f"Ready — slicer: {Path(slicer).stem}"
        else:
            self._status_message = "Ready (no slicer found — set slicer_path in config)"
        self._connected = True
        return True

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "add_job":        self._add_job,
            "list_jobs":      self._list_jobs,
            "update_status":  self._update_status,
            "complete_job":   self._complete_job,
            "remove_job":     self._remove_job,
            "open_slicer":    self._open_slicer,
            "get_stats":      self._get_stats,
            "estimate":       self._estimate,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "add_job",       "description": "Add a 3D print job to the queue", "params": ["name", "file", "material", "notes"]},
            {"action": "list_jobs",     "description": "List all print jobs and their status", "params": []},
            {"action": "update_status", "description": "Update a print job status", "params": ["name", "status", "progress"]},
            {"action": "complete_job",  "description": "Mark a print job as complete", "params": ["name", "grams_used", "print_time_hours"]},
            {"action": "remove_job",    "description": "Remove a job from the queue", "params": ["name"]},
            {"action": "open_slicer",   "description": "Open an STL file in the installed slicer", "params": ["file"]},
            {"action": "get_stats",     "description": "Get print queue statistics and material usage", "params": []},
            {"action": "estimate",      "description": "Estimate print time and filament for a job", "params": ["name", "volume_cm3", "infill_pct"]},
        ]

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _add_job(self, params: dict) -> str:
        name = params.get("name", f"job_{datetime.now().strftime('%H%M%S')}")
        file_path = params.get("file", "")
        material = params.get("material", "PLA")
        notes = params.get("notes", "")

        self._jobs[name] = {
            "name":     name,
            "file":     file_path,
            "material": material,
            "notes":    notes,
            "status":   "queued",
            "progress": 0,
            "added":    datetime.now().strftime("%Y-%m-%d %H:%M"),
            "started":  None,
            "completed":None,
            "grams":    0,
            "hours":    0,
        }
        self._save_queue()

        file_note = f"\n  📄 File: {file_path}" if file_path else ""
        return (
            f"✅ Print job '{name}' added to queue, sir.\n"
            f"  Material: {material}{file_note}\n\n"
            f"Queue position: {list(self._jobs.keys()).index(name) + 1}"
        )

    async def _list_jobs(self, params: dict) -> str:
        if not self._jobs:
            return (
                "🖨️ Print queue is empty, sir.\n\n"
                "Add a job: 'add print job bracket.stl material PLA'\n"
                "Or generate a CAD part and it can go straight to queue."
            )
        status_icons = {"queued": "⏳", "printing": "🔄", "paused": "⏸️", "complete": "✅", "failed": "❌"}
        lines = ["🖨️ Print Queue:\n"]
        for name, job in self._jobs.items():
            icon = status_icons.get(job["status"], "•")
            prog = f" [{job['progress']}%]" if job["status"] == "printing" else ""
            lines.append(f"  {icon} {name}{prog}  [{job['material']}]")
            if job["file"]:
                lines.append(f"      📄 {Path(job['file']).name}")
            if job["notes"]:
                lines.append(f"      {job['notes']}")
            lines.append(f"      Added: {job['added']}")
            if job["completed"]:
                lines.append(f"      Completed: {job['completed']}  ({job['grams']}g, {job['hours']}h)")
            lines.append("")
        return "\n".join(lines)

    async def _update_status(self, params: dict) -> str:
        name = params.get("name", "")
        status = params.get("status", "")
        progress = params.get("progress", None)

        if name not in self._jobs:
            return f"❌ Job '{name}' not found."
        if status:
            self._jobs[name]["status"] = status
            if status == "printing" and not self._jobs[name]["started"]:
                self._jobs[name]["started"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        if progress is not None:
            self._jobs[name]["progress"] = int(progress)
        self._save_queue()
        return f"✅ Job '{name}' → {status or 'updated'} ({progress}%)" if progress else f"✅ Job '{name}' → {status}"

    async def _complete_job(self, params: dict) -> str:
        name = params.get("name", "")
        grams = float(params.get("grams_used", 0))
        hours = float(params.get("print_time_hours", 0))
        if name not in self._jobs:
            return f"❌ Job '{name}' not found."
        self._jobs[name].update({
            "status": "complete",
            "progress": 100,
            "grams": grams,
            "hours": hours,
            "completed": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        self._save_queue()
        cost = (grams / 1000) * self._filament_cost
        return f"✅ Job '{name}' complete, sir!\n  {grams}g filament used, {hours}h print time\n  Material cost: ${cost:.2f}"

    async def _remove_job(self, params: dict) -> str:
        name = params.get("name", "")
        if name not in self._jobs:
            return f"❌ Job '{name}' not found."
        del self._jobs[name]
        self._save_queue()
        return f"🗑️ Job '{name}' removed."

    async def _open_slicer(self, params: dict) -> str:
        file_path = params.get("file", "")
        if not file_path:
            # Try the first queued job with a file
            for job in self._jobs.values():
                if job.get("file") and job["status"] == "queued":
                    file_path = job["file"]
                    break
        if not file_path:
            return "❌ No file specified or found in queue."

        slicer = self._find_slicer()
        if not slicer:
            try:
                os.startfile(file_path)
                return f"✅ Opening {Path(file_path).name} in default program."
            except Exception as e:
                return f"❌ Could not open file: {e}\n\nSet slicer_path in config or install a slicer."

        import subprocess
        try:
            subprocess.Popen([slicer, file_path])
            return f"✅ Opening {Path(file_path).name} in {Path(slicer).stem}, sir."
        except Exception as e:
            return f"❌ Could not open slicer: {e}"

    async def _get_stats(self, params: dict) -> str:
        if not self._jobs:
            return "🖨️ No print history yet."
        completed = [j for j in self._jobs.values() if j["status"] == "complete"]
        queued = [j for j in self._jobs.values() if j["status"] == "queued"]
        printing = [j for j in self._jobs.values() if j["status"] == "printing"]
        total_g = sum(j["grams"] for j in completed)
        total_h = sum(j["hours"] for j in completed)
        total_cost = (total_g / 1000) * self._filament_cost
        lines = [
            "🖨️ Print Queue Stats:\n",
            f"  Queued:    {len(queued)} jobs",
            f"  Printing:  {len(printing)} jobs",
            f"  Completed: {len(completed)} jobs",
            f"\n  Total filament used: {total_g:.0f}g ({total_g/1000:.2f}kg)",
            f"  Total print time:    {total_h:.1f}h",
            f"  Material cost:       ${total_cost:.2f}",
        ]
        return "\n".join(lines)

    async def _estimate(self, params: dict) -> str:
        name = params.get("name", "")
        volume_cm3 = float(params.get("volume_cm3", 10))
        infill = float(params.get("infill_pct", 20)) / 100

        # PLA: ~1.24 g/cm³, typical shell + infill approximation
        shell_fraction = 0.3
        effective_volume = volume_cm3 * (shell_fraction + (1 - shell_fraction) * infill)
        grams = effective_volume * 1.24
        # Rough time: ~30mm/s at 0.2mm layer, ~5cm³/h throughput
        hours = effective_volume / 5.0
        cost = (grams / 1000) * self._filament_cost

        return (
            f"📊 Estimate for '{name or 'part'}' ({volume_cm3}cm³, {infill*100:.0f}% infill):\n\n"
            f"  Filament:   ~{grams:.0f}g\n"
            f"  Print time: ~{hours:.1f}h\n"
            f"  Cost:       ~${cost:.2f} ({self._filament_cost:.0f}/kg PLA)\n\n"
            f"💡 Actual values depend on your printer settings and slicer."
        )

    def _find_slicer(self) -> str | None:
        if self._slicer_path and Path(self._slicer_path).exists():
            return self._slicer_path
        for path in SLICERS:
            if Path(path).exists():
                return path
        return None

    def _load_queue(self):
        QUEUE_FILE.parent.mkdir(exist_ok=True)
        if QUEUE_FILE.exists():
            try:
                self._jobs = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._jobs = {}

    def _save_queue(self):
        try:
            QUEUE_FILE.write_text(json.dumps(self._jobs, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save print queue: {e}")
