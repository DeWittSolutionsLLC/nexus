"""
HUD Canvas — Animated JARVIS Iron Man holographic widgets.

ArcReactor : rotating outer ring, pulsing pentagon core — use in sidebar header
ArcGauge   : circular progress arc (replaces flat progress bars)
ScanLine   : sweeping horizontal scan line overlay
"""

import math
import tkinter as tk


# ─────────────────────────────────────────────────────────────────────────────
# Palette
# ─────────────────────────────────────────────────────────────────────────────
BG      = "#050A18"
CYAN    = "#00D4FF"
CYAN2   = "#00AACC"
CYAN_DIM= "#003344"
GREEN   = "#00FF88"
AMBER   = "#FFB800"
DARK    = "#0A1228"


# ─────────────────────────────────────────────────────────────────────────────
# Arc Reactor
# ─────────────────────────────────────────────────────────────────────────────
class ArcReactor(tk.Canvas):
    """Animated arc reactor ring — drop into any frame."""

    TICK_MS = 33   # ~30 fps

    def __init__(self, parent, size: int = 84, bg: str = BG, **kwargs):
        super().__init__(
            parent,
            width=size, height=size,
            bg=bg, highlightthickness=0,
            **kwargs,
        )
        self.size = size
        self.cx   = size / 2
        self.cy   = size / 2
        self._angle  = 0.0
        self._pulse  = 0.0
        self._running = True
        self.after(self.TICK_MS, self._tick)

    def stop(self):
        self._running = False

    def _tick(self):
        if not self._running:
            return
        self._angle = (self._angle + 3.0) % 360.0
        self._pulse = (self._pulse + 4.0) % 360.0
        self._redraw()
        self.after(self.TICK_MS, self._tick)

    def _redraw(self):
        self.delete("all")
        cx, cy = self.cx, self.cy
        s = self.size
        pf = (math.sin(math.radians(self._pulse)) + 1) / 2   # 0 → 1

        # ── Outer segmented ring (12 rotating dashes) ──
        r_out = s * 0.44
        r_in  = s * 0.37
        for i in range(12):
            ang = math.radians(self._angle + i * 30)
            # Alternating bright/dim segments
            bright = 0.25 + 0.75 * abs(math.sin(ang * 2 + math.radians(self._angle * 0.5)))
            g = int(min(255, 212 * bright))
            b = int(min(255, 255 * bright))
            color = f"#00{g:02x}{b:02x}"
            x1 = cx + r_out * math.cos(ang)
            y1 = cy + r_out * math.sin(ang)
            x2 = cx + r_in  * math.cos(ang)
            y2 = cy + r_in  * math.sin(ang)
            self.create_line(x1, y1, x2, y2, fill=color, width=2, capstyle=tk.ROUND)

        # ── Outer thin ring ──
        ro = s * 0.46
        self.create_oval(cx-ro, cy-ro, cx+ro, cy+ro, outline=CYAN_DIM, width=1)

        # ── Middle ring (pulsing) ──
        rm = s * 0.30 + s * 0.015 * pf
        mid_b = int(100 + 155 * pf)
        mid_color = f"#00{int(mid_b*0.83):02x}{mid_b:02x}"
        self.create_oval(cx-rm, cy-rm, cx+rm, cy+rm, outline=mid_color, width=1)

        # ── Inner pentagon (counter-rotates slowly) ──
        rp = s * 0.185
        pa = -self._angle * 0.25
        pts = []
        for i in range(5):
            ang = math.radians(pa - 90 + i * 72)
            pts += [cx + rp * math.cos(ang), cy + rp * math.sin(ang)]
        pent_b = int(140 + 115 * pf)
        pent_color = f"#00{int(pent_b*0.83):02x}{pent_b:02x}"
        self.create_polygon(pts, outline=pent_color, fill="", width=1)

        # ── Core glow ──
        rc = s * 0.09 + s * 0.025 * pf
        core_b = int(180 + 75 * pf)
        core_color = f"#00{int(core_b * 0.83):02x}{min(255, core_b):02x}"
        self.create_oval(cx-rc, cy-rc, cx+rc, cy+rc, fill=core_color, outline="")

        # ── Soft halo around core ──
        rh = s * 0.14 + s * 0.03 * pf
        halo_b = int(60 + 60 * pf)
        halo_color = f"#00{int(halo_b * 0.83):02x}{min(255, halo_b):02x}"
        self.create_oval(cx-rh, cy-rh, cx+rh, cy+rh, outline=halo_color, width=1)


# ─────────────────────────────────────────────────────────────────────────────
# Arc Gauge  (replaces flat progress bars)
# ─────────────────────────────────────────────────────────────────────────────
class ArcGauge(tk.Canvas):
    """
    Circular arc progress gauge — like Iron Man HUD instrument.

    Usage:
        gauge = ArcGauge(parent, label="CPU", color="#00D4FF", size=72)
        gauge.set_value(0.73)   # 73%
    """

    START_ANGLE = 225   # degrees (bottom-left)
    SWEEP       = 270   # degrees of arc (270 = 3/4 circle)

    def __init__(self, parent, label: str = "", color: str = CYAN,
                 size: int = 72, bg: str = DARK, **kwargs):
        super().__init__(
            parent,
            width=size, height=size,
            bg=bg, highlightthickness=0,
            **kwargs,
        )
        self.size   = size
        self.label  = label
        self.color  = color
        self._value = 0.0   # 0.0 – 1.0
        self._anim_value = 0.0
        self._target = 0.0
        self._draw()

    def set_value(self, value: float):
        """Animate to new value (0.0 – 1.0)."""
        self._target = max(0.0, min(1.0, value))
        self._animate()

    def _animate(self):
        diff = self._target - self._anim_value
        if abs(diff) < 0.005:
            self._anim_value = self._target
            self._draw()
            return
        self._anim_value += diff * 0.18
        self._draw()
        self.after(20, self._animate)

    def _draw(self):
        self.delete("all")
        s   = self.size
        pad = 7
        cx  = s / 2
        cy  = s / 2

        # Background arc
        self.create_arc(
            pad, pad, s - pad, s - pad,
            start=self.START_ANGLE,
            extent=-self.SWEEP,
            style=tk.ARC,
            outline=CYAN_DIM,
            width=4,
        )

        # Value arc
        if self._anim_value > 0.001:
            extent = -self.SWEEP * self._anim_value
            # Color shifts: green → cyan → amber → red
            v = self._anim_value
            if v < 0.5:
                color = self.color
            elif v < 0.8:
                color = AMBER
            else:
                color = "#FF4444"
            self.create_arc(
                pad, pad, s - pad, s - pad,
                start=self.START_ANGLE,
                extent=extent,
                style=tk.ARC,
                outline=color,
                width=4,
            )

        # End cap dot
        if self._anim_value > 0.02:
            end_ang = math.radians(self.START_ANGLE - self.SWEEP * self._anim_value)
            r = (s - 2 * pad) / 2
            ex = cx + r * math.cos(end_ang)
            ey = cy - r * math.sin(end_ang)
            self.create_oval(ex - 3, ey - 3, ex + 3, ey + 3,
                             fill=self.color, outline="")

        # Label text
        pct = int(self._anim_value * 100)
        self.create_text(cx, cy - 5,
                         text=f"{pct}%",
                         fill=CYAN if pct < 80 else "#FF4444",
                         font=("Cascadia Code", 10, "bold"))
        self.create_text(cx, cy + 9,
                         text=self.label,
                         fill="#3A6B85",
                         font=("Cascadia Code", 8))


# ─────────────────────────────────────────────────────────────────────────────
# Scan Line overlay
# ─────────────────────────────────────────────────────────────────────────────
class ScanLine(tk.Canvas):
    """
    A faint horizontal sweep across a region — holographic scan effect.
    Place over any container and it draws a faint moving cyan line.
    """

    def __init__(self, parent, width: int = 400, height: int = 60,
                 bg: str = BG, speed: int = 2, **kwargs):
        super().__init__(
            parent,
            width=width, height=height,
            bg=bg, highlightthickness=0,
            **kwargs,
        )
        self._speed   = speed
        self._y       = 0
        self._running = True
        self.after(30, self._tick)

    def stop(self):
        self._running = False

    def _tick(self):
        if not self._running:
            return
        h = self.winfo_height()
        w = self.winfo_width()
        if h < 1:
            h = self.winfo_reqheight()
        self.delete("scan")
        # Faint trailing glow (3 lines with decreasing opacity via color)
        for offset, color in [(2, "#001A22"), (1, "#003344"), (0, "#005566")]:
            y = (self._y - offset) % max(h, 1)
            self.create_line(0, y, w, y, fill=color, tags="scan")
        self._y = (self._y + self._speed) % max(h, 1)
        self.after(30, self._tick)


# ─────────────────────────────────────────────────────────────────────────────
# Waveform bar (for speaking indicator)
# ─────────────────────────────────────────────────────────────────────────────
class Waveform(tk.Canvas):
    """
    Animated frequency bars — shown when JARVIS is speaking.
    Call .start() / .stop() to control animation.
    """

    BAR_COUNT = 12
    BAR_W     = 3
    GAP       = 2

    def __init__(self, parent, height: int = 28, color: str = CYAN,
                 bg: str = BG, **kwargs):
        total_w = self.BAR_COUNT * (self.BAR_W + self.GAP) + self.GAP
        super().__init__(
            parent,
            width=total_w, height=height,
            bg=bg, highlightthickness=0,
            **kwargs,
        )
        self.h      = height
        self.color  = color
        self._phase = 0.0
        self._active = False
        self._draw_idle()

    def start(self):
        if not self._active:
            self._active = True
            self._tick()

    def stop(self):
        self._active = False
        self._draw_idle()

    def _tick(self):
        if not self._active:
            return
        self._phase += 0.25
        self._draw_active()
        self.after(40, self._tick)

    def _draw_active(self):
        self.delete("all")
        for i in range(self.BAR_COUNT):
            wave = math.sin(self._phase + i * 0.6) * 0.4 + 0.5
            noise = math.sin(self._phase * 1.7 + i * 1.2) * 0.2
            h_frac = max(0.1, min(1.0, wave + noise))
            bar_h = int(self.h * h_frac)
            x1 = self.GAP + i * (self.BAR_W + self.GAP)
            x2 = x1 + self.BAR_W
            y1 = (self.h - bar_h) // 2
            y2 = y1 + bar_h
            self.create_rectangle(x1, y1, x2, y2, fill=self.color, outline="")

    def _draw_idle(self):
        self.delete("all")
        mid = self.h // 2
        for i in range(self.BAR_COUNT):
            x1 = self.GAP + i * (self.BAR_W + self.GAP)
            x2 = x1 + self.BAR_W
            self.create_rectangle(x1, mid - 1, x2, mid + 1,
                                  fill=CYAN_DIM, outline="")
