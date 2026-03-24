"""
Browser Recorder Plugin — Record browser sequences once, replay on demand.

Records Playwright actions as a JSON script. Replay with one command.
Useful for repetitive client reporting, form fills, scraping tasks.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.browser_recorder")

RECORDINGS_DIR = Path.home() / "NexusScripts" / "recordings"


class BrowserRecorderPlugin(BasePlugin):
    name = "browser_recorder"
    description = "Record and replay browser automation sequences"
    icon = "🎬"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._recordings: dict[str, dict] = {}
        self._recording_name: str | None = None
        self._recorded_steps: list[dict] = []
        self._is_recording = False
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_recordings()

    async def connect(self) -> bool:
        try:
            from playwright.async_api import async_playwright  # noqa: F401
            self._connected = True
            self._status_message = f"{len(self._recordings)} recordings saved"
            return True
        except ImportError:
            self._status_message = "Playwright not installed"
            return False

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "start_recording": self._start_recording,
            "stop_recording":  self._stop_recording,
            "play_recording":  self._play_recording,
            "list_recordings": self._list_recordings,
            "show_recording":  self._show_recording,
            "delete_recording":self._delete_recording,
            "record_step":     self._record_step,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "start_recording", "description": "Start recording a browser sequence", "params": ["name"]},
            {"action": "stop_recording",  "description": "Stop recording and save the sequence", "params": []},
            {"action": "play_recording",  "description": "Replay a saved browser recording", "params": ["name", "slow"]},
            {"action": "list_recordings", "description": "List all saved browser recordings", "params": []},
            {"action": "show_recording",  "description": "Show the steps of a recording", "params": ["name"]},
            {"action": "delete_recording","description": "Delete a recording", "params": ["name"]},
            {"action": "record_step",     "description": "Add a manual step to the current recording", "params": ["action", "selector", "value", "url"]},
        ]

    # ── Recording mode ────────────────────────────────────────────────────────

    async def _start_recording(self, params: dict) -> str:
        name = params.get("name") or f"rec_{datetime.now().strftime('%H%M%S')}"
        if self._is_recording:
            return f"⚠️ Already recording '{self._recording_name}'. Say 'stop recording' first."
        self._recording_name = name
        self._recorded_steps = []
        self._is_recording = True
        return (
            f"🔴 Recording started: '{name}'\n\n"
            f"Use your browser normally, then add steps manually:\n"
            f"  • 'record step navigate to https://example.com'\n"
            f"  • 'record step click selector #submit-btn'\n"
            f"  • 'record step fill selector #email value user@example.com'\n"
            f"  • 'record step wait 2000'\n"
            f"  • 'record step screenshot'\n\n"
            f"Say 'stop recording' when done."
        )

    async def _record_step(self, params: dict) -> str:
        if not self._is_recording:
            return "❌ Not currently recording. Say 'start recording <name>' first."
        action = params.get("action", "").lower()
        step = {
            "action":   action,
            "selector": params.get("selector", ""),
            "value":    params.get("value", ""),
            "url":      params.get("url", ""),
            "wait":     params.get("wait", 0),
        }
        self._recorded_steps.append(step)
        return f"✅ Step {len(self._recorded_steps)} recorded: {action} {step.get('selector') or step.get('url') or ''}"

    async def _stop_recording(self, params: dict) -> str:
        if not self._is_recording:
            return "❌ Not currently recording."
        self._is_recording = False
        name = self._recording_name
        steps = self._recorded_steps.copy()
        if not steps:
            return "⚠️ No steps recorded — recording discarded."

        self._recordings[name] = {
            "steps": steps,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "run_count": 0,
        }
        self._save_recordings()
        self._recording_name = None
        self._recorded_steps = []

        step_list = "\n".join(f"  {i+1}. {s['action']} {s.get('selector') or s.get('url') or ''}" for i, s in enumerate(steps))
        return f"✅ Recording '{name}' saved ({len(steps)} steps):\n\n{step_list}\n\nSay 'play recording {name}' to replay."

    # ── Playback ──────────────────────────────────────────────────────────────

    async def _play_recording(self, params: dict) -> str:
        name = params.get("name", "")
        slow_mo = int(params.get("slow", 500))

        rec = self._recordings.get(name)
        if not rec:
            return f"❌ Recording '{name}' not found. Say 'list recordings'."

        if not self.browser:
            return "❌ Browser engine not available."

        steps = rec["steps"]
        results = [f"▶️ Playing '{name}' ({len(steps)} steps)\n"]

        try:
            page = await self.browser.get_page(f"recorder_{name}")

            for i, step in enumerate(steps):
                action = step.get("action", "")
                selector = step.get("selector", "")
                value = step.get("value", "")
                url = step.get("url", "")
                wait = int(step.get("wait", slow_mo))

                results.append(f"  Step {i+1}: {action}...")
                try:
                    if action == "navigate" and url:
                        await page.goto(url, wait_until="domcontentloaded")
                    elif action == "click" and selector:
                        await page.click(selector)
                    elif action == "fill" and selector and value:
                        await page.fill(selector, value)
                    elif action == "type" and selector and value:
                        await page.type(selector, value)
                    elif action == "press" and selector and value:
                        await page.press(selector, value)
                    elif action == "select" and selector and value:
                        await page.select_option(selector, value)
                    elif action == "screenshot":
                        path = str(RECORDINGS_DIR / f"{name}_step{i+1}.png")
                        await page.screenshot(path=path)
                        results[-1] += f" saved to {path}"
                    elif action == "wait":
                        await asyncio.sleep(wait / 1000)
                    elif action == "scroll" and selector:
                        await page.evaluate(f"document.querySelector('{selector}')?.scrollIntoView()")
                    results[-1] += " ✓"
                except Exception as e:
                    results[-1] += f" ❌ {str(e)[:60]}"

                await asyncio.sleep(wait / 1000)

            self._recordings[name]["run_count"] = rec.get("run_count", 0) + 1
            self._recordings[name]["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            self._save_recordings()
            results.append(f"\n✅ Recording complete.")
        except Exception as e:
            results.append(f"\n❌ Playback error: {e}")

        return "\n".join(results)

    # ── List / Show / Delete ──────────────────────────────────────────────────

    async def _list_recordings(self, params: dict) -> str:
        if not self._recordings:
            return (
                "🎬 No recordings yet, sir.\n\n"
                "Start one: 'start recording client-report'\n"
                "Then: 'record step navigate to https://example.com'"
            )
        lines = ["🎬 Saved Recordings:\n"]
        for name, data in self._recordings.items():
            runs = data.get("run_count", 0)
            lines.append(f"  ▶️  {name}  —  {len(data['steps'])} steps  (run {runs}×)")
            lines.append(f"       Created: {data['created']}")
            if data.get("last_run"):
                lines.append(f"       Last run: {data['last_run']}")
        return "\n".join(lines)

    async def _show_recording(self, params: dict) -> str:
        name = params.get("name", "")
        rec = self._recordings.get(name)
        if not rec:
            return f"❌ Recording '{name}' not found."
        lines = [f"🎬 Recording: {name}\n"]
        for i, s in enumerate(rec["steps"]):
            detail = s.get("selector") or s.get("url") or s.get("value") or ""
            lines.append(f"  {i+1}. {s['action']}  {detail}")
        return "\n".join(lines)

    async def _delete_recording(self, params: dict) -> str:
        name = params.get("name", "")
        if name not in self._recordings:
            return f"❌ Recording '{name}' not found."
        del self._recordings[name]
        self._save_recordings()
        return f"🗑️ Recording '{name}' deleted."

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_recordings(self):
        rec_file = RECORDINGS_DIR / "index.json"
        if rec_file.exists():
            try:
                self._recordings = json.loads(rec_file.read_text(encoding="utf-8"))
            except Exception:
                self._recordings = {}

    def _save_recordings(self):
        rec_file = RECORDINGS_DIR / "index.json"
        try:
            rec_file.write_text(json.dumps(self._recordings, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save recordings: {e}")
