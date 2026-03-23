"""
Screen Eye Plugin — Screen awareness via screenshots + local OCR/vision.

Captures your screen, extracts text via OCR, and lets the AI understand
what you're looking at. Fully local — nothing leaves your machine.

Uses:
  - mss for fast screenshots
  - Whisper-compatible image analysis via Ollama vision models
  - Fallback: basic OCR with pytesseract (if installed)
"""

import asyncio
import base64
import io
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("nexus.plugins.screen")


class ScreenEyePlugin:
    """Note: This is a standalone module, not a BasePlugin, because it's used
    as a utility by the assistant rather than a user-facing action plugin."""

    def __init__(self, config: dict):
        self.config = config
        self._last_capture = None
        self._last_text = ""

    def capture_screen(self, monitor: int = 1) -> bytes:
        """Take a screenshot and return it as PNG bytes."""
        import mss

        with mss.mss() as sct:
            mon = sct.monitors[monitor]  # 0 = all monitors, 1 = primary
            screenshot = sct.grab(mon)
            # Convert to PNG bytes
            png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
            self._last_capture = png_bytes
            return png_bytes

    def capture_region(self, x: int, y: int, width: int, height: int) -> bytes:
        """Capture a specific screen region."""
        import mss

        with mss.mss() as sct:
            region = {"left": x, "top": y, "width": width, "height": height}
            screenshot = sct.grab(region)
            png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
            return png_bytes

    def extract_text_ocr(self, image_bytes: bytes = None) -> str:
        """Extract text from screenshot using OCR (pytesseract)."""
        if image_bytes is None:
            image_bytes = self._last_capture
        if image_bytes is None:
            return "No screenshot available"

        try:
            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(img)
            self._last_text = text
            return text
        except ImportError:
            return "[OCR unavailable - install pytesseract]"
        except Exception as e:
            return f"[OCR error: {e}]"

    async def describe_screen(self, ollama_client, model: str = "llava:7b") -> str:
        """
        Use a local vision model (LLaVA via Ollama) to describe what's on screen.
        
        Requires: ollama pull llava:7b (or llava:13b for better quality)
        Note: LLaVA needs ~8GB RAM. On 8GB systems, use OCR fallback instead.
        """
        screenshot = self.capture_screen()
        if not screenshot:
            return "Could not capture screen"

        b64_image = base64.b64encode(screenshot).decode("utf-8")

        try:
            response = ollama_client.chat(
                model=model,
                messages=[{
                    "role": "user",
                    "content": "Describe what's on this screen concisely. Focus on the main application, any text content, and what the user appears to be working on.",
                    "images": [b64_image],
                }],
            )
            return response["message"]["content"]
        except Exception as e:
            # Fallback to OCR
            logger.warning(f"Vision model failed ({e}), falling back to OCR")
            return self.extract_text_ocr(screenshot)

    def get_screen_context(self) -> str:
        """Quick screen context via OCR (lighter than vision model)."""
        try:
            screenshot = self.capture_screen()
            text = self.extract_text_ocr(screenshot)
            # Truncate to keep context window manageable
            if len(text) > 2000:
                text = text[:2000] + "...[truncated]"
            return text
        except Exception as e:
            return f"[Screen capture unavailable: {e}]"

    def save_screenshot(self, path: str = None) -> str:
        """Save the last screenshot to disk."""
        if self._last_capture is None:
            self.capture_screen()
        if self._last_capture is None:
            return "No screenshot to save"

        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(Path(tempfile.gettempdir()) / f"nexus_screen_{timestamp}.png")

        Path(path).write_bytes(self._last_capture)
        return path
