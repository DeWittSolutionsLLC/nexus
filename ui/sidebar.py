"""Sidebar — JARVIS-style system status, live stats, and quick actions."""

import threading
import customtkinter as ctk
from datetime import datetime
from ui.theme import COLORS, FONTS, SPACING


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, plugin_manager, on_quick_action=None):
        super().__init__(parent, fg_color=COLORS["bg_secondary"], width=270, corner_radius=0)
        self.plugin_manager = plugin_manager
        self.on_quick_action = on_quick_action
        self.pack_propagate(False)
        self._sysmon = None
        self._build()
        self._start_clock()
        self._start_stats()

    # ── Build ──────────────────────────────────────────────────

    def _build(self):
        # ── Logo ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"], 0))

        logo_row = ctk.CTkFrame(header, fg_color="transparent")
        logo_row.pack(fill="x")
        ctk.CTkLabel(
            logo_row, text="◆ NEXUS",
            font=("Segoe UI", 22, "bold"),
            text_color=COLORS["accent"],
        ).pack(side="left")
        self.clock_label = ctk.CTkLabel(
            logo_row, text="",
            font=FONTS["mono_small"],
            text_color=COLORS["text_muted"],
        )
        self.clock_label.pack(side="right")

        ctk.CTkLabel(
            header, text="J.A.R.V.I.S.  •  100% Local",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(2, 0))

        self._divider()

        # ── System Stats ──
        ctk.CTkLabel(
            self, text="SYSTEM", font=FONTS["label"],
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=SPACING["md"], pady=(0, SPACING["xs"]))

        self.stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_frame.pack(fill="x", padx=SPACING["md"])
        self._build_stat_row("CPU", "cpu_bar",   "cpu_label",  COLORS["cpu_bar"])
        self._build_stat_row("RAM", "ram_bar",   "ram_label",  COLORS["ram_bar"])
        self._build_stat_row("DSK", "disk_bar",  "disk_label", COLORS["disk_bar"])

        self._divider()

        # ── Connections ──
        ctk.CTkLabel(
            self, text="CONNECTIONS", font=FONTS["label"],
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=SPACING["md"], pady=(0, SPACING["xs"]))

        self.connections_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.connections_frame.pack(fill="x", padx=SPACING["md"])

        self._divider()

        # ── Quick Actions ──
        ctk.CTkLabel(
            self, text="QUICK ACTIONS", font=FONTS["label"],
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=SPACING["md"], pady=(0, SPACING["xs"]))

        quick_actions = [
            ("📧  Check Email",          "Check my email inbox"),
            ("💬  WhatsApp Chats",        "List my recent WhatsApp chats"),
            ("🎮  Discord DMs",           "Check my Discord DMs"),
            ("🐙  GitHub Notifications",  "Check my GitHub notifications"),
            ("🚀  My Projects",           "List my projects"),
            ("💰  Invoices",              "List my invoices"),
            ("⚡  System Stats",          "Get system stats"),
            ("🌤️  Weather",               "Get weather"),
            ("📡  Morning Briefing",      "Good morning"),
            ("🌐  Phone URL",             "Get web remote URL"),
        ]
        for label, cmd in quick_actions:
            ctk.CTkButton(
                self, text=label,
                font=FONTS["small"],
                fg_color="transparent",
                hover_color=COLORS["bg_tertiary"],
                text_color=COLORS["text_secondary"],
                anchor="w",
                height=30,
                corner_radius=6,
                command=lambda c=cmd: self._action(c),
            ).pack(fill="x", padx=SPACING["sm"], pady=1)

        # ── Footer ──
        ctk.CTkFrame(self, fg_color="transparent").pack(fill="both", expand=True)
        ctk.CTkLabel(
            self, text="v2.0 • Ollama + Playwright + psutil",
            font=("Segoe UI", 9),
            text_color=COLORS["text_dim"],
        ).pack(pady=SPACING["sm"])

    def _build_stat_row(self, label: str, bar_attr: str, lbl_attr: str, color: str):
        row = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text=label, font=FONTS["hud"], text_color=COLORS["text_muted"], width=28).pack(side="left")

        bar = ctk.CTkProgressBar(row, height=6, corner_radius=3, progress_color=color, fg_color=COLORS["bg_tertiary"])
        bar.set(0)
        bar.pack(side="left", fill="x", expand=True, padx=(4, 6))
        setattr(self, bar_attr, bar)

        lbl = ctk.CTkLabel(row, text="--", font=FONTS["hud"], text_color=COLORS["text_secondary"], width=40, anchor="e")
        lbl.pack(side="right")
        setattr(self, lbl_attr, lbl)

    def _divider(self):
        ctk.CTkFrame(self, fg_color=COLORS["border"], height=1).pack(fill="x", padx=SPACING["md"], pady=SPACING["sm"])

    # ── Clock ──────────────────────────────────────────────────

    def _start_clock(self):
        self._update_clock()

    def _update_clock(self):
        now = datetime.now().strftime("%H:%M")
        if hasattr(self, "clock_label"):
            self.clock_label.configure(text=now)
        self.after(15000, self._update_clock)

    # ── System stats ───────────────────────────────────────────

    def _start_stats(self):
        threading.Thread(target=self._find_sysmon, daemon=True).start()
        self.after(3000, self._update_stats)

    def _find_sysmon(self):
        """Wait for system_monitor plugin to load and store reference."""
        import time
        for _ in range(20):
            plugin = self.plugin_manager.get_plugin("system_monitor")
            if plugin and plugin.is_connected:
                self._sysmon = plugin
                return
            time.sleep(1)

    def _update_stats(self):
        try:
            import psutil
            cpu  = psutil.cpu_percent(interval=None) / 100
            ram  = psutil.virtual_memory().percent / 100
            disk = psutil.disk_usage("/").percent / 100

            self.cpu_bar.set(cpu)
            self.ram_bar.set(ram)
            self.disk_bar.set(disk)

            self.cpu_label.configure(text=f"{cpu*100:.0f}%")
            self.ram_label.configure(text=f"{ram*100:.0f}%")
            self.disk_label.configure(text=f"{disk*100:.0f}%")
        except Exception:
            pass
        self.after(3000, self._update_stats)

    # ── Connection status ──────────────────────────────────────

    def update_status(self):
        for w in self.connections_frame.winfo_children():
            w.destroy()

        for info in self.plugin_manager.get_status_summary():
            # Hide utility plugins from the connection list
            if info["name"] in ("screen", "file_manager", "system_monitor", "weather_eye",
                                "project_manager", "invoice_system", "website_auditor", "uptime_monitor"):
                continue
            row = ctk.CTkFrame(self.connections_frame, fg_color="transparent", height=26)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            dot_color = COLORS["success"] if info["connected"] else COLORS["text_muted"]
            ctk.CTkLabel(
                row, text="●", font=("Segoe UI", 9),
                text_color=dot_color, width=14,
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=f"{info['icon']} {info['name']}  —  {info['status']}",
                font=FONTS["small"],
                text_color=COLORS["text_primary"] if info["connected"] else COLORS["text_muted"],
            ).pack(side="left", padx=(4, 0))

    def _action(self, cmd: str):
        if self.on_quick_action:
            self.on_quick_action(cmd)
