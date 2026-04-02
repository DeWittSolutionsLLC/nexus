"""
Voice Engine Plugin — Wraps voice.py into the Nexus plugin system.
Adds voice status to sidebar and routes voice commands through the assistant.
"""

import logging
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.voice")


class VoicePlugin(BasePlugin):
    name = "voice"
    description = "Voice control - say 'Nexus' to activate"
    icon = "🎙️"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.voice_engine = None

    async def connect(self) -> bool:
        try:
            from plugins.voice_engine.voice import VoiceEngine

            voice_config = self.config if self.config else {
                "whisper_model": "tiny",
                "wake_word": False,
                "voice_rate": 175,
                "voice_volume": 0.9,
            }

            self.voice_engine = VoiceEngine(voice_config)
            self.voice_engine.initialize()

            if self.voice_engine.is_available:
                self._connected = True
                self._status_message = "Ready (click MIC to talk)"
                return True
            elif self.voice_engine.tts_available:
                # TTS works but Whisper/STT is not loaded — still connect for read-back
                self._connected = True
                self._status_message = "TTS only (Whisper not loaded)"
                return True
            else:
                self._status_message = "Whisper model not loaded"
                return False

        except ImportError as e:
            self._status_message = f"Missing dependency: {e}"
            return False
        except Exception as e:
            self._status_message = f"Init failed: {str(e)[:60]}"
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self.voice_engine:
            return "Voice engine not initialized"

        if action == "speak":
            text = params.get("text", "")
            self.voice_engine.speak_async(text)
            return f"Speaking: {text[:50]}..."

        if action == "start_listening":
            callback = params.get("callback")
            self.voice_engine.start_listening(on_command=callback)
            return "Listening started"

        if action == "stop_listening":
            self.voice_engine.stop_listening()
            return "Listening stopped"

        return f"Unknown voice action: {action}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "speak", "description": "Say something out loud via TTS", "params": ["text"]},
            {"action": "start_listening", "description": "Start listening for voice commands", "params": []},
            {"action": "stop_listening", "description": "Stop voice listening", "params": []},
        ]