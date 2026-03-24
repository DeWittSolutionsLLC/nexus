"""
Vision AI Plugin — JARVIS can truly SEE your screen using a local vision model.

Uses Ollama's vision API (LLaVA / llava:13b / moondream) to understand images.
"What's wrong with this UI?" → takes screenshot → sends to vision model → answers.
"""

import asyncio
import base64
import logging
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.vision_ai")

SCREENSHOTS_DIR = Path.home() / "NexusScreenshots"


class VisionAIPlugin(BasePlugin):
    name = "vision_ai"
    description = "AI vision — JARVIS understands screenshots and images using LLaVA"
    icon = "👁️"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._ollama_host = config.get("ollama_host", "http://localhost:11434")
        self._vision_model = config.get("vision_model", "llava")
        SCREENSHOTS_DIR.mkdir(exist_ok=True)

    async def connect(self) -> bool:
        loop = asyncio.get_event_loop()

        def _check():
            try:
                import mss  # noqa: F401
                import ollama as ollama_lib
                client = ollama_lib.Client(host=self._ollama_host)
                models = client.list()
                names = [m.model for m in models.models] if models.models else []
                vision_available = any(self._vision_model in n for n in names)
                return vision_available, names
            except ImportError as e:
                return None, str(e)
            except Exception as e:
                return None, str(e)

        try:
            result, info = await asyncio.wait_for(
                loop.run_in_executor(None, _check), timeout=10.0
            )
            if result is None:
                self._status_message = f"Missing dependency: {info}"
                return False
            if not result:
                self._status_message = (
                    f"Vision model '{self._vision_model}' not found. "
                    f"Run: ollama pull {self._vision_model}"
                )
                # Still connect — screenshot + describe still works with text models
            else:
                self._status_message = f"Vision model '{self._vision_model}' ready"
            self._connected = True
            return True
        except asyncio.TimeoutError:
            self._status_message = "Connection timed out"
            return False
        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            return False

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "describe_screen":   self._describe_screen,
            "analyze_screen":    self._describe_screen,
            "analyze_image":     self._analyze_image,
            "read_ui":           self._read_ui,
            "find_on_screen":    self._find_on_screen,
            "screenshot":        self._take_screenshot,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "describe_screen", "description": "Take a screenshot and describe what JARVIS sees on screen", "params": ["question"]},
            {"action": "analyze_image",   "description": "Analyze a specific image file", "params": ["path", "question"]},
            {"action": "read_ui",         "description": "Identify UI elements, buttons, and layout on screen", "params": []},
            {"action": "find_on_screen",  "description": "Find a specific element or text on screen", "params": ["target"]},
            {"action": "screenshot",      "description": "Take and save a screenshot", "params": ["path"]},
        ]

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _describe_screen(self, params: dict) -> str:
        question = params.get("question", "Describe everything you see on this screen in detail.")
        img_b64 = await self._capture_screen_b64()
        if not img_b64:
            return "❌ Could not capture screen. Is 'mss' installed? pip install mss"
        return await self._ask_vision(img_b64, question)

    async def _read_ui(self, params: dict) -> str:
        img_b64 = await self._capture_screen_b64()
        if not img_b64:
            return "❌ Could not capture screen."
        prompt = (
            "Identify all visible UI elements: buttons, menus, input fields, text areas, "
            "windows, and their approximate positions. Be specific and structured."
        )
        return await self._ask_vision(img_b64, prompt)

    async def _find_on_screen(self, params: dict) -> str:
        target = params.get("target", "")
        if not target:
            return "❌ Please specify what to find on screen."
        img_b64 = await self._capture_screen_b64()
        if not img_b64:
            return "❌ Could not capture screen."
        prompt = f"Find '{target}' on this screen. Is it visible? If yes, describe exactly where it is and what it looks like."
        return await self._ask_vision(img_b64, prompt)

    async def _analyze_image(self, params: dict) -> str:
        path = params.get("path", "")
        question = params.get("question", "Describe this image in detail.")
        if not path:
            return "❌ Please provide an image path."
        img_path = Path(path)
        if not img_path.exists():
            return f"❌ Image not found: {path}"
        try:
            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
        except Exception as e:
            return f"❌ Could not read image: {e}"
        return await self._ask_vision(img_b64, question)

    async def _take_screenshot(self, params: dict) -> str:
        save_path = params.get("path") or str(SCREENSHOTS_DIR / f"shot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        try:
            import mss
            with mss.mss() as sct:
                sct.shot(output=save_path)
            return f"✅ Screenshot saved: {save_path}"
        except ImportError:
            return "❌ mss not installed. Run: pip install mss"
        except Exception as e:
            return f"❌ Screenshot failed: {e}"

    # ── Internals ────────────────────────────────────────────────────────────

    async def _capture_screen_b64(self) -> str | None:
        loop = asyncio.get_event_loop()

        def _capture():
            try:
                import mss
                import mss.tools
                with mss.mss() as sct:
                    monitor = sct.monitors[1]  # primary monitor
                    img = sct.grab(monitor)
                    import io
                    from PIL import Image
                    pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                    # Resize to reasonable resolution for vision model
                    pil_img.thumbnail((1280, 720))
                    buf = io.BytesIO()
                    pil_img.save(buf, format="PNG")
                    return base64.b64encode(buf.getvalue()).decode()
            except Exception as e:
                logger.error(f"Screen capture error: {e}")
                return None

        return await loop.run_in_executor(None, _capture)

    async def _ask_vision(self, img_b64: str, question: str) -> str:
        loop = asyncio.get_event_loop()

        def _call():
            import ollama as ollama_lib
            client = ollama_lib.Client(host=self._ollama_host)
            response = client.chat(
                model=self._vision_model,
                messages=[{
                    "role": "user",
                    "content": question,
                    "images": [img_b64],
                }],
                options={"temperature": 0.3},
                keep_alive="30m",
            )
            return response["message"]["content"]

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _call),
                timeout=60.0,
            )
            return f"👁️ Vision Analysis:\n\n{result}"
        except asyncio.TimeoutError:
            return "❌ Vision model timed out. Try: ollama pull moondream (faster model)"
        except Exception as e:
            # Fallback: try with llava:7b or moondream
            logger.error(f"Vision AI error: {e}")
            return (
                f"❌ Vision model error: {e}\n\n"
                f"To enable vision, run: ollama pull {self._vision_model}\n"
                f"Or set vision_model to 'moondream' in config for a faster model."
            )
