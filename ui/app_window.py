"""App Window — JARVIS-style AI Command Center with tabs and live HUD."""

import asyncio
import threading
import logging
from datetime import datetime
import customtkinter as ctk
from ui.theme import COLORS, FONTS, SPACING
from ui.chat_panel import ChatPanel
from ui.sidebar import Sidebar

logger = logging.getLogger("nexus.ui")


class AppWindow:
    def __init__(self, plugin_manager, assistant, scheduler, browser_engine):
        self.plugin_manager = plugin_manager
        self.assistant = assistant
        self.scheduler = scheduler
        self.browser_engine = browser_engine
        self.voice_engine = None

        self.loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        # Expose loop on assistant so web_remote can find it
        if assistant:
            assistant._remote_loop = self.loop

        self._setup_window()
        self._build_layout()

    # ── Window setup ───────────────────────────────────────────

    def _setup_window(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.root = ctk.CTk()
        self.root.title("NEXUS  —  J.A.R.V.I.S. Command Center")
        self.root.geometry("1200x760")
        self.root.minsize(950, 620)
        self.root.configure(fg_color=COLORS["bg_primary"])

        # Keyboard shortcuts
        self.root.bind("<Control-l>", lambda e: self._trigger_voice())
        self.root.bind("<Control-k>", lambda e: self._clear_chat())
        self.root.bind("<Escape>",    lambda e: self.chat.input_field.focus_set())

    def _build_layout(self):
        self._build_header()
        self._build_tabs()
        self._build_statusbar()

    # ── Header ─────────────────────────────────────────────────

    def _build_header(self):
        header = ctk.CTkFrame(self.root, fg_color=COLORS["bg_secondary"], height=52, corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["xs"])

        # Left: Logo
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text="◆", font=("Segoe UI", 20, "bold"), text_color=COLORS["accent"]).pack(side="left")
        ctk.CTkLabel(left, text=" NEXUS", font=("Segoe UI", 18, "bold"), text_color=COLORS["text_primary"]).pack(side="left")
        ctk.CTkLabel(left, text="  J.A.R.V.I.S.", font=("Segoe UI", 11), text_color=COLORS["text_muted"]).pack(side="left")

        # Right: model + status indicator
        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="right")

        self.status_dot = ctk.CTkLabel(right, text="●", font=("Segoe UI", 12), text_color=COLORS["warning"])
        self.status_dot.pack(side="right", padx=(4, 0))

        model = self.assistant.model if self.assistant else "offline"
        self.model_label = ctk.CTkLabel(
            right, text=f"Ollama  {model}",
            font=FONTS["hud"],
            text_color=COLORS["text_muted"],
        )
        self.model_label.pack(side="right", padx=(0, SPACING["sm"]))

    # ── Tabs ───────────────────────────────────────────────────

    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(
            self.root,
            fg_color=COLORS["bg_primary"],
            segmented_button_fg_color=COLORS["bg_secondary"],
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_selected_hover_color=COLORS["accent_hover"],
            segmented_button_unselected_color=COLORS["bg_secondary"],
            segmented_button_unselected_hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_primary"],
            text_color_disabled=COLORS["text_muted"],
        )
        self.tabview.pack(fill="both", expand=True)
        self.tabview.add("  COMMAND  ")
        self.tabview.add("  PROJECTS  ")
        self.tabview.add("  INTELLIGENCE  ")
        self.tabview.add("  MONITOR  ")

        self._build_command_tab()
        self._build_projects_tab()
        self._build_intelligence_tab()
        self._build_monitor_tab()

    def _build_command_tab(self):
        tab = self.tabview.tab("  COMMAND  ")
        tab.configure(fg_color=COLORS["bg_primary"])

        # Sidebar | divider | Chat
        self.sidebar = Sidebar(tab, self.plugin_manager, on_quick_action=self._on_quick_action)
        self.sidebar.pack(side="left", fill="y")

        ctk.CTkFrame(tab, fg_color=COLORS["border"], width=1).pack(side="left", fill="y")

        self.chat = ChatPanel(tab, on_send=self._on_user_send)
        self.chat.pack(side="right", fill="both", expand=True)

    def _build_projects_tab(self):
        tab = self.tabview.tab("  PROJECTS  ")
        tab.configure(fg_color=COLORS["bg_primary"])

        # Toolbar
        toolbar = ctk.CTkFrame(tab, fg_color=COLORS["bg_secondary"], height=48, corner_radius=0)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        inner = ctk.CTkFrame(toolbar, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["xs"])

        ctk.CTkLabel(inner, text="🚀 PROJECT MANAGER", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(side="left")

        ctk.CTkButton(inner, text="+ New Project", font=FONTS["small"],
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color=COLORS["bg_primary"], width=110, height=30,
                      command=self._new_project_dialog).pack(side="right")

        ctk.CTkButton(inner, text="↻ Refresh", font=FONTS["small"],
                      fg_color="transparent", hover_color=COLORS["bg_tertiary"],
                      text_color=COLORS["text_secondary"], width=80, height=30,
                      command=self._refresh_projects).pack(side="right", padx=(0, SPACING["sm"]))

        # Stats bar
        self.project_stats_frame = ctk.CTkFrame(tab, fg_color=COLORS["bg_tertiary"], height=36, corner_radius=0)
        self.project_stats_frame.pack(fill="x")
        self.project_stats_label = ctk.CTkLabel(
            self.project_stats_frame, text="",
            font=FONTS["small"], text_color=COLORS["text_secondary"],
        )
        self.project_stats_label.pack(anchor="w", padx=SPACING["md"], pady=SPACING["xs"])

        # Project list
        self.projects_scroll = ctk.CTkScrollableFrame(
            tab, fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
        )
        self.projects_scroll.pack(fill="both", expand=True)
        self.projects_content = ctk.CTkLabel(
            self.projects_scroll, text="Loading projects...",
            font=FONTS["body"], text_color=COLORS["text_muted"],
        )
        self.projects_content.pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")

    def _build_intelligence_tab(self):
        tab = self.tabview.tab("  INTELLIGENCE  ")
        tab.configure(fg_color=COLORS["bg_primary"])

        # Split: left = leads, right = website auditor
        panes = ctk.CTkFrame(tab, fg_color="transparent")
        panes.pack(fill="both", expand=True)

        # Left: Leads
        left_panel = ctk.CTkFrame(panes, fg_color=COLORS["bg_secondary"], corner_radius=8)
        left_panel.pack(side="left", fill="both", expand=True, padx=(SPACING["md"], SPACING["sm"]), pady=SPACING["md"])

        ctk.CTkLabel(left_panel, text="🎯  LEAD FINDER", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        ctk.CTkLabel(left_panel, text="Find businesses without websites via Google Maps.",
                     font=FONTS["small"], text_color=COLORS["text_muted"]).pack(anchor="w", padx=SPACING["md"])

        inp_row = ctk.CTkFrame(left_panel, fg_color="transparent")
        inp_row.pack(fill="x", padx=SPACING["md"], pady=SPACING["sm"])
        self.lead_city_entry = ctk.CTkEntry(inp_row, placeholder_text="City (e.g. Manchester)",
                                            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
                                            text_color=COLORS["text_primary"], height=36, corner_radius=8)
        self.lead_city_entry.pack(side="left", fill="x", expand=True, padx=(0, SPACING["sm"]))
        self.lead_industry_entry = ctk.CTkEntry(inp_row, placeholder_text="Industry (e.g. plumbers)",
                                                fg_color=COLORS["bg_input"], border_color=COLORS["border"],
                                                text_color=COLORS["text_primary"], height=36, corner_radius=8, width=120)
        self.lead_industry_entry.pack(side="left", padx=(0, SPACING["sm"]))
        ctk.CTkButton(inp_row, text="Search", font=FONTS["small"], fg_color=COLORS["accent"],
                      hover_color=COLORS["accent_hover"], text_color=COLORS["bg_primary"],
                      width=70, height=36, command=self._run_lead_search).pack(side="right")

        self.leads_result = ctk.CTkScrollableFrame(left_panel, fg_color="transparent",
                                                    scrollbar_button_color=COLORS["bg_tertiary"])
        self.leads_result.pack(fill="both", expand=True, padx=SPACING["sm"], pady=SPACING["sm"])
        ctk.CTkLabel(self.leads_result, text="Enter a city and industry to find leads, sir.",
                     font=FONTS["small"], text_color=COLORS["text_muted"]).pack(anchor="w")

        # Right: Website Auditor
        right_panel = ctk.CTkFrame(panes, fg_color=COLORS["bg_secondary"], corner_radius=8)
        right_panel.pack(side="right", fill="both", expand=True, padx=(0, SPACING["md"]), pady=SPACING["md"])

        ctk.CTkLabel(right_panel, text="🔍  WEBSITE AUDITOR", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        audit_row = ctk.CTkFrame(right_panel, fg_color="transparent")
        audit_row.pack(fill="x", padx=SPACING["md"], pady=SPACING["sm"])
        self.audit_url_entry = ctk.CTkEntry(audit_row, placeholder_text="https://example.com",
                                            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
                                            text_color=COLORS["text_primary"], height=36, corner_radius=8)
        self.audit_url_entry.pack(side="left", fill="x", expand=True, padx=(0, SPACING["sm"]))
        ctk.CTkButton(audit_row, text="Audit", font=FONTS["small"], fg_color=COLORS["accent"],
                      hover_color=COLORS["accent_hover"], text_color=COLORS["bg_primary"],
                      width=70, height=36, command=self._run_audit).pack(side="right")

        self.audit_result = ctk.CTkScrollableFrame(right_panel, fg_color="transparent",
                                                    scrollbar_button_color=COLORS["bg_tertiary"])
        self.audit_result.pack(fill="both", expand=True, padx=SPACING["sm"], pady=SPACING["sm"])
        self.audit_result_label = ctk.CTkLabel(self.audit_result,
                                               text="Enter a URL to analyze SEO, speed, SSL, and more.",
                                               font=FONTS["small"], text_color=COLORS["text_muted"],
                                               wraplength=380, justify="left")
        self.audit_result_label.pack(anchor="w")

    def _build_monitor_tab(self):
        tab = self.tabview.tab("  MONITOR  ")
        tab.configure(fg_color=COLORS["bg_primary"])

        panes = ctk.CTkFrame(tab, fg_color="transparent")
        panes.pack(fill="both", expand=True)

        # Left: System stats
        sys_panel = ctk.CTkFrame(panes, fg_color=COLORS["bg_secondary"], corner_radius=8)
        sys_panel.pack(side="left", fill="both", expand=True, padx=(SPACING["md"], SPACING["sm"]), pady=SPACING["md"])

        hdr = ctk.CTkFrame(sys_panel, fg_color="transparent")
        hdr.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))
        ctk.CTkLabel(hdr, text="⚡  SYSTEM MONITOR", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(side="left")
        ctk.CTkButton(hdr, text="↻", font=FONTS["small"], fg_color=COLORS["bg_tertiary"],
                      hover_color=COLORS["border"], text_color=COLORS["accent"],
                      width=28, height=28, command=self._refresh_system_stats).pack(side="right")

        self.sys_stats_label = ctk.CTkLabel(
            sys_panel, text="Refreshing system stats...",
            font=FONTS["mono_small"],
            text_color=COLORS["text_secondary"],
            justify="left",
            anchor="nw",
        )
        self.sys_stats_label.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["sm"])

        # Right: Uptime monitor
        uptime_panel = ctk.CTkFrame(panes, fg_color=COLORS["bg_secondary"], corner_radius=8)
        uptime_panel.pack(side="right", fill="both", expand=True, padx=(0, SPACING["md"]), pady=SPACING["md"])

        uhdr = ctk.CTkFrame(uptime_panel, fg_color="transparent")
        uhdr.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))
        ctk.CTkLabel(uhdr, text="🛡️  UPTIME MONITOR", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(side="left")
        ctk.CTkButton(uhdr, text="Check All", font=FONTS["small"], fg_color=COLORS["accent"],
                      hover_color=COLORS["accent_hover"], text_color=COLORS["bg_primary"],
                      width=80, height=28, command=self._check_uptime).pack(side="right")

        add_row = ctk.CTkFrame(uptime_panel, fg_color="transparent")
        add_row.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["sm"]))
        self.uptime_url_entry = ctk.CTkEntry(add_row, placeholder_text="https://client-site.com",
                                             fg_color=COLORS["bg_input"], border_color=COLORS["border"],
                                             text_color=COLORS["text_primary"], height=32, corner_radius=8)
        self.uptime_url_entry.pack(side="left", fill="x", expand=True, padx=(0, SPACING["xs"]))
        self.uptime_name_entry = ctk.CTkEntry(add_row, placeholder_text="Name",
                                              fg_color=COLORS["bg_input"], border_color=COLORS["border"],
                                              text_color=COLORS["text_primary"], height=32, corner_radius=8, width=90)
        self.uptime_name_entry.pack(side="left", padx=(0, SPACING["xs"]))
        ctk.CTkButton(add_row, text="+ Add", font=FONTS["small"], fg_color=COLORS["bg_tertiary"],
                      hover_color=COLORS["accent_dim"], text_color=COLORS["accent"],
                      width=55, height=32, command=self._add_uptime_site).pack(side="right")

        self.uptime_scroll = ctk.CTkScrollableFrame(uptime_panel, fg_color="transparent",
                                                     scrollbar_button_color=COLORS["bg_tertiary"])
        self.uptime_scroll.pack(fill="both", expand=True, padx=SPACING["sm"], pady=SPACING["sm"])
        self.uptime_content = ctk.CTkLabel(self.uptime_scroll,
                                           text="No sites monitored yet.\nAdd a client site above, sir.",
                                           font=FONTS["small"], text_color=COLORS["text_muted"], justify="left")
        self.uptime_content.pack(anchor="w")

    # ── Status bar ─────────────────────────────────────────────

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self.root, fg_color=COLORS["bg_secondary"], height=26, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=SPACING["md"])

        self.status_label = ctk.CTkLabel(
            inner, text="Initializing systems...",
            font=FONTS["hud"], text_color=COLORS["text_muted"],
        )
        self.status_label.pack(side="left")

        ctk.CTkLabel(
            inner, text="Ctrl+L: Voice  •  Ctrl+K: Clear  •  ↑↓: History",
            font=FONTS["hud"], text_color=COLORS["text_dim"],
        ).pack(side="right")

    def _set_status(self, text: str):
        self.root.after(0, lambda: self.status_label.configure(text=text))

    # ── Event handlers ─────────────────────────────────────────

    def _on_user_send(self, text: str):
        self.chat.add_loading()
        self.chat.set_processing(True)
        self._set_status(f"Processing: {text[:60]}...")
        asyncio.run_coroutine_threadsafe(self._process_command(text), self.loop)

    def _on_quick_action(self, cmd: str):
        self.chat.inject_text(cmd)

    def _trigger_voice(self):
        if hasattr(self, "chat"):
            self.chat._toggle_recording()

    def _clear_chat(self):
        if hasattr(self, "chat"):
            self.chat.clear_chat()
            self.chat.add_system_message("[NEXUS] Chat cleared. All systems nominal.")

    # ── Command processing ─────────────────────────────────────

    async def _process_command(self, text: str):
        try:
            capabilities = self.plugin_manager.get_all_capabilities()
            result = await self.assistant.process_input(text, capabilities)
            rtype = result.get("type", "conversation")
            speak_text = result.get("speak", "")

            if rtype == "conversation":
                msg = result.get("message", "I'm not sure how to help with that, sir.")
                self._reply(msg, speak_text or msg[:200])
                self._set_status("Ready")

            elif rtype == "action":
                explanation = result.get("explanation", "Processing...")
                self._reply(f">> {explanation}", speak_text, animated=False)
                plugin = self.plugin_manager.get_plugin(result.get("plugin", ""))
                if plugin and plugin.is_connected:
                    self._set_status(f"Executing: {result.get('plugin')} → {result.get('action')}")
                    out = await plugin.execute(result["action"], result.get("params", {}))
                    short = out[:150].split("\n")[0] if out else "Done."
                    if self.voice_engine and hasattr(self.voice_engine, "play_confirm"):
                        self.voice_engine.play_confirm()
                    self._reply(out, short)
                    self._set_status("Ready")
                elif plugin:
                    self._reply(f"Warning: {plugin.name} isn't connected, sir. Check sidebar.")
                    self._set_status("Ready")
                else:
                    self._reply(f"Plugin '{result.get('plugin')}' not found in active systems, sir.")
                    self._set_status("Ready")

            elif rtype == "multi_action":
                self._reply(f">> {result.get('explanation', 'Executing sequence...')}", speak_text, animated=False)
                steps = result.get("steps", [])
                for i, step in enumerate(steps, 1):
                    plugin = self.plugin_manager.get_plugin(step.get("plugin", ""))
                    if plugin and plugin.is_connected:
                        self._set_status(f"Step {i}/{len(steps)}: {step.get('plugin')} → {step.get('action')}")
                        out = await plugin.execute(step["action"], step.get("params", {}))
                        self._reply(f"Step {i}: {out}", animated=False)
                self._set_status("Ready")

            elif rtype == "schedule":
                task_id = self.scheduler.add_task(
                    result.get("explanation", "Task"),
                    result.get("cron", ""),
                    result.get("actions", []),
                )
                self._reply(
                    f"Scheduled: {result.get('explanation')}\nCron: {result.get('cron')}\nID: {task_id}",
                    speak_text,
                )
                self._set_status("Ready")

            elif rtype == "error":
                self._reply(f"Error: {result.get('message', 'Unknown error')}")
                self._set_status("Error — ready")

        except Exception as e:
            logger.error(f"Process error: {e}", exc_info=True)
            self._reply(f"I encountered an error, sir: {str(e)[:100]}")
            self._set_status("Error — ready")

    def _reply(self, message: str, speak: str = "", animated: bool = True):
        self.root.after(0, lambda: (
            self.chat.remove_loading(),
            self.chat.set_processing(False),
            self.chat.add_bot_message(message, animated=animated),
        ))
        if speak and self.voice_engine:
            self.root.after(0, self.chat.show_waveform)
            def _speak_and_hide():
                self.voice_engine.speak(speak)
                self.root.after(0, self.chat.hide_waveform)
            threading.Thread(target=_speak_and_hide, daemon=True).start()

    # ── Startup ────────────────────────────────────────────────

    async def _startup(self):
        boot_seq = [
            (0.00, "NEXUS v2.1 — J.A.R.V.I.S. Command Core"),
            (0.08, "Initializing neural interface...                [  0%]"),
            (0.12, "Loading Ollama language model...                [ 10%]"),
            (0.16, "Mounting plugin subsystems...                   [ 20%]"),
            (0.20, "Calibrating holographic HUD...                  [ 30%]"),
            (0.24, "Activating arc reactor animation...             [ 40%]"),
            (0.28, "Launching persistent browser context...         [ 50%]"),
        ]
        for delay, msg in boot_seq:
            await asyncio.sleep(delay)
            self.root.after(0, lambda m=msg: self.chat.add_system_message(m))

        try:
            await self.browser_engine.start()
            self.root.after(0, lambda: self.chat.add_system_message(
                "Browser context established.                    [ 60%]  ✓"
            ))
        except Exception as e:
            self.root.after(0, lambda: self.chat.add_system_message(
                f"Browser warning: {str(e)[:50]}  — continuing..."
            ))

        self.root.after(0, lambda: self.chat.add_system_message(
            "Connecting all subsystems...                    [ 70%]"
        ))
        total = len(self.plugin_manager.plugins)
        connected_so_far = [0]

        def _on_plugin():
            connected_so_far[0] += 1
            pct = 70 + int(connected_so_far[0] / max(total, 1) * 28)
            self.root.after(0, self.sidebar.update_status)

        await self.plugin_manager.connect_all(on_plugin_connected=_on_plugin)

        plugin_count = sum(1 for p in self.plugin_manager.plugins.values() if p.is_connected)
        self.root.after(0, lambda: self.chat.add_system_message(
            f"Subsystems online: {plugin_count}/{total}              [ 98%]  ✓"
        ))
        await asyncio.sleep(0.1)
        self.root.after(0, lambda: self.chat.add_system_message(
            "All systems nominal.                            [100%]  ✓"
        ))

        self.root.after(0, self.sidebar.update_status)
        self.root.after(0, self._wire_voice)
        self.root.after(0, self._update_status_dot)
        self.root.after(0, self._post_boot_message)
        self.root.after(500, self._refresh_system_stats)
        self.root.after(1000, self._refresh_projects)
        self.root.after(1500, self._refresh_uptime_display)

        self._set_status(f"All systems online — {plugin_count} plugins active")

    def _post_boot_message(self):
        now = datetime.now()
        hour = now.hour
        greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        day_str = now.strftime("%A, %B %d")
        time_str = now.strftime("%H:%M")

        model = self.assistant.model if self.assistant else "unknown"
        ollama_ok = self.assistant.client is not None

        lines = [
            f"{greeting}, sir. It is {time_str} on {day_str}.",
            f"",
            f"All systems are online and operating normally.",
            f"Neural core: {'✓ ' + model if ollama_ok else '⚠ Ollama offline — keyword routing active'}",
            f"",
            f"Say 'good morning' for a full briefing, or enter any command below.",
        ]
        self.chat.add_bot_message("\n".join(lines))

    def _update_status_dot(self):
        ollama_ok = self.assistant and self.assistant.client is not None
        color = COLORS["success"] if ollama_ok else COLORS["warning"]
        if hasattr(self, "status_dot"):
            self.status_dot.configure(text_color=color)

    # ── Voice ──────────────────────────────────────────────────

    def _on_voice_command(self, text: str):
        if text == "[wake]":
            if self.voice_engine:
                self.voice_engine.speak_async("Yes, sir?")
            return
        self.root.after(0, lambda t=text: self._handle_voice_command(t))

    def _handle_voice_command(self, text: str):
        self.chat.add_user_message(f"[Voice] {text}")
        self.chat.add_loading()
        asyncio.run_coroutine_threadsafe(self._process_command(text), self.loop)

    def _wire_voice(self):
        voice_plugin = self.plugin_manager.get_plugin("voice")
        if voice_plugin and hasattr(voice_plugin, "voice_engine") and voice_plugin.voice_engine:
            ve = voice_plugin.voice_engine
            self.voice_engine = ve
            self.chat.set_voice_engine(ve)
            self.assistant.voice_engine = ve
            ve.start_listening(on_command=self._on_voice_command)
            voice_plugin._status_message = "Listening for 'Nexus'"
            self.sidebar.update_status()
            ve.speak_async("Nexus online. All systems ready, sir.")
            logger.info("Voice active — wake-word listening started")

    # ── Tab panel refreshers ───────────────────────────────────

    def _refresh_projects(self):
        plugin = self.plugin_manager.get_plugin("project_manager")
        if not plugin or not plugin.is_connected:
            return
        projects = plugin.get_all_projects()

        # Stats bar
        active = sum(1 for p in projects if p.get("status") == "in_progress")
        overdue_count = 0
        from datetime import date
        today = date.today().isoformat()
        overdue_count = sum(
            1 for p in projects
            if p.get("deadline") and p["deadline"] < today and p.get("status") not in ("complete", "cancelled")
        )
        total_earned = sum(
            p.get("logged_hours", 0) * p.get("hourly_rate", 0) for p in projects
        )
        stats_text = (
            f"Total: {len(projects)}  |  Active: {active}  |  "
            f"Overdue: {overdue_count}  |  "
            f"Earned: £{total_earned:.0f}"
        )
        self.project_stats_label.configure(text=stats_text)

        # Clear and rebuild list
        for w in self.projects_scroll.winfo_children():
            w.destroy()

        if not projects:
            ctk.CTkLabel(
                self.projects_scroll,
                text="No projects yet, sir. Use the chat to add one: 'add project Acme Corp website'",
                font=FONTS["body"], text_color=COLORS["text_muted"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")
            return

        STATUS_ICONS = {"planning": "🔵", "in_progress": "🟡", "review": "🟠",
                        "complete": "🟢", "paused": "⚪", "cancelled": "🔴"}

        for p in sorted(projects, key=lambda x: (x.get("status") != "in_progress", x.get("deadline", "9999"))):
            card = ctk.CTkFrame(self.projects_scroll, fg_color=COLORS["bg_secondary"], corner_radius=8)
            card.pack(fill="x", padx=SPACING["sm"], pady=SPACING["xs"])

            row1 = ctk.CTkFrame(card, fg_color="transparent")
            row1.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], 2))

            icon = STATUS_ICONS.get(p.get("status", "planning"), "⚪")
            ctk.CTkLabel(row1, text=f"{icon} {p['name']}", font=FONTS["subheading"],
                         text_color=COLORS["text_primary"]).pack(side="left")

            rate = p.get("hourly_rate", 0)
            logged = p.get("logged_hours", 0)
            earned = logged * rate if rate else 0
            if earned:
                ctk.CTkLabel(row1, text=f"£{earned:.0f}", font=FONTS["subheading"],
                             text_color=COLORS["success"]).pack(side="right")

            row2 = ctk.CTkFrame(card, fg_color="transparent")
            row2.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["sm"]))

            details = []
            if p.get("client"):
                details.append(p["client"])
            if p.get("deadline"):
                details.append(f"Due: {p['deadline']}")
            if logged:
                details.append(f"{logged:.1f}h logged")
            if rate:
                details.append(f"£{rate:.0f}/hr")

            ctk.CTkLabel(row2, text="  •  ".join(details) if details else p.get("status", ""),
                         font=FONTS["small"], text_color=COLORS["text_muted"]).pack(side="left")

            if p.get("status") == "in_progress":
                log_btn = ctk.CTkButton(
                    row2, text="+ Hours", font=FONTS["small"],
                    fg_color=COLORS["bg_tertiary"], hover_color=COLORS["border"],
                    text_color=COLORS["accent"], width=65, height=24,
                    command=lambda n=p["name"]: self._log_hours_dialog(n),
                )
                log_btn.pack(side="right")

    def _refresh_system_stats(self):
        plugin = self.plugin_manager.get_plugin("system_monitor")
        if not plugin or not plugin.is_connected:
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=0.5)
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage("/")

                def bar(pct): return "█" * int(pct / 5) + "░" * (20 - int(pct / 5))

                text = (
                    f"CPU     {bar(cpu)} {cpu:.1f}%\n"
                    f"RAM     {bar(mem.percent)} {mem.percent:.1f}%"
                    f"  ({mem.used/1024**3:.1f}/{mem.total/1024**3:.1f} GB)\n"
                    f"Disk    {bar(disk.percent)} {disk.percent:.1f}%"
                    f"  ({disk.used/1024**3:.1f}/{disk.total/1024**3:.1f} GB)\n\n"
                    f"Uptime: {self._get_uptime()}"
                )
                self.sys_stats_label.configure(text=text)
            except Exception:
                self.sys_stats_label.configure(text="psutil not installed. Run: pip install psutil")
            return

        asyncio.run_coroutine_threadsafe(self._async_refresh_stats(), self.loop)

    async def _async_refresh_stats(self):
        plugin = self.plugin_manager.get_plugin("system_monitor")
        if plugin:
            result = await plugin.execute("get_full_report", {})
            self.root.after(0, lambda: self.sys_stats_label.configure(text=result))

    def _refresh_uptime_display(self):
        plugin = self.plugin_manager.get_plugin("uptime_monitor")
        if not plugin:
            return
        sites = plugin.get_all_sites()
        for w in self.uptime_scroll.winfo_children():
            w.destroy()

        if not sites:
            ctk.CTkLabel(self.uptime_scroll,
                         text="No sites being monitored.\nAdd a client URL above, sir.",
                         font=FONTS["small"], text_color=COLORS["text_muted"]).pack(anchor="w")
            return

        for s in sites:
            status = s.get("last_status", "unknown")
            icon = "🟢" if status == "up" else "🔴" if status == "down" else "⚫"
            uptime = (s["up_checks"] / s["total_checks"] * 100) if s.get("total_checks", 0) > 0 else 0
            ms_str = f"  {s['last_response_ms']}ms" if s.get("last_response_ms") else ""

            row = ctk.CTkFrame(self.uptime_scroll, fg_color=COLORS["bg_secondary"], corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{icon} {s['name']}", font=FONTS["small"],
                         text_color=COLORS["text_primary"]).pack(side="left", padx=SPACING["sm"], pady=SPACING["xs"])
            ctk.CTkLabel(row, text=f"{uptime:.1f}%{ms_str}", font=FONTS["hud"],
                         text_color=COLORS["text_muted"]).pack(side="right", padx=SPACING["sm"])

    def _check_uptime(self):
        plugin = self.plugin_manager.get_plugin("uptime_monitor")
        if not plugin or not plugin.is_connected:
            return

        async def _do():
            await plugin.execute("check_all", {})
            self.root.after(0, self._refresh_uptime_display)

        asyncio.run_coroutine_threadsafe(_do(), self.loop)

    def _add_uptime_site(self):
        url = self.uptime_url_entry.get().strip()
        name = self.uptime_name_entry.get().strip()
        if not url:
            return

        plugin = self.plugin_manager.get_plugin("uptime_monitor")
        if not plugin or not plugin.is_connected:
            return

        async def _do():
            result = await plugin.execute("add_site", {"url": url, "name": name})
            self.root.after(0, lambda: self._refresh_uptime_display())
            self.root.after(0, lambda: self.uptime_url_entry.delete(0, "end"))
            self.root.after(0, lambda: self.uptime_name_entry.delete(0, "end"))
            self.root.after(0, lambda: self.chat.add_system_message(f"[UPTIME] {result}"))

        asyncio.run_coroutine_threadsafe(_do(), self.loop)

    def _run_audit(self):
        url = self.audit_url_entry.get().strip()
        if not url:
            return
        self.audit_result_label.configure(text="Auditing... please wait, sir.")

        plugin = self.plugin_manager.get_plugin("website_auditor")
        if not plugin or not plugin.is_connected:
            self.audit_result_label.configure(text="Website auditor plugin not available.")
            return

        async def _do():
            result = await plugin.execute("audit_site", {"url": url})
            self.root.after(0, lambda: self.audit_result_label.configure(text=result, font=FONTS["mono_small"]))

        asyncio.run_coroutine_threadsafe(_do(), self.loop)

    def _run_lead_search(self):
        city = self.lead_city_entry.get().strip()
        industry = self.lead_industry_entry.get().strip() or "businesses"

        plugin = self.plugin_manager.get_plugin("leads")
        if not plugin or not plugin.is_connected:
            for w in self.leads_result.winfo_children():
                w.destroy()
            ctk.CTkLabel(self.leads_result, text="Lead finder plugin not connected.",
                         font=FONTS["small"], text_color=COLORS["error"]).pack(anchor="w")
            return

        for w in self.leads_result.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.leads_result, text=f"Searching for {industry} in {city}...",
                     font=FONTS["small"], text_color=COLORS["accent"]).pack(anchor="w")

        async def _do():
            result = await plugin.execute("search_leads", {"city": city, "industry": industry})
            self.root.after(0, lambda: self._show_leads_result(result))

        asyncio.run_coroutine_threadsafe(_do(), self.loop)

    def _show_leads_result(self, result: str):
        for w in self.leads_result.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.leads_result, text=result, font=FONTS["small"],
                     text_color=COLORS["text_secondary"], justify="left", wraplength=380).pack(anchor="w")

    def _new_project_dialog(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("New Project")
        dialog.geometry("420x320")
        dialog.configure(fg_color=COLORS["bg_secondary"])
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="NEW PROJECT", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(pady=(SPACING["md"], SPACING["sm"]))

        fields = {}
        for label, placeholder in [
            ("Project Name", "e.g. Acme Corp Website"),
            ("Client",       "e.g. Acme Corp"),
            ("Deadline",     "e.g. 2025-04-30"),
            ("Rate (£/hr)",  "e.g. 75"),
            ("Est. Hours",   "e.g. 40"),
        ]:
            row = ctk.CTkFrame(dialog, fg_color="transparent")
            row.pack(fill="x", padx=SPACING["lg"], pady=2)
            ctk.CTkLabel(row, text=label, font=FONTS["small"], text_color=COLORS["text_muted"],
                         width=90, anchor="w").pack(side="left")
            entry = ctk.CTkEntry(row, placeholder_text=placeholder, fg_color=COLORS["bg_input"],
                                 border_color=COLORS["border"], text_color=COLORS["text_primary"],
                                 height=32, corner_radius=8)
            entry.pack(side="left", fill="x", expand=True)
            fields[label] = entry

        def submit():
            params = {
                "name":             fields["Project Name"].get().strip(),
                "client":           fields["Client"].get().strip(),
                "deadline":         fields["Deadline"].get().strip(),
                "rate":             fields["Rate (£/hr)"].get().strip(),
                "estimated_hours":  fields["Est. Hours"].get().strip(),
            }
            if not params["name"]:
                return
            plugin = self.plugin_manager.get_plugin("project_manager")
            if plugin:
                asyncio.run_coroutine_threadsafe(
                    self._add_project_async(params), self.loop
                )
            dialog.destroy()

        ctk.CTkButton(dialog, text="Add Project", font=FONTS["body"],
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color=COLORS["bg_primary"], height=36, command=submit).pack(pady=SPACING["md"])

    async def _add_project_async(self, params: dict):
        plugin = self.plugin_manager.get_plugin("project_manager")
        if plugin:
            result = await plugin.execute("add_project", params)
            self.root.after(0, lambda: self.chat.add_system_message(f"[PROJECTS] {result.split(chr(10))[0]}"))
            self.root.after(100, self._refresh_projects)

    def _log_hours_dialog(self, project_name: str):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(f"Log Hours — {project_name}")
        dialog.geometry("300x200")
        dialog.configure(fg_color=COLORS["bg_secondary"])
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=f"Log hours: {project_name}", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(pady=(SPACING["md"], SPACING["sm"]))

        hours_entry = ctk.CTkEntry(dialog, placeholder_text="Hours (e.g. 2.5)",
                                   fg_color=COLORS["bg_input"], border_color=COLORS["border"],
                                   text_color=COLORS["text_primary"], height=36, corner_radius=8)
        hours_entry.pack(fill="x", padx=SPACING["lg"], pady=SPACING["xs"])

        note_entry = ctk.CTkEntry(dialog, placeholder_text="Note (optional)",
                                  fg_color=COLORS["bg_input"], border_color=COLORS["border"],
                                  text_color=COLORS["text_primary"], height=36, corner_radius=8)
        note_entry.pack(fill="x", padx=SPACING["lg"], pady=SPACING["xs"])

        def submit():
            hours_str = hours_entry.get().strip()
            try:
                hours = float(hours_str)
            except ValueError:
                return
            plugin = self.plugin_manager.get_plugin("project_manager")
            if plugin:
                asyncio.run_coroutine_threadsafe(
                    self._log_hours_async(project_name, hours, note_entry.get()),
                    self.loop,
                )
            dialog.destroy()

        ctk.CTkButton(dialog, text="Log Hours", font=FONTS["body"],
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color=COLORS["bg_primary"], height=36, command=submit).pack(pady=SPACING["md"])

    async def _log_hours_async(self, name: str, hours: float, note: str):
        plugin = self.plugin_manager.get_plugin("project_manager")
        if plugin:
            result = await plugin.execute("log_hours", {"name": name, "hours": hours, "note": note})
            self.root.after(0, lambda: self.chat.add_system_message(f"[PROJECTS] {result.split(chr(10))[0]}"))
            self.root.after(100, self._refresh_projects)

    # ── Utilities ──────────────────────────────────────────────

    @staticmethod
    def _get_uptime() -> str:
        try:
            import psutil
            delta = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
            h, rem = divmod(int(delta.total_seconds()), 3600)
            return f"{h}h {rem//60}m"
        except Exception:
            return "unknown"

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _update_chat(self, msg: str):
        self.root.after(0, lambda: self.chat.add_bot_message(msg))

    def run(self):
        self._loop_thread.start()
        self.sidebar.update_status()
        asyncio.run_coroutine_threadsafe(self._startup(), self.loop)
        self.root.mainloop()

        # Cleanup on exit
        asyncio.run_coroutine_threadsafe(self.browser_engine.stop(), self.loop)
        asyncio.run_coroutine_threadsafe(self.plugin_manager.disconnect_all(), self.loop)
        self.loop.call_soon_threadsafe(self.loop.stop)
