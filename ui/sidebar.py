"""Sidebar — Plugin status and quick-action buttons."""

import customtkinter as ctk
from ui.theme import COLORS, FONTS, SPACING


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, plugin_manager, on_quick_action=None):
        super().__init__(parent, fg_color=COLORS["bg_secondary"], width=260, corner_radius=0)
        self.plugin_manager = plugin_manager
        self.on_quick_action = on_quick_action
        self.pack_propagate(False)
        self._build()

    def _build(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["lg"], SPACING["sm"]))
        ctk.CTkLabel(header, text="◆ NEXUS", font=("Segoe UI", 22, "bold"),
                     text_color=COLORS["accent"]).pack(anchor="w")
        ctk.CTkLabel(header, text="100% Local • No Cloud • No APIs",
                     font=FONTS["small"], text_color=COLORS["text_muted"]).pack(anchor="w", pady=(2, 0))

        ctk.CTkFrame(self, fg_color=COLORS["border"], height=1).pack(fill="x", padx=SPACING["md"], pady=SPACING["md"])

        # Connections
        ctk.CTkLabel(self, text="CONNECTIONS", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"]).pack(anchor="w", padx=SPACING["md"], pady=(0, SPACING["sm"]))
        self.connections_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.connections_frame.pack(fill="x", padx=SPACING["md"])

        ctk.CTkFrame(self, fg_color=COLORS["border"], height=1).pack(fill="x", padx=SPACING["md"], pady=SPACING["md"])

        # Quick Actions
        ctk.CTkLabel(self, text="QUICK ACTIONS", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"]).pack(anchor="w", padx=SPACING["md"], pady=(0, SPACING["sm"]))

        quick_actions = [
            ("📧 Check Email", "Check my email inbox"),
            ("💬 WhatsApp Chats", "List my recent WhatsApp chats"),
            ("🎮 Discord DMs", "Check my Discord DMs"),
            ("🐙 GitHub Notifs", "Check my GitHub notifications"),
            ("📁 Desktop Files", "List files on my Desktop"),
            ("📊 Daily Summary", "Summarize unread messages across all platforms"),
        ]
        for label, cmd in quick_actions:
            ctk.CTkButton(
                self, text=label, font=FONTS["small"], fg_color="transparent",
                hover_color=COLORS["bg_tertiary"], text_color=COLORS["text_secondary"],
                anchor="w", height=32, command=lambda c=cmd: self._action(c),
            ).pack(fill="x", padx=SPACING["sm"], pady=1)

        # Bottom
        ctk.CTkFrame(self, fg_color="transparent").pack(fill="both", expand=True)
        ctk.CTkLabel(self, text="v1.0.0 • Ollama + Playwright", font=("Segoe UI", 9),
                     text_color=COLORS["text_muted"]).pack(pady=SPACING["sm"])

    def _action(self, cmd):
        if self.on_quick_action:
            self.on_quick_action(cmd)

    def update_status(self):
        for w in self.connections_frame.winfo_children():
            w.destroy()
        for info in self.plugin_manager.get_status_summary():
            row = ctk.CTkFrame(self.connections_frame, fg_color="transparent", height=28)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)
            dot_color = COLORS["success"] if info["connected"] else COLORS["text_muted"]
            ctk.CTkLabel(row, text="●", font=("Segoe UI", 10), text_color=dot_color, width=16).pack(side="left")
            ctk.CTkLabel(
                row, text=f"{info['icon']} {info['name']}  —  {info['status']}",
                font=FONTS["small"],
                text_color=COLORS["text_primary"] if info["connected"] else COLORS["text_muted"],
            ).pack(side="left", padx=(4, 0))
