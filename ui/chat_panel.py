"""Chat Panel — JARVIS-style message display with animated typing and command history."""

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
        self._history: list[str] = []
        self._history_idx = -1
        self._build()

    def set_voice_engine(self, voice_engine):
        self._voice_engine = voice_engine
        if voice_engine and voice_engine.is_available:
            self.mic_btn.configure(state="normal", fg_color=COLORS["error"])

    def _build(self):
        # Chat area
        self.chat_area = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
        )
        self.chat_area.pack(fill="both", expand=True, padx=SPACING["md"], pady=(SPACING["sm"], 0))

        # Input bar
        input_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], height=70, corner_radius=12)
        input_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["md"])
        input_frame.pack_propagate(False)

        inner = ctk.CTkFrame(input_frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=SPACING["sm"], pady=SPACING["sm"])

        # Mic button
        self.mic_btn = ctk.CTkButton(
            inner, text="MIC", font=("Segoe UI", 11, "bold"),
            fg_color="#333333", hover_color="#CC2222", text_color="white",
            width=52, height=44, corner_radius=10,
            state="disabled",
            command=self._toggle_recording,
        )
        self.mic_btn.pack(side="left", padx=(0, SPACING["sm"]))

        # Text input
        self.input_field = ctk.CTkEntry(
            inner,
            placeholder_text="Enter command or query, sir...",
            font=FONTS["chat_input"],
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"],
            height=44,
            corner_radius=10,
        )
        self.input_field.pack(side="left", fill="both", expand=True, padx=(0, SPACING["sm"]))
        self.input_field.bind("<Return>", self._handle_send)
        self.input_field.bind("<Up>",     self._history_up)
        self.input_field.bind("<Down>",   self._history_down)

        # Send button
        ctk.CTkButton(
            inner, text="Send",
            font=("Segoe UI", 12, "bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"],
            width=70, height=44, corner_radius=10,
            command=self._handle_send,
        ).pack(side="right")

    # ── Voice ─────────────────────────────────────────────────

    def _toggle_recording(self):
        if not self._voice_engine:
            return
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._is_recording = True
        self.mic_btn.configure(text="● REC", fg_color=COLORS["success"])
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
                    elif chunks:
                        chunks.append(chunk)
                        silent_chunks += 1
                        if silent_chunks >= max_silent:
                            break
                    total_chunks += 1

            self._is_recording = False
            self.after(0, lambda: self.mic_btn.configure(text="...", fg_color=COLORS["warning"]))

            if not chunks or len(chunks) < int(0.5 / CHUNK_DURATION):
                self.after(0, lambda: self.mic_btn.configure(text="MIC", fg_color=COLORS["error"]))
                return

            audio = np.concatenate(chunks)
            audio_float = audio.astype(np.float32) / 32768.0
            result = self._voice_engine.whisper_model.transcribe(audio_float, language="en", fp16=False)
            text = result.get("text", "").strip()

            if text and len(text) > 1:
                self.after(0, lambda t=text: self._submit_voice_text(t))
            else:
                self.after(0, lambda: self.mic_btn.configure(text="MIC", fg_color=COLORS["error"]))

        except Exception as e:
            print(f"[MIC] Error: {e}")
            self.after(0, lambda: self.mic_btn.configure(text="MIC", fg_color=COLORS["error"]))

    def _submit_voice_text(self, text: str):
        self.mic_btn.configure(text="MIC", fg_color=COLORS["error"])
        self.input_field.delete(0, "end")
        self.input_field.insert(0, text)
        self._handle_send()

    # ── History navigation ─────────────────────────────────────

    def _history_up(self, event=None):
        if not self._history:
            return
        self._history_idx = min(self._history_idx + 1, len(self._history) - 1)
        self._fill_from_history()

    def _history_down(self, event=None):
        if self._history_idx <= 0:
            self._history_idx = -1
            self.input_field.delete(0, "end")
            return
        self._history_idx -= 1
        self._fill_from_history()

    def _fill_from_history(self):
        if 0 <= self._history_idx < len(self._history):
            self.input_field.delete(0, "end")
            self.input_field.insert(0, self._history[self._history_idx])

    # ── Sending ────────────────────────────────────────────────

    def _handle_send(self, event=None):
        text = self.input_field.get().strip()
        if not text:
            return
        self.input_field.delete(0, "end")
        self._history_idx = -1
        # Prepend to history (most recent first)
        if not self._history or self._history[0] != text:
            self._history.insert(0, text)
            if len(self._history) > 100:
                self._history = self._history[:100]
        self.add_user_message(text)
        if self.on_send:
            self.on_send(text)

    # ── Message display ────────────────────────────────────────

    def add_user_message(self, text: str):
        ts = datetime.now().strftime("%H:%M")
        frame = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        frame.pack(fill="x", pady=(SPACING["sm"], 0))
        right = ctk.CTkFrame(frame, fg_color="transparent")
        right.pack(anchor="e")
        ctk.CTkLabel(
            right, text=ts, font=("Segoe UI", 9),
            text_color=COLORS["text_muted"],
        ).pack(anchor="e", padx=SPACING["sm"])
        ctk.CTkLabel(
            right, text=text,
            font=FONTS["body"],
            fg_color=COLORS["user_bubble"],
            text_color=COLORS["text_primary"],
            corner_radius=12,
            wraplength=500,
            justify="left",
            padx=14, pady=10,
        ).pack(anchor="e")
        self._scroll_bottom()

    def add_bot_message(self, text: str, animated: bool = True):
        """Add a JARVIS-style bot message, optionally with typing animation."""
        ts = datetime.now().strftime("%H:%M")
        frame = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        frame.pack(fill="x", pady=(SPACING["sm"], 0))
        left = ctk.CTkFrame(frame, fg_color="transparent")
        left.pack(anchor="w")

        # Header row: ◆ NEXUS  HH:MM
        hdr = ctk.CTkFrame(left, fg_color="transparent")
        hdr.pack(anchor="w", padx=SPACING["sm"])
        ctk.CTkLabel(
            hdr, text="◆ NEXUS", font=("Segoe UI", 10, "bold"),
            text_color=COLORS["accent"],
        ).pack(side="left")
        ctk.CTkLabel(
            hdr, text=f"  {ts}", font=("Segoe UI", 9),
            text_color=COLORS["text_muted"],
        ).pack(side="left")

        # Message bubble
        bubble = ctk.CTkLabel(
            left, text="",
            font=FONTS["body"],
            fg_color=COLORS["bot_bubble"],
            text_color=COLORS["text_primary"],
            corner_radius=12,
            wraplength=570,
            justify="left",
            padx=14, pady=10,
        )
        bubble.pack(anchor="w")

        # Animate short messages; display long messages instantly
        if animated and len(text) <= 300:
            self._animate_text(bubble, text, 0)
        else:
            bubble.configure(text=text)
            self._scroll_bottom()

    def add_system_message(self, text: str):
        """JARVIS boot / system message — monospace cyan style."""
        frame = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        frame.pack(fill="x", pady=1)
        ctk.CTkLabel(
            frame, text=text,
            font=FONTS["mono_small"],
            fg_color="transparent",
            text_color=COLORS["accent"],
            anchor="w",
            justify="left",
        ).pack(anchor="w", padx=SPACING["md"])
        self._scroll_bottom()

    def add_loading(self):
        self._loading = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        self._loading.pack(fill="x", pady=(SPACING["sm"], 0))
        self._loading_label = ctk.CTkLabel(
            self._loading,
            text="◆ Analyzing",
            font=("Segoe UI", 12),
            text_color=COLORS["accent"],
        )
        self._loading_label.pack(anchor="w", padx=SPACING["sm"])
        self._loading_dots = 0
        self._animate_loading()
        self._scroll_bottom()

    def _animate_loading(self):
        if not hasattr(self, "_loading") or not self._loading.winfo_exists():
            return
        dots = "." * (self._loading_dots % 4)
        self._loading_label.configure(text=f"◆ Analyzing{dots}")
        self._loading_dots += 1
        self.after(400, self._animate_loading)

    def remove_loading(self):
        if hasattr(self, "_loading") and self._loading.winfo_exists():
            self._loading.destroy()

    def _animate_text(self, label: ctk.CTkLabel, full_text: str, idx: int):
        if idx <= len(full_text):
            label.configure(text=full_text[:idx])
            self._scroll_bottom()
            if idx < len(full_text):
                ch = full_text[idx] if idx > 0 else ""
                delay = 80 if ch in ".!?" else 40 if ch in ",;:" else 12
                self.after(delay, lambda: self._animate_text(label, full_text, idx + 1))

    def _scroll_bottom(self):
        self.chat_area.after(50, lambda: self.chat_area._parent_canvas.yview_moveto(1.0))

    def inject_text(self, text: str):
        self.input_field.delete(0, "end")
        self.input_field.insert(0, text)
        self._handle_send()

    def clear_chat(self):
        for widget in self.chat_area.winfo_children():
            widget.destroy()
