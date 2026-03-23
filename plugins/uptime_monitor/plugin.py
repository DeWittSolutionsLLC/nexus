"""
Uptime Monitor Plugin — Monitor client websites 24/7.
Tracks response time, availability, and incidents. All local.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.uptime_monitor")

SITES_FILE = "memory/uptime_sites.json"


class UptimeMonitorPlugin(BasePlugin):
    name = "uptime_monitor"
    description = "Monitor client websites — uptime, response time, outage alerts"
    icon = "🛡️"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.sites: list[dict] = []
        self._available = False
        self._load()

    def _load(self):
        path = Path(SITES_FILE)
        if path.exists():
            try:
                self.sites = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Could not load uptime sites: {e}")

    def _save(self):
        path = Path(SITES_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.sites, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    async def connect(self) -> bool:
        try:
            import requests  # noqa: F401
            self._available = True
            self._connected = True
            self._status_message = f"Monitoring {len(self.sites)} sites"
            return True
        except ImportError:
            self._status_message = "requests not installed"
            self._connected = False
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self._available:
            return "⚠️ requests not installed. Run: pip install requests"

        actions = {
            "add_site":    self._add_site,
            "check_all":   self._check_all,
            "check_site":  self._check_site,
            "list_sites":  self._list_sites,
            "remove_site": self._remove_site,
            "get_history": self._get_history,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown uptime action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "add_site",    "description": "Add a website to uptime monitoring",          "params": ["url", "name"]},
            {"action": "check_all",   "description": "Check all monitored sites right now",          "params": []},
            {"action": "check_site",  "description": "Check a specific site",                        "params": ["url"]},
            {"action": "list_sites",  "description": "List all monitored sites with latest status",  "params": []},
            {"action": "remove_site", "description": "Remove a site from monitoring",                "params": ["name"]},
            {"action": "get_history", "description": "Get uptime history for a specific site",       "params": ["name"]},
        ]

    async def _add_site(self, params: dict) -> str:
        url = params.get("url", "").strip()
        name = params.get("name", "").strip()

        if not url:
            return "⚠️ Please provide a URL to monitor, sir."
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if not name:
            from urllib.parse import urlparse
            name = urlparse(url).netloc

        if any(s["url"] == url for s in self.sites):
            return f"⚠️ '{url}' is already being monitored, sir."

        site = {
            "id":           len(self.sites) + 1,
            "name":         name,
            "url":          url,
            "added":        datetime.now().isoformat(),
            "last_check":   None,
            "last_status":  "unknown",
            "last_response_ms": None,
            "total_checks": 0,
            "up_checks":    0,
            "history":      [],
            "incidents":    [],
        }
        self.sites.append(site)
        self._save()
        return f"🛡️ Now monitoring: {name} ({url})\nSay 'check all sites' to run an immediate check, sir."

    async def _check_all(self, params: dict) -> str:
        if not self.sites:
            return "📋 No sites being monitored yet, sir. Say 'monitor site [url]' to add one."

        results = []
        for site in self.sites:
            status, ms = self._ping(site["url"])
            self._update_site(site, status, ms)
            icon = "🟢" if status == "up" else "🔴"
            ms_str = f" ({ms}ms)" if ms else ""
            results.append(f"  {icon} {site['name']}{ms_str}")

        self._save()

        down = [s for s in self.sites if s["last_status"] == "down"]
        header = f"🛡️ UPTIME CHECK — {len(self.sites)} sites\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
        body = "\n".join(results)

        if down:
            alert = f"\n\n⚠️ {len(down)} site(s) DOWN: {', '.join(s['name'] for s in down)}"
            return f"{header}\n{body}{alert}"

        return f"{header}\n{body}\n\n✅ All sites operational."

    async def _check_site(self, params: dict) -> str:
        url = params.get("url", "").strip()
        if not url:
            return "⚠️ Please specify a URL to check."
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Check if it's a monitored site
        site = next((s for s in self.sites if s["url"] == url or s["name"].lower() == url.lower()), None)

        status, ms = self._ping(url)
        icon = "🟢" if status == "up" else "🔴"
        ms_str = f"  Response: {ms}ms" if ms else ""

        if site:
            self._update_site(site, status, ms)
            self._save()
            uptime_pct = (site["up_checks"] / site["total_checks"] * 100) if site["total_checks"] > 0 else 0
            return (
                f"{icon} {site['name']}\n"
                f"  URL:     {url}\n"
                f"  Status:  {status.upper()}\n"
                f"{ms_str}\n"
                f"  Uptime:  {uptime_pct:.1f}%  ({site['up_checks']}/{site['total_checks']} checks)"
            )

        return f"{icon} {url}  —  {status.upper()}" + (f"  ({ms}ms)" if ms else "")

    async def _list_sites(self, params: dict) -> str:
        if not self.sites:
            return "📋 No sites being monitored yet, sir."

        lines = [f"🛡️ MONITORED SITES ({len(self.sites)})\n{'─'*55}"]
        for s in self.sites:
            icon = "🟢" if s["last_status"] == "up" else "🔴" if s["last_status"] == "down" else "⚫"
            uptime = (s["up_checks"] / s["total_checks"] * 100) if s["total_checks"] > 0 else 0
            ms_str = f"  {s['last_response_ms']}ms" if s.get("last_response_ms") else ""
            last = s["last_check"][:16].replace("T", " ") if s.get("last_check") else "Never"
            lines.append(f"\n  {icon} {s['name']:<25}{ms_str}")
            lines.append(f"     {s['url']}")
            lines.append(f"     Uptime: {uptime:.1f}%  |  Last: {last}")
        return "\n".join(lines)

    async def _remove_site(self, params: dict) -> str:
        name = params.get("name", "").lower()
        site = next((s for s in self.sites if name in s["name"].lower() or name in s["url"].lower()), None)
        if not site:
            return f"⚠️ Site '{name}' not found in monitoring list, sir."
        self.sites.remove(site)
        self._save()
        return f"🗑️ Removed '{site['name']}' from uptime monitoring."

    async def _get_history(self, params: dict) -> str:
        name = params.get("name", "").lower()
        site = next((s for s in self.sites if name in s["name"].lower()), None)
        if not site:
            return f"⚠️ Site '{name}' not found."

        uptime = (site["up_checks"] / site["total_checks"] * 100) if site["total_checks"] > 0 else 0
        history = site.get("history", [])[-20:]

        lines = [
            f"📊 HISTORY — {site['name']}",
            f"  URL:      {site['url']}",
            f"  Uptime:   {uptime:.1f}%",
            f"  Checks:   {site['total_checks']}",
            f"\n  Recent checks:",
        ]
        for entry in reversed(history[-10:]):
            icon = "🟢" if entry["status"] == "up" else "🔴"
            ts = entry["timestamp"][:16].replace("T", " ")
            ms = f"  {entry['ms']}ms" if entry.get("ms") else ""
            lines.append(f"    {icon} {ts}{ms}")

        if site.get("incidents"):
            lines.append(f"\n  Incidents ({len(site['incidents'])}):")
            for inc in site["incidents"][-5:]:
                lines.append(f"    ⚠️ {inc['start'][:16]} — {inc.get('duration', 'ongoing')}")

        return "\n".join(lines)

    def _ping(self, url: str) -> tuple[str, int | None]:
        """Return (status, response_ms)."""
        import requests
        try:
            start = time.perf_counter()
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0 Nexus-Uptime/2.0"}, allow_redirects=True)
            ms = int((time.perf_counter() - start) * 1000)
            return ("up" if r.status_code < 500 else "down"), ms
        except Exception:
            return "down", None

    def _update_site(self, site: dict, status: str, ms: int | None):
        now = datetime.now().isoformat()
        site["last_check"] = now
        site["last_status"] = status
        site["last_response_ms"] = ms
        site["total_checks"] = site.get("total_checks", 0) + 1
        if status == "up":
            site["up_checks"] = site.get("up_checks", 0) + 1

        site.setdefault("history", []).append({
            "timestamp": now,
            "status":    status,
            "ms":        ms,
        })
        # Keep last 100 history entries
        if len(site["history"]) > 100:
            site["history"] = site["history"][-100:]

        # Track incidents
        history = site["history"]
        if status == "down" and len(history) >= 2 and history[-2].get("status") == "up":
            site.setdefault("incidents", []).append({"start": now, "duration": None})
        elif status == "up" and site.get("incidents") and site["incidents"][-1].get("duration") is None:
            site["incidents"][-1]["duration"] = "Resolved"

    def get_all_sites(self) -> list[dict]:
        return self.sites
