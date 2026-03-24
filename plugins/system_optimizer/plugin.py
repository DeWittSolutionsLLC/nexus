"""
System Optimizer Plugin — Cleans temp files, kills heavy processes, frees RAM, and analyzes disk usage.
Uses psutil, subprocess, os, shutil, ctypes for Windows-native optimizations.
"""

import os
import shutil
import logging
import subprocess
import ctypes
import time
from datetime import datetime, timedelta
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.system_optimizer")


class SystemOptimizerPlugin(BasePlugin):
    name = "system_optimizer"
    description = "Optimizes Windows: cleans temp files, kills heavy processes, frees RAM"
    icon = "⚡"

    TEMP_DIRS = [
        os.environ.get("TEMP", ""),
        "C:/Windows/Temp",
        str(Path.home() / "AppData" / "Local" / "Temp"),
    ]

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._psutil_available = False

    async def connect(self) -> bool:
        try:
            import psutil  # noqa: F401
            self._psutil_available = True
        except ImportError:
            logger.warning("psutil not installed — some actions will be limited")
        self._connected = True
        self._status_message = "Ready"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "clean_temp", "description": "Delete temp files older than 24 h, return freed MB"},
            {"action": "kill_heavy_processes", "description": "Kill processes above CPU threshold (default 80%)"},
            {"action": "get_startup_items", "description": "List Windows startup registry entries"},
            {"action": "free_ram", "description": "Trim process working sets to free RAM"},
            {"action": "get_top_processes", "description": "List top N processes by CPU/RAM (default 10)"},
            {"action": "disk_cleanup", "description": "Analyze folder sizes at a given path"},
            {"action": "defrag_check", "description": "Check if C: drive needs defragmentation"},
        ]

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "clean_temp": self._clean_temp,
            "kill_heavy_processes": self._kill_heavy_processes,
            "get_startup_items": self._get_startup_items,
            "free_ram": self._free_ram,
            "get_top_processes": self._get_top_processes,
            "disk_cleanup": self._disk_cleanup,
            "defrag_check": self._defrag_check,
        }
        if action not in actions:
            return f"Unknown action: {action}. Available: {', '.join(actions)}"
        try:
            return await actions[action](params)
        except Exception as e:
            logger.error("Action %s failed: %s", action, e)
            return f"Error in {action}: {e}"

    async def _clean_temp(self, params: dict) -> str:
        cutoff = datetime.now() - timedelta(hours=24)
        freed_bytes = 0
        errors = 0
        for temp_dir in self.TEMP_DIRS:
            if not temp_dir or not os.path.isdir(temp_dir):
                continue
            for entry in os.scandir(temp_dir):
                try:
                    mtime = datetime.fromtimestamp(entry.stat().st_mtime)
                    if mtime < cutoff:
                        size = entry.stat().st_size if entry.is_file() else 0
                        if entry.is_file():
                            os.remove(entry.path)
                            freed_bytes += size
                        elif entry.is_dir():
                            dir_size = sum(f.stat().st_size for f in Path(entry.path).rglob("*") if f.is_file())
                            shutil.rmtree(entry.path, ignore_errors=True)
                            freed_bytes += dir_size
                except Exception:
                    errors += 1
        freed_mb = freed_bytes / (1024 * 1024)
        return f"Temp cleanup complete. Freed: {freed_mb:.2f} MB. Errors skipped: {errors}"

    async def _kill_heavy_processes(self, params: dict) -> str:
        if not self._psutil_available:
            return "psutil not available — cannot inspect processes"
        import psutil
        threshold = float(params.get("cpu_threshold", 80))
        heavy = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
            try:
                cpu = proc.info["cpu_percent"] or 0
                if cpu > threshold:
                    heavy.append((proc.info["pid"], proc.info["name"], cpu))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if not heavy:
            return f"No processes found using more than {threshold}% CPU"
        killed = []
        for pid, name, cpu in heavy:
            try:
                p = psutil.Process(pid)
                p.kill()
                killed.append(f"{name} (PID {pid}, {cpu:.1f}%)")
            except Exception as e:
                killed.append(f"{name} (PID {pid}) — could not kill: {e}")
        return "Killed heavy processes:\n" + "\n".join(killed)

    async def _get_startup_items(self, params: dict) -> str:
        try:
            result = subprocess.run(
                ["reg", "query", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip() or "No startup items found"
            return f"Startup items (HKCU Run):\n{output}"
        except Exception as e:
            return f"Failed to query startup items: {e}"

    async def _free_ram(self, params: dict) -> str:
        if not self._psutil_available:
            return "psutil not available — cannot enumerate processes"
        import psutil
        freed_count = 0
        errors = 0
        for proc in psutil.process_iter(["pid"]):
            try:
                handle = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, proc.info["pid"])
                if handle:
                    ctypes.windll.kernel32.SetProcessWorkingSetSize(handle, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
                    ctypes.windll.kernel32.CloseHandle(handle)
                    freed_count += 1
            except Exception:
                errors += 1
        ram = psutil.virtual_memory()
        return (f"Working sets trimmed for {freed_count} processes ({errors} skipped). "
                f"Available RAM: {ram.available / (1024**2):.0f} MB / {ram.total / (1024**2):.0f} MB")

    async def _get_top_processes(self, params: dict) -> str:
        if not self._psutil_available:
            return "psutil not available"
        import psutil
        n = int(params.get("n", 10))
        procs = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                ram_mb = proc.info["memory_info"].rss / (1024 * 1024) if proc.info["memory_info"] else 0
                procs.append((proc.info["name"], proc.info["pid"], proc.info["cpu_percent"] or 0, ram_mb))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: x[2], reverse=True)
        lines = [f"{'Name':<30} {'PID':>7} {'CPU%':>6} {'RAM MB':>8}"]
        lines.append("-" * 55)
        for name, pid, cpu, ram in procs[:n]:
            lines.append(f"{name[:30]:<30} {pid:>7} {cpu:>6.1f} {ram:>8.1f}")
        return "\n".join(lines)

    async def _disk_cleanup(self, params: dict) -> str:
        path = params.get("path", str(Path.home()))
        target = Path(path)
        if not target.is_dir():
            return f"Path not found or not a directory: {path}"
        entries = []
        for item in target.iterdir():
            try:
                if item.is_dir():
                    size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                else:
                    size = item.stat().st_size
                entries.append((item.name, size, "DIR" if item.is_dir() else "FILE"))
            except Exception:
                pass
        entries.sort(key=lambda x: x[1], reverse=True)
        lines = [f"Disk usage for: {path}", f"{'Name':<40} {'Size MB':>10} {'Type':>5}"]
        lines.append("-" * 58)
        for name, size, kind in entries[:20]:
            lines.append(f"{name[:40]:<40} {size/(1024*1024):>10.2f} {kind:>5}")
        return "\n".join(lines)

    async def _defrag_check(self, params: dict) -> str:
        try:
            result = subprocess.run(
                ["defrag", "C:", "/A"],
                capture_output=True, text=True, timeout=60
            )
            output = (result.stdout + result.stderr).strip()
            return f"Defrag analysis for C:\n{output}" if output else "Defrag analysis complete (no output)"
        except FileNotFoundError:
            return "defrag.exe not found — may require admin or not available on this OS edition"
        except Exception as e:
            return f"Defrag check failed: {e}"
