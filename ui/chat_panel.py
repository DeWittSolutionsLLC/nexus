"""
Chat Panel — JARVIS Iron Man HUD-style message display.

Improvements over v2.0:
  • Bot messages have a left cyan accent bar + header glyph
  • Loading uses a targeting-reticle spinner (◐◓◑◒) not plain dots
  • Input border pulses cyan while JARVIS is processing
  • System messages use a ► prefix and fade-in feel
  • Waveform shown while speaking
"""

import math
import threading
import tkinter as tk
import customtkinter as ctk
from datetime import datetime
from ui.theme import COLORS, FONTS, SPACING
from ui.hud_canvas import Waveform


# Targeting reticle frames
_RETICLE = ["◜ ", " ◝", " ◞", "◟ "]
_SPINNER  = ["◐", "◓", "◑", "◒"]


class ChatPanel(ctk.CTkFrame):
    def __init__(self, parent, on_send=None):
        super().__init__(parent, fg_color=COLORS["bg_primary"], corner_radius=0)
        self.on_send = on_send
        self._voice_engine  = None
        self._is_recording  = False
        self._history: list[str] = []
        self._history_idx   = -1
        self._processing    = False
        self._spinner_idx   = 0
        self._waveform: Waveform | None = None
        self._build()

    def set_voice_engine(self, voice_engine):
        self._voice_engine = voice_engine
        if voice_engine and voice_engine.is_available:
            self.mic_btn.configure(state="normal", fg_color=COLORS["error"])

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Chat area ──
        self.chat_area = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
        )
        self.chat_area.pack(fill="both", expand=True,
                            padx=SPACING["sm"], pady=(SPACING["xs"], 0))

        # ── Thin separator ──
        tk.Frame(self, bg=COLORS["border"], height=1).pack(fill="x",
                                                           padx=SPACING["sm"])

        # ── Input bar ──
        self._input_bar = ctk.CTkFrame(
            self, fg_color=COLORS["bg_secondary"],
            height=72, corner_radius=10,
        )
        self._input_bar.pack(fill="x", padx=SPACING["sm"], pady=SPACING["sm"])
        self._input_bar.pack_propagate(False)

        inner = ctk.CTkFrame(self._input_bar, fg_color="transparent")
        inner.pack(fill="both", expand=True,
                   padx=SPACING["sm"], pady=SPACING["sm"])

        # Mic button
        self.mic_btn = ctk.CTkButton(
            inner, text="🎙",
            font=("Segoe UI", 16),
            fg_color=COLORS["bg_tertiary"],
            hover_color="#CC2222",
            text_color=COLORS["text_muted"],
            width=48, height=46, corner_radius=8,
            state="disabled",
            command=self._toggle_recording,
        )
        self.mic_btn.pack(side="left", padx=(0, SPACING["xs"]))

        # Input field
        self.input_field = ctk.CTkEntry(
            inner,
            placeholder_text="Command interface active, sir...",
            font=("Cascadia Code", 13),
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"],
            height=46,
            corner_radius=8,
        )
        self.input_field.pack(side="left", fill="both", expand=True,
                               padx=(0, SPACING["xs"]))
        self.input_field.bind("<Return>",     self._handle_send)
        self.input_field.bind("<Up>",         self._history_up)
        self.input_field.bind("<Down>",       self._history_down)
        self.input_field.bind("<FocusIn>",    self._on_focus_in)
        self.input_field.bind("<FocusOut>",   self._on_focus_out)

        # Send button
        ctk.CTkButton(
            inner, text="SEND ▶",
            font=("Cascadia Code", 11, "bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"],
            width=78, height=46, corner_radius=8,
            command=self._handle_send,
        ).pack(side="right")

    # ── Input border pulse ────────────────────────────────────────────────────

    def _on_focus_in(self, _=None):
        self.input_field.configure(border_color=COLORS["accent"], border_width=2)

    def _on_focus_out(self, _=None):
        if not self._processing:
            self.input_field.configure(border_color=COLORS["border"], border_width=1)

    def set_processing(self, active: bool):
        """Called by app_window when JARVIS is thinking — pulses input border."""
        self._processing = active
        if active:
            self.input_field.configure(border_color=COLORS["accent"], border_width=2)
            self._pulse_border()
        else:
            self.input_field.configure(border_color=COLORS["border"], border_width=1)

    def _pulse_border(self, step: int = 0):
        if not self._processing:
            return
        # Alternate between accent and accent_dim
        colors = [COLORS["accent"], COLORS["accent_dim"], COLORS["accent"]]
        idx = step % len(colors)
        self.input_field.configure(border_color=colors[idx])
        self.after(350, lambda: self._pulse_border(step + 1))

    # ── Voice ─────────────────────────────────────────────────────────────────

    def _toggle_recording(self):
        if not self._voice_engine:
            return
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._is_recording = True
        self.mic_btn.configure(text="⏹", fg_color=COLORS["success"])
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

            chunks, silent_chunks, total_chunks = [], 0, 0

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
            self.after(0, lambda: self.mic_btn.configure(
                text="⌛", fg_color=COLORS["warning"]
            ))

            if not chunks or len(chunks) < int(0.5 / CHUNK_DURATION):
                self.after(0, lambda: self.mic_btn.configure(
                    text="🎙", fg_color=COLORS["error"]
                ))
                return

            audio = np.concatenate(chunks)
            audio_float = audio.astype(np.float32) / 32768.0
            result = self._voice_engine.whisper_model.transcribe(
                audio_float, language="en", fp16=False
            )
            text = result.get("text", "").strip()

            if text and len(text) > 1:
                self.after(0, lambda t=text: self._submit_voice_text(t))
            else:
                self.after(0, lambda: self.mic_btn.configure(
                    text="🎙", fg_color=COLORS["error"]
                ))

        except Exception as e:
            print(f"[MIC] Error: {e}")
            self.after(0, lambda: self.mic_btn.configure(
                text="🎙", fg_color=COLORS["error"]
            ))

    def _submit_voice_text(self, text: str):
        self.mic_btn.configure(text="🎙", fg_color=COLORS["error"])
        self.input_field.delete(0, "end")
        self.input_field.insert(0, text)
        self._handle_send()

    # ── History navigation ────────────────────────────────────────────────────

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

    # ── Sending ───────────────────────────────────────────────────────────────

    def _handle_send(self, event=None):
        text = self.input_field.get().strip()
        if not text:
            return
        self.input_field.delete(0, "end")
        self._history_idx = -1
        if not self._history or self._history[0] != text:
            self._history.insert(0, text)
            if len(self._history) > 100:
                self._history = self._history[:100]
        self.add_user_message(text)
        if self.on_send:
            self.on_send(text)

    # ── Message display ───────────────────────────────────────────────────────

    def _copy_to_clipboard(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)

    def add_user_message(self, text: str):
        ts = datetime.now().strftime("%H:%M")
        outer = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        outer.pack(fill="x", pady=(SPACING["xs"], 0))

        right = ctk.CTkFrame(outer, fg_color="transparent")
        right.pack(anchor="e")

        # Timestamp + copy button row
        hdr = ctk.CTkFrame(right, fg_color="transparent")
        hdr.pack(anchor="e", padx=SPACING["sm"])
        ctk.CTkLabel(
            hdr, text=f"YOU  {ts}",
            font=("Cascadia Code", 8),
            text_color=COLORS["text_muted"],
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="⧉",
            font=("Segoe UI", 9),
            fg_color="transparent",
            hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_muted"],
            width=20, height=16, corner_radius=4,
            command=lambda t=text: self._copy_to_clipboard(t),
        ).pack(side="left", padx=(4, 0))

        # Bubble with right-side cyan accent bar
        bubble_row = ctk.CTkFrame(right, fg_color="transparent")
        bubble_row.pack(anchor="e")

        ctk.CTkLabel(
            bubble_row, text=text,
            font=("Segoe UI", 13),
            fg_color=COLORS["user_bubble"],
            text_color=COLORS["text_primary"],
            corner_radius=10,
            wraplength=480,
            justify="left",
            padx=14, pady=10,
        ).pack(side="left")

        # Right accent bar
        tk.Frame(bubble_row, bg=COLORS["accent_dim"], width=3).pack(
            side="right", fill="y", padx=(3, 0)
        )

        self._scroll_bottom()

    def add_bot_message(self, text: str, animated: bool = True):
        ts = datetime.now().strftime("%H:%M")
        outer = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        outer.pack(fill="x", pady=(SPACING["sm"], 0))

        # Left row: accent bar + content
        row = ctk.CTkFrame(outer, fg_color="transparent")
        row.pack(anchor="w", fill="x")

        # Left cyan accent bar
        tk.Frame(row, bg=COLORS["accent"], width=3).pack(
            side="left", fill="y", padx=(0, SPACING["xs"])
        )

        content = ctk.CTkFrame(row, fg_color="transparent")
        content.pack(side="left", fill="x", expand=True)

        # Header: ◆ J.A.R.V.I.S  timestamp
        hdr = ctk.CTkFrame(content, fg_color="transparent")
        hdr.pack(anchor="w")
        ctk.CTkLabel(
            hdr, text="◆ J.A.R.V.I.S",
            font=("Cascadia Code", 9, "bold"),
            text_color=COLORS["accent"],
        ).pack(side="left")
        ctk.CTkLabel(
            hdr, text=f"  {ts}",
            font=("Cascadia Code", 8),
            text_color=COLORS["text_muted"],
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="⧉",
            font=("Segoe UI", 9),
            fg_color="transparent",
            hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_muted"],
            width=20, height=16, corner_radius=4,
            command=lambda t=text: self._copy_to_clipboard(t),
        ).pack(side="left", padx=(6, 0))

        # Message bubble
        bubble = ctk.CTkLabel(
            content, text="",
            font=("Segoe UI", 13),
            fg_color=COLORS["bot_bubble"],
            text_color=COLORS["text_primary"],
            corner_radius=10,
            wraplength=560,
            justify="left",
            padx=14, pady=10,
        )
        bubble.pack(anchor="w")

        if animated and len(text) <= 400:
            self._animate_text(bubble, text, 0)
        else:
            bubble.configure(text=text)
            self._scroll_bottom()

    def add_system_message(self, text: str):
        """JARVIS boot / system event — monospace, cyan, ► prefix."""
        frame = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        frame.pack(fill="x", pady=1)
        ctk.CTkLabel(
            frame,
            text=f"►  {text}",
            font=("Cascadia Code", 9),
            fg_color="transparent",
            text_color=COLORS["accent"],
            anchor="w",
            justify="left",
        ).pack(anchor="w", padx=SPACING["md"])
        self._scroll_bottom()

    # ── Loading / spinner ─────────────────────────────────────────────────────

    def add_loading(self):
        self._loading = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        self._loading.pack(fill="x", pady=(SPACING["xs"], 0))

        # Left accent bar
        row = ctk.CTkFrame(self._loading, fg_color="transparent")
        row.pack(anchor="w", fill="x")
        tk.Frame(row, bg=COLORS["accent_dim"], width=3).pack(
            side="left", fill="y", padx=(0, SPACING["xs"])
        )

        self._loading_label = ctk.CTkLabel(
            row,
            text="◐  PROCESSING",
            font=("Cascadia Code", 11, "bold"),
            text_color=COLORS["accent"],
        )
        self._loading_label.pack(side="left", padx=SPACING["xs"])

        self._spinner_idx = 0
        self._animate_spinner()
        self._scroll_bottom()

    def _animate_spinner(self):
        if not hasattr(self, "_loading") or not self._loading.winfo_exists():
            return
        frames = [
            "◐  PROCESSING  ···",
            "◓  PROCESSING  ···",
            "◑  PROCESSING  ···",
            "◒  PROCESSING  ···",
        ]
        self._loading_label.configure(text=frames[self._spinner_idx % 4])
        self._spinner_idx += 1
        self.after(150, self._animate_spinner)

    def remove_loading(self):
        if hasattr(self, "_loading") and self._loading.winfo_exists():
            self._loading.destroy()

    # ── Text animation ────────────────────────────────────────────────────────

    def _animate_text(self, label: ctk.CTkLabel, full_text: str, idx: int):
        if idx <= len(full_text):
            label.configure(text=full_text[:idx])
            self._scroll_bottom()
            if idx < len(full_text):
                ch = full_text[idx] if idx > 0 else ""
                delay = 60 if ch in ".!?" else 30 if ch in ",;:" else 8
                self.after(delay, lambda: self._animate_text(label, full_text, idx + 1))

    def _scroll_bottom(self):
        self.chat_area.after(
            50, lambda: self.chat_area._parent_canvas.yview_moveto(1.0)
        )

    # ── Waveform (speaking indicator) ─────────────────────────────────────────

    def show_waveform(self):
        """Call when JARVIS starts speaking."""
        if self._waveform:
            self._waveform.start()

    def hide_waveform(self):
        """Call when JARVIS stops speaking."""
        if self._waveform:
            self._waveform.stop()

    # ── Utilities ─────────────────────────────────────────────────────────────

    def inject_text(self, text: str):
        self.input_field.delete(0, "end")
        self.input_field.insert(0, text)
        self._handle_send()

    def clear_chat(self):
        for widget in self.chat_area.winfo_children():
            widget.destroy()
