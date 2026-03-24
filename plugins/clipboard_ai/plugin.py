from core.plugin_manager import BasePlugin
import logging
import json
import requests
from datetime import datetime
from collections import deque

logger = logging.getLogger("nexus.plugins.clipboard_ai")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"
MAX_HISTORY = 50


class ClipboardAIPlugin(BasePlugin):
    name = "clipboard_ai"
    description = "Monitors clipboard and applies AI-powered transformations via Ollama."
    icon = "📋"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pyperclip = None
        self._history: deque[dict] = deque(maxlen=MAX_HISTORY)

    async def connect(self) -> bool:
        try:
            import pyperclip
            self._pyperclip = pyperclip
            self._connected = True
            self._status_message = "Ready"
            logger.info("pyperclip loaded successfully.")
        except ImportError:
            logger.warning("pyperclip not installed. Clipboard read/write unavailable.")
            self._pyperclip = None
            self._connected = True
            self._status_message = "Ready (no clipboard access — install pyperclip)"
        return True

    def _read_clipboard(self) -> str:
        if self._pyperclip is None:
            return ""
        try:
            return self._pyperclip.paste() or ""
        except Exception as e:
            logger.error(f"clipboard read error: {e}")
            return ""

    def _write_clipboard(self, text: str) -> bool:
        if self._pyperclip is None:
            return False
        try:
            self._pyperclip.copy(text)
            return True
        except Exception as e:
            logger.error(f"clipboard write error: {e}")
            return False

    def _ollama_generate(self, prompt: str) -> str:
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()
        except requests.ConnectionError:
            return "Error: Ollama is not running. Start it with 'ollama serve'."
        except requests.Timeout:
            return "Error: Ollama request timed out."
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            return f"Error: {e}"

    def _add_to_history(self, text: str):
        self._history.append({"timestamp": datetime.now().isoformat(), "content": text})

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "get_clipboard":
                return self._do_get_clipboard()
            elif action == "set_clipboard":
                return self._do_set_clipboard(str(params.get("text", "")))
            elif action == "transform":
                return self._do_transform(str(params.get("text", "")), str(params.get("instruction", "")))
            elif action == "history":
                return self._do_history(int(params.get("n", 10)))
            elif action == "clear_history":
                self._history.clear()
                return "Clipboard history cleared."
            elif action == "smart_paste":
                return self._do_smart_paste()
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"execute({action}) error: {e}")
            return f"Error executing {action}: {e}"

    def _do_get_clipboard(self) -> str:
        if self._pyperclip is None:
            return "pyperclip not installed. Cannot read clipboard."
        text = self._read_clipboard()
        if not text:
            return "Clipboard is empty."
        self._add_to_history(text)
        preview = text[:500] + ("..." if len(text) > 500 else "")
        return f"Clipboard ({len(text)} chars):\n{preview}"

    def _do_set_clipboard(self, text: str) -> str:
        if not text:
            return "No text provided."
        if self._pyperclip is None:
            return "pyperclip not installed. Cannot write clipboard."
        if self._write_clipboard(text):
            self._add_to_history(text)
            return f"Clipboard set ({len(text)} chars)."
        return "Failed to write to clipboard."

    def _do_transform(self, text: str, instruction: str) -> str:
        if not instruction:
            return "No instruction provided. Example: 'translate to Spanish', 'fix grammar', 'summarize'."
        if not text:
            text = self._read_clipboard()
        if not text:
            return "No text to transform (clipboard is empty and no text param provided)."
        prompt = (
            f"You are a helpful assistant. Apply this instruction to the text below and return ONLY the transformed result, "
            f"no explanations.\n\nInstruction: {instruction}\n\nText:\n{text}"
        )
        result = self._ollama_generate(prompt)
        if not result.startswith("Error:"):
            self._add_to_history(result)
            if self._pyperclip is not None:
                self._write_clipboard(result)
                return f"Transformation applied and copied to clipboard:\n\n{result}"
        return f"Transformation result:\n\n{result}"

    def _do_history(self, n: int) -> str:
        items = list(self._history)[-n:]
        if not items:
            return "No clipboard history."
        lines = [f"Last {len(items)} clipboard items:"]
        for i, item in enumerate(reversed(items), 1):
            preview = item["content"][:80].replace("\n", " ")
            lines.append(f"  {i}. [{item['timestamp'][11:19]}] {preview}{'...' if len(item['content']) > 80 else ''}")
        return "\n".join(lines)

    def _do_smart_paste(self) -> str:
        if self._pyperclip is None:
            return "pyperclip not installed. Cannot read clipboard."
        text = self._read_clipboard()
        if not text:
            return "Clipboard is empty."
        prompt = (
            f"Analyze the following clipboard content and suggest the single best action to take with it "
            f"(e.g., translate, summarize, fix grammar, extract key info, format as JSON, etc.). "
            f"Reply with: ACTION: <action>\nREASON: <one sentence why>\n\nContent:\n{text[:1000]}"
        )
        suggestion = self._ollama_generate(prompt)
        return f"Smart Paste Analysis:\n{suggestion}\n\nClipboard preview: {text[:200]}{'...' if len(text) > 200 else ''}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "get_clipboard", "description": "Read and return current clipboard content."},
            {"action": "set_clipboard", "description": "Write text to clipboard. Param: text (str)."},
            {"action": "transform", "description": "AI-transform text. Params: instruction (str), text (str, optional — uses clipboard if omitted)."},
            {"action": "history", "description": "Show clipboard history. Param: n (int, default 10)."},
            {"action": "clear_history", "description": "Clear in-memory clipboard history."},
            {"action": "smart_paste", "description": "AI analyzes clipboard and suggests the best action to take."},
        ]
