"""
Meeting Notes Plugin — Record audio, transcribe with Whisper, extract action items.

"Start meeting" → records system/mic audio
"Stop meeting"  → transcribes with local Whisper → Ollama summarizes → adds tasks to memory
"""

import asyncio
import logging
import threading
import wave
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.meeting_notes")

MEETINGS_DIR = Path.home() / "NexusMeetings"


class MeetingNotesPlugin(BasePlugin):
    name = "meeting_notes"
    description = "Record meetings, transcribe with Whisper, extract action items automatically"
    icon = "🎙️"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._ollama_host = config.get("ollama_host", "http://localhost:11434")
        self._model = config.get("model", "llama3.1:8b")
        self._whisper_model = config.get("whisper_model", "base")
        self._recording = False
        self._record_thread: threading.Thread | None = None
        self._audio_frames: list = []
        self._current_meeting: str | None = None
        self._meetings: dict[str, dict] = {}
        self._plugin_manager = None
        MEETINGS_DIR.mkdir(exist_ok=True)

    def set_plugin_manager(self, pm):
        self._plugin_manager = pm

    async def connect(self) -> bool:
        loop = asyncio.get_event_loop()

        def _check():
            try:
                import sounddevice  # noqa: F401
                import numpy       # noqa: F401
                return True, None
            except ImportError as e:
                return False, str(e)

        ok, err = await asyncio.wait_for(loop.run_in_executor(None, _check), timeout=5.0)
        if not ok:
            self._status_message = f"Missing: {err} (pip install sounddevice numpy)"
            return False
        self._connected = True
        self._status_message = "Ready — mic available"
        return True

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "start_meeting":    self._start_meeting,
            "stop_meeting":     self._stop_meeting,
            "transcribe_file":  self._transcribe_file,
            "list_meetings":    self._list_meetings,
            "summarize":        self._summarize_meeting,
            "get_actions":      self._get_action_items,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "start_meeting",   "description": "Start recording a meeting", "params": ["title"]},
            {"action": "stop_meeting",    "description": "Stop recording, transcribe, and extract action items", "params": []},
            {"action": "transcribe_file", "description": "Transcribe an existing audio file", "params": ["path"]},
            {"action": "list_meetings",   "description": "List all recorded meetings", "params": []},
            {"action": "summarize",       "description": "Summarize a meeting", "params": ["name"]},
            {"action": "get_actions",     "description": "Extract action items from a meeting", "params": ["name"]},
        ]

    # ── Recording ─────────────────────────────────────────────────────────────

    async def _start_meeting(self, params: dict) -> str:
        if self._recording:
            return f"⚠️ Already recording '{self._current_meeting}'. Say 'stop meeting' first."

        title = params.get("title", f"Meeting_{datetime.now().strftime('%Y%m%d_%H%M')}")
        self._current_meeting = title
        self._audio_frames = []
        self._recording = True

        self._record_thread = threading.Thread(target=self._record_audio, daemon=True)
        self._record_thread.start()

        return (
            f"🔴 Recording meeting: '{title}'\n\n"
            f"Microphone is live. Say 'stop meeting' when done.\n"
            f"I'll transcribe with Whisper and extract action items automatically."
        )

    def _record_audio(self):
        try:
            import sounddevice as sd
            import numpy as np

            SAMPLE_RATE = 16000
            CHANNELS = 1

            def callback(indata, frames, time, status):
                if self._recording:
                    self._audio_frames.append(indata.copy())

            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                dtype="int16", callback=callback):
                while self._recording:
                    import time
                    time.sleep(0.1)

        except Exception as e:
            logger.error(f"Recording error: {e}")
            self._recording = False

    async def _stop_meeting(self, params: dict) -> str:
        if not self._recording:
            return "❌ No meeting in progress."

        self._recording = False
        title = self._current_meeting
        await asyncio.sleep(0.5)   # let record thread finish

        if not self._audio_frames:
            return "❌ No audio captured."

        # Save WAV file
        audio_path = MEETINGS_DIR / f"{title}.wav"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._save_wav(audio_path))

        # Transcribe
        yield_text = f"⏸️ Recording stopped ({audio_path.stat().st_size // 1024}KB).\n⌛ Transcribing with Whisper..."
        transcript = await self._run_whisper(audio_path)

        if not transcript:
            return (
                f"✅ Meeting '{title}' saved.\n📄 {audio_path}\n\n"
                f"⚠️ Whisper transcription failed. Install: pip install openai-whisper\n"
                f"Transcribe manually: 'transcribe file {audio_path}'"
            )

        # Save transcript
        txt_path = MEETINGS_DIR / f"{title}.txt"
        txt_path.write_text(transcript, encoding="utf-8")

        # Summarize + extract action items
        summary, actions = await self._process_transcript(transcript)

        # Save to meetings registry
        self._meetings[title] = {
            "audio": str(audio_path),
            "transcript": str(txt_path),
            "summary": summary,
            "actions": actions,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        # Add action items to memory if available
        action_note = ""
        if actions and self._plugin_manager:
            mem = self._plugin_manager.get_plugin("memory")
            if mem and hasattr(mem, "add_task"):
                for a in actions[:5]:
                    try:
                        mem.add_task(a, priority="high", source="meeting")
                    except Exception:
                        pass
                action_note = f"\n\n✅ {len(actions)} action items added to your task list."

        action_list = "\n".join(f"  • {a}" for a in actions[:8]) if actions else "  None extracted"
        return (
            f"✅ Meeting '{title}' processed, sir.\n\n"
            f"📋 Summary:\n{summary}\n\n"
            f"✅ Action Items:\n{action_list}"
            f"{action_note}"
        )

    def _save_wav(self, path: Path):
        try:
            import numpy as np
            import sounddevice as sd   # noqa — just to verify
            frames = self._audio_frames
            if not frames:
                return
            audio = __import__("numpy").concatenate(frames, axis=0)
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)   # int16 = 2 bytes
                wf.setframerate(16000)
                wf.writeframes(audio.tobytes())
        except Exception as e:
            logger.error(f"WAV save error: {e}")

    async def _run_whisper(self, audio_path: Path) -> str | None:
        loop = asyncio.get_event_loop()

        def _transcribe():
            try:
                import whisper
                model = whisper.load_model(self._whisper_model)
                result = model.transcribe(str(audio_path))
                return result["text"]
            except ImportError:
                return None
            except Exception as e:
                logger.error(f"Whisper error: {e}")
                return None

        try:
            return await asyncio.wait_for(loop.run_in_executor(None, _transcribe), timeout=300.0)
        except asyncio.TimeoutError:
            return None

    async def _transcribe_file(self, params: dict) -> str:
        path = Path(params.get("path", ""))
        if not path.exists():
            return f"❌ File not found: {path}"
        transcript = await self._run_whisper(path)
        if not transcript:
            return "❌ Transcription failed. Is openai-whisper installed?"
        txt_path = path.with_suffix(".txt")
        txt_path.write_text(transcript, encoding="utf-8")
        return f"✅ Transcribed '{path.name}'.\n\n📄 {txt_path}\n\n{transcript[:500]}..."

    # ── Processing ────────────────────────────────────────────────────────────

    async def _process_transcript(self, transcript: str) -> tuple[str, list[str]]:
        """Returns (summary, action_items_list)."""
        try:
            import ollama as ollama_lib
            loop = asyncio.get_event_loop()

            def _call():
                c = ollama_lib.Client(host=self._ollama_host)
                prompt = (
                    f"Meeting transcript:\n{transcript[:4000]}\n\n"
                    f"1. Write a 3-sentence summary of the meeting.\n"
                    f"2. List all action items as bullet points starting with 'ACTION:'.\n\n"
                    f"Format:\nSUMMARY: <your summary>\n\nACTION: <task 1>\nACTION: <task 2>"
                )
                return c.chat(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.2},
                    keep_alive="30m",
                )

            response = await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=60.0)
            text = response["message"]["content"]

            summary = ""
            actions = []
            for line in text.split("\n"):
                if line.startswith("SUMMARY:"):
                    summary = line[8:].strip()
                elif line.startswith("ACTION:"):
                    actions.append(line[7:].strip())
            if not summary:
                summary = text[:300]
            return summary, actions
        except Exception as e:
            logger.error(f"Transcript processing error: {e}")
            return transcript[:200], []

    # ── List / Summarize ─────────────────────────────────────────────────────

    async def _list_meetings(self, params: dict) -> str:
        disk = list(MEETINGS_DIR.glob("*.wav")) + list(MEETINGS_DIR.glob("*.txt"))
        if not self._meetings and not disk:
            return "🎙️ No meetings recorded yet, sir.\n\nSay 'start meeting' to begin."
        lines = [f"🎙️ Meetings in {MEETINGS_DIR}:\n"]
        for name, data in self._meetings.items():
            lines.append(f"  🎙️  {name}")
            lines.append(f"       {data['date']}")
            if data.get("summary"):
                lines.append(f"       {data['summary'][:80]}...")
        for f in disk:
            if f.stem not in self._meetings:
                lines.append(f"  📄 {f.name}  [on disk]")
        return "\n".join(lines)

    async def _summarize_meeting(self, params: dict) -> str:
        name = params.get("name", "")
        data = self._meetings.get(name)
        if data and data.get("summary"):
            return f"📋 {name}:\n\n{data['summary']}"
        # Try reading transcript from disk
        txt = MEETINGS_DIR / f"{name}.txt"
        if txt.exists():
            transcript = txt.read_text(encoding="utf-8")
            summary, _ = await self._process_transcript(transcript)
            return f"📋 {name}:\n\n{summary}"
        return f"❌ Meeting '{name}' not found."

    async def _get_action_items(self, params: dict) -> str:
        name = params.get("name", "")
        data = self._meetings.get(name)
        if data and data.get("actions"):
            lines = [f"✅ Action items from '{name}':\n"]
            for a in data["actions"]:
                lines.append(f"  • {a}")
            return "\n".join(lines)
        return f"❌ No action items found for '{name}'."
