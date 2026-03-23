"""
Voice Engine - Hands-free Jarvis-style voice control.

Speech-to-Text: OpenAI Whisper (runs locally on CPU)
Text-to-Speech: pyttsx3 (uses Windows SAPI5 built-in voices - zero setup)

Everything runs offline. Nothing leaves your machine.
"""

import logging
import queue
import threading
import numpy as np

logger = logging.getLogger("nexus.voice")

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
SILENCE_THRESHOLD = 300
SILENCE_DURATION = 1.8
MIN_RECORDING_DURATION = 0.5
WAKE_WORD = "nexus"
# Whisper tiny often mishears "nexus" as these variants
WAKE_WORD_VARIANTS = ["nexus", "nexis", "naxus", "next us", "next is", "nexas", "nekus", "nexos", "lettuce", "texas"]


class VoiceEngine:
    """
    Voice input (Whisper STT) and output (pyttsx3 TTS).

    Usage:
        voice = VoiceEngine(config)
        voice.initialize()
        voice.start_listening(on_command=callback)
        voice.speak("Hello!")
    """

    def __init__(self, config: dict):
        self.config = config
        self.whisper_model = None
        self.tts_engine = None
        self.whisper_size = config.get("whisper_model", "tiny")
        self._listening = False
        self._on_command = None
        self._on_status_change = None
        self._wake_word_enabled = config.get("wake_word", True)
        self._tts_lock = threading.Lock()
        self._voice_rate = config.get("voice_rate", 175)
        self._voice_volume = config.get("voice_volume", 0.9)
        self._voice_id = config.get("voice_id", None)

    def initialize(self):
        """Load Whisper STT model and init pyttsx3 TTS."""
        # -- Speech-to-Text: Whisper --
        try:
            import whisper
            logger.info(f"Loading Whisper '{self.whisper_size}' model...")
            self.whisper_model = whisper.load_model(self.whisper_size)
            logger.info("Whisper STT ready")
        except ImportError:
            logger.error("openai-whisper not installed. Run: pip install openai-whisper")
        except Exception as e:
            logger.error(f"Whisper load failed: {e}")

        # -- Text-to-Speech: pyttsx3 (Windows SAPI5) --
        try:
            import pyttsx3
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty("rate", self._voice_rate)
            self.tts_engine.setProperty("volume", self._voice_volume)

            voices = self.tts_engine.getProperty("voices")
            if voices:
                voice_names = [v.name for v in voices]
                logger.info(f"Available TTS voices: {voice_names}")

                if self._voice_id:
                    for v in voices:
                        if self._voice_id.lower() in v.name.lower() or self._voice_id == v.id:
                            self.tts_engine.setProperty("voice", v.id)
                            logger.info(f"TTS voice set to: {v.name}")
                            break
                else:
                    # Try to pick a male English voice for Jarvis feel
                    for v in voices:
                        name_lower = v.name.lower()
                        if "david" in name_lower or "mark" in name_lower or "james" in name_lower:
                            self.tts_engine.setProperty("voice", v.id)
                            logger.info(f"TTS voice auto-selected: {v.name}")
                            break

            logger.info("pyttsx3 TTS ready (Windows SAPI5)")
        except ImportError:
            logger.error("pyttsx3 not installed. Run: pip install pyttsx3")
        except Exception as e:
            logger.error(f"TTS init failed: {e}")

    # -- Speech-to-Text --

    def start_listening(self, on_command=None, on_status_change=None):
        self._on_command = on_command
        self._on_status_change = on_status_change
        self._listening = True
        thread = threading.Thread(target=self._listen_loop, daemon=True)
        thread.start()
        logger.info("Voice listening started - say 'Nexus' to activate")

    def stop_listening(self):
        self._listening = False

    def _listen_loop(self):
        import sounddevice as sd

        while self._listening:
            try:
                self._set_status("listening")
                audio_data = self._record_until_silence(sd)

                if audio_data is None or len(audio_data) < SAMPLE_RATE * MIN_RECORDING_DURATION:
                    continue

                self._set_status("processing")
                text = self._transcribe(audio_data)

                if not text or len(text.strip()) < 2:
                    continue

                text = text.strip()
                logger.info(f">>> HEARD: \"{text}\"")
                print(f"\n[VOICE] Heard: \"{text}\"\n")  # Also print to terminal

                if self._wake_word_enabled:
                    text_lower = text.lower()
                    # Check for exact wake word or common misheard variants
                    wake_found = False
                    wake_end = 0
                    for variant in WAKE_WORD_VARIANTS:
                        if variant in text_lower:
                            wake_found = True
                            idx = text_lower.find(variant)
                            wake_end = idx + len(variant)
                            break

                    # Also try fuzzy matching on the first word
                    if not wake_found:
                        first_word = text_lower.split()[0] if text_lower.split() else ""
                        try:
                            from rapidfuzz import fuzz
                            score = fuzz.ratio(first_word, "nexus")
                            if score > 60:
                                wake_found = True
                                wake_end = len(first_word) + (1 if len(text_lower) > len(first_word) else 0)
                                logger.info(f"Fuzzy wake word match: '{first_word}' (score: {score})")
                        except ImportError:
                            pass

                    if not wake_found:
                        logger.debug(f"No wake word in: {text}")
                        continue

                    text = text[wake_end:].strip().lstrip(",").lstrip(".").strip()
                    if not text:
                        if self._on_command:
                            self._on_command("[wake]")
                        continue

                    logger.info(f">>> COMMAND: \"{text}\"")

                if self._on_command:
                    self._on_command(text)

            except Exception as e:
                logger.error(f"Listen loop error: {e}")
                import time
                time.sleep(1)

    def _record_until_silence(self, sd):
        chunks = []
        silent_chunks = 0
        chunk_duration = 0.1
        chunk_size = int(SAMPLE_RATE * chunk_duration)
        max_silent = int(SILENCE_DURATION / chunk_duration)
        max_chunks = int(30 / chunk_duration)
        total_chunks = 0
        peak_rms = 0

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE,
                            blocksize=chunk_size) as stream:
            while self._listening and total_chunks < max_chunks:
                data, _ = stream.read(chunk_size)
                chunk = np.frombuffer(data, dtype=np.int16)
                rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))
                peak_rms = max(peak_rms, rms)

                if rms > SILENCE_THRESHOLD:
                    chunks.append(chunk)
                    silent_chunks = 0
                elif len(chunks) > 0:
                    chunks.append(chunk)
                    silent_chunks += 1
                    if silent_chunks >= max_silent:
                        break
                total_chunks += 1

        if chunks:
            duration = len(chunks) * chunk_duration
            logger.info(f"Recorded {duration:.1f}s of audio (peak RMS: {peak_rms:.0f})")
        
        return np.concatenate(chunks) if chunks else None

    def _transcribe(self, audio_data: np.ndarray) -> str:
        if self.whisper_model is None:
            return ""
        audio_float = audio_data.astype(np.float32) / 32768.0
        result = self.whisper_model.transcribe(audio_float, language="en", fp16=False)
        return result.get("text", "")

    # -- Text-to-Speech --

    def speak(self, text: str):
        """Say text out loud using Windows built-in voices. Blocks until done."""
        if not text:
            return
        if self.tts_engine is None:
            print(f"[NEXUS]: {text}")
            return

        with self._tts_lock:
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except RuntimeError:
                # Engine sometimes gets stuck after interrupts - reinitialize
                try:
                    import pyttsx3
                    self.tts_engine = pyttsx3.init()
                    self.tts_engine.setProperty("rate", self._voice_rate)
                    self.tts_engine.setProperty("volume", self._voice_volume)
                    self.tts_engine.say(text)
                    self.tts_engine.runAndWait()
                except Exception as e:
                    logger.error(f"TTS recovery failed: {e}")
            except Exception as e:
                logger.error(f"TTS error: {e}")

    def speak_async(self, text: str):
        """Non-blocking version of speak."""
        threading.Thread(target=self.speak, args=(text,), daemon=True).start()

    def list_voices(self) -> list[dict]:
        """Return all available system voices."""
        if not self.tts_engine:
            return []
        voices = self.tts_engine.getProperty("voices")
        return [{"id": v.id, "name": v.name} for v in voices]

    def set_voice(self, voice_name: str) -> bool:
        """Switch voice by name (e.g. 'David', 'Zira', 'Mark')."""
        if not self.tts_engine:
            return False
        voices = self.tts_engine.getProperty("voices")
        for v in voices:
            if voice_name.lower() in v.name.lower():
                self.tts_engine.setProperty("voice", v.id)
                logger.info(f"Voice changed to: {v.name}")
                return True
        return False

    def set_rate(self, rate: int):
        """Adjust speaking speed. Default 175 WPM. Lower = slower."""
        if self.tts_engine:
            self._voice_rate = rate
            self.tts_engine.setProperty("rate", rate)

    def _set_status(self, status: str):
        if self._on_status_change:
            self._on_status_change(status)

    @property
    def is_available(self) -> bool:
        return self.whisper_model is not None