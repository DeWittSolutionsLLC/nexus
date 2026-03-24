"""Sidebar — JARVIS HUD with arc reactor, arc gauges, and quick actions."""

import threading
import tkinter as tk
import customtkinter as ctk
from datetime import datetime
from ui.theme import COLORS, FONTS, SPACING
from ui.hud_canvas import ArcReactor, ArcGauge


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, plugin_manager, on_quick_action=None):
        super().__init__(parent, fg_color=COLORS["bg_secondary"], width=272, corner_radius=0)
        self.plugin_manager = plugin_manager
        self.on_quick_action = on_quick_action
        self.pack_propagate(False)
        self._sysmon   = None
        self._cpu_gauge = None
        self._ram_gauge = None
        self._dsk_gauge = None
        self._build()
        self._start_clock()
        self._start_stats()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self._build_header()
        self._divider()
        self._build_gauges()
        self._divider()
        self._build_connections()
        self._divider()
        self._build_quick_actions()
        self._build_footer()

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=SPACING["sm"], pady=(SPACING["sm"], 0))

        # Left: arc reactor + title
        left = ctk.CTkFrame(hdr, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)

        title_row = ctk.CTkFrame(left, fg_color="transparent")
        title_row.pack(anchor="w")
        ctk.CTkLabel(
            title_row, text="◆ NEXUS",
            font=("Segoe UI", 20, "bold"),
            text_color=COLORS["accent"],
        ).pack(side="left")

        ctk.CTkLabel(
            left, text="J.A.R.V.I.S.  ·  100% Local  ·  Offline",
            font=("Cascadia Code", 9),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(2, 0))

        self.clock_label = ctk.CTkLabel(
            left, text="",
            font=("Cascadia Code", 10, "bold"),
            text_color=COLORS["accent"],
        )
        self.clock_label.pack(anchor="w")

        # Right: arc reactor
        self._reactor = ArcReactor(hdr, size=76, bg=COLORS["bg_secondary"])
        self._reactor.pack(side="right", padx=(SPACING["xs"], 0))

    def _build_gauges(self):
        ctk.CTkLabel(
            self, text="SYSTEM STATUS",
            font=("Cascadia Code", 9, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["xs"], SPACING["xs"]))

        gauge_row = ctk.CTkFrame(self, fg_color="transparent")
        gauge_row.pack(fill="x", padx=SPACING["sm"], pady=(0, SPACING["xs"]))

        self._cpu_gauge = ArcGauge(gauge_row, label="CPU", color=COLORS["cpu_bar"],
                                   size=72, bg=COLORS["bg_secondary"])
        self._cpu_gauge.pack(side="left", expand=True)

        self._ram_gauge = ArcGauge(gauge_row, label="RAM", color=COLORS["ram_bar"],
                                   size=72, bg=COLORS["bg_secondary"])
        self._ram_gauge.pack(side="left", expand=True)

        self._dsk_gauge = ArcGauge(gauge_row, label="DISK", color=COLORS["disk_bar"],
                                   size=72, bg=COLORS["bg_secondary"])
        self._dsk_gauge.pack(side="left", expand=True)

    def _build_connections(self):
        ctk.CTkLabel(
            self, text="SUBSYSTEMS",
            font=("Cascadia Code", 9, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["xs"], SPACING["xs"]))

        self.connections_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.connections_frame.pack(fill="x", padx=SPACING["sm"])

    def _build_quick_actions(self):
        ctk.CTkLabel(
            self, text="QUICK ACCESS",
            font=("Cascadia Code", 9, "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["xs"], SPACING["xs"]))

        # Scrollable quick actions
        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
            height=220,
        )
        scroll.pack(fill="x", padx=SPACING["xs"], expand=False)

        quick_actions = [
            # Communication
            ("✉  Check Email",           "Check my email inbox"),
            ("💬  WhatsApp",              "List my recent WhatsApp chats"),
            ("🎮  Discord",               "Check my Discord DMs"),
            ("🐙  GitHub",                "Check my GitHub notifications"),
            # Business
            ("🚀  Projects",              "List my projects"),
            ("💰  Invoices",              "List my invoices"),
            ("📋  Write Proposal",        "Write a proposal"),
            ("⏱  Today's Time",          "Today's time"),
            ("🌐  Client Portal",         "Start client portal"),
            ("📝  Expense Summary",       "Expense summary"),
            ("💳  Profit & Loss",         "Profit and loss"),
            # Intelligence
            ("👁  Screen Analysis",       "What's on screen"),
            ("📡  Morning Briefing",      "Run morning routine"),
            ("🤖  Run Macro",             "List macros"),
            ("📰  News Digest",           "Today's news"),
            ("🔬  Research",              "Research a topic"),
            # Productivity
            ("🍅  Start Pomodoro",        "Start pomodoro focus session"),
            ("🎯  Focus Status",          "Focus status"),
            ("✅  Habits Today",          "Today's habits"),
            ("📅  Today's Schedule",      "Today's schedule"),
            # System
            ("⚡  System Stats",          "Get system stats"),
            ("🌤  Weather",               "Get weather"),
            ("🧠  AI Models",             "List models"),
            ("💻  List Scripts",          "List scripts"),
            ("🧹  Clean Temp",            "Clean temp files"),
            # Security & Network
            ("🌐  My IP",                 "My IP address"),
            ("🔐  Gen Password",          "Generate password"),
            # CAD & Print
            ("⚙  CAD Parts",             "List parts"),
            ("🖨  Print Queue",           "Print queue"),
            # Knowledge
            ("📚  My Notes",              "List notes"),
            ("🔍  Query My Docs",         "Query documents"),
            ("🌍  Translate",             "Translate text"),
            # Fun
            ("🌙  Dream Journal",         "List dreams"),
            ("⬛  QR Code",              "List qr codes"),
            # Remote
            ("📱  Phone URL",             "Get web remote URL"),
            ("⌨  Hotkeys",               "List hotkeys"),
        ]

        for label, cmd in quick_actions:
            btn = ctk.CTkButton(
                scroll, text=label,
                font=("Cascadia Code", 10),
                fg_color="transparent",
                hover_color=COLORS["bg_tertiary"],
                text_color=COLORS["text_secondary"],
                anchor="w",
                height=26,
                corner_radius=4,
                command=lambda c=cmd: self._action(c),
            )
            btn.pack(fill="x", padx=2, pady=1)

    def _build_footer(self):
        ctk.CTkFrame(self, fg_color="transparent").pack(fill="both", expand=True)
        self._divider()
        ctk.CTkLabel(
            self,
            text="v2.2  ·  Ollama  ·  Playwright  ·  psutil",
            font=("Cascadia Code", 8),
            text_color=COLORS["text_dim"],
        ).pack(pady=(SPACING["xs"], SPACING["sm"]))

    def _divider(self):
        tk.Frame(self, bg=COLORS["border"], height=1).pack(
            fill="x", padx=SPACING["md"], pady=SPACING["xs"]
        )

    # ── Clock ─────────────────────────────────────────────────────────────────

    def _start_clock(self):
        self._update_clock()

    def _update_clock(self):
        if hasattr(self, "clock_label"):
            now = datetime.now()
            self.clock_label.configure(
                text=now.strftime("%H:%M:%S  ·  %a %d %b")
            )
        self.after(1000, self._update_clock)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def _start_stats(self):
        threading.Thread(target=self._find_sysmon, daemon=True).start()
        self.after(3000, self._update_stats)

    def _find_sysmon(self):
        import time
        for _ in range(30):
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

            if self._cpu_gauge:
                self._cpu_gauge.set_value(cpu)
            if self._ram_gauge:
                self._ram_gauge.set_value(ram)
            if self._dsk_gauge:
                self._dsk_gauge.set_value(disk)
        except Exception:
            pass
        self.after(3000, self._update_stats)

    # ── Connection status ─────────────────────────────────────────────────────

    HIDDEN_PLUGINS = {
        "screen", "file_manager", "system_monitor", "weather_eye",
        "project_manager", "invoice_system", "website_auditor",
        "uptime_monitor", "memory", "llm_router", "print_queue",
        "auto_documenter", "cad_engine", "hotkey_daemon",
        # New background plugins
        "ambient_monitor", "smart_calendar", "local_rag", "jarvis_memory_v2",
        "knowledge_base", "habit_tracker", "expense_tracker",
    }

    def update_status(self):
        for w in self.connections_frame.winfo_children():
            w.destroy()

        for info in self.plugin_manager.get_status_summary():
            if info["name"] in self.HIDDEN_PLUGINS:
                continue
            row = ctk.CTkFrame(self.connections_frame, fg_color="transparent", height=22)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            connected = info["connected"]
            dot_color = COLORS["success"] if connected else COLORS["text_muted"]

            # Pulse dot using tk.Canvas (1 pixel animated dot)
            dot_canvas = tk.Canvas(row, width=10, height=10,
                                   bg=COLORS["bg_secondary"], highlightthickness=0)
            dot_canvas.pack(side="left", padx=(2, 0))
            dot_canvas.create_oval(1, 1, 8, 8, fill=dot_color, outline="")

            ctk.CTkLabel(
                row,
                text=f"{info['icon']} {info['name']}",
                font=("Cascadia Code", 9),
                text_color=COLORS["text_primary"] if connected else COLORS["text_muted"],
            ).pack(side="left", padx=(3, 0))

            ctk.CTkLabel(
                row,
                text=info["status"][:22],
                font=("Cascadia Code", 8),
                text_color=COLORS["success"] if connected else COLORS["error"],
            ).pack(side="right", padx=(0, 4))

    def _action(self, cmd: str):
        if self.on_quick_action:
            self.on_quick_action(cmd)
