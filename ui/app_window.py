"""App Window — JARVIS-style AI Command Center with tabs and live HUD."""

import asyncio
import queue
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
        self._ui_queue: queue.SimpleQueue = queue.SimpleQueue()
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

        # Graceful shutdown — stop asyncio loop before Tkinter tears down
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
        self.tabview.add("  RESEARCH  ")
        self.tabview.add("  PROJECTS  ")
        self.tabview.add("  INTELLIGENCE  ")
        self.tabview.add("  MONITOR  ")
        self.tabview.add("  ML  ")

        self._build_command_tab()
        self._build_research_tab()
        self._build_projects_tab()
        self._build_intelligence_tab()
        self._build_monitor_tab()
        self._build_ml_tab()

    def _build_command_tab(self):
        tab = self.tabview.tab("  COMMAND  ")
        tab.configure(fg_color=COLORS["bg_primary"])

        # Sidebar | divider | Chat
        self.sidebar = Sidebar(tab, self.plugin_manager, on_quick_action=self._on_quick_action)
        self.sidebar.pack(side="left", fill="y")

        ctk.CTkFrame(tab, fg_color=COLORS["border"], width=1).pack(side="left", fill="y")

        self.chat = ChatPanel(tab, on_send=self._on_user_send)
        self.chat.pack(side="right", fill="both", expand=True)

    def _build_research_tab(self):
        tab = self.tabview.tab("  RESEARCH  ")
        tab.configure(fg_color=COLORS["bg_primary"])

        # Toolbar
        toolbar = ctk.CTkFrame(tab, fg_color=COLORS["bg_secondary"], height=48, corner_radius=0)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        inner = ctk.CTkFrame(toolbar, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["xs"])

        ctk.CTkLabel(inner, text="🔬  RESEARCH AGENT", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(side="left")

        ctk.CTkButton(inner, text="↻ Refresh", font=FONTS["small"],
                      fg_color="transparent", hover_color=COLORS["bg_tertiary"],
                      text_color=COLORS["text_secondary"], width=80, height=30,
                      command=self._refresh_research).pack(side="right")

        # Stats bar
        self.research_stats_frame = ctk.CTkFrame(tab, fg_color=COLORS["bg_tertiary"], height=36, corner_radius=0)
        self.research_stats_frame.pack(fill="x")
        self.research_stats_label = ctk.CTkLabel(
            self.research_stats_frame, text="Monitoring active research tasks...",
            font=FONTS["small"], text_color=COLORS["text_secondary"],
        )
        self.research_stats_label.pack(anchor="w", padx=SPACING["md"], pady=SPACING["xs"])

        # Research scrollable area
        self.research_scroll = ctk.CTkScrollableFrame(
            tab, fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
        )
        self.research_scroll.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["md"])
        
        self.research_content = ctk.CTkLabel(
            self.research_scroll, text="No active research tasks.\nAssign research tasks from the COMMAND tab, sir.",
            font=FONTS["body"], text_color=COLORS["text_muted"],
        )
        self.research_content.pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")

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

    def _refresh_ml(self):
        """Refresh the ML tab with current AI/ML activities and progress."""
        try:
            import json
            import os
            from datetime import datetime, timedelta
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import matplotlib.dates as mdates

            # Load tasks and filter AI/ML tasks
            tasks_file = os.path.join(os.path.dirname(__file__), "..", "memory", "tasks.json")
            if os.path.exists(tasks_file):
                with open(tasks_file, 'r') as f:
                    tasks = json.load(f)

                ml_tasks = [t for t in tasks if any(tag in (t.get("tags", []) or []) for tag in ["ai_ml", "evolution", "memory"])]

                # Stats
                total_ml = len(ml_tasks)
                active_ml = len([t for t in ml_tasks if t.get("status") == "open"])
                completed_ml = len([t for t in ml_tasks if t.get("status") == "done"])
                in_progress_ml = len([t for t in ml_tasks if t.get("status") == "in_progress"])

                stats_text = f"Total ML Tasks: {total_ml}  |  Active: {active_ml}  |  In Progress: {in_progress_ml}  |  Completed: {completed_ml}"
                self.ml_stats_label.configure(text=stats_text)

                # Refresh tasks tab
                self._refresh_ml_tasks_tab(ml_tasks)

                # Refresh progress tab with charts and learning data
                self._refresh_ml_progress_tab()

                # Refresh research tab
                self._refresh_ml_research_tab(ml_tasks)

                # Refresh metrics tab
                self._refresh_ml_metrics_tab()

            # Load AI/ML research framework for additional context
            research_file = os.path.join(os.path.dirname(__file__), "..", "memory", "ai_ml_research.json")
            if os.path.exists(research_file):
                with open(research_file, 'r') as f:
                    research_data = json.load(f)

                # Update recommendations based on current tasks
                self._update_ml_recommendations(research_data, ml_tasks)

        except Exception as e:
            self.ml_stats_label.configure(text=f"Error loading ML data: {str(e)[:50]}")
            logger.error(f"ML refresh error: {e}")

    def _refresh_ml_tasks_tab(self, ml_tasks):
        """Refresh the tasks tab with completion functionality."""
        # Clear existing content
        for w in self.ml_tasks_scroll.winfo_children():
            w.destroy()

        if not ml_tasks:
            ctk.CTkLabel(
                self.ml_tasks_scroll,
                text="No AI/ML improvement tasks found.\nCreate a new task to get started.",
                font=FONTS["body"], text_color=COLORS["text_muted"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")
            return

        # Group tasks by category
        categories = {}
        for task in ml_tasks:
            tags = task.get("tags", [])
            category = "General"
            if "ai_ml" in tags:
                category = "AI/ML Research"
            elif "evolution" in tags:
                category = "Code Evolution"
            elif "memory" in tags:
                category = "Memory Optimization"

            if category not in categories:
                categories[category] = []
            categories[category].append(task)

        # Display tasks by category
        for category, cat_tasks in categories.items():
            # Category header
            cat_frame = ctk.CTkFrame(self.ml_tasks_scroll, fg_color=COLORS["bg_secondary"], corner_radius=8)
            cat_frame.pack(fill="x", padx=SPACING["sm"], pady=SPACING["xs"])

            ctk.CTkLabel(cat_frame, text=f"📊 {category}", font=FONTS["subheading"],
                         text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

            # Tasks in category
            for task in sorted(cat_tasks, key=lambda x: (x.get("status") != "open", x.get("priority", 3))):
                task_frame = ctk.CTkFrame(cat_frame, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                task_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                # Task content frame
                content_frame = ctk.CTkFrame(task_frame, fg_color="transparent")
                content_frame.pack(fill="x", padx=SPACING["sm"], pady=SPACING["sm"])

                # Status and title row
                header_row = ctk.CTkFrame(content_frame, fg_color="transparent")
                header_row.pack(fill="x")

                # Status icon and checkbox
                status_frame = ctk.CTkFrame(header_row, fg_color="transparent")
                status_frame.pack(side="left")

                status = task.get("status", "open")
                icon = "✅" if status == "done" else "🔄" if status == "in_progress" else "⏳"

                # Priority color
                priority = task.get("priority", 3)
                if isinstance(priority, str):
                    priority = {"high": 1, "medium": 2, "low": 3}.get(priority, 3)
                color = COLORS["success"] if status == "done" else COLORS["warning"] if priority == 1 else COLORS["text_primary"]

                # Checkbox for completion
                checkbox = ctk.CTkCheckBox(
                    status_frame, text="", width=20, height=20,
                    command=lambda t=task: self._toggle_task_completion(t)
                )
                checkbox.pack(side="left", padx=(0, SPACING["xs"]))
                if status == "done":
                    checkbox.select()

                # Status icon
                ctk.CTkLabel(status_frame, text=icon, font=("Segoe UI", 16),
                             text_color=color).pack(side="left", padx=(0, SPACING["xs"]))

                # Title
                title_label = ctk.CTkLabel(header_row, text=task['title'], font=FONTS["body"],
                                           text_color=color)
                title_label.pack(side="left")

                # Action buttons
                actions_frame = ctk.CTkFrame(header_row, fg_color="transparent")
                actions_frame.pack(side="right")

                if status != "done":
                    ctk.CTkButton(actions_frame, text="Start", font=FONTS["small"],
                                  fg_color=COLORS["bg_tertiary"], hover_color=COLORS["accent_dim"],
                                  text_color=COLORS["accent"], width=50, height=24,
                                  command=lambda t=task: self._start_task(t)).pack(side="left", padx=(0, SPACING["xs"]))

                ctk.CTkButton(actions_frame, text="Edit", font=FONTS["small"],
                              fg_color="transparent", hover_color=COLORS["bg_tertiary"],
                              text_color=COLORS["text_muted"], width=40, height=24,
                              command=lambda t=task: self._edit_task(t)).pack(side="left")

                # Details
                details = []
                if task.get("due"):
                    details.append(f"Due: {task['due']}")
                if task.get("description"):
                    desc = task["description"][:80] + "..." if len(task["description"]) > 80 else task["description"]
                    details.append(desc)

                if details:
                    details_label = ctk.CTkLabel(content_frame, text="  •  ".join(details),
                                                 font=FONTS["small"], text_color=COLORS["text_muted"],
                                                 wraplength=500, justify="left")
                    details_label.pack(anchor="w", pady=(SPACING["xs"], 0))

    def _refresh_ml_progress_tab(self):
        """Refresh the progress tab with charts and learning data."""
        try:
            # Clear charts
            for w in self.ml_charts_canvas.winfo_children():
                w.destroy()

            # Generate progress chart
            self._generate_progress_chart()

            # Load and display learning progress
            self._load_learning_progress()

        except Exception as e:
            logger.error(f"Progress tab refresh error: {e}")

    def _refresh_ml_research_tab(self, ml_tasks):
        """Refresh the research tab with current research tasks."""
        # Clear existing content
        for w in self.ml_research_scroll.winfo_children():
            w.destroy()

        # Filter research tasks
        research_tasks = [t for t in ml_tasks if "research" in t.get("tags", []) or "ai_ml" in t.get("tags", [])]

        if not research_tasks:
            ctk.CTkLabel(
                self.ml_research_scroll,
                text="No active research tasks.\nResearch tasks will appear here.",
                font=FONTS["body"], text_color=COLORS["text_muted"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")
        else:
            for task in research_tasks:
                task_frame = ctk.CTkFrame(self.ml_research_scroll, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                task_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                status = task.get("status", "open")
                icon = "✅" if status == "done" else "🔄" if status == "in_progress" else "🔬"

                ctk.CTkLabel(task_frame, text=f"{icon} {task['title']}", font=FONTS["body"],
                             text_color=COLORS["text_primary"]).pack(anchor="w", padx=SPACING["sm"], pady=SPACING["sm"])

                if task.get("description"):
                    ctk.CTkLabel(task_frame, text=task["description"], font=FONTS["small"],
                                 text_color=COLORS["text_muted"], wraplength=400).pack(anchor="w", padx=SPACING["sm"])

    def _refresh_ml_metrics_tab(self):
        """Refresh the metrics dashboard."""
        # Clear existing content
        for w in self.ml_metrics_scroll.winfo_children():
            w.destroy()

        try:
            # Load learning progress for metrics
            import json
            from pathlib import Path
            from datetime import datetime, timedelta

            progress_file = Path.home() / "NexusScripts" / "learning_progress.json"
            if progress_file.exists():
                with open(progress_file, 'r') as f:
                    progress_data = json.load(f)

                # Calculate metrics
                self._display_ml_metrics(progress_data)
            else:
                ctk.CTkLabel(
                    self.ml_metrics_scroll,
                    text="No learning progress data available.\nStart logging improvements to see metrics.",
                    font=FONTS["body"], text_color=COLORS["text_muted"],
                ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")

        except Exception as e:
            ctk.CTkLabel(
                self.ml_metrics_scroll,
                text=f"Error loading metrics: {str(e)}",
                font=FONTS["body"], text_color=COLORS["error"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")

    def _generate_progress_chart(self):
        """Generate progress chart using matplotlib."""
        try:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import matplotlib.dates as mdates
            from datetime import datetime, timedelta
            import json
            from pathlib import Path

            # Load progress data
            progress_file = Path.home() / "NexusScripts" / "learning_progress.json"
            if not progress_file.exists():
                return

            with open(progress_file, 'r') as f:
                progress_data = json.load(f)

            # Create figure
            fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
            fig.patch.set_facecolor(COLORS["bg_secondary"])
            ax.set_facecolor(COLORS["bg_secondary"])

            # Get data for last 30 days
            cutoff = datetime.now() - timedelta(days=30)
            dates = []
            model_improvements = []
            code_improvements = []

            current_date = cutoff
            while current_date <= datetime.now():
                date_str = current_date.date().isoformat()
                dates.append(current_date)

                # Count improvements for this date
                model_count = len([m for m in progress_data.get("model_performance", [])
                                 if m["timestamp"].startswith(date_str)])
                code_count = len([c for c in progress_data.get("code_quality", [])
                                if c["timestamp"].startswith(date_str)])

                model_improvements.append(model_count)
                code_improvements.append(code_count)

                current_date += timedelta(days=1)

            # Plot data
            ax.plot(dates, model_improvements, label='Model Improvements', color='#00ff88', linewidth=2)
            ax.plot(dates, code_improvements, label='Code Improvements', color='#0088ff', linewidth=2)

            # Styling
            ax.set_title('Learning Progress (30 Days)', color=COLORS["text_primary"], fontsize=12, pad=20)
            ax.set_xlabel('Date', color=COLORS["text_muted"], fontsize=10)
            ax.set_ylabel('Improvements', color=COLORS["text_muted"], fontsize=10)
            ax.legend(facecolor=COLORS["bg_tertiary"], edgecolor=COLORS["border"])
            ax.tick_params(colors=COLORS["text_muted"])
            ax.grid(True, alpha=0.3, color=COLORS["border"])

            # Date formatting
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
            plt.setp(ax.get_xticklabels(), rotation=45)

            # Embed in tkinter
            canvas = FigureCanvasTkAgg(fig, master=self.ml_charts_canvas)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)

        except Exception as e:
            logger.error(f"Chart generation error: {e}")

    def _load_learning_progress(self):
        """Load and display learning progress data."""
        # Clear existing content
        for w in self.ml_learning_scroll.winfo_children():
            w.destroy()

        try:
            import json
            from pathlib import Path

            progress_file = Path.home() / "NexusScripts" / "learning_progress.json"
            if not progress_file.exists():
                ctk.CTkLabel(
                    self.ml_learning_scroll,
                    text="No learning progress data.\nStart logging improvements to track progress.",
                    font=FONTS["body"], text_color=COLORS["text_muted"],
                ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")
                return

            with open(progress_file, 'r') as f:
                progress_data = json.load(f)

            # Get recent improvements (last 7 days)
            from datetime import datetime, timedelta
            week_ago = datetime.now() - timedelta(days=7)
            week_iso = week_ago.isoformat()

            recent_model = [m for m in progress_data.get("model_performance", []) if m["timestamp"] > week_iso]
            recent_code = [c for c in progress_data.get("code_quality", []) if c["timestamp"] > week_iso]
            recent_research = [r for r in progress_data.get("research_activities", []) if r["timestamp"] > week_iso]

            # Display recent activity
            if recent_model:
                model_frame = ctk.CTkFrame(self.ml_learning_scroll, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                model_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                ctk.CTkLabel(model_frame, text=f"🤖 {len(recent_model)} Model Improvements", font=FONTS["subheading"],
                             text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["sm"], pady=SPACING["sm"])

                for improvement in recent_model[-3:]:  # Show last 3
                    ctk.CTkLabel(model_frame,
                                 text=f"• {improvement['model']}: +{improvement['improvement_pct']:.2f}% {improvement['metric']}",
                                 font=FONTS["small"], text_color=COLORS["text_secondary"]).pack(anchor="w", padx=SPACING["sm"])

            if recent_code:
                code_frame = ctk.CTkFrame(self.ml_learning_scroll, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                code_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                ctk.CTkLabel(code_frame, text=f"💻 {len(recent_code)} Code Improvements", font=FONTS["subheading"],
                             text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["sm"], pady=SPACING["sm"])

                for improvement in recent_code[-3:]:  # Show last 3
                    ctk.CTkLabel(code_frame,
                                 text=f"• {improvement['area']}: {improvement['improvement']:+.2f} {improvement['metric_name']}",
                                 font=FONTS["small"], text_color=COLORS["text_secondary"]).pack(anchor="w", padx=SPACING["sm"])

            if recent_research:
                research_frame = ctk.CTkFrame(self.ml_learning_scroll, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                research_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                ctk.CTkLabel(research_frame, text=f"🔬 {len(recent_research)} Research Activities", font=FONTS["subheading"],
                             text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["sm"], pady=SPACING["sm"])

                for research in recent_research[-3:]:  # Show last 3
                    ctk.CTkLabel(research_frame,
                                 text=f"• {research['topic']} ({research['type']})",
                                 font=FONTS["small"], text_color=COLORS["text_secondary"]).pack(anchor="w", padx=SPACING["sm"])

        except Exception as e:
            ctk.CTkLabel(
                self.ml_learning_scroll,
                text=f"Error loading learning progress: {str(e)}",
                font=FONTS["body"], text_color=COLORS["error"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")

    def _update_ml_recommendations(self, research_data, ml_tasks):
        """Update research recommendations based on current tasks and research framework."""
        # Clear existing content
        for w in self.ml_recommendations_scroll.winfo_children():
            w.destroy()

        recommendations = []

        # Analyze current task gaps
        current_tags = set()
        for task in ml_tasks:
            current_tags.update(task.get("tags", []))

        # Check for missing research areas
        research_practices = research_data.get("sections", {}).get("research_practices", {}).get("practices", [])
        if "research" not in current_tags and research_practices:
            recommendations.append({
                "title": "Start Research Program",
                "description": "Begin systematic review of latest ML papers and conferences",
                "priority": "high",
                "action": "Create weekly research task"
            })

        # Check for algorithm exploration
        if not any("algorithm" in tag for tag in current_tags):
            recommendations.append({
                "title": "Explore ML Algorithms",
                "description": "Investigate different ML algorithm families for current use cases",
                "priority": "medium",
                "action": "Create algorithm exploration task"
            })

        # Check for hyperparameter tuning
        if not any("optimization" in tag or "tuning" in tag for tag in current_tags):
            recommendations.append({
                "title": "Implement Hyperparameter Tuning",
                "description": "Set up systematic hyperparameter optimization for models",
                "priority": "high",
                "action": "Create tuning pipeline task"
            })

        # Display recommendations
        if not recommendations:
            ctk.CTkLabel(
                self.ml_recommendations_scroll,
                text="All research areas covered!\nGreat job maintaining comprehensive ML improvement program.",
                font=FONTS["body"], text_color=COLORS["success"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")
        else:
            for rec in recommendations:
                rec_frame = ctk.CTkFrame(self.ml_recommendations_scroll, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                rec_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                priority_color = COLORS["warning"] if rec["priority"] == "high" else COLORS["text_primary"]

                ctk.CTkLabel(rec_frame, text=f"💡 {rec['title']}", font=FONTS["body"],
                             text_color=priority_color).pack(anchor="w", padx=SPACING["sm"], pady=(SPACING["sm"], SPACING["xs"]))

                ctk.CTkLabel(rec_frame, text=rec["description"], font=FONTS["small"],
                             text_color=COLORS["text_muted"], wraplength=350).pack(anchor="w", padx=SPACING["sm"], pady=(0, SPACING["xs"]))

                ctk.CTkButton(rec_frame, text=rec["action"], font=FONTS["small"],
                              fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                              text_color=COLORS["bg_primary"], height=28,
                              command=lambda r=rec: self._create_recommended_task(r)).pack(anchor="w", padx=SPACING["sm"], pady=(0, SPACING["sm"]))

    def _display_ml_metrics(self, progress_data):
        """Display comprehensive ML metrics dashboard."""
        from datetime import datetime, timedelta

        # Calculate metrics for different time periods
        periods = [7, 30, 90]
        period_names = ["Week", "Month", "Quarter"]

        for i, (days, name) in enumerate(zip(periods, period_names)):
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            # Filter data
            model_improvements = [m for m in progress_data.get("model_performance", []) if m["timestamp"] > cutoff_iso]
            code_improvements = [c for c in progress_data.get("code_quality", []) if c["timestamp"] > cutoff_iso]
            research_activities = [r for r in progress_data.get("research_activities", []) if r["timestamp"] > cutoff_iso]
            memory_work = [m for m in progress_data.get("memory_consolidations", []) if m["timestamp"] > cutoff_iso]

            # Metrics frame
            metrics_frame = ctk.CTkFrame(self.ml_metrics_scroll, fg_color=COLORS["bg_secondary"], corner_radius=8)
            metrics_frame.pack(fill="x", padx=SPACING["sm"], pady=SPACING["xs"])

            ctk.CTkLabel(metrics_frame, text=f"📊 {name} Metrics", font=FONTS["subheading"],
                         text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

            # Stats grid
            stats_frame = ctk.CTkFrame(metrics_frame, fg_color="transparent")
            stats_frame.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["md"]))

            # Row 1: Model and Code improvements
            row1 = ctk.CTkFrame(stats_frame, fg_color="transparent")
            row1.pack(fill="x", pady=(0, SPACING["xs"]))

            # Model improvements
            model_frame = ctk.CTkFrame(row1, fg_color=COLORS["bg_tertiary"], corner_radius=6)
            model_frame.pack(side="left", fill="x", expand=True, padx=(0, SPACING["xs"]))

            avg_model = sum(m["improvement_pct"] for m in model_improvements) / len(model_improvements) if model_improvements else 0
            ctk.CTkLabel(model_frame, text=f"🤖 Model\n{len(model_improvements)} improvements\n+{avg_model:.1f}% avg",
                         font=FONTS["mono_small"], text_color=COLORS["text_primary"]).pack(padx=SPACING["sm"], pady=SPACING["sm"])

            # Code improvements
            code_frame = ctk.CTkFrame(row1, fg_color=COLORS["bg_tertiary"], corner_radius=6)
            code_frame.pack(side="left", fill="x", expand=True, padx=(SPACING["xs"], 0))

            total_code = sum(c["improvement"] for c in code_improvements)
            ctk.CTkLabel(code_frame, text=f"💻 Code\n{len(code_improvements)} improvements\n{total_code:+.1f} total",
                         font=FONTS["mono_small"], text_color=COLORS["text_primary"]).pack(padx=SPACING["sm"], pady=SPACING["sm"])

            # Row 2: Research and Memory
            row2 = ctk.CTkFrame(stats_frame, fg_color="transparent")
            row2.pack(fill="x")

            # Research activities
            research_frame = ctk.CTkFrame(row2, fg_color=COLORS["bg_tertiary"], corner_radius=6)
            research_frame.pack(side="left", fill="x", expand=True, padx=(0, SPACING["xs"]))

            topics = len(set(r["topic"] for r in research_activities))
            ctk.CTkLabel(research_frame, text=f"🔬 Research\n{len(research_activities)} activities\n{topics} topics",
                         font=FONTS["mono_small"], text_color=COLORS["text_primary"]).pack(padx=SPACING["sm"], pady=SPACING["sm"])

            # Memory optimization
            memory_frame = ctk.CTkFrame(row2, fg_color=COLORS["bg_tertiary"], corner_radius=6)
            memory_frame.pack(side="left", fill="x", expand=True, padx=(SPACING["xs"], 0))

            duplicates = sum(m["duplicates_removed"] for m in memory_work)
            ctk.CTkLabel(memory_frame, text=f"🧠 Memory\n{len(memory_work)} consolidations\n{duplicates} duplicates removed",
                         font=FONTS["mono_small"], text_color=COLORS["text_primary"]).pack(padx=SPACING["sm"], pady=SPACING["sm"])

    def _start_ml_auto_refresh(self):
        """Start automatic refresh of ML tab."""
        self._refresh_ml()  # Initial refresh
        # Auto-refresh every 30 seconds
        self.ml_auto_refresh_id = self.root.after(30000, self._start_ml_auto_refresh)

    def _stop_ml_auto_refresh(self):
        """Stop automatic refresh of ML tab."""
        if self.ml_auto_refresh_id:
            self.root.after_cancel(self.ml_auto_refresh_id)
            self.ml_auto_refresh_id = None

    def _toggle_task_completion(self, task):
        """Toggle task completion status."""
        try:
            import json
            import os
            from datetime import datetime

            tasks_file = os.path.join(os.path.dirname(__file__), "..", "memory", "tasks.json")
            if os.path.exists(tasks_file):
                with open(tasks_file, 'r') as f:
                    tasks = json.load(f)

                # Find and update task
                for t in tasks:
                    if t["id"] == task["id"]:
                        if t.get("status") == "done":
                            t["status"] = "open"
                            if "completed" in t:
                                del t["completed"]
                        else:
                            t["status"] = "done"
                            t["completed"] = datetime.now().isoformat()
                        break

                # Save updated tasks
                with open(tasks_file, 'w') as f:
                    json.dump(tasks, f, indent=2)

                # Refresh display
                self._refresh_ml()

        except Exception as e:
            logger.error(f"Task completion toggle error: {e}")

    def _start_task(self, task):
        """Mark task as in progress."""
        try:
            import json
            import os

            tasks_file = os.path.join(os.path.dirname(__file__), "..", "memory", "tasks.json")
            if os.path.exists(tasks_file):
                with open(tasks_file, 'r') as f:
                    tasks = json.load(f)

                # Find and update task
                for t in tasks:
                    if t["id"] == task["id"]:
                        t["status"] = "in_progress"
                        break

                # Save updated tasks
                with open(tasks_file, 'w') as f:
                    json.dump(tasks, f, indent=2)

                # Refresh display
                self._refresh_ml()

        except Exception as e:
            logger.error(f"Task start error: {e}")

    def _edit_task(self, task):
        """Open task edit dialog."""
        # For now, just show a simple message. Could be enhanced with a full dialog
        self._set_status(f"Edit task: {task['title']}")

    def _create_ml_task_dialog(self):
        """Open dialog to create a new ML task."""
        # Create dialog window
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Create ML Task")
        dialog.geometry("500x600")
        dialog.transient(self.root)
        dialog.grab_set()

        # Title
        ctk.CTkLabel(dialog, text="Create New ML Task", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(pady=(20, 10))

        # Task title
        title_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        title_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(title_frame, text="Title:", font=FONTS["body"]).pack(anchor="w")
        title_entry = ctk.CTkEntry(title_frame, placeholder_text="Enter task title",
                                   fg_color=COLORS["bg_input"], border_color=COLORS["border"])
        title_entry.pack(fill="x", pady=(5, 0))

        # Description
        desc_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        desc_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(desc_frame, text="Description:", font=FONTS["body"]).pack(anchor="w")
        desc_textbox = ctk.CTkTextbox(desc_frame, height=80,
                                      fg_color=COLORS["bg_input"], border_color=COLORS["border"])
        desc_textbox.pack(fill="x", pady=(5, 0))

        # Category/Tags
        tags_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        tags_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(tags_frame, text="Category:", font=FONTS["body"]).pack(anchor="w")

        tag_var = ctk.StringVar(value="ai_ml")
        tag_options = ["ai_ml", "evolution", "memory", "research", "optimization"]
        tag_menu = ctk.CTkOptionMenu(tags_frame, variable=tag_var, values=tag_options,
                                     fg_color=COLORS["bg_input"], button_color=COLORS["border"])
        tag_menu.pack(fill="x", pady=(5, 0))

        # Priority
        priority_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        priority_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(priority_frame, text="Priority:", font=FONTS["body"]).pack(anchor="w")

        priority_var = ctk.StringVar(value="medium")
        priority_options = ["low", "medium", "high"]
        priority_menu = ctk.CTkOptionMenu(priority_frame, variable=priority_var, values=priority_options,
                                          fg_color=COLORS["bg_input"], button_color=COLORS["border"])
        priority_menu.pack(fill="x", pady=(5, 0))

        # Due date
        due_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        due_frame.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkLabel(due_frame, text="Due Date (optional):", font=FONTS["body"]).pack(anchor="w")
        due_entry = ctk.CTkEntry(due_frame, placeholder_text="e.g. Next Week, 2026-04-01",
                                 fg_color=COLORS["bg_input"], border_color=COLORS["border"])
        due_entry.pack(fill="x", pady=(5, 0))

        # Buttons
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        def create_task():
            title = title_entry.get().strip()
            if not title:
                return

            description = desc_textbox.get("1.0", "end").strip()
            tags = [tag_var.get()]
            priority = priority_var.get()
            due = due_entry.get().strip() or None

            self._create_new_ml_task(title, description, tags, priority, due)
            dialog.destroy()

        def cancel():
            dialog.destroy()

        ctk.CTkButton(button_frame, text="Create Task", font=FONTS["body"],
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      command=create_task).pack(side="left", padx=(0, 10))

        ctk.CTkButton(button_frame, text="Cancel", font=FONTS["body"],
                      fg_color="transparent", hover_color=COLORS["bg_tertiary"],
                      command=cancel).pack(side="left")

    def _create_new_ml_task(self, title, description, tags, priority, due):
        """Create a new ML task."""
        try:
            import json
            import os
            from datetime import datetime

            tasks_file = os.path.join(os.path.dirname(__file__), "..", "memory", "tasks.json")
            if os.path.exists(tasks_file):
                with open(tasks_file, 'r') as f:
                    tasks = json.load(f)

                # Generate new ID
                max_id = max((t["id"] for t in tasks), default=0)
                new_task = {
                    "id": max_id + 1,
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "priority": priority,
                    "status": "open",
                    "created": datetime.now().isoformat(),
                    "due": due
                }

                tasks.append(new_task)

                # Save updated tasks
                with open(tasks_file, 'w') as f:
                    json.dump(tasks, f, indent=2)

                # Refresh display
                self._refresh_ml()
                self._set_status(f"Created ML task: {title}")

        except Exception as e:
            logger.error(f"Task creation error: {e}")
            self._set_status(f"Error creating task: {str(e)}")

    def _create_recommended_task(self, recommendation):
        """Create a task from a recommendation."""
        title = recommendation["title"]
        description = recommendation["description"]
        tags = []

        # Map recommendation to appropriate tags
        if "research" in title.lower():
            tags = ["ai_ml", "research"]
        elif "algorithm" in title.lower():
            tags = ["ai_ml", "algorithms"]
        elif "tuning" in title.lower() or "optimization" in title.lower():
            tags = ["ai_ml", "optimization"]
        else:
            tags = ["ai_ml"]

        priority = recommendation.get("priority", "medium")

        self._create_new_ml_task(title, description, tags, priority, None)

    def _show_ml_metrics(self):
        """Switch to metrics tab."""
        self.ml_tabview.set("Metrics")

    def _show_ml_charts(self):
        """Switch to progress tab to show charts."""
        self.ml_tabview.set("Progress")

    def _generate_automated_tasks(self):
        """Generate automated ML improvement tasks based on system analysis."""
        try:
            import json
            import os
            from datetime import datetime, timedelta

            tasks_file = os.path.join(os.path.dirname(__file__), "..", "memory", "tasks.json")
            if not os.path.exists(tasks_file):
                return

            with open(tasks_file, 'r') as f:
                tasks = json.load(f)

            # Check for missing routine tasks
            existing_titles = {t["title"] for t in tasks}

            automated_tasks = [
                {
                    "title": "[AI/ML] Weekly Research Review",
                    "description": "Review latest papers from arXiv, NeurIPS, ICML. Focus on practical applications.",
                    "tags": ["ai_ml", "research", "self-improvement"],
                    "priority": "medium",
                    "due": "Every Friday"
                },
                {
                    "title": "[Evolution] Code Quality Audit",
                    "description": "Review codebase for optimization opportunities, DRY violations, and performance bottlenecks.",
                    "tags": ["evolution", "code-quality", "refactoring"],
                    "priority": "medium",
                    "due": "Weekly"
                },
                {
                    "title": "[Memory] Knowledge Base Consolidation",
                    "description": "Remove duplicate entries, consolidate similar information, improve categorization.",
                    "tags": ["memory", "maintenance", "optimization"],
                    "priority": "low",
                    "due": "Monthly"
                }
            ]

            new_tasks = []
            for task_data in automated_tasks:
                if task_data["title"] not in existing_titles:
                    max_id = max((t["id"] for t in tasks), default=0)
                    new_task = {
                        "id": max_id + len(new_tasks) + 1,
                        "title": task_data["title"],
                        "description": task_data["description"],
                        "tags": task_data["tags"],
                        "priority": task_data["priority"],
                        "status": "open",
                        "created": datetime.now().isoformat(),
                        "due": task_data["due"]
                    }
                    new_tasks.append(new_task)

            if new_tasks:
                tasks.extend(new_tasks)

                # Save updated tasks
                with open(tasks_file, 'w') as f:
                    json.dump(tasks, f, indent=2)

                # Refresh display
                self._refresh_ml()
                self._set_status(f"Generated {len(new_tasks)} automated ML tasks")

        except Exception as e:
            logger.error(f"Automated task generation error: {e}")

    # ── ML Tab Methods ──────────────────────────────────────────

    def _build_ml_progress_tab(self):
        """Build the progress view with charts and learning integration."""
        tab = self.ml_tabview.tab("Progress")
        tab.configure(fg_color=COLORS["bg_primary"])

        # Split view: left = charts, right = learning progress
        self.ml_progress_panes = ctk.CTkFrame(tab, fg_color="transparent")
        self.ml_progress_panes.pack(fill="both", expand=True)

        # Left: Charts area
        self.ml_charts_frame = ctk.CTkFrame(self.ml_progress_panes, fg_color=COLORS["bg_secondary"], corner_radius=8)
        self.ml_charts_frame.pack(side="left", fill="both", expand=True, padx=(0, SPACING["sm"]), pady=0)

        ctk.CTkLabel(self.ml_charts_frame, text="📈 Progress Charts", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        self.ml_charts_canvas = ctk.CTkCanvas(self.ml_charts_frame, bg=COLORS["bg_secondary"], height=300)
        self.ml_charts_canvas.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))

        # Right: Learning progress
        self.ml_learning_frame = ctk.CTkFrame(self.ml_progress_panes, fg_color=COLORS["bg_secondary"], corner_radius=8)
        self.ml_learning_frame.pack(side="right", fill="both", expand=True, padx=(SPACING["sm"], 0), pady=0)

        ctk.CTkLabel(self.ml_learning_frame, text="🎯 Learning Progress", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        self.ml_learning_scroll = ctk.CTkScrollableFrame(self.ml_learning_frame, fg_color="transparent",
                                                         scrollbar_button_color=COLORS["bg_tertiary"])
        self.ml_learning_scroll.pack(fill="both", expand=True, padx=SPACING["sm"], pady=(0, SPACING["md"]))

    def _build_ml_research_tab(self):
        """Build the research view with recommendations."""
        tab = self.ml_tabview.tab("Research")
        tab.configure(fg_color=COLORS["bg_primary"])

        # Split: left = current research, right = recommendations
        panes = ctk.CTkFrame(tab, fg_color="transparent")
        panes.pack(fill="both", expand=True)

        # Left: Current research tasks
        left_panel = ctk.CTkFrame(panes, fg_color=COLORS["bg_secondary"], corner_radius=8)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, SPACING["sm"]), pady=0)

        ctk.CTkLabel(left_panel, text="🔬 Active Research", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        self.ml_research_scroll = ctk.CTkScrollableFrame(left_panel, fg_color="transparent",
                                                         scrollbar_button_color=COLORS["bg_tertiary"])
        self.ml_research_scroll.pack(fill="both", expand=True, padx=SPACING["sm"], pady=(0, SPACING["md"]))

        # Right: Recommendations
        right_panel = ctk.CTkFrame(panes, fg_color=COLORS["bg_secondary"], corner_radius=8)
        right_panel.pack(side="right", fill="both", expand=True, padx=(SPACING["sm"], 0), pady=0)

        ctk.CTkLabel(right_panel, text="💡 Recommendations", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        self.ml_recommendations_scroll = ctk.CTkScrollableFrame(right_panel, fg_color="transparent",
                                                                scrollbar_button_color=COLORS["bg_tertiary"])
        self.ml_recommendations_scroll.pack(fill="both", expand=True, padx=SPACING["sm"], pady=(0, SPACING["md"]))

    def _build_ml_metrics_tab(self):
        """Build the metrics dashboard."""
        tab = self.ml_tabview.tab("Metrics")
        tab.configure(fg_color=COLORS["bg_primary"])

        self.ml_metrics_scroll = ctk.CTkScrollableFrame(
            tab, fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
        )
        self.ml_metrics_scroll.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["md"])

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
                self._reply(msg, speak_text or msg)
                self._set_status("Ready")

            elif rtype == "action":
                explanation = result.get("explanation", "Processing...")
                self._reply(f">> {explanation}", speak_text, animated=False)
                plugin = self.plugin_manager.get_plugin(result.get("plugin", ""))
                if plugin and plugin.is_connected:
                    self._set_status(f"Executing: {result.get('plugin')} → {result.get('action')}")
                    out = await plugin.execute(result["action"], result.get("params", {}))
                    short = out[:400] if out else "Done."
                    if self.voice_engine and hasattr(self.voice_engine, "play_confirm"):
                        self.voice_engine.play_confirm()
                    self._reply(out, short)
                    self._set_status("Ready")
                elif plugin:
                    self._reply(self.assistant.personality.wrap_error(
                        f"{plugin.name} isn't connected, sir. Check sidebar."
                    ))
                    self._set_status("Ready")
                else:
                    self._reply(self.assistant.personality.wrap_error(
                        f"the '{result.get('plugin')}' system doesn't appear to be active"
                    ))
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
                raw = result.get('message', 'an unknown error occurred')
                self._reply(self.assistant.personality.wrap_error(raw))
                self._set_status("Error — ready")

        except Exception as e:
            logger.error(f"Process error: {e}", exc_info=True)
            self._reply(self.assistant.personality.wrap_error(str(e)[:120]))
            self._set_status("Error — ready")

    def _reply(self, message: str, speak: str = "", animated: bool = True):
        self.root.after(0, lambda: (
            self.chat.remove_loading(),
            self.chat.set_processing(False),
            self.chat.add_bot_message(message, animated=animated),
        ))
        if self.voice_engine:
            tts_text = speak if speak else message[:600]
            self.root.after(0, self.chat.show_waveform)
            def _speak_and_hide():
                self.voice_engine.speak(tts_text)
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
            self._ui_call(lambda m=msg: self.chat.add_system_message(m))

        try:
            await asyncio.wait_for(self.browser_engine.start(), timeout=30)
            self._ui_call(lambda: self.chat.add_system_message(
                "Browser context established.                    [ 60%]  ✓"
            ))
        except asyncio.TimeoutError:
            self._ui_call(lambda: self.chat.add_system_message(
                "Browser timed out — browser plugins unavailable, continuing..."
            ))
        except Exception as e:
            self._ui_call(lambda: self.chat.add_system_message(
                f"Browser warning: {str(e)[:50]}  — continuing..."
            ))

        self._ui_call(lambda: self.chat.add_system_message(
            "Connecting all subsystems...                    [ 70%]"
        ))
        total = len(self.plugin_manager.plugins)
        connected_so_far = [0]

        def _on_plugin():
            connected_so_far[0] += 1
            self._ui_call(self.sidebar.update_status)

        await self.plugin_manager.connect_all(on_plugin_connected=_on_plugin)

        # Wire evolution_engine with the full plugin_manager + ai config
        evo = self.plugin_manager.get_plugin("evolution_engine")
        if evo and hasattr(evo, "set_plugin_manager"):
            evo.config.update(self.assistant.config)
            evo.set_plugin_manager(self.plugin_manager)

        plugin_count = sum(1 for p in self.plugin_manager.plugins.values() if p.is_connected)
        self._ui_call(lambda: self.chat.add_system_message(
            f"Subsystems online: {plugin_count}/{total}              [ 98%]  ✓"
        ))
        await asyncio.sleep(0.1)
        self._ui_call(lambda: self.chat.add_system_message(
            "All systems nominal.                            [100%]  ✓"
        ))

        self._ui_call(self.sidebar.update_status)
        self._ui_call(self._wire_voice)
        self._ui_call(self._update_status_dot)
        self._ui_call(self._post_boot_message)
        self._ui_call(self._refresh_system_stats, delay_ms=500)
        self._ui_call(self._refresh_projects, delay_ms=1000)
        self._ui_call(self._refresh_uptime_display, delay_ms=1500)
        self._ui_call(self._refresh_ml, delay_ms=2000)

        # Start the scheduler now that the event loop is running
        asyncio.create_task(self.scheduler.start())

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
                address = getattr(self.assistant.personality, "address_as", "sir")
                self.voice_engine.speak_async(f"Yes, {address}?")
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
            if ve.tts_available:
                self.voice_engine = ve
                self.chat.set_voice_engine(ve)
                self.assistant.voice_engine = ve
                address = getattr(self.assistant.personality, "address_as", "sir")
                ve.speak_async(f"Nexus online. All systems ready, {address}.")
                logger.info("TTS wired — responses will be read aloud")
            if ve.is_available:
                ve.start_listening(on_command=self._on_voice_command)
                voice_plugin._status_message = "Listening for 'Nexus'"
                logger.info("Voice active — wake-word listening started")
            self.sidebar.update_status()

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

    def _refresh_research(self):
        """Refresh the research tab with active research tasks."""
        plugin = self.plugin_manager.get_plugin("research_agent")
        if not plugin or not plugin.is_connected:
            self.research_stats_label.configure(text="Research Agent unavailable")
            return

        # Try to get research tasks from plugin
        try:
            research_tasks = getattr(plugin, "get_research_tasks", lambda: [])()
        except Exception:
            research_tasks = []

        # Stats bar
        active_count = len([t for t in research_tasks if t.get("status") == "in_progress"])
        completed_count = len([t for t in research_tasks if t.get("status") == "complete"])
        total_count = len(research_tasks)
        
        stats_text = f"Total: {total_count}  |  Active: {active_count}  |  Completed: {completed_count}"
        self.research_stats_label.configure(text=stats_text)

        # Clear and rebuild list
        for w in self.research_scroll.winfo_children():
            w.destroy()

        if not research_tasks:
            ctk.CTkLabel(
                self.research_scroll,
                text="No active research tasks.\nUse the COMMAND tab to initiate research, sir.",
                font=FONTS["body"], text_color=COLORS["text_muted"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")
            return

        STATUS_ICONS = {"pending": "⏳", "in_progress": "🔵", "complete": "✓", 
                        "cancelled": "✗", "error": "⚠"}

        for task in sorted(research_tasks, key=lambda x: (x.get("status") != "in_progress", -len(x.get("results", [])))):
            card = ctk.CTkFrame(self.research_scroll, fg_color=COLORS["bg_secondary"], corner_radius=8)
            card.pack(fill="x", padx=SPACING["sm"], pady=SPACING["xs"])

            # Header
            hdr = ctk.CTkFrame(card, fg_color="transparent")
            hdr.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

            status_icon = STATUS_ICONS.get(task.get("status", "pending"), "⏳")
            ctk.CTkLabel(hdr, text=f"{status_icon} {task.get('query', 'Untitled Research')}", 
                         font=FONTS["subheading"], text_color=COLORS["text_primary"]).pack(side="left", fill="x", expand=True)

            if task.get("progress"):
                ctk.CTkLabel(hdr, text=f"{task['progress']}%", font=FONTS["small"],
                             text_color=COLORS["accent"]).pack(side="right")

            # Details
            details_row = ctk.CTkFrame(card, fg_color="transparent")
            details_row.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["xs"]))

            details = []
            if task.get("created_at"):
                details.append(f"Started: {task['created_at']}")
            result_count = len(task.get("results", []))
            if result_count > 0:
                details.append(f"Results: {result_count}")

            if details:
                ctk.CTkLabel(details_row, text="  •  ".join(details), font=FONTS["small"],
                             text_color=COLORS["text_muted"]).pack(side="left")

            # Results preview
            if task.get("results") and len(task["results"]) > 0:
                res_frame = ctk.CTkFrame(card, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                res_frame.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["sm"]))

                for i, result in enumerate(task["results"][:3]):
                    res_text = result if isinstance(result, str) else str(result.get("title", str(result)))[:80]
                    ctk.CTkLabel(res_frame, text=f"• {res_text}", font=FONTS["small"],
                                 text_color=COLORS["text_secondary"], wraplength=300, justify="left").pack(anchor="w", padx=SPACING["xs"], pady=2)

                if len(task["results"]) > 3:
                    ctk.CTkLabel(res_frame, text=f"... and {len(task['results']) - 3} more results", 
                                 font=FONTS["small"], text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["xs"])

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

    def _ui_call(self, fn, delay_ms: int = 0):
        """Thread-safe: schedule fn on the main Tk thread (safe from any thread)."""
        if delay_ms == 0:
            self._ui_queue.put(fn)
        else:
            self._ui_queue.put(lambda: self.root.after(delay_ms, fn))

    def _drain_ui_queue(self):
        """Main-thread poller — drains pending UI callbacks ~60 fps."""
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        self.root.after(16, self._drain_ui_queue)

    def _update_chat(self, msg: str):
        self._ui_call(lambda: self.chat.add_bot_message(msg))

    def _on_close(self):
        """Graceful shutdown: stop asyncio loop before Tkinter destroys the window."""
        # Stop the background event loop so no thread touches Tkinter after this point
        self.loop.call_soon_threadsafe(self.loop.stop)
        # Give the loop thread ~150 ms to drain, then destroy the window
        self.root.after(150, self._final_destroy)

    def _final_destroy(self):
        try:
            self._loop_thread.join(timeout=0.5)
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self._loop_thread.start()
        try:
            self.sidebar.update_status()
        except Exception as e:
            logger.error(f"sidebar.update_status failed: {e}")
        self.root.after(0, self._drain_ui_queue)   # start queue drain on main thread
        asyncio.run_coroutine_threadsafe(self._startup(), self.loop)
        self.root.mainloop()

    # ── ML Tab Methods ──────────────────────────────────────────

    def _build_ml_tab(self):
        """Build the enhanced ML tab with tasks, progress, research, and metrics."""
        tab = self.tabview.tab("  ML  ")
        tab.configure(fg_color=COLORS["bg_primary"])

        # Enhanced toolbar with multiple buttons
        toolbar = ctk.CTkFrame(tab, fg_color=COLORS["bg_secondary"], height=48, corner_radius=0)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        inner = ctk.CTkFrame(toolbar, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["xs"])

        ctk.CTkLabel(inner, text="🤖  MACHINE LEARNING", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(side="left")

        # Button group
        button_frame = ctk.CTkFrame(inner, fg_color="transparent")
        button_frame.pack(side="right")

        ctk.CTkButton(button_frame, text="+ Task", font=FONTS["small"],
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color=COLORS["bg_primary"], width=70, height=30,
                      command=self._create_ml_task_dialog).pack(side="left", padx=(0, SPACING["xs"]))

        ctk.CTkButton(button_frame, text="📊 Metrics", font=FONTS["small"],
                      fg_color="transparent", hover_color=COLORS["bg_tertiary"],
                      text_color=COLORS["text_secondary"], width=80, height=30,
                      command=self._show_ml_metrics).pack(side="left", padx=(0, SPACING["xs"]))

        ctk.CTkButton(button_frame, text="📈 Charts", font=FONTS["small"],
                      fg_color="transparent", hover_color=COLORS["bg_tertiary"],
                      text_color=COLORS["text_secondary"], width=70, height=30,
                      command=self._show_ml_charts).pack(side="left", padx=(0, SPACING["xs"]))

        ctk.CTkButton(button_frame, text="↻ Refresh", font=FONTS["small"],
                      fg_color="transparent", hover_color=COLORS["bg_tertiary"],
                      text_color=COLORS["text_secondary"], width=80, height=30,
                      command=self._refresh_ml).pack(side="left")

        # Enhanced stats bar with multiple metrics
        self.ml_stats_frame = ctk.CTkFrame(tab, fg_color=COLORS["bg_tertiary"], height=40, corner_radius=0)
        self.ml_stats_frame.pack(fill="x")
        self.ml_stats_label = ctk.CTkLabel(
            self.ml_stats_frame, text="Loading ML activities...",
            font=FONTS["small"], text_color=COLORS["text_secondary"],
        )
        self.ml_stats_label.pack(anchor="w", padx=SPACING["md"], pady=SPACING["xs"])

        # Main content area with tabs for different views
        self.ml_main_frame = ctk.CTkFrame(tab, fg_color=COLORS["bg_primary"])
        self.ml_main_frame.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["md"])

        # Create tabview for ML content
        self.ml_tabview = ctk.CTkTabview(
            self.ml_main_frame,
            fg_color=COLORS["bg_primary"],
            segmented_button_fg_color=COLORS["bg_secondary"],
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_selected_hover_color=COLORS["accent_hover"],
            segmented_button_unselected_color=COLORS["bg_tertiary"],
            segmented_button_unselected_hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            text_color_disabled=COLORS["text_muted"],
            height=30
        )
        self.ml_tabview.pack(fill="both", expand=True)
        self.ml_tabview.add("Tasks")
        self.ml_tabview.add("Progress")
        self.ml_tabview.add("Research")
        self.ml_tabview.add("Metrics")

        # Initialize content frames
        self._build_ml_tasks_tab()
        self._build_ml_progress_tab()
        self._build_ml_research_tab()
        self._build_ml_metrics_tab()

        # Auto-refresh timer — deferred so it runs after mainloop starts,
        # avoiding a blocking matplotlib font-cache scan during __init__
        self.ml_auto_refresh_id = None
        self.root.after(500, self._start_ml_auto_refresh)

    def _build_ml_tasks_tab(self):
        """Build the tasks view with completion functionality."""
        tab = self.ml_tabview.tab("Tasks")
        tab.configure(fg_color=COLORS["bg_primary"])

        self.ml_tasks_scroll = ctk.CTkScrollableFrame(
            tab, fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
        )
        self.ml_tasks_scroll.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["md"])

    def _build_ml_progress_tab(self):
        """Build the progress view with charts."""
        tab = self.ml_tabview.tab("Progress")
        tab.configure(fg_color=COLORS["bg_primary"])

        self.ml_progress_scroll = ctk.CTkScrollableFrame(
            tab, fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
        )
        self.ml_progress_scroll.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["md"])

    def _build_ml_research_tab(self):
        """Build the research view with recommendations."""
        tab = self.ml_tabview.tab("Research")
        tab.configure(fg_color=COLORS["bg_primary"])

        # Split into two sections
        research_frame = ctk.CTkFrame(tab, fg_color="transparent")
        research_frame.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["md"])

        # Learning progress section
        learning_frame = ctk.CTkFrame(research_frame, fg_color=COLORS["bg_secondary"], corner_radius=8)
        learning_frame.pack(fill="both", expand=True, side="left", padx=(0, SPACING["sm"]))

        ctk.CTkLabel(learning_frame, text="📚 Learning Progress", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        self.ml_learning_scroll = ctk.CTkScrollableFrame(
            learning_frame, fg_color=COLORS["bg_secondary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
        )
        self.ml_learning_scroll.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))

        # Recommendations section
        rec_frame = ctk.CTkFrame(research_frame, fg_color=COLORS["bg_secondary"], corner_radius=8)
        rec_frame.pack(fill="both", expand=True, side="right", padx=(SPACING["sm"], 0))

        ctk.CTkLabel(rec_frame, text="💡 Recommendations", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        self.ml_recommendations_scroll = ctk.CTkScrollableFrame(
            rec_frame, fg_color=COLORS["bg_secondary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
        )
        self.ml_recommendations_scroll.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))

    def _build_ml_metrics_tab(self):
        """Build the metrics dashboard."""
        tab = self.ml_tabview.tab("Metrics")
        tab.configure(fg_color=COLORS["bg_primary"])

        self.ml_metrics_scroll = ctk.CTkScrollableFrame(
            tab, fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["bg_tertiary"],
            scrollbar_button_hover_color=COLORS["border"],
        )
        self.ml_metrics_scroll.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["md"])

    def _refresh_ml(self):
        """Refresh all ML tab content."""
        try:
            # Load data
            tasks_data = self._load_ml_tasks()
            progress_data = self._load_learning_progress()
            research_data = self._load_research_data()

            # Update each tab
            self._refresh_ml_tasks_tab(tasks_data)
            self._refresh_ml_progress_tab(progress_data)
            self._refresh_ml_research_tab(research_data, tasks_data)
            self._refresh_ml_metrics_tab(progress_data)

            # Update stats bar
            self._update_ml_stats(tasks_data, progress_data)

        except Exception as e:
            logger.error(f"ML refresh error: {e}")
            self._set_status(f"ML refresh error: {str(e)}")

    def _load_ml_tasks(self):
        """Load ML-related tasks from tasks.json."""
        try:
            import json
            import os

            tasks_file = os.path.join(os.path.dirname(__file__), "..", "memory", "tasks.json")
            if not os.path.exists(tasks_file):
                return []

            with open(tasks_file, 'r') as f:
                tasks = json.load(f)

            # Filter for ML-related tasks
            ml_tags = ["ai_ml", "evolution", "memory", "research", "optimization", "algorithms"]
            ml_tasks = [t for t in tasks if any(tag in t.get("tags", []) for tag in ml_tags)]

            return ml_tasks

        except Exception as e:
            logger.error(f"Task loading error: {e}")
            return []

    def _load_learning_progress(self):
        """Load learning progress data."""
        try:
            import json
            import os

            progress_file = os.path.join(os.path.dirname(__file__), "..", "memory", "learning_progress.json")
            if not os.path.exists(progress_file):
                return {
                    "model_performance": [],
                    "code_quality": [],
                    "research_activities": [],
                    "memory_consolidations": []
                }

            with open(progress_file, 'r') as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"Progress loading error: {e}")
            return {
                "model_performance": [],
                "code_quality": [],
                "research_activities": [],
                "memory_consolidations": []
            }

    def _load_research_data(self):
        """Load research framework data."""
        try:
            import json
            import os

            research_file = os.path.join(os.path.dirname(__file__), "..", "memory", "ai_ml_research.json")
            if not os.path.exists(research_file):
                return {"sections": {}}

            with open(research_file, 'r') as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"Research loading error: {e}")
            return {"sections": {}}

    def _refresh_ml_tasks_tab(self, tasks_data):
        """Refresh the tasks tab with current data."""
        # Clear existing content
        for w in self.ml_tasks_scroll.winfo_children():
            w.destroy()

        if not tasks_data:
            ctk.CTkLabel(
                self.ml_tasks_scroll,
                text="No ML tasks found.\nCreate your first task to get started!",
                font=FONTS["body"], text_color=COLORS["text_muted"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")
            return

        # Group tasks by status
        status_groups = {
            "open": [],
            "in_progress": [],
            "done": []
        }

        for task in tasks_data:
            status = task.get("status", "open")
            status_groups[status].append(task)

        # Display tasks by status
        for status, tasks in status_groups.items():
            if not tasks:
                continue

            # Status header
            status_colors = {
                "open": COLORS["text_primary"],
                "in_progress": COLORS["accent"],
                "done": COLORS["success"]
            }

            status_icons = {
                "open": "⏳",
                "in_progress": "🔄",
                "done": "✅"
            }

            header_frame = ctk.CTkFrame(self.ml_tasks_scroll, fg_color=COLORS["bg_secondary"], corner_radius=6)
            header_frame.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"] if status == "open" else SPACING["xs"], SPACING["xs"]))

            ctk.CTkLabel(header_frame, text=f"{status_icons[status]} {status.replace('_', ' ').title()} ({len(tasks)})",
                         font=FONTS["subheading"], text_color=status_colors[status]).pack(anchor="w", padx=SPACING["sm"], pady=SPACING["sm"])

            # Task items
            for task in tasks:
                task_frame = ctk.CTkFrame(self.ml_tasks_scroll, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                task_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                # Task content
                content_frame = ctk.CTkFrame(task_frame, fg_color="transparent")
                content_frame.pack(fill="x", padx=SPACING["sm"], pady=SPACING["sm"])

                # Checkbox for completion
                if status != "done":
                    checkbox = ctk.CTkCheckBox(
                        content_frame, text="", width=20, height=20,
                        fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                        command=lambda t=task: self._toggle_task_completion(t)
                    )
                    checkbox.pack(side="left", padx=(0, SPACING["sm"]))
                else:
                    ctk.CTkLabel(content_frame, text="✅", font=FONTS["body"],
                                 text_color=COLORS["success"]).pack(side="left", padx=(0, SPACING["sm"]))

                # Task details
                details_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
                details_frame.pack(side="left", fill="x", expand=True)

                # Title and priority
                title_frame = ctk.CTkFrame(details_frame, fg_color="transparent")
                title_frame.pack(fill="x")

                priority_colors = {
                    "high": COLORS["error"],
                    "medium": COLORS["warning"],
                    "low": COLORS["text_muted"]
                }

                priority = task.get("priority", "medium")
                ctk.CTkLabel(title_frame, text=task["title"], font=FONTS["body"],
                             text_color=priority_colors.get(priority, COLORS["text_primary"])).pack(side="left")

                if priority == "high":
                    ctk.CTkLabel(title_frame, text="🔥", font=FONTS["small"],
                                 text_color=COLORS["error"]).pack(side="right")

                # Description
                if task.get("description"):
                    ctk.CTkLabel(details_frame, text=task["description"], font=FONTS["small"],
                                 text_color=COLORS["text_secondary"], wraplength=400).pack(anchor="w", pady=(SPACING["xs"], 0))

                # Tags and due date
                meta_frame = ctk.CTkFrame(details_frame, fg_color="transparent")
                meta_frame.pack(fill="x", pady=(SPACING["xs"], 0))

                tags = task.get("tags", [])
                if tags:
                    tags_text = "🏷️ " + ", ".join(tags)
                    ctk.CTkLabel(meta_frame, text=tags_text, font=FONTS["small"],
                                 text_color=COLORS["text_muted"]).pack(side="left")

                due = task.get("due")
                if due:
                    ctk.CTkLabel(meta_frame, text=f"📅 {due}", font=FONTS["small"],
                                 text_color=COLORS["text_muted"]).pack(side="right")

                # Action buttons
                if status == "open":
                    start_btn = ctk.CTkButton(content_frame, text="▶️ Start", font=FONTS["small"],
                                              fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                                              text_color=COLORS["bg_primary"], width=60, height=28,
                                              command=lambda t=task: self._start_task(t))
                    start_btn.pack(side="right", padx=(SPACING["xs"], 0))

                edit_btn = ctk.CTkButton(content_frame, text="✏️", font=FONTS["small"],
                                         fg_color="transparent", hover_color=COLORS["bg_tertiary"],
                                         text_color=COLORS["text_secondary"], width=30, height=28,
                                         command=lambda t=task: self._edit_task(t))
                edit_btn.pack(side="right")

    def _refresh_ml_progress_tab(self, progress_data):
        """Refresh the progress tab with charts."""
        # Clear existing content
        for w in self.ml_progress_scroll.winfo_children():
            w.destroy()

        try:
            # Generate and display progress chart
            self._generate_progress_chart(progress_data)

        except Exception as e:
            ctk.CTkLabel(
                self.ml_progress_scroll,
                text=f"Error generating progress chart: {str(e)}",
                font=FONTS["body"], text_color=COLORS["error"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")

    def _refresh_ml_research_tab(self, research_data, tasks_data):
        """Refresh the research tab with learning progress and recommendations."""
        # Update learning progress
        self._load_learning_progress_display(research_data)

        # Update recommendations
        self._update_ml_recommendations(research_data, tasks_data)

    def _refresh_ml_metrics_tab(self, progress_data):
        """Refresh the metrics tab with dashboard."""
        # Clear existing content
        for w in self.ml_metrics_scroll.winfo_children():
            w.destroy()

        try:
            # Display metrics
            self._display_ml_metrics(progress_data)

        except Exception as e:
            ctk.CTkLabel(
                self.ml_metrics_scroll,
                text=f"Error displaying metrics: {str(e)}",
                font=FONTS["body"], text_color=COLORS["error"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")

    def _update_ml_stats(self, tasks_data, progress_data):
        """Update the stats bar with summary information."""
        try:
            total_tasks = len(tasks_data)
            completed_tasks = len([t for t in tasks_data if t.get("status") == "done"])
            in_progress_tasks = len([t for t in tasks_data if t.get("status") == "in_progress"])

            model_improvements = len(progress_data.get("model_performance", []))
            code_improvements = len(progress_data.get("code_quality", []))
            research_activities = len(progress_data.get("research_activities", []))

            stats_text = f"📋 Tasks: {completed_tasks}/{total_tasks} done, {in_progress_tasks} in progress  |  🤖 Models: {model_improvements} improvements  |  💻 Code: {code_improvements} optimizations  |  🔬 Research: {research_activities} activities"

            self.ml_stats_label.configure(text=stats_text)

        except Exception as e:
            self.ml_stats_label.configure(text=f"Error loading stats: {str(e)}")

    def _generate_progress_chart(self, progress_data):
        """Generate and display progress charts using matplotlib."""
        try:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from datetime import datetime
            import matplotlib.dates as mdates

            # Create figure with subplots
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 8))
            fig.patch.set_facecolor(COLORS["bg_primary"])
            fig.suptitle('AI/ML Improvement Progress', fontsize=14, color=COLORS["text_primary"])

            # Model Performance Chart
            model_data = progress_data.get("model_performance", [])
            if model_data:
                dates = [datetime.fromisoformat(m["timestamp"]) for m in model_data]
                improvements = [m["improvement_pct"] for m in model_data]

                ax1.plot(dates, improvements, 'o-', color=COLORS["accent"], linewidth=2, markersize=4)
                ax1.set_title('Model Performance Improvements', color=COLORS["text_primary"])
                ax1.set_ylabel('Improvement %', color=COLORS["text_primary"])
                ax1.grid(True, alpha=0.3)
                ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
                ax1.tick_params(colors=COLORS["text_primary"])
            else:
                ax1.text(0.5, 0.5, 'No model data yet', ha='center', va='center',
                        transform=ax1.transAxes, color=COLORS["text_muted"])
                ax1.set_title('Model Performance', color=COLORS["text_primary"])

            # Code Quality Chart
            code_data = progress_data.get("code_quality", [])
            if code_data:
                dates = [datetime.fromisoformat(c["timestamp"]) for c in code_data]
                improvements = [c["improvement"] for c in code_data]

                ax2.bar(dates, improvements, color=COLORS["success"], alpha=0.7, width=0.5)
                ax2.set_title('Code Quality Improvements', color=COLORS["text_primary"])
                ax2.set_ylabel('Improvement Score', color=COLORS["text_primary"])
                ax2.grid(True, alpha=0.3)
                ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
                ax2.tick_params(colors=COLORS["text_primary"])
            else:
                ax2.text(0.5, 0.5, 'No code data yet', ha='center', va='center',
                        transform=ax2.transAxes, color=COLORS["text_muted"])
                ax2.set_title('Code Quality', color=COLORS["text_primary"])

            # Research Activities Chart
            research_data = progress_data.get("research_activities", [])
            if research_data:
                dates = [datetime.fromisoformat(r["timestamp"]) for r in research_data]
                topics = [r["topic"] for r in research_data]

                # Count activities per day
                from collections import Counter
                date_counts = Counter(d.date() for d in dates)

                ax3.plot(list(date_counts.keys()), list(date_counts.values()), 's-',
                        color=COLORS["warning"], linewidth=2, markersize=4)
                ax3.set_title('Research Activity Frequency', color=COLORS["text_primary"])
                ax3.set_ylabel('Activities per Day', color=COLORS["text_primary"])
                ax3.grid(True, alpha=0.3)
                ax3.tick_params(colors=COLORS["text_primary"])
            else:
                ax3.text(0.5, 0.5, 'No research data yet', ha='center', va='center',
                        transform=ax3.transAxes, color=COLORS["text_muted"])
                ax3.set_title('Research Activity', color=COLORS["text_primary"])

            # Memory Consolidation Chart
            memory_data = progress_data.get("memory_consolidations", [])
            if memory_data:
                dates = [datetime.fromisoformat(m["timestamp"]) for m in memory_data]
                duplicates = [m["duplicates_removed"] for m in memory_data]

                ax4.fill_between(dates, duplicates, color=COLORS["error"], alpha=0.6)
                ax4.set_title('Memory Optimization', color=COLORS["text_primary"])
                ax4.set_ylabel('Duplicates Removed', color=COLORS["text_primary"])
                ax4.grid(True, alpha=0.3)
                ax4.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
                ax4.tick_params(colors=COLORS["text_primary"])
            else:
                ax4.text(0.5, 0.5, 'No memory data yet', ha='center', va='center',
                        transform=ax4.transAxes, color=COLORS["text_muted"])
                ax4.set_title('Memory Optimization', color=COLORS["text_primary"])

            # Set background colors for all axes
            for ax in [ax1, ax2, ax3, ax4]:
                ax.set_facecolor(COLORS["bg_secondary"])
                ax.title.set_color(COLORS["text_primary"])
                ax.xaxis.label.set_color(COLORS["text_primary"])
                ax.yaxis.label.set_color(COLORS["text_primary"])

            plt.tight_layout()

            # Embed in tkinter
            canvas = FigureCanvasTkAgg(fig, master=self.ml_progress_scroll)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["md"])
            plt.close(fig)  # Release matplotlib's reference to avoid memory leak

        except ImportError:
            ctk.CTkLabel(
                self.ml_progress_scroll,
                text="Matplotlib not available.\nInstall with: pip install matplotlib",
                font=FONTS["body"], text_color=COLORS["error"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")
        except Exception as e:
            ctk.CTkLabel(
                self.ml_progress_scroll,
                text=f"Error generating chart: {str(e)}",
                font=FONTS["body"], text_color=COLORS["error"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")

    def _load_learning_progress_display(self, research_data):
        """Display learning progress from the learning_progress plugin."""
        # Clear existing content
        for w in self.ml_learning_scroll.winfo_children():
            w.destroy()

        try:
            # Load learning progress data
            progress_data = self._load_learning_progress()

            # Get recent activities
            recent_model = progress_data.get("model_performance", [])[-5:]  # Last 5
            recent_code = progress_data.get("code_quality", [])[-5:]  # Last 5
            recent_research = progress_data.get("research_activities", [])[-5:]  # Last 5

            if recent_model:
                model_frame = ctk.CTkFrame(self.ml_learning_scroll, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                model_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                ctk.CTkLabel(model_frame, text=f"🤖 {len(recent_model)} Model Improvements", font=FONTS["subheading"],
                             text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["sm"], pady=SPACING["sm"])

                for improvement in recent_model[-3:]:  # Show last 3
                    ctk.CTkLabel(model_frame,
                                 text=f"• {improvement['model_name']}: +{improvement['improvement_pct']:.1f}% ({improvement['metric']})",
                                 font=FONTS["small"], text_color=COLORS["text_secondary"]).pack(anchor="w", padx=SPACING["sm"])

            if recent_code:
                code_frame = ctk.CTkFrame(self.ml_learning_scroll, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                code_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                ctk.CTkLabel(code_frame, text=f"💻 {len(recent_code)} Code Improvements", font=FONTS["subheading"],
                             text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["sm"], pady=SPACING["sm"])

                for improvement in recent_code[-3:]:  # Show last 3
                    ctk.CTkLabel(code_frame,
                                 text=f"• {improvement['area']}: {improvement['improvement']:+.2f} {improvement['metric_name']}",
                                 font=FONTS["small"], text_color=COLORS["text_secondary"]).pack(anchor="w", padx=SPACING["sm"])

            if recent_research:
                research_frame = ctk.CTkFrame(self.ml_learning_scroll, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                research_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                ctk.CTkLabel(research_frame, text=f"🔬 {len(recent_research)} Research Activities", font=FONTS["subheading"],
                             text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["sm"], pady=SPACING["sm"])

                for research in recent_research[-3:]:  # Show last 3
                    ctk.CTkLabel(research_frame,
                                 text=f"• {research['topic']} ({research['type']})",
                                 font=FONTS["small"], text_color=COLORS["text_secondary"]).pack(anchor="w", padx=SPACING["sm"])

        except Exception as e:
            ctk.CTkLabel(
                self.ml_learning_scroll,
                text=f"Error loading learning progress: {str(e)}",
                font=FONTS["body"], text_color=COLORS["error"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")

    def _update_ml_recommendations(self, research_data, ml_tasks):
        """Update research recommendations based on current tasks and research framework."""
        # Clear existing content
        for w in self.ml_recommendations_scroll.winfo_children():
            w.destroy()

        recommendations = []

        # Analyze current task gaps
        current_tags = set()
        for task in ml_tasks:
            current_tags.update(task.get("tags", []))

        # Check for missing research areas
        research_practices = research_data.get("sections", {}).get("research_practices", {}).get("practices", [])
        if "research" not in current_tags and research_practices:
            recommendations.append({
                "title": "Start Research Program",
                "description": "Begin systematic review of latest ML papers and conferences",
                "priority": "high",
                "action": "Create weekly research task"
            })

        # Check for algorithm exploration
        if not any("algorithm" in tag for tag in current_tags):
            recommendations.append({
                "title": "Explore ML Algorithms",
                "description": "Investigate different ML algorithm families for current use cases",
                "priority": "medium",
                "action": "Create algorithm exploration task"
            })

        # Check for hyperparameter tuning
        if not any("optimization" in tag or "tuning" in tag for tag in current_tags):
            recommendations.append({
                "title": "Implement Hyperparameter Tuning",
                "description": "Set up systematic hyperparameter optimization for models",
                "priority": "high",
                "action": "Create tuning pipeline task"
            })

        # Display recommendations
        if not recommendations:
            ctk.CTkLabel(
                self.ml_recommendations_scroll,
                text="All research areas covered!\nGreat job maintaining comprehensive ML improvement program.",
                font=FONTS["body"], text_color=COLORS["success"],
            ).pack(padx=SPACING["md"], pady=SPACING["md"], anchor="w")
        else:
            for rec in recommendations:
                rec_frame = ctk.CTkFrame(self.ml_recommendations_scroll, fg_color=COLORS["bg_tertiary"], corner_radius=6)
                rec_frame.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                priority_color = COLORS["warning"] if rec["priority"] == "high" else COLORS["text_primary"]

                ctk.CTkLabel(rec_frame, text=f"💡 {rec['title']}", font=FONTS["body"],
                             text_color=priority_color).pack(anchor="w", padx=SPACING["sm"], pady=(SPACING["sm"], SPACING["xs"]))

                ctk.CTkLabel(rec_frame, text=rec["description"], font=FONTS["small"],
                             text_color=COLORS["text_muted"], wraplength=350).pack(anchor="w", padx=SPACING["sm"], pady=(0, SPACING["xs"]))

                ctk.CTkButton(rec_frame, text=rec["action"], font=FONTS["small"],
                              fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                              text_color=COLORS["bg_primary"], height=28,
                              command=lambda r=rec: self._create_recommended_task(r)).pack(anchor="w", padx=SPACING["sm"], pady=(0, SPACING["sm"]))

    def _display_ml_metrics(self, progress_data):
        """Display comprehensive ML metrics dashboard."""
        from datetime import datetime, timedelta

        # Calculate metrics for different time periods
        periods = [7, 30, 90]
        period_names = ["Week", "Month", "Quarter"]

        for i, (days, name) in enumerate(zip(periods, period_names)):
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            # Filter data
            model_improvements = [m for m in progress_data.get("model_performance", []) if m["timestamp"] > cutoff_iso]
            code_improvements = [c for c in progress_data.get("code_quality", []) if c["timestamp"] > cutoff_iso]
            research_activities = [r for r in progress_data.get("research_activities", []) if r["timestamp"] > cutoff_iso]
            memory_work = [m for m in progress_data.get("memory_consolidations", []) if m["timestamp"] > cutoff_iso]

            # Metrics frame
            metrics_frame = ctk.CTkFrame(self.ml_metrics_scroll, fg_color=COLORS["bg_secondary"], corner_radius=8)
            metrics_frame.pack(fill="x", padx=SPACING["sm"], pady=SPACING["xs"])

            ctk.CTkLabel(metrics_frame, text=f"📊 {name} Metrics", font=FONTS["subheading"],
                         text_color=COLORS["accent"]).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

            # Stats grid
            stats_frame = ctk.CTkFrame(metrics_frame, fg_color="transparent")
            stats_frame.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["md"]))

            # Row 1: Model and Code improvements
            row1 = ctk.CTkFrame(stats_frame, fg_color="transparent")
            row1.pack(fill="x", pady=(0, SPACING["xs"]))

            # Model improvements
            model_frame = ctk.CTkFrame(row1, fg_color=COLORS["bg_tertiary"], corner_radius=6)
            model_frame.pack(side="left", fill="x", expand=True, padx=(0, SPACING["xs"]))

            avg_model = sum(m["improvement_pct"] for m in model_improvements) / len(model_improvements) if model_improvements else 0
            ctk.CTkLabel(model_frame, text=f"🤖 Model\n{len(model_improvements)} improvements\n+{avg_model:.1f}% avg",
                         font=FONTS["mono_small"], text_color=COLORS["text_primary"]).pack(padx=SPACING["sm"], pady=SPACING["sm"])

            # Code improvements
            code_frame = ctk.CTkFrame(row1, fg_color=COLORS["bg_tertiary"], corner_radius=6)
            code_frame.pack(side="left", fill="x", expand=True, padx=(SPACING["xs"], 0))

            total_code = sum(c["improvement"] for c in code_improvements)
            ctk.CTkLabel(code_frame, text=f"💻 Code\n{len(code_improvements)} improvements\n{total_code:+.1f} total",
                         font=FONTS["mono_small"], text_color=COLORS["text_primary"]).pack(padx=SPACING["sm"], pady=SPACING["sm"])

            # Row 2: Research and Memory
            row2 = ctk.CTkFrame(stats_frame, fg_color="transparent")
            row2.pack(fill="x")

            # Research activities
            research_frame = ctk.CTkFrame(row2, fg_color=COLORS["bg_tertiary"], corner_radius=6)
            research_frame.pack(side="left", fill="x", expand=True, padx=(0, SPACING["xs"]))

            topics = len(set(r["topic"] for r in research_activities))
            ctk.CTkLabel(research_frame, text=f"🔬 Research\n{len(research_activities)} activities\n{topics} topics",
                         font=FONTS["mono_small"], text_color=COLORS["text_primary"]).pack(padx=SPACING["sm"], pady=SPACING["sm"])

            # Memory optimization
            memory_frame = ctk.CTkFrame(row2, fg_color=COLORS["bg_tertiary"], corner_radius=6)
            memory_frame.pack(side="left", fill="x", expand=True, padx=(SPACING["xs"], 0))

            duplicates = sum(m["duplicates_removed"] for m in memory_work)
            ctk.CTkLabel(memory_frame, text=f"🧠 Memory\n{len(memory_work)} consolidations\n{duplicates} duplicates removed",
                         font=FONTS["mono_small"], text_color=COLORS["text_primary"]).pack(padx=SPACING["sm"], pady=SPACING["sm"])

    def _start_ml_auto_refresh(self):
        """Start automatic refresh of ML tab."""
        self._refresh_ml()  # Initial refresh
        # Auto-refresh every 30 seconds
        self.ml_auto_refresh_id = self.root.after(30000, self._start_ml_auto_refresh)

    def _stop_ml_auto_refresh(self):
        """Stop automatic refresh of ML tab."""
        if self.ml_auto_refresh_id:
            self.root.after_cancel(self.ml_auto_refresh_id)
            self.ml_auto_refresh_id = None

    def _toggle_task_completion(self, task):
        """Toggle task completion status."""
        try:
            import json
            import os
            from datetime import datetime

            tasks_file = os.path.join(os.path.dirname(__file__), "..", "memory", "tasks.json")
            if os.path.exists(tasks_file):
                with open(tasks_file, 'r') as f:
                    tasks = json.load(f)

                # Find and update task
                for t in tasks:
                    if t["id"] == task["id"]:
                        if t.get("status") == "done":
                            t["status"] = "open"
                            if "completed" in t:
                                del t["completed"]
                        else:
                            t["status"] = "done"
                            t["completed"] = datetime.now().isoformat()
                        break

                # Save updated tasks
                with open(tasks_file, 'w') as f:
                    json.dump(tasks, f, indent=2)

                # Refresh display
                self._refresh_ml()

        except Exception as e:
            logger.error(f"Task completion toggle error: {e}")

    def _start_task(self, task):
        """Mark task as in progress."""
        try:
            import json
            import os

            tasks_file = os.path.join(os.path.dirname(__file__), "..", "memory", "tasks.json")
            if os.path.exists(tasks_file):
                with open(tasks_file, 'r') as f:
                    tasks = json.load(f)

                # Find and update task
                for t in tasks:
                    if t["id"] == task["id"]:
                        t["status"] = "in_progress"
                        break

                # Save updated tasks
                with open(tasks_file, 'w') as f:
                    json.dump(tasks, f, indent=2)

                # Refresh display
                self._refresh_ml()

        except Exception as e:
            logger.error(f"Task start error: {e}")

    def _edit_task(self, task):
        """Open task edit dialog."""
        # For now, just show a simple message. Could be enhanced with a full dialog
        self._set_status(f"Edit task: {task['title']}")

    def _create_ml_task_dialog(self):
        """Open dialog to create a new ML task."""
        # Create dialog window
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Create ML Task")
        dialog.geometry("500x600")
        dialog.transient(self.root)
        dialog.grab_set()

        # Title
        ctk.CTkLabel(dialog, text="Create New ML Task", font=FONTS["subheading"],
                     text_color=COLORS["accent"]).pack(pady=(20, 10))

        # Task title
        title_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        title_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(title_frame, text="Title:", font=FONTS["body"]).pack(anchor="w")
        title_entry = ctk.CTkEntry(title_frame, placeholder_text="Enter task title",
                                   fg_color=COLORS["bg_input"], border_color=COLORS["border"])
        title_entry.pack(fill="x", pady=(5, 0))

        # Description
        desc_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        desc_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(desc_frame, text="Description:", font=FONTS["body"]).pack(anchor="w")
        desc_textbox = ctk.CTkTextbox(desc_frame, height=80,
                                      fg_color=COLORS["bg_input"], border_color=COLORS["border"])
        desc_textbox.pack(fill="x", pady=(5, 0))

        # Category/Tags
        tags_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        tags_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(tags_frame, text="Category:", font=FONTS["body"]).pack(anchor="w")

        tag_var = ctk.StringVar(value="ai_ml")
        tag_options = ["ai_ml", "evolution", "memory", "research", "optimization"]
        tag_menu = ctk.CTkOptionMenu(tags_frame, variable=tag_var, values=tag_options,
                                     fg_color=COLORS["bg_input"], button_color=COLORS["border"])
        tag_menu.pack(fill="x", pady=(5, 0))

        # Priority
        priority_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        priority_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(priority_frame, text="Priority:", font=FONTS["body"]).pack(anchor="w")

        priority_var = ctk.StringVar(value="medium")
        priority_options = ["low", "medium", "high"]
        priority_menu = ctk.CTkOptionMenu(priority_frame, variable=priority_var, values=priority_options,
                                          fg_color=COLORS["bg_input"], button_color=COLORS["border"])
        priority_menu.pack(fill="x", pady=(5, 0))

        # Due date
        due_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        due_frame.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkLabel(due_frame, text="Due Date (optional):", font=FONTS["body"]).pack(anchor="w")
        due_entry = ctk.CTkEntry(due_frame, placeholder_text="e.g. Next Week, 2026-04-01",
                                 fg_color=COLORS["bg_input"], border_color=COLORS["border"])
        due_entry.pack(fill="x", pady=(5, 0))

        # Buttons
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        def create_task():
            title = title_entry.get().strip()
            if not title:
                return

            description = desc_textbox.get("1.0", "end").strip()
            tags = [tag_var.get()]
            priority = priority_var.get()
            due = due_entry.get().strip() or None

            self._create_new_ml_task(title, description, tags, priority, due)
            dialog.destroy()

        def cancel():
            dialog.destroy()

        ctk.CTkButton(button_frame, text="Create Task", font=FONTS["body"],
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      command=create_task).pack(side="left", padx=(0, 10))

        ctk.CTkButton(button_frame, text="Cancel", font=FONTS["body"],
                      fg_color="transparent", hover_color=COLORS["bg_tertiary"],
                      command=cancel).pack(side="left")

    def _create_new_ml_task(self, title, description, tags, priority, due):
        """Create a new ML task."""
        try:
            import json
            import os
            from datetime import datetime

            tasks_file = os.path.join(os.path.dirname(__file__), "..", "memory", "tasks.json")
            if os.path.exists(tasks_file):
                with open(tasks_file, 'r') as f:
                    tasks = json.load(f)

                # Generate new ID
                max_id = max((t["id"] for t in tasks), default=0)
                new_task = {
                    "id": max_id + 1,
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "priority": priority,
                    "status": "open",
                    "created": datetime.now().isoformat(),
                    "due": due
                }

                tasks.append(new_task)

                # Save updated tasks
                with open(tasks_file, 'w') as f:
                    json.dump(tasks, f, indent=2)

                # Refresh display
                self._refresh_ml()
                self._set_status(f"Created ML task: {title}")

        except Exception as e:
            logger.error(f"Task creation error: {e}")
            self._set_status(f"Error creating task: {str(e)}")

    def _create_recommended_task(self, recommendation):
        """Create a task from a recommendation."""
        title = recommendation["title"]
        description = recommendation["description"]
        tags = []

        # Map recommendation to appropriate tags
        if "research" in title.lower():
            tags = ["ai_ml", "research"]
        elif "algorithm" in title.lower():
            tags = ["ai_ml", "algorithms"]
        elif "tuning" in title.lower() or "optimization" in title.lower():
            tags = ["ai_ml", "optimization"]
        else:
            tags = ["ai_ml"]

        priority = recommendation.get("priority", "medium")

        self._create_new_ml_task(title, description, tags, priority, None)

    def _show_ml_metrics(self):
        """Switch to metrics tab."""
        self.ml_tabview.set("Metrics")

    def _show_ml_charts(self):
        """Switch to progress tab to show charts."""
        self.ml_tabview.set("Progress")

    def _generate_automated_tasks(self):
        """Generate automated ML improvement tasks based on system analysis."""
        try:
            import json
            import os
            from datetime import datetime, timedelta

            tasks_file = os.path.join(os.path.dirname(__file__), "..", "memory", "tasks.json")
            if not os.path.exists(tasks_file):
                return

            with open(tasks_file, 'r') as f:
                tasks = json.load(f)

            # Check for missing routine tasks
            existing_titles = {t["title"] for t in tasks}

            automated_tasks = [
                {
                    "title": "[AI/ML] Weekly Research Review",
                    "description": "Review latest papers from arXiv, NeurIPS, ICML. Focus on practical applications.",
                    "tags": ["ai_ml", "research", "self-improvement"],
                    "priority": "medium",
                    "due": "Every Friday"
                },
                {
                    "title": "[Evolution] Code Quality Audit",
                    "description": "Review codebase for optimization opportunities, DRY violations, and performance bottlenecks.",
                    "tags": ["evolution", "code-quality", "refactoring"],
                    "priority": "medium",
                    "due": "Weekly"
                },
                {
                    "title": "[Memory] Knowledge Base Consolidation",
                    "description": "Remove duplicate entries, consolidate similar information, improve categorization.",
                    "tags": ["memory", "maintenance", "optimization"],
                    "priority": "low",
                    "due": "Monthly"
                }
            ]

            new_tasks = []
            for task_data in automated_tasks:
                if task_data["title"] not in existing_titles:
                    max_id = max((t["id"] for t in tasks), default=0)
                    new_task = {
                        "id": max_id + len(new_tasks) + 1,
                        "title": task_data["title"],
                        "description": task_data["description"],
                        "tags": task_data["tags"],
                        "priority": task_data["priority"],
                        "status": "open",
                        "created": datetime.now().isoformat(),
                        "due": task_data["due"]
                    }
                    new_tasks.append(new_task)

            if new_tasks:
                tasks.extend(new_tasks)

                # Save updated tasks
                with open(tasks_file, 'w') as f:
                    json.dump(tasks, f, indent=2)

                # Refresh display
                self._refresh_ml()
                self._set_status(f"Generated {len(new_tasks)} automated ML tasks")

        except Exception as e:
            logger.error(f"Automated task generation error: {e}")



        # Generate automated tasks on startup
        self._generate_automated_tasks()
