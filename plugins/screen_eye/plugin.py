"""
Screen Eye Plugin — Lets Nexus see and understand your screen.
"""

import logging
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.screen")


class ScreenPlugin(BasePlugin):
    name = "screen"
    description = "Screen awareness - Nexus can see what you're working on"
    icon = "👁️"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.eye = None

    async def connect(self) -> bool:
        try:
            from plugins.screen_eye.screen_eye import ScreenEyePlugin
            self.eye = ScreenEyePlugin(self.config)
            self.eye.capture_screen()  # Test capture
            self._connected = True
            self._status_message = "Screen capture ready"
            return True
        except ImportError as e:
            self._status_message = f"Missing: {e} (pip install mss)"
            return False
        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self.eye:
            return "Screen eye not initialized"

        if action == "read_screen":
            text = self.eye.get_screen_context()
            return f"Screen text:\n{text}" if text else "Couldn't read screen"

        if action == "screenshot":
            path = self.eye.save_screenshot(params.get("path"))
            return f"Screenshot saved to {path}"

        if action == "whats_on_screen":
            text = self.eye.get_screen_context()
            if not text.strip():
                return "Screen appears blank or I couldn't extract any text."
            # Summarize via the first 1500 chars
            preview = text[:1500]
            return f"Here's what I can see on your screen:\n\n{preview}"

        return f"Unknown screen action: {action}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "read_screen", "description": "Read all text currently visible on screen via OCR", "params": []},
            {"action": "screenshot", "description": "Take and save a screenshot", "params": ["path"]},
            {"action": "whats_on_screen", "description": "Describe what's currently on your screen", "params": []},
        ]
