"""Chat Panel - Message bubbles + input field + push-to-talk mic button."""

import threading
import customtkinter as ctk
from datetime import datetime
from ui.theme import COLORS, FONTS, SPACING


class ChatPanel(ctk.CTkFrame):
    def __init__(self, parent, on_send=None):
        super().__init__(parent, fg_color=COLORS["bg_primary"], corner_radius=0)
        self.on_send = on_send
        self._voice_engine = None
        self._is_recording = False
        self._build()

    def set_voice_engine(self, voice_engine):
        """Give the chat panel access to the voice engine for push-to-talk."""
        self._voice_engine = voice_engine
        if voice_engine and voice_engine.is_available:
            self.mic_btn.configure(state="normal", fg_color="#EF4444")

    def _build(self):
        # Scrollable chat area
        self.chat_area = ctk.CTkScrollableFrame(
            self, fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
        )
        self.chat_area.pack(fill="both", expand=True, padx=SPACING["md"], pady=(SPACING["md"], 0))

        # Welcome message
        welcome = ctk.CTkFrame(self.chat_area, fg_color=COLORS["bg_tertiary"], corner_radius=12)
        welcome.pack(fill="x", pady=SPACING["md"])
        ctk.CTkLabel(welcome, text="Welcome to Nexus", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["sm"], 0))
        ctk.CTkLabel(
            welcome, font=FONTS["body"], text_color=COLORS["text_secondary"], wraplength=550, justify="left",
            text="Your fully local AI command center is online.\n"
                 "Type a command below or click the red MIC button to speak.\n\n"
                 "Try: \"Check my email\" or \"Good morning\" for a full briefing",
        ).pack(anchor="w", padx=SPACING["md"], pady=(4, SPACING["sm"]))

        # Input bar
        input_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], height=70, corner_radius=12)
        input_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["md"])
        input_frame.pack_propagate(False)

        inner = ctk.CTkFrame(input_frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=SPACING["sm"], pady=SPACING["sm"])

        # Mic button (left side) - red = ready, green = recording, yellow = processing
        self.mic_btn = ctk.CTkButton(
            inner, text="MIC", font=("Segoe UI", 12, "bold"),
            fg_color="#555555", hover_color="#DC2626", text_color="white",
            width=50, height=44, corner_radius=10,
            state="disabled",
            command=self._toggle_recording,
        )
        self.mic_btn.pack(side="left", padx=(0, SPACING["sm"]))

        # Text input (middle)
        self.input_field = ctk.CTkEntry(
            inner, placeholder_text="Type a command or click MIC to speak...",
            font=FONTS["chat_input"], fg_color=COLORS["bg_input"],
            border_color=COLORS["border"], text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"], height=44, corner_radius=10,
        )
        self.input_field.pack(side="left", fill="both", expand=True, padx=(0, SPACING["sm"]))
        self.input_field.bind("<Return>", self._handle_send)

        # Send button (right side)
        ctk.CTkButton(
            inner, text="Send", font=FONTS["body"], fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], text_color="white",
            width=70, height=44, corner_radius=10, command=self._handle_send,
        ).pack(side="right")

    def _toggle_recording(self):
        if not self._voice_engine:
            return
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._is_recording = True
        self.mic_btn.configure(text="REC", fg_color="#22C55E")  # Green = recording
        threading.Thread(target=self._record_audio, daemon=True).start()

    def _stop_recording(self):
        self._is_recording = False

    def _record_audio(self):
        try:
            import sounddevice as sd
            import numpy as np

            SAMPLE_RATE = 16000
            CHUNK_DURATION = 0.1
            CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)
            SILENCE_THRESHOLD = 200
            SILENCE_DURATION = 2.0
            MAX_DURATION = 30

            max_silent = int(SILENCE_DURATION / CHUNK_DURATION)
            max_chunks = int(MAX_DURATION / CHUNK_DURATION)

            chunks = []
            silent_chunks = 0
            total_chunks = 0

            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=CHUNK_SIZE) as stream:
                while self._is_recording and total_chunks < max_chunks:
                    data, _ = stream.read(CHUNK_SIZE)
                    chunk = np.frombuffer(data, dtype=np.int16)
                    rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

                    if rms > SILENCE_THRESHOLD:
                        chunks.append(chunk)
                        silent_chunks = 0
                    elif len(chunks) > 0:
                        chunks.append(chunk)
                        silent_chunks += 1
                        if silent_chunks >= max_silent:
                            break
                    total_chunks += 1

            self._is_recording = False
            self.after(0, lambda: self.mic_btn.configure(text="...", fg_color="#F59E0B"))  # Yellow = processing

            if not chunks or len(chunks) < int(0.5 / CHUNK_DURATION):
                print("[MIC] No speech detected")
                self.after(0, lambda: self.mic_btn.configure(text="MIC", fg_color="#EF4444"))
                return

            audio = np.concatenate(chunks)
            duration = len(audio) / SAMPLE_RATE
            print(f"[MIC] Recorded {duration:.1f}s of audio")

            # Transcribe with Whisper
            audio_float = audio.astype(np.float32) / 32768.0
            result = self._voice_engine.whisper_model.transcribe(
                audio_float, language="en", fp16=False
            )
            text = result.get("text", "").strip()
            print(f"[MIC] Transcribed: \"{text}\"")

            if text and len(text) > 1:
                self.after(0, lambda: self._submit_voice_text(text))
            else:
                print("[MIC] Nothing transcribed")
                self.after(0, lambda: self.mic_btn.configure(text="MIC", fg_color="#EF4444"))

        except Exception as e:
            print(f"[MIC] Error: {e}")
            self.after(0, lambda: self.mic_btn.configure(text="MIC", fg_color="#EF4444"))

    def _submit_voice_text(self, text: str):
        self.mic_btn.configure(text="MIC", fg_color="#EF4444")
        self.input_field.delete(0, "end")
        self.input_field.insert(0, text)
        self._handle_send()

    def _handle_send(self, event=None):
        text = self.input_field.get().strip()
        if not text:
            return
        self.input_field.delete(0, "end")
        self.add_user_message(text)
        if self.on_send:
            self.on_send(text)

    def add_user_message(self, text: str):
        ts = datetime.now().strftime("%H:%M")
        frame = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        frame.pack(fill="x", pady=(SPACING["sm"], 0))
        right = ctk.CTkFrame(frame, fg_color="transparent")
        right.pack(anchor="e")
        ctk.CTkLabel(right, text=ts, font=("Segoe UI", 9), text_color=COLORS["text_muted"]).pack(anchor="e", padx=SPACING["sm"])
        ctk.CTkLabel(right, text=text, font=FONTS["body"], fg_color=COLORS["user_bubble"],
                     text_color="white", corner_radius=12, wraplength=500, justify="left",
                     padx=14, pady=10).pack(anchor="e")
        self._scroll_bottom()

    def add_bot_message(self, text: str):
        ts = datetime.now().strftime("%H:%M")
        frame = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        frame.pack(fill="x", pady=(SPACING["sm"], 0))
        left = ctk.CTkFrame(frame, fg_color="transparent")
        left.pack(anchor="w")
        hdr = ctk.CTkFrame(left, fg_color="transparent")
        hdr.pack(anchor="w", padx=SPACING["sm"])
        ctk.CTkLabel(hdr, text="Nexus", font=("Segoe UI", 10, "bold"), text_color=COLORS["accent"]).pack(side="left")
        ctk.CTkLabel(hdr, text=f"  {ts}", font=("Segoe UI", 9), text_color=COLORS["text_muted"]).pack(side="left")
        ctk.CTkLabel(left, text=text, font=FONTS["body"], fg_color=COLORS["bot_bubble"],
                     text_color=COLORS["text_primary"], corner_radius=12, wraplength=550,
                     justify="left", padx=14, pady=10).pack(anchor="w")
        self._scroll_bottom()

    def add_loading(self):
        self._loading = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        self._loading.pack(fill="x", pady=(SPACING["sm"], 0))
        ctk.CTkLabel(self._loading, text="Thinking...", font=("Segoe UI", 12),
                     text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["sm"])
        self._scroll_bottom()

    def remove_loading(self):
        if hasattr(self, "_loading") and self._loading.winfo_exists():
            self._loading.destroy()

    def _scroll_bottom(self):
        self.chat_area.after(50, lambda: self.chat_area._parent_canvas.yview_moveto(1.0))

    def inject_text(self, text: str):
        self.input_field.delete(0, "end")
        self.input_field.insert(0, text)
        self._handle_send()