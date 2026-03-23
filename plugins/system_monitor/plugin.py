"""
System Monitor Plugin — Real-time CPU, RAM, disk, and process monitoring.
Uses psutil — no external APIs, fully local.
"""

import logging
from datetime import datetime
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.system_monitor")


class SystemMonitorPlugin(BasePlugin):
    name = "system_monitor"
    description = "Real-time system performance — CPU, RAM, disk, processes"
    icon = "⚡"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._psutil_available = False

    async def connect(self) -> bool:
        try:
            import psutil  # noqa: F401
            self._psutil_available = True
            self._connected = True
            self._status_message = "Monitoring"
            return True
        except ImportError:
            self._status_message = "psutil not installed"
            self._connected = False
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self._psutil_available:
            return "⚠️ psutil not installed. Run: pip install psutil"

        actions = {
            "get_stats":      self._get_stats,
            "get_cpu":        self._get_cpu,
            "get_memory":     self._get_memory,
            "get_disk":       self._get_disk,
            "get_network":    self._get_network,
            "get_processes":  self._get_processes,
            "get_full_report": self._get_full_report,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown system_monitor action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "get_stats",       "description": "Get CPU, RAM, and disk overview", "params": []},
            {"action": "get_cpu",         "description": "Detailed CPU usage per core", "params": []},
            {"action": "get_memory",      "description": "RAM and swap memory details", "params": []},
            {"action": "get_disk",        "description": "Disk usage for all drives", "params": []},
            {"action": "get_network",     "description": "Network interface statistics", "params": []},
            {"action": "get_processes",   "description": "Top processes by CPU or memory usage", "params": ["sort_by"]},
            {"action": "get_full_report", "description": "Full system health report", "params": []},
        ]

    async def _get_stats(self, params: dict) -> str:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        freq = psutil.cpu_freq()
        freq_str = f"  @ {freq.current:.0f} MHz" if freq else ""

        return (
            f"⚡ SYSTEM STATUS\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"CPU    {self._bar(cpu)} {cpu:.1f}%{freq_str}\n"
            f"RAM    {self._bar(mem.percent)} {mem.percent:.1f}%"
            f"  ({self._fmt_gb(mem.used)} / {self._fmt_gb(mem.total)})\n"
            f"DISK   {self._bar(disk.percent)} {disk.percent:.1f}%"
            f"  ({self._fmt_gb(disk.used)} / {self._fmt_gb(disk.total)})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"System uptime: {self._uptime()}"
        )

    async def _get_cpu(self, params: dict) -> str:
        import psutil
        per_core = psutil.cpu_percent(interval=0.5, percpu=True)
        freq = psutil.cpu_freq(percpu=False)
        logical = psutil.cpu_count(logical=True)
        physical = psutil.cpu_count(logical=False)

        lines = [f"⚡ CPU — {physical} cores / {logical} threads"]
        if freq:
            lines.append(f"   Frequency: {freq.current:.0f} MHz  (max {freq.max:.0f} MHz)")
        lines.append("")
        for i, pct in enumerate(per_core):
            lines.append(f"  Core {i:<2}  {self._bar(pct, 15)} {pct:5.1f}%")

        avg = sum(per_core) / len(per_core) if per_core else 0
        lines.append(f"\n  Overall average: {avg:.1f}%")
        return "\n".join(lines)

    async def _get_memory(self, params: dict) -> str:
        import psutil
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cached = getattr(mem, "cached", 0)

        return (
            f"🧠 MEMORY\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"RAM     {self._bar(mem.percent)}  {mem.percent:.1f}%\n"
            f"  Total:     {self._fmt_gb(mem.total)}\n"
            f"  Used:      {self._fmt_gb(mem.used)}\n"
            f"  Available: {self._fmt_gb(mem.available)}\n"
            f"  Cached:    {self._fmt_gb(cached)}\n\n"
            f"SWAP    {self._bar(swap.percent)}  {swap.percent:.1f}%\n"
            f"  Total: {self._fmt_gb(swap.total)}  Used: {self._fmt_gb(swap.used)}"
        )

    async def _get_disk(self, params: dict) -> str:
        import psutil
        lines = ["💾 DISK USAGE\n━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                lines.append(
                    f"\n{part.device}  ({part.fstype})\n"
                    f"  {self._bar(usage.percent)}  {usage.percent:.1f}%\n"
                    f"  {self._fmt_gb(usage.used)} used  /  {self._fmt_gb(usage.total)} total"
                    f"  ({self._fmt_gb(usage.free)} free)"
                )
            except (PermissionError, OSError):
                pass
        return "\n".join(lines)

    async def _get_network(self, params: dict) -> str:
        import psutil
        stats = psutil.net_io_counters(pernic=True)
        lines = ["🌐 NETWORK\n━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        for iface, c in list(stats.items())[:8]:
            if c.bytes_sent + c.bytes_recv == 0:
                continue
            lines.append(
                f"\n  {iface}\n"
                f"    ↑ Sent:     {self._fmt_mb(c.bytes_sent)}\n"
                f"    ↓ Received: {self._fmt_mb(c.bytes_recv)}"
            )
        return "\n".join(lines) or "No active network interfaces found."

    async def _get_processes(self, params: dict) -> str:
        import psutil
        sort_by = params.get("sort_by", "cpu")
        key = "memory_percent" if "mem" in sort_by.lower() else "cpu_percent"

        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        procs.sort(key=lambda x: x.get(key) or 0, reverse=True)

        header = f"{'PID':>6}  {'NAME':<25}  {'CPU%':>6}  {'MEM%':>6}"
        lines = [f"📊 TOP PROCESSES (by {sort_by.upper()})\n{header}", "─" * 52]
        for p in procs[:15]:
            cpu = p.get("cpu_percent") or 0
            mem = p.get("memory_percent") or 0
            lines.append(f"{p['pid']:>6}  {p['name']:<25}  {cpu:6.1f}  {mem:6.1f}")
        return "\n".join(lines)

    async def _get_full_report(self, params: dict) -> str:
        parts = [
            await self._get_stats({}),
            await self._get_memory({}),
            await self._get_disk({}),
            await self._get_processes({}),
        ]
        return "\n\n".join(parts)

    def get_quick_stats(self) -> dict:
        """Return quick stats dict for live UI display."""
        try:
            import psutil
            return {
                "cpu":  psutil.cpu_percent(interval=None),
                "ram":  psutil.virtual_memory().percent,
                "disk": psutil.disk_usage("/").percent,
            }
        except Exception:
            return {"cpu": 0, "ram": 0, "disk": 0}

    @staticmethod
    def _bar(pct: float, width: int = 20) -> str:
        filled = int(max(0, min(100, pct)) / 100 * width)
        return "█" * filled + "░" * (width - filled)

    @staticmethod
    def _fmt_gb(b: int) -> str:
        if b >= 1024 ** 3:
            return f"{b / 1024**3:.1f} GB"
        return f"{b / 1024**2:.0f} MB"

    @staticmethod
    def _fmt_mb(b: int) -> str:
        return f"{b / 1024**2:.1f} MB"

    @staticmethod
    def _uptime() -> str:
        try:
            import psutil
            boot = datetime.fromtimestamp(psutil.boot_time())
            delta = datetime.now() - boot
            h, rem = divmod(int(delta.total_seconds()), 3600)
            m = rem // 60
            return f"{h}h {m}m"
        except Exception:
            return "unknown"
