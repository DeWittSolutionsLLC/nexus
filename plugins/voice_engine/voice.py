"""
Voice Engine v2 — JARVIS-quality speech for Nexus.

Speech-to-Text: OpenAI Whisper (local, zero-latency)
Text-to-Speech: Windows Neural SAPI5 voices (Windows 11 built-in neural voices
                sound remarkably good — especially "Microsoft Guy Natural")
                Falls back to standard SAPI5 (David/Mark) on older Windows.

Sound Effects:  Generated programmatically — no audio files needed.
                Plays via sounddevice (already installed).

Everything runs 100% offline.
"""

import logging
import queue
import threading
import numpy as np

logger = logging.getLogger("nexus.voice")

SAMPLE_RATE       = 16000
CHANNELS          = 1
DTYPE             = "int16"
SILENCE_THRESHOLD = 300
SILENCE_DURATION  = 1.8
MIN_RECORDING_S   = 0.5
WAKE_WORD         = "nexus"
WAKE_WORD_VARIANTS = [
    "nexus", "nexis", "naxus", "next us", "next is",
    "nexas", "nekus", "nexos", "lettuce", "texas",
]

# Preferred voice names — checked in priority order.
# Windows 11 ships with Neural voices that sound excellent.
PREFERRED_VOICES = [
    "microsoft guy online (natural)",   # Win11 neural — best JARVIS match
    "microsoft ryan online (natural)",  # Win11 neural — British male
    "microsoft aria online (natural)",  # Win11 neural — alternative
    "microsoft david desktop",          # Win10 standard — decent male
    "david",                            # Generic SAPI fallback
    "mark",
    "james",
]


# ─────────────────────────────────────────────────────────────────────────────
# Sound FX — generated with numpy, no files needed
# ─────────────────────────────────────────────────────────────────────────────

class SoundFX:
    SR = 44100

    @classmethod
    def _play(cls, wave: np.ndarray, volume: float = 0.6):
        try:
            import sounddevice as sd
            buf = (wave * volume * 32767).astype(np.int16)
            sd.play(buf, cls.SR, blocking=False)
        except Exception as e:
            logger.debug(f"SoundFX play error: {e}")

    @classmethod
    def _tone(cls, freq: float, duration: float, decay: float = 4.0) -> np.ndarray:
        t = np.linspace(0, duration, int(cls.SR * duration), endpoint=False)
        wave = np.sin(2 * np.pi * freq * t) * np.exp(-decay * t)
        return wave.astype(np.float32)

    @classmethod
    def _chord(cls, freqs: list, duration: float, decay: float = 4.0) -> np.ndarray:
        wave = sum(cls._tone(f, duration, decay) for f in freqs)
        return wave / len(freqs)

    @classmethod
    def boot(cls):
        """JARVIS boot chime — rising arpeggio."""
        def _play():
            notes = [523, 659, 784, 1047]   # C5 E5 G5 C6
            parts = []
            for i, f in enumerate(notes):
                t = np.linspace(0, 0.12, int(cls.SR * 0.12), endpoint=False)
                wave = np.sin(2 * np.pi * f * t) * np.exp(-8 * t)
                silence = np.zeros(int(cls.SR * 0.04))
                parts.extend([wave.astype(np.float32), silence])
            full = np.concatenate(parts)
            cls._play(full, volume=0.35)
        threading.Thread(target=_play, daemon=True).start()

    @classmethod
    def confirm(cls):
        """Soft double-ping — action confirmed."""
        def _play():
            t1 = cls._tone(880, 0.08, decay=12)
            gap = np.zeros(int(cls.SR * 0.05))
            t2 = cls._tone(1100, 0.08, decay=12)
            cls._play(np.concatenate([t1, gap, t2]), volume=0.25)
        threading.Thread(target=_play, daemon=True).start()

    @classmethod
    def alert(cls):
        """Urgent alert — low double beep."""
        def _play():
            t1 = cls._tone(330, 0.15, decay=5)
            gap = np.zeros(int(cls.SR * 0.08))
            t2 = cls._tone(330, 0.15, decay=5)
            cls._play(np.concatenate([t1, gap, t2]), volume=0.4)
        threading.Thread(target=_play, daemon=True).start()

    @classmethod
    def wake(cls):
        """Wake-word detected ping."""
        def _play():
            wave = cls._tone(1200, 0.07, decay=15)
            cls._play(wave, volume=0.2)
        threading.Thread(target=_play, daemon=True).start()

    @classmethod
    def speak_start(cls):
        """Subtle click before JARVIS speaks."""
        def _play():
            wave = cls._tone(600, 0.04, decay=20)
            cls._play(wave, volume=0.15)
        threading.Thread(target=_play, daemon=True).start()

    @classmethod
    def error(cls):
        """Error tone — descending."""
        def _play():
            t1 = cls._tone(440, 0.12, decay=6)
            gap = np.zeros(int(cls.SR * 0.06))
            t2 = cls._tone(330, 0.18, decay=4)
            cls._play(np.concatenate([t1, gap, t2]), volume=0.3)
        threading.Thread(target=_play, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Voice Engine
# ─────────────────────────────────────────────────────────────────────────────

class VoiceEngine:
    def __init__(self, config: dict):
        self.config = config
        self.whisper_model  = None
        self.tts_engine     = None
        self.whisper_size   = config.get("whisper_model", "tiny")
        self._listening     = False
        self._on_command    = None
        self._on_status_change = None
        self._wake_word_enabled = config.get("wake_word", True)
        self._tts_lock      = threading.Lock()
        self._voice_rate    = config.get("voice_rate", 155)    # slightly slower = more authoritative
        self._voice_volume  = config.get("voice_volume", 0.95)
        self._voice_id      = config.get("voice_id", None)
        self._sound_enabled = config.get("sound_effects", True)
        # Personality preferred voices override PREFERRED_VOICES if provided
        self._personality_voices: list[str] = config.get("personality_voices", [])

    def initialize(self):
        self._load_whisper()
        self._load_tts()
        if self._sound_enabled:
            SoundFX.boot()

    # ── Whisper STT ───────────────────────────────────────────────────────────

    def _load_whisper(self):
        try:
            import whisper
            logger.info(f"Loading Whisper '{self.whisper_size}'...")
            self.whisper_model = whisper.load_model(self.whisper_size)
            logger.info("Whisper STT ready")
        except ImportError:
            logger.error("openai-whisper not installed: pip install openai-whisper")
        except Exception as e:
            logger.error(f"Whisper load failed: {e}")

    # ── TTS ───────────────────────────────────────────────────────────────────

    def _load_tts(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate",   self._voice_rate)
            engine.setProperty("volume", self._voice_volume)

            voices = engine.getProperty("voices")
            if voices:
                names = [v.name.lower() for v in voices]
                logger.info(f"Available TTS voices: {[v.name for v in voices]}")

                selected = None

                # Try explicit voice_id from config
                if self._voice_id:
                    for v in voices:
                        if self._voice_id.lower() in v.name.lower() or self._voice_id == v.id:
                            selected = v
                            break

                # Try preferred voices in priority order (personality list first, then defaults)
                if not selected:
                    voice_order = self._personality_voices + PREFERRED_VOICES
                    for pref in voice_order:
                        for v in voices:
                            if pref.lower() in v.name.lower():
                                selected = v
                                break
                        if selected:
                            break

                if selected:
                    engine.setProperty("voice", selected.id)
                    logger.info(f"TTS voice: {selected.name}")
                else:
                    logger.info("TTS voice: using system default")

            self.tts_engine = engine
            logger.info("TTS engine ready")

        except ImportError:
            logger.error("pyttsx3 not installed: pip install pyttsx3")
        except Exception as e:
            logger.error(f"TTS init failed: {e}")

    # ── Listening loop ────────────────────────────────────────────────────────

    def start_listening(self, on_command=None, on_status_change=None):
        self._on_command       = on_command
        self._on_status_change = on_status_change
        self._listening = True
        threading.Thread(target=self._listen_loop, daemon=True).start()
        logger.info("Voice listening started — say 'Nexus' to activate")

    def stop_listening(self):
        self._listening = False

    def _listen_loop(self):
        import sounddevice as sd
        while self._listening:
            try:
                self._set_status("listening")
                audio = self._record_until_silence(sd)
                if audio is None or len(audio) < SAMPLE_RATE * MIN_RECORDING_S:
                    continue

                self._set_status("processing")
                text = self._transcribe(audio)
                if not text or len(text.strip()) < 2:
                    continue

                text = text.strip()
                logger.info(f'HEARD: "{text}"')

                if self._wake_word_enabled:
                    text_lower = text.lower()
                    wake_found, wake_end = False, 0

                    for variant in WAKE_WORD_VARIANTS:
                        if variant in text_lower:
                            wake_found = True
                            idx = text_lower.find(variant)
                            wake_end = idx + len(variant)
                            break

                    if not wake_found:
                        first = text_lower.split()[0] if text_lower.split() else ""
                        try:
                            from rapidfuzz import fuzz
                            if fuzz.ratio(first, "nexus") > 60:
                                wake_found = True
                                wake_end = len(first) + 1
                        except ImportError:
                            pass

                    if not wake_found:
                        continue

                    if self._sound_enabled:
                        SoundFX.wake()

                    text = text[wake_end:].strip().lstrip(",.").strip()
                    if not text:
                        if self._on_command:
                            self._on_command("[wake]")
                        continue

                if self._on_command:
                    self._on_command(text)

            except Exception as e:
                logger.error(f"Listen loop error: {e}")
                import time
                time.sleep(1)

    def _record_until_silence(self, sd):
        chunks, silent_chunks, total_chunks = [], 0, 0
        chunk_dur  = 0.1
        chunk_size = int(SAMPLE_RATE * chunk_dur)
        max_silent = int(SILENCE_DURATION / chunk_dur)
        max_chunks = int(30 / chunk_dur)
        peak_rms = 0.0

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype=DTYPE, blocksize=chunk_size) as stream:
            while self._listening and total_chunks < max_chunks:
                data, _ = stream.read(chunk_size)
                chunk = np.frombuffer(data, dtype=np.int16)
                rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                peak_rms = max(peak_rms, rms)
                if rms > SILENCE_THRESHOLD:
                    chunks.append(chunk)
                    silent_chunks = 0
                elif chunks:
                    chunks.append(chunk)
                    silent_chunks += 1
                    if silent_chunks >= max_silent:
                        break
                total_chunks += 1

        return np.concatenate(chunks) if chunks else None

    def _transcribe(self, audio: np.ndarray) -> str:
        if self.whisper_model is None:
            return ""
        audio_f = audio.astype(np.float32) / 32768.0
        result = self.whisper_model.transcribe(audio_f, language="en", fp16=False)
        return result.get("text", "")

    # ── TTS speak ─────────────────────────────────────────────────────────────

    def speak(self, text: str):
        """Speak text using Windows SAPI5 — blocks until done."""
        if not text:
            return
        if self.tts_engine is None:
            print(f"[NEXUS]: {text}")
            return

        if self._sound_enabled:
            SoundFX.speak_start()

        # Strip markdown that sounds weird when spoken
        clean = self._clean_for_speech(text)

        with self._tts_lock:
            try:
                self.tts_engine.say(clean)
                self.tts_engine.runAndWait()
            except RuntimeError:
                try:
                    import pyttsx3
                    self.tts_engine = pyttsx3.init()
                    self.tts_engine.setProperty("rate",   self._voice_rate)
                    self.tts_engine.setProperty("volume", self._voice_volume)
                    self.tts_engine.say(clean)
                    self.tts_engine.runAndWait()
                except Exception as e:
                    logger.error(f"TTS recovery failed: {e}")
            except Exception as e:
                logger.error(f"TTS error: {e}")

    def speak_async(self, text: str):
        threading.Thread(target=self.speak, args=(text,), daemon=True).start()

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """Strip markdown / symbols that sound bad when read aloud."""
        import re
        # Remove markdown code fences
        text = re.sub(r"```[\s\S]*?```", "code block omitted.", text)
        # Remove inline code
        text = re.sub(r"`[^`]+`", "", text)
        # Remove markdown bold/italic
        text = re.sub(r"\*+([^*]+)\*+", r"\1", text)
        # Remove URLs
        text = re.sub(r"https?://\S+", "link", text)
        # Remove emoji-ish unicode blocks (rough)
        text = re.sub(r"[◆►▶◐◓◑◒●📁📄✅❌⚠️🔴⏳🔄⏸️🎬⌨️🧠🖨️📝🎙️📋🌐⏱️⚙️💻🤖👁️]", "", text)
        # Collapse multiple spaces/newlines
        text = re.sub(r"\n+", ". ", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    # ── Utilities ─────────────────────────────────────────────────────────────

    def list_voices(self) -> list[dict]:
        if not self.tts_engine:
            return []
        voices = self.tts_engine.getProperty("voices")
        return [{"id": v.id, "name": v.name} for v in voices]

    def set_voice(self, voice_name: str) -> bool:
        if not self.tts_engine:
            return False
        voices = self.tts_engine.getProperty("voices")
        for v in voices:
            if voice_name.lower() in v.name.lower():
                self.tts_engine.setProperty("voice", v.id)
                logger.info(f"Voice changed to: {v.name}")
                return True
        return False

    def apply_personality(self, personality_data: dict) -> None:
        """Apply voice settings from a personality dict (hot-swap safe)."""
        voice_cfg = personality_data.get("voice", {})
        preferred = voice_cfg.get("preferred_voices", [])
        rate = voice_cfg.get("voice_rate")
        volume = voice_cfg.get("voice_volume")

        if rate is not None:
            self._voice_rate = rate
        if volume is not None:
            self._voice_volume = volume

        if self.tts_engine:
            if rate is not None:
                self.tts_engine.setProperty("rate", rate)
            if volume is not None:
                self.tts_engine.setProperty("volume", volume)

            if preferred:
                voices = self.tts_engine.getProperty("voices") or []
                selected = None
                for pref in preferred:
                    for v in voices:
                        if pref.lower() in v.name.lower():
                            selected = v
                            break
                    if selected:
                        break
                if selected:
                    self.tts_engine.setProperty("voice", selected.id)
                    logger.info(f"Personality voice applied: {selected.name} @ {rate} wpm")

    def set_rate(self, rate: int):
        self._voice_rate = rate
        if self.tts_engine:
            self.tts_engine.setProperty("rate", rate)

    def play_confirm(self):
        if self._sound_enabled:
            SoundFX.confirm()

    def play_alert(self):
        if self._sound_enabled:
            SoundFX.alert()

    def play_error(self):
        if self._sound_enabled:
            SoundFX.error()

    def _set_status(self, status: str):
        if self._on_status_change:
            self._on_status_change(status)

    @property
    def is_available(self) -> bool:
        return self.whisper_model is not None

    @property
    def tts_available(self) -> bool:
        return self.tts_engine is not None
