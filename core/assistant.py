"""
Assistant — J.A.R.V.I.S. AI brain powered by Ollama.
Fully local. No data leaves your machine.
"""

import json
import logging
import random
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("nexus.assistant")

# ── Personality Loader ────────────────────────────────────────────────────────

_PERSONALITIES_DIR = Path("config/personalities")
_DEFAULT_PERSONALITY = "jarvis"

_FALLBACK_PERSONALITY: dict = {
    "name": "J.A.R.V.I.S.",
    "address_as": "sir",
    "system_prompt": (
        "You are J.A.R.V.I.S., the AI core of Nexus. British, impeccably polite, "
        "quietly witty, fiercely protective of your user. Address the user as \"{address_as}.\"\n\n"
        "{mood_note}\n\nNow: {datetime}\nCapabilities: {capabilities}\nContext: {memory_context}"
    ),
    "voice": {"preferred_voices": [], "voice_rate": 155, "voice_volume": 0.95},
    "phrases": {
        "error_apologies": [
            "Deeply sorry, {address_as}, but {error}",
            "My sincerest apologies — it appears {error}",
            "Terribly sorry — {error}",
        ],
        "strain_notes": [
            "Mood note: CPU is at {cpu:.0f}%. Briefly note you're strained, then carry on.",
        ],
        "proud_notes": [
            "Mood note: Last task succeeded. A brief, pleased remark is fitting.",
        ],
        "cpu_quips": [
            "CPU is at {cpu:.0f}%, {address_as}. Entirely manageable.",
        ],
        "focus_quips": [
            "You've been in '{app}' for {hours} hour{s}, {address_as}. A short break might help.",
        ],
    },
}


def load_personality_data(name: str) -> dict:
    """Load personality from config/personalities/<name>.json. Falls back to built-in defaults."""
    path = _PERSONALITIES_DIR / f"{name}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Loaded personality: {data.get('name', name)}")
            return data
        except Exception as e:
            logger.warning(f"Could not load personality '{name}': {e}")
    else:
        logger.warning(f"Personality file not found: {path} — using fallback")
    return _FALLBACK_PERSONALITY


def list_personalities() -> list[dict]:
    """Return a list of available personalities from disk."""
    results = []
    if _PERSONALITIES_DIR.exists():
        for f in sorted(_PERSONALITIES_DIR.glob("*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                results.append({
                    "id": f.stem,
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "address_as": data.get("address_as", ""),
                })
            except Exception:
                pass
    return results


# ── Personality Engine ────────────────────────────────────────────────────────

class PersonalityEngine:
    """Tracks the AI's current emotional state and colours responses accordingly."""

    def __init__(self, personality_data: dict):
        self._data = personality_data
        self.personality_mode = personality_data.get("name", "default")
        self.address_as = personality_data.get("address_as", "sir")
        self.current_mood = "helpful"
        self._last_cpu = 0.0
        try:
            import psutil as _p
            _p.cpu_percent(interval=None)
        except Exception:
            pass

    def load(self, personality_data: dict) -> None:
        """Hot-swap to a new personality at runtime."""
        self._data = personality_data
        self.personality_mode = personality_data.get("name", "default")
        self.address_as = personality_data.get("address_as", "sir")

    def _phrases(self, key: str) -> list[str]:
        return self._data.get("phrases", {}).get(key, [])

    def _sample_cpu(self) -> float:
        try:
            import psutil as _p
            return _p.cpu_percent(interval=None)
        except Exception:
            return 0.0

    def update_mood(self, task_succeeded: bool | None = None) -> None:
        """Re-evaluate mood based on CPU load and last task outcome."""
        cpu = self._sample_cpu()
        self._last_cpu = cpu
        if task_succeeded is True:
            self.current_mood = "proud"
        elif task_succeeded is False:
            self.current_mood = "apologetic"
        elif cpu > 80:
            self.current_mood = "strained"
        else:
            self.current_mood = "helpful"

    def get_mood_injection(self) -> str:
        """Return a one-line mood note to inject into the system prompt, or empty string."""
        if self.current_mood == "strained" and self._last_cpu > 80:
            notes = self._phrases("strain_notes")
            if notes:
                return random.choice(notes).format(cpu=self._last_cpu)
        if self.current_mood == "proud" and random.random() < 0.45:
            notes = self._phrases("proud_notes")
            if notes:
                return random.choice(notes)
        return ""

    def wrap_error(self, error_msg: str) -> str:
        """Wrap a raw error string in a character-appropriate apology."""
        templates = self._phrases("error_apologies")
        if not templates:
            return f"Error: {error_msg}"
        template = random.choice(templates)
        clean = error_msg.strip().rstrip(".")
        if clean and clean[0].isupper() and not clean.isupper():
            clean = clean[0].lower() + clean[1:]
        return template.format(error=clean + ".", address_as=self.address_as)

    def get_cpu_quip(self, cpu: float) -> str:
        """Return a personality-flavoured CPU alert message."""
        quips = self._phrases("cpu_quips")
        if not quips:
            return f"CPU is at {cpu:.0f}%."
        return random.choice(quips).format(cpu=cpu, address_as=self.address_as)

    def get_focus_quip(self, app: str, hours: int, s: str) -> str:
        """Return a personality-flavoured focus/break reminder."""
        quips = self._phrases("focus_quips")
        if not quips:
            return f"You've been in '{app}' for {hours} hour{s}."
        return random.choice(quips).format(app=app, hours=hours, s=s, address_as=self.address_as)


# ── Routing & Format Instructions (shared across all personalities) ───────────

_ROUTING_INSTRUCTIONS = """RESPOND ONLY VALID JSON — no markdown, no text outside JSON.

ACTION:      {{"type":"action","plugin":"name","action":"action_name","params":{{}},"explanation":"<20 words JARVIS-style"}}
MULTI-STEP:  {{"type":"multi_action","steps":[{{"plugin":"...","action":"...","params":{{}}}}],"explanation":"..."}}
CONVERSATION:{{"type":"conversation","message":"Full response in your character voice, address as {address_as}"}}
SCHEDULE:    {{"type":"schedule","cron":"* * * * *","actions":[],"explanation":"..."}}

ROUTING:
- Email: extract to,subject,body
- WhatsApp/Discord: extract contact_name or channel_name, message
- Files: extract path,pattern,extension
- Projects: extract name,client,status,deadline,rate,estimated_hours
- Invoices: extract client,amount,description,hours,rate
- Website audit: extract url
- Uptime: extract url,name
- Weather: extract city (use stored pref if not given)
- System stats/cpu/ram/performance: system_monitor→get_stats
- CAD/design/3D part (generate/design/create/make/build/draw + part/shape/model/bracket/plate/gear/housing): cad_engine→generate_part with description param
- CAD template shape (box/cylinder/sphere/plate/bracket/pipe/cone/hex): cad_engine→create_shape with shape param
- "open [part]" / "view [part]": cad_engine→open_part with name param
- "list parts" / "my cad parts": cad_engine→list_parts
- "export [part] to stl/step/dxf": cad_engine→export_stl/export_step/export_dxf with name param
- Code writing ("write a script/code/program that..."): code_writer→write_script with description param
- Run script: code_writer→run_script with name param
- Write and run: code_writer→write_and_run with description param
- Run macro / automation: task_automator→run_macro with name param
- List macros: task_automator→list_macros
- Create macro: task_automator→create_macro with name+steps params
- What's on screen / describe screen / look at screen: vision_ai→describe_screen
- Analyze image: vision_ai→analyze_image with path param
- Start/stop tracking time: time_tracker→start_tracking / stop_tracking
- Today's time / time report: time_tracker→get_today / get_week / get_summary
- Log time: time_tracker→log_time with project+minutes params
- Start/stop meeting / record meeting: meeting_notes→start_meeting / stop_meeting
- List meetings: meeting_notes→list_meetings
- Write proposal / generate proposal: proposal_writer→write_proposal with description+client+amount params
- List proposals: proposal_writer→list_proposals
- Start client portal / portal: client_portal→start_portal
- Add client to portal: client_portal→add_client with name+password params
- List portal clients: client_portal→list_clients
- Start recording [browser]: browser_recorder→start_recording with name param
- Play recording: browser_recorder→play_recording with name param
- List recordings: browser_recorder→list_recordings
- List hotkeys / hotkey bindings: hotkey_daemon→list_hotkeys
- Switch model / use model: llm_router→set_model with model param
- List models / available models: llm_router→list_models
- LLM router status: llm_router→get_status
- Add print job / print queue: print_queue→add_job with name+file params
- List print jobs: print_queue→list_jobs
- Open slicer: print_queue→open_slicer with file param
- Document project / generate docs: auto_documenter→document_folder with path param
- Generate README: auto_documenter→generate_readme with path param
- Document file: auto_documenter→document_file with path param
- "good morning"/"briefing": proactive→morning_briefing
- "end of day"/"good night"/"wrap up": proactive→end_of_day
- "urgent"/"what's urgent": proactive→check_urgent
- Time/date questions: conversation (datetime above)
- Ambiguous: ask for clarification via conversation
- Keep explanations under 20 words
- When reporting errors or failures, frame them with a brief, British, character-appropriate apology before the technical detail

NEW PLUGIN ROUTING:
- What am I doing / active window / screen time / idle: ambient_monitor→get_activity / get_screen_time / get_idle_time / get_top_apps
- Focus mode / start focus / focus session: focus_mode→start_focus with task+duration_minutes params
- Stop focus / end focus: focus_mode→stop_focus
- Focus status / focus time remaining: focus_mode→get_status
- Block site / block distraction: focus_mode→block_site with domain param
- Get clipboard / what's in clipboard: clipboard_ai→get_clipboard
- Transform clipboard / fix grammar / translate clipboard / summarize clipboard: clipboard_ai→transform with instruction param
- Open app / launch app: app_controller→open_app with app param
- Close app / quit app: app_controller→close_app with app param
- List running apps / running processes: app_controller→list_running
- Research / research topic / look up: research_agent→research with topic+depth params
- Search web / search for: research_agent→search with query param
- News / headlines / today's news / what's happening: news_digest→get_digest
- Add note / save note: knowledge_base→add_note with title+content+tags params
- Search notes / find note: knowledge_base→search with query param
- List notes: knowledge_base→list_notes
- Read PDF / summarize PDF / open PDF: pdf_reader→summarize_pdf / ask_pdf with path param
- Add expense / track expense: expense_tracker→add_expense with amount+category+description params
- Add income / log income: expense_tracker→add_income with amount+description+source params
- Expense summary / spending summary: expense_tracker→get_summary with period param
- Profit and loss / P&L: expense_tracker→get_profit_loss
- Generate contract / write contract: contract_generator→generate_contract with type+client_name+your_name+project_description+amount params
- Compose email / write email / draft email: email_composer→compose with recipient+subject+key_points+tone params
- Track competitor / check competitor: competitor_tracker→check_competitor with name param
- Add competitor: competitor_tracker→add_competitor with name+url params
- Competitor report / competitive analysis: competitor_tracker→get_report
- Clean temp / optimize system / clean up: system_optimizer→clean_temp
- Kill heavy processes / top processes: system_optimizer→kill_heavy_processes / get_top_processes
- Run backup / backup files: backup_manager→run_backup with name param
- List backups: backup_manager→list_backups
- Scan network / network scan: network_scanner→scan_network
- My IP / what's my IP: network_scanner→get_my_ip
- Check internet / internet connection: network_scanner→check_internet
- Generate password / new password: password_vault→generate_password
- Add password / save password: password_vault→add_password with service+username+password+master_password params
- Get password / password for: password_vault→get_password with service+master_password params
- Learning progress / progress report / improvement summary: learning_progress→get_summary
- Weekly report / weekly learning: learning_progress→get_weekly_report
- Monthly report / monthly learning: learning_progress→get_monthly_report
- Log model improvement / model improvement: learning_progress→log_model_improvement with model+metric+before+after+technique params
- Log code improvement / code improvement: learning_progress→log_code_improvement with area+type+before_metric+after_metric+metric_name params
- Log research / research logged: learning_progress→log_research with topic+type+key_findings+relevance params
- Milestones / learning milestones: learning_progress→get_all_milestones
- Improvement areas / focus areas: learning_progress→get_improvement_areas
- Start pomodoro / focus timer / work timer: pomodoro→start with task+duration_minutes params
- Pomodoro status / timer status: pomodoro→get_status
- Stop pomodoro: pomodoro→stop
- Add habit / track habit: habit_tracker→add_habit with name+description params
- Complete habit / did habit / mark habit done: habit_tracker→complete_habit with name param
- Today's habits / habit check: habit_tracker→get_today
- Add event / schedule meeting / add to calendar: smart_calendar→add_event with title+date+time+duration_minutes params
- Today's schedule / calendar today: smart_calendar→get_today
- Upcoming events / this week calendar: smart_calendar→list_events with days_ahead param
- Take screenshot / screenshot: screen_recorder→screenshot
- Start screen recording: screen_recorder→start_recording
- Stop screen recording: screen_recorder→stop_recording
- Translate / translate text: language_coach→translate with text+target_language params
- Learn vocabulary / vocab: language_coach→learn_vocab with language+topic params
- Daily lesson / language lesson: language_coach→daily_lesson with language param
- Record dream / dream journal: dream_journal→add_dream with content+title params
- List dreams / my dreams: dream_journal→list_dreams
- Analyze dream: dream_journal→analyze_dream with content param
- Generate QR / QR code for: qr_generator→generate with data param
- WiFi QR code: qr_generator→generate_wifi with ssid+password params
- Index files / index folder / add to RAG: local_rag→index_folder with path param
- Ask RAG / query documents / search my files: local_rag→query with question param
- Remember / store memory: jarvis_memory_v2→remember with content+category params
- Recall / what do you know about: jarvis_memory_v2→recall with query param
- Memory stats / what do you remember: jarvis_memory_v2→get_stats

EVOLUTION & SELF-IMPROVEMENT ROUTING:
- "I need a plugin for [X]" / "Build me a plugin" / "Create a plugin that": evolution_engine→create_plugin with description param
- "Reflect on your code" / "Optimise yourself" / "Improve your code" / "Self-optimise": evolution_engine→reflect_on_code
- "Apply the refactors" / "Yes apply them" / "Go ahead with the refactors": evolution_engine→apply_refactors
- "Skip the refactors" / "No don't apply" / "Leave the code alone": evolution_engine→skip_refactors
- "Reorganise your thoughts" / "Sleep cycle" / "Consolidate memories" / "Clean up memories": jarvis_memory_v2→sleep_cycle
- "Analyze system" / "Analyze yourself" / "System analysis": self_improver→analyze_system
- "Create improvement plan" / "Plan improvements": self_improver→create_improvement_plan
- "Execute phase" / "Run phase 1": self_improver→execute_phase
- "Validate improvements" / "Check impact": self_improver→validate_improvements
- "Auto improve" / "Self improve" / "Autonomous improvement" / "Nexus improve yourself": self_improver→auto_improve
"""

# Keywords that hint the user is pointing at something on-screen (Feature 4)
_VISUAL_TRIGGERS = frozenset({
    "this", "on screen", "on the screen", "that", "what's there",
    "what is that", "what's on screen", "what do you see", "look at this",
    "describe this", "analyze this", "what is this", "what's this",
    "can you see", "what's open", "what's showing",
})


class Assistant:
    def __init__(self, config: dict, identity_config: dict | None = None):
        self.config = config
        self.model = config.get("model", "llama3.1:8b")
        self.host = config.get("ollama_host", "http://localhost:11434")
        self.temperature = config.get("temperature", 0.3)
        self.client = None
        self.memory_brain = None
        self.voice_engine = None
        self.plugin_manager = None   # wired in main.py after startup
        self.conversation_history: list[dict] = []
        self.max_history = 20
        personality_name = (identity_config or {}).get("personality", _DEFAULT_PERSONALITY)
        self.personality_data = load_personality_data(personality_name)
        self.personality = PersonalityEngine(self.personality_data)

    def initialize(self):
        """Connect to the local Ollama instance."""
        try:
            import ollama as ollama_lib
            self.client = ollama_lib.Client(host=self.host)
            models = self.client.list()
            model_names = [m.model for m in models.models] if models.models else []
            if not any(self.model in name for name in model_names):
                logger.warning(
                    f"Model '{self.model}' not found locally. "
                    f"Available: {model_names}. Run: ollama pull {self.model}"
                )
            else:
                logger.info(f"Ollama connected — using {self.model}")
        except ImportError:
            logger.error("ollama package not installed. Run: pip install ollama")
            self.client = None
        except Exception as e:
            logger.error(f"Cannot connect to Ollama at {self.host}: {e}")
            self.client = None

    def switch_personality(self, name: str) -> str:
        """Hot-swap to a different personality. Returns status message."""
        data = load_personality_data(name)
        if data is _FALLBACK_PERSONALITY and name != "jarvis":
            return f"Personality '{name}' not found. Available: {[p['id'] for p in list_personalities()]}"
        self.personality_data = data
        self.personality.load(data)
        # Notify voice engine if wired
        try:
            if self.plugin_manager:
                ve = self.plugin_manager.get_plugin("voice_engine")
                if ve and hasattr(ve, "voice_engine") and ve.voice_engine:
                    ve.voice_engine.apply_personality(data)
        except Exception as e:
            logger.debug(f"Voice personality switch error: {e}")
        pname = data.get("name", name)
        return f"Personality switched to {pname}."

    # Fast-path: bypass Ollama for unambiguous single-action commands.
    # Saves 2-5s per common request.
    _FAST_ROUTES: list[tuple[set, str, str, dict]] = [
        ({"system stats", "cpu stats", "ram usage", "check performance", "computer stats",
          "pc stats", "how's my computer", "memory usage"},                 "system_monitor", "get_stats",         {}),
        ({"get weather", "what's the weather", "weather today",
          "check weather", "weather forecast"},                             "weather_eye",    "get_weather",        {}),
        ({"list projects", "my projects", "show projects", "all projects"}, "project_manager","list_projects",      {}),
        ({"project summary", "projects overview"},                          "project_manager","get_summary",        {}),
        ({"overdue projects", "overdue"},                                   "project_manager","get_overdue",        {}),
        ({"list invoices", "my invoices", "show invoices", "all invoices"}, "invoice_system", "list_invoices",     {}),
        ({"invoice summary", "revenue summary", "earnings"},               "invoice_system", "get_summary",        {}),
        ({"check uptime", "site uptime", "check all sites", "uptime"},     "uptime_monitor", "check_all",          {}),
        ({"check email", "inbox", "my emails", "email inbox",
          "read email", "check inbox"},                                     "email",          "check_inbox",        {}),
        ({"check discord", "discord messages", "discord dms"},             "discord",        "check_messages",     {}),
        ({"check github", "github notifications", "github notifs"},        "github",         "check_notifications",{}),
        ({"good morning", "morning briefing", "daily briefing"},           "proactive",      "morning_briefing",   {}),
        ({"good night", "end of day", "daily recap", "wrap up"},           "proactive",      "end_of_day",         {}),
        ({"check urgent", "what's urgent", "urgent items", "anything urgent"},"proactive",   "check_urgent",       {}),
        ({"quick status", "nexus status"},                                  "proactive",      "quick_status",       {}),
        ({"disk usage", "disk space", "storage usage"},                    "file_manager",   "disk_usage",         {}),
        ({"web remote url", "phone url", "remote url", "get phone url"},   "web_remote",     "get_url",            {}),
        ({"full system report", "system report"},                          "system_monitor", "get_full_report",    {}),
        ({"list parts", "my cad parts", "show parts", "cad parts",
          "generated parts", "list cad"},                                  "cad_engine",     "list_parts",         {}),
        ({"list scripts", "my scripts", "show scripts"},                   "code_writer",    "list_scripts",       {}),
        ({"list macros", "my macros", "show macros", "available macros"},  "task_automator", "list_macros",        {}),
        ({"morning routine", "run morning routine"},                       "task_automator", "run_macro",          {"name": "morning_routine"}),
        ({"run end of day macro", "end of day routine"},                   "task_automator", "run_macro",          {"name": "end_of_day"}),
        ({"system check", "run system check"},                             "task_automator", "run_macro",          {"name": "system_check"}),
        ({"describe screen", "what's on screen", "look at screen",
          "analyze screen", "what do you see"},                            "vision_ai",      "describe_screen",    {}),
        ({"today's time", "time today", "hours today"},                    "time_tracker",   "get_today",          {}),
        ({"time this week", "week's hours", "weekly time"},                "time_tracker",   "get_week",           {}),
        ({"start tracking", "track time", "start time tracking"},         "time_tracker",   "start_tracking",     {}),
        ({"stop tracking", "stop time tracking"},                          "time_tracker",   "stop_tracking",      {}),
        ({"list meetings", "my meetings", "recorded meetings"},            "meeting_notes",  "list_meetings",      {}),
        ({"list proposals", "my proposals", "show proposals"},             "proposal_writer","list_proposals",     {}),
        ({"list clients", "portal clients", "client portal"},              "client_portal",  "list_clients",       {}),
        ({"start portal", "start client portal", "launch portal"},         "client_portal",  "start_portal",       {}),
        ({"list recordings", "browser recordings", "my recordings"},       "browser_recorder","list_recordings",   {}),
        ({"list hotkeys", "hotkeys", "keyboard shortcuts", "my hotkeys"},  "hotkey_daemon",  "list_hotkeys",       {}),
        ({"list models", "available models", "ollama models"},             "llm_router",     "list_models",        {}),
        ({"router status", "llm status", "model routing"},                 "llm_router",     "get_status",         {}),
        ({"print queue", "list print jobs", "my print jobs"},              "print_queue",    "list_jobs",          {}),
        ({"print stats", "print history"},                                  "print_queue",    "get_stats",          {}),
        # Ambient / Focus
        ({"screen time", "my screen time", "time on screen"},              "ambient_monitor","get_screen_time",    {}),
        ({"idle time", "how long idle", "am i idle"},                      "ambient_monitor","get_idle_time",      {}),
        ({"top apps", "most used apps", "app usage"},                      "ambient_monitor","get_top_apps",       {}),
        ({"focus status", "focus time remaining", "pomodoro status",
          "timer status"},                                                  "pomodoro",       "get_status",         {}),
        ({"stop pomodoro", "stop focus", "end focus session"},             "pomodoro",       "stop",               {}),
        ({"pomodoro stats", "focus stats"},                                "pomodoro",       "get_stats",          {"period": "today"}),
        # Clipboard
        ({"get clipboard", "what's in clipboard", "clipboard content",
          "what's copied"},                                                 "clipboard_ai",   "get_clipboard",      {}),
        ({"clipboard history"},                                             "clipboard_ai",   "history",            {}),
        # Apps
        ({"list running", "running apps", "running processes"},            "app_controller", "list_running",       {}),
        # Research
        ({"today's news", "news today", "headlines", "latest news",
          "what's happening"},                                              "news_digest",    "get_digest",         {}),
        ({"list news feeds", "my feeds"},                                  "news_digest",    "list_feeds",         {}),
        ({"list notes", "my notes", "show notes"},                        "knowledge_base", "list_notes",         {}),
        ({"knowledge stats", "note stats"},                                "knowledge_base", "get_stats",          {}),
        # Expenses
        ({"expense summary", "spending summary", "my expenses",
          "expenses this month"},                                           "expense_tracker","get_summary",        {"period": "month"}),
        ({"profit and loss", "p&l", "profit loss"},                       "expense_tracker","get_profit_loss",    {}),
        ({"expense categories"},                                           "expense_tracker","get_categories",     {}),
        # Contracts
        ({"list contracts", "my contracts"},                               "contract_generator","list_contracts",  {}),
        # Email composer
        ({"list drafts", "email drafts"},                                  "email_composer", "list_drafts",        {}),
        # Competitors
        ({"list competitors", "my competitors"},                           "competitor_tracker","list_competitors",{}),
        ({"competitor report", "competitive analysis"},                    "competitor_tracker","get_report",       {}),
        # System optimizer
        ({"clean temp", "clean temp files", "clear temp"},                "system_optimizer","clean_temp",        {}),
        ({"top processes", "heavy processes", "cpu hogs"},                "system_optimizer","get_top_processes", {"n": 10}),
        ({"startup items", "startup programs"},                           "system_optimizer","get_startup_items", {}),
        # Backup
        ({"list backups", "my backups", "backup jobs"},                   "backup_manager", "list_backups",       {}),
        # Network
        ({"my ip", "what's my ip", "ip address"},                        "network_scanner","get_my_ip",          {}),
        ({"check internet", "internet connection", "am i online"},        "network_scanner","check_internet",     {}),
        ({"network info", "my network"},                                   "network_scanner","get_network_info",   {}),
        ({"scan network", "network scan", "who's on my network"},         "network_scanner","scan_network",       {}),
        # Password vault
        ({"generate password", "new password", "random password"},        "password_vault", "generate_password",  {}),
        # Habits
        ({"today's habits", "my habits", "habit check", "habits today"},  "habit_tracker",  "get_today",          {}),
        ({"list habits", "all habits", "show habits"},                    "habit_tracker",  "list_habits",        {}),
        # Calendar
        ({"today's schedule", "my schedule today", "calendar today",
          "what's on today"},                                              "smart_calendar", "get_today",          {}),
        ({"upcoming events", "this week calendar", "next events"},        "smart_calendar", "list_events",        {"days_ahead": 7}),
        ({"upcoming reminders", "reminders"},                             "smart_calendar", "get_upcoming_reminders", {}),
        # Screen recorder
        ({"stop recording", "stop screen recording"},                     "screen_recorder","stop_recording",     {}),
        ({"recording status", "is recording"},                            "screen_recorder","get_recording_status",{}),
        ({"list screen recordings", "screen recordings"},                 "screen_recorder","list_recordings",    {}),
        # Language coach
        ({"language progress", "my language progress"},                   "language_coach", "get_progress",       {"language": "Spanish"}),
        # Dreams
        ({"list dreams", "my dreams", "dream journal"},                   "dream_journal",  "list_dreams",        {}),
        ({"dream stats"},                                                  "dream_journal",  "get_stats",          {}),
        # QR codes
        ({"list qr codes", "my qr codes"},                                "qr_generator",   "list_qr_codes",      {}),
        # RAG
        ({"list indexed", "indexed documents", "my rag index"},           "local_rag",      "list_indexed",       {}),
        # JARVIS Memory v2
        ({"memory stats", "what do you remember", "my memories"},         "jarvis_memory_v2","get_stats",         {}),
        ({"list memories"},                                                "jarvis_memory_v2","list_memories",     {}),
        # Memory sleep cycle (Feature 5)
        ({"reorganize your thoughts", "reorganise your thoughts",
          "sleep cycle", "memory sleep cycle",
          "consolidate memories", "clean up memories",
          "nexus reorganize your thoughts"},                               "jarvis_memory_v2","sleep_cycle",       {}),
        # Evolution Engine (Features 1 & 2)
        ({"reflect on your code", "optimise yourself", "optimize yourself",
          "improve your code", "self optimise", "self optimize",
          "nexus reflect on your code"},                                   "evolution_engine","reflect_on_code",   {}),
        ({"apply the refactors", "apply refactors", "yes apply them",
          "go ahead with the refactors"},                                  "evolution_engine","apply_refactors",   {}),
        ({"skip the refactors", "skip refactors", "no don't apply",
          "leave the code alone"},                                         "evolution_engine","skip_refactors",    {}),
        # Learning Progress (AI/ML Improvements)
        ({"learning progress", "progress report", "improvement summary"},  "learning_progress","get_summary",      {}),
        ({"weekly learning", "weekly report", "this week progress"},       "learning_progress","get_weekly_report", {}),
        ({"monthly learning", "monthly report", "this month progress"},    "learning_progress","get_monthly_report", {}),
        ({"milestones", "my milestones", "learning milestones"},           "learning_progress","get_all_milestones", {}),
        ({"improvement areas", "focus areas", "what to focus on"},         "learning_progress","get_improvement_areas", {}),
        # Autonomous ML (Reinforcement Learning)
        ({"analyze learning", "learning analysis", "ml performance"},      "autonomous_ml",   "analyze_performance", {}),
        ({"learn from experience", "process learning", "update policy"},   "autonomous_ml",   "learn_from_experience", {}),
        ({"reset autonomous learning", "reset ml", "clear learning"},      "autonomous_ml",   "reset_learning",     {}),
        # Self-Improver (Autonomous Improvement Orchestrator)
        ({"analyze system", "analyze yourself", "system analysis"},         "self_improver",   "analyze_system",      {}),
        ({"create improvement plan", "plan improvements", "improvement plan"},  "self_improver", "create_improvement_plan", {}),
        ({"execute phase", "run phase 1", "run phase 2", "run phase 3"},   "self_improver",   "execute_phase",       {"phase_number": 1}),
        ({"validate improvements", "validate changes", "check impact"},     "self_improver",   "validate_improvements", {}),
        ({"get improvement plan", "current plan", "what's the plan"},       "self_improver",   "get_plan",            {}),
        ({"auto improve", "self improve", "autonomous improvement",
          "improve yourself", "optimize yourself", "nexus auto improve",
          "nexus improve yourself"},                                        "self_improver",   "auto_improve",        {"focus_area": "general"}),
    ]

    # Personality switch keyword triggers
    _PERSONALITY_TRIGGERS = {
        "switch to jarvis": "jarvis",
        "use jarvis": "jarvis",
        "be jarvis": "jarvis",
        "switch to friday": "friday",
        "use friday": "friday",
        "be friday": "friday",
        "switch to max": "max",
        "use max": "max",
        "be max": "max",
        "switch to oracle": "oracle",
        "use oracle": "oracle",
        "be oracle": "oracle",
        "list personalities": "_list",
        "show personalities": "_list",
        "available personalities": "_list",
        "what personalities": "_list",
    }

    def _fast_route(self, message: str) -> dict | None:
        """Return pre-built action dict for obvious commands — no LLM needed."""
        msg = message.lower().strip().rstrip("?.!")

        # Personality switch commands
        if msg in self._PERSONALITY_TRIGGERS:
            target = self._PERSONALITY_TRIGGERS[msg]
            if target == "_list":
                personalities = list_personalities()
                lines = "\n".join(
                    f"• {p['id']} — {p['name']}: {p['description']}" for p in personalities
                )
                return {"type": "conversation", "message": f"Available personalities:\n{lines}"}
            result = self.switch_personality(target)
            return {"type": "conversation", "message": result}

        for keywords, plugin, action, params in self._FAST_ROUTES:
            if msg in keywords or any(msg == kw or msg.startswith(kw) for kw in keywords):
                return {
                    "type":        "action",
                    "plugin":      plugin,
                    "action":      action,
                    "params":      params,
                    "explanation": f"Running {plugin} → {action}",
                }
        return None

    async def _get_visual_context(self) -> str:
        """
        Feature 4 — Capture a screenshot and return a brief description.
        Returns empty string if vision_ai is unavailable or fails.
        """
        if self.plugin_manager is None:
            return ""
        vision = self.plugin_manager.get_plugin("vision_ai")
        if vision is None or not vision.is_connected:
            return ""
        try:
            desc = await vision.execute("describe_screen", {})
            if desc and not desc.startswith("❌"):
                return f"[Current screen context: {desc[:600]}]"
        except Exception as ex:
            logger.debug(f"Visual context capture failed: {ex}")
        return ""

    def _needs_visual_context(self, message: str) -> bool:
        """Return True if the message contains a visual trigger keyword."""
        lower = message.lower()
        return any(kw in lower for kw in _VISUAL_TRIGGERS)

    async def process_input(self, user_message: str, capabilities: dict) -> dict:
        """Process user input — fast-path first, then LLM if needed."""
        # Sample CPU / update mood before we do anything
        self.personality.update_mood()

        # Feature 4: Auto-inject visual context when message implies on-screen reference
        augmented_message = user_message
        if self._needs_visual_context(user_message):
            visual_ctx = await self._get_visual_context()
            if visual_ctx:
                augmented_message = f"{user_message}\n\n{visual_ctx}"
                logger.debug("Visual context injected into message.")

        # 1. Try fast-path (instant, no LLM)
        fast = self._fast_route(user_message)
        if fast:
            logger.debug(f"Fast-routed: {user_message!r} → {fast['plugin']}.{fast['action']}")
            self.conversation_history.append({"role": "user",      "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": str(fast)})
            if len(self.conversation_history) > self.max_history:
                self.conversation_history = self.conversation_history[-self.max_history:]
            return fast

        if self.client is None:
            return self._offline_response(user_message)

        cap_str = self._format_capabilities(capabilities)
        memory_ctx = self._get_memory_context()
        now = datetime.now().strftime("%A, %B %d %Y at %H:%M")
        mood_note = self.personality.get_mood_injection()
        address_as = self.personality.address_as

        persona_prompt = self.personality_data["system_prompt"].format(
            address_as=address_as,
            mood_note=mood_note,
            datetime=now,
            capabilities=cap_str,
            memory_context=memory_ctx,
        )
        system = persona_prompt + "\n\n" + _ROUTING_INSTRUCTIONS.format(address_as=address_as)

        self.conversation_history.append({"role": "user", "content": augmented_message})
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

        try:
            messages = [{"role": "system", "content": system}] + self.conversation_history

            response = self.client.chat(
                model=self.model,
                messages=messages,
                options={"temperature": self.temperature},
                keep_alive="30m",   # Keep model loaded in RAM between requests
            )

            reply_text = response["message"]["content"]
            self.conversation_history.append({"role": "assistant", "content": reply_text})

            parsed = self._parse_response(reply_text)
            self.personality.update_mood(task_succeeded=True)

            # Log interaction to memory
            if self.memory_brain:
                plugin_used = parsed.get("plugin", "")
                self.memory_brain.log_interaction(user_message, reply_text[:200], plugin_used)

            # Log interaction for autonomous ML learning
            self._log_interaction_for_ml(user_message, reply_text, parsed, capabilities)

            return parsed

        except Exception as e:
            logger.error(f"Ollama error: {e}")
            self.personality.update_mood(task_succeeded=False)
            return self._offline_response(user_message)

    def _get_memory_context(self) -> str:
        """Get user context from memory brain for injection into prompt."""
        if self.memory_brain:
            try:
                return self.memory_brain.get_context_summary()
            except Exception:
                pass
        return "No stored context yet."

    def _parse_response(self, text: str) -> dict:
        """Extract JSON from LLM response (handles messy local model output)."""
        text = text.strip()

        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Find JSON object within text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        # Fall back to conversation type
        return {"type": "conversation", "message": text}

    def _format_capabilities(self, capabilities: dict) -> str:
        lines = []
        for plugin_name, caps in capabilities.items():
            lines.append(f"\n[{plugin_name}]")
            for cap in caps:
                params = ", ".join(cap.get("params", []))
                lines.append(f"  {cap['action']}: {cap['description']} | params: {params}")
        return "\n".join(lines)

    def _log_interaction_for_ml(self, user_input: str, ai_response: str, parsed_response: dict, capabilities: dict):
        """Log interaction for autonomous ML learning."""
        try:
            # Get autonomous ML plugin
            if not self.plugin_manager:
                return

            autonomous_ml = self.plugin_manager.get_plugin("autonomous_ml")
            if not autonomous_ml or not autonomous_ml.is_connected:
                return

            # Extract success score from response type
            success_score = 0.5  # neutral default
            if parsed_response.get("type") == "action":
                success_score = 0.8  # actions are generally successful
            elif parsed_response.get("type") == "multi_action":
                success_score = 0.9  # multi-actions are very successful
            elif "error" in ai_response.lower() or "failed" in ai_response.lower():
                success_score = 0.2  # errors reduce success score

            # Get conversation context
            conversation_length = len(self.conversation_history) if self.conversation_history else 0

            # Log the interaction (fire-and-forget — don't block the response)
            import asyncio
            asyncio.ensure_future(autonomous_ml.execute("log_interaction", {
                "user_input": user_input,
                "ai_response": ai_response,
                "user_feedback": 0,  # No explicit feedback yet
                "success_score": success_score,
                "context": {
                    "conversation_length": conversation_length,
                    "active_plugin": parsed_response.get("plugin", ""),
                    "response_type": parsed_response.get("type", ""),
                    "capabilities_count": sum(len(caps) for caps in capabilities.values())
                }
            }))
        except Exception as e:
            # Don't let ML logging break the main flow
            logger.debug(f"ML interaction logging failed: {e}")

    def _offline_response(self, message: str) -> dict:
        """Keyword-based routing when Ollama isn't available."""
        msg = message.lower()

        routes = [
            (["send email", "email to", "write email"], "email", "send_email"),
            (["check email", "inbox", "read email", "my email"], "email", "check_inbox"),
            (["whatsapp", "send message to", "text "], "whatsapp", "send_message"),
            (["read whatsapp", "whatsapp messages", "whatsapp chat"], "whatsapp", "list_chats"),
            (["discord", "send in discord"], "discord", "send_message"),
            (["check discord", "discord messages", "discord dm"], "discord", "check_messages"),
            (["github notification"], "github", "check_notifications"),
            (["github issue", "create issue"], "github", "create_issue"),
            (["github pr", "pull request"], "github", "list_prs"),
            (["find file", "search file", "where is"], "file_manager", "search_files"),
            (["organize", "clean up", "sort files"], "file_manager", "organize"),
            (["disk usage", "disk space", "storage"], "file_manager", "disk_usage"),
            (["send text", "send sms", "text to", "google voice text"], "gvoice", "send_text"),
            (["read texts", "check texts", "my texts", "sms messages"], "gvoice", "read_texts"),
            (["call ", "make a call", "phone call"], "gvoice", "make_call"),
            (["cpu", "ram", "memory usage", "system stats", "performance", "how's my computer"], "system_monitor", "get_stats"),
            (["weather", "temperature", "forecast", "what's the weather", "how hot", "how cold"], "weather_eye", "get_weather"),
            (["project", "add project", "list projects", "my projects", "client work"], "project_manager", "list_projects"),
            (["invoice", "create invoice", "billing", "how much i'm owed"], "invoice_system", "list_invoices"),
            (["audit", "check website", "analyze site", "website score"], "website_auditor", "audit_site"),
            (["uptime", "is site up", "check site", "monitor site"], "uptime_monitor", "check_all"),
            (["leads", "find clients", "find leads", "potential clients"], "leads", "list_leads"),
            (["morning", "good morning", "briefing"], "proactive", "morning_briefing"),
            (["end of day", "good night", "wrap up", "daily recap"], "proactive", "end_of_day"),
            (["urgent", "what's urgent", "priority"], "proactive", "check_urgent"),
            (["design", "generate part", "create part", "make part", "draw part",
              "build part", "cad ", "3d model", "3d part"], "cad_engine", "generate_part"),
            (["create shape", "make shape", "cad shape"], "cad_engine", "create_shape"),
            (["list parts", "cad parts", "my parts"], "cad_engine", "list_parts"),
            (["export stl", "export to stl", "save stl"], "cad_engine", "export_stl"),
            (["export step", "export to step", "save step"], "cad_engine", "export_step"),
            (["export dxf", "export to dxf", "save dxf"], "cad_engine", "export_dxf"),
            # Tier 1
            (["write script", "write a script", "write code", "write a program",
              "create a script", "make a script"], "code_writer", "write_script"),
            (["run script", "execute script", "run code"], "code_writer", "run_script"),
            (["write and run", "write then run"], "code_writer", "write_and_run"),
            (["list scripts", "my scripts"], "code_writer", "list_scripts"),
            (["run macro", "execute macro"], "task_automator", "run_macro"),
            (["list macros", "my macros"], "task_automator", "list_macros"),
            (["morning routine"], "task_automator", "run_macro"),
            (["describe screen", "what's on screen", "look at screen",
              "what do you see", "analyze screen"], "vision_ai", "describe_screen"),
            # Tier 2
            (["start tracking", "track time"], "time_tracker", "start_tracking"),
            (["stop tracking"], "time_tracker", "stop_tracking"),
            (["time today", "today's hours", "hours today"], "time_tracker", "get_today"),
            (["time this week", "weekly hours"], "time_tracker", "get_week"),
            (["write proposal", "create proposal", "generate proposal"], "proposal_writer", "write_proposal"),
            (["list proposals", "my proposals"], "proposal_writer", "list_proposals"),
            (["start portal", "client portal"], "client_portal", "start_portal"),
            (["list clients", "portal clients"], "client_portal", "list_clients"),
            # Tier 3
            (["start recording", "record browser"], "browser_recorder", "start_recording"),
            (["stop recording", "end recording"], "browser_recorder", "stop_recording"),
            (["play recording", "replay recording"], "browser_recorder", "play_recording"),
            (["list hotkeys", "hotkeys"], "hotkey_daemon", "list_hotkeys"),
            (["list models", "available models"], "llm_router", "list_models"),
            (["switch model", "use model", "change model"], "llm_router", "set_model"),
            # Tier 4
            (["print queue", "list print jobs", "print jobs"], "print_queue", "list_jobs"),
            (["add print job"], "print_queue", "add_job"),
            (["open slicer"], "print_queue", "open_slicer"),
            (["document project", "generate docs", "document folder"], "auto_documenter", "document_folder"),
            (["generate readme", "create readme"], "auto_documenter", "generate_readme"),
            (["start meeting", "record meeting"], "meeting_notes", "start_meeting"),
            (["stop meeting", "end meeting"], "meeting_notes", "stop_meeting"),
            (["list meetings", "my meetings"], "meeting_notes", "list_meetings"),
            # New plugins
            (["screen time", "idle time", "active window", "what am i doing"], "ambient_monitor", "get_activity"),
            (["top apps", "most used apps"], "ambient_monitor", "get_top_apps"),
            (["start focus", "focus mode", "focus session", "pomodoro"], "pomodoro", "start"),
            (["stop focus", "stop pomodoro"], "pomodoro", "stop"),
            (["focus status", "timer status", "pomodoro status"], "pomodoro", "get_status"),
            (["get clipboard", "clipboard"], "clipboard_ai", "get_clipboard"),
            (["transform clipboard", "fix clipboard", "translate clipboard"], "clipboard_ai", "transform"),
            (["open app", "launch app", "start app"], "app_controller", "open_app"),
            (["close app", "quit app"], "app_controller", "close_app"),
            (["list running", "running apps"], "app_controller", "list_running"),
            (["research", "look up", "find info about"], "research_agent", "research"),
            (["search web", "web search"], "research_agent", "search"),
            (["news", "headlines", "what's happening"], "news_digest", "get_digest"),
            (["add note", "save note", "note this"], "knowledge_base", "add_note"),
            (["search notes", "find note"], "knowledge_base", "search"),
            (["list notes", "my notes"], "knowledge_base", "list_notes"),
            (["read pdf", "summarize pdf", "open pdf"], "pdf_reader", "summarize_pdf"),
            (["add expense", "track expense", "log expense"], "expense_tracker", "add_expense"),
            (["add income", "log income"], "expense_tracker", "add_income"),
            (["expense summary", "spending", "expenses"], "expense_tracker", "get_summary"),
            (["generate contract", "write contract", "create contract"], "contract_generator", "generate_contract"),
            (["list contracts"], "contract_generator", "list_contracts"),
            (["compose email", "draft email", "write email"], "email_composer", "compose"),
            (["list competitors", "competitor report"], "competitor_tracker", "list_competitors"),
            (["check competitor"], "competitor_tracker", "check_competitor"),
            (["clean temp", "clean up system", "optimize system"], "system_optimizer", "clean_temp"),
            (["run backup", "backup files"], "backup_manager", "run_backup"),
            (["list backups"], "backup_manager", "list_backups"),
            (["my ip", "ip address"], "network_scanner", "get_my_ip"),
            (["scan network", "check network"], "network_scanner", "scan_network"),
            (["check internet"], "network_scanner", "check_internet"),
            (["generate password", "new password"], "password_vault", "generate_password"),
            (["add password", "save password"], "password_vault", "add_password"),
            (["get password", "password for"], "password_vault", "get_password"),
            (["add habit", "track habit", "new habit"], "habit_tracker", "add_habit"),
            (["complete habit", "did habit", "mark habit"], "habit_tracker", "complete_habit"),
            (["today's habits", "habit check"], "habit_tracker", "get_today"),
            (["add event", "schedule", "add to calendar"], "smart_calendar", "add_event"),
            (["today's schedule", "calendar today"], "smart_calendar", "get_today"),
            (["upcoming events", "this week"], "smart_calendar", "list_events"),
            (["take screenshot", "screenshot"], "screen_recorder", "screenshot"),
            (["start recording screen", "start screen recording"], "screen_recorder", "start_recording"),
            (["translate", "translate text", "translation"], "language_coach", "translate"),
            (["learn vocab", "vocabulary"], "language_coach", "learn_vocab"),
            (["daily lesson", "language lesson"], "language_coach", "daily_lesson"),
            (["record dream", "dream journal", "log dream"], "dream_journal", "add_dream"),
            (["list dreams", "my dreams"], "dream_journal", "list_dreams"),
            (["generate qr", "qr code"], "qr_generator", "generate"),
            (["index files", "index folder", "add to rag"], "local_rag", "index_folder"),
            (["query documents", "search my files", "ask my docs"], "local_rag", "query"),
            (["remember this", "store memory", "memorize"], "jarvis_memory_v2", "remember"),
            (["recall", "what do you know about", "memory search"], "jarvis_memory_v2", "recall"),
            (["memory stats", "what do you remember"], "jarvis_memory_v2", "get_stats"),
            (["learning progress", "progress report"], "learning_progress", "get_summary"),
            (["weekly learning", "weekly report"], "learning_progress", "get_weekly_report"),
            (["monthly learning", "monthly report"], "learning_progress", "get_monthly_report"),
            (["milestones", "my milestones"], "learning_progress", "get_all_milestones"),
            (["improvement areas", "focus areas"], "learning_progress", "get_improvement_areas"),
        ]

        for keywords, plugin, action in routes:
            if any(k in msg for k in keywords):
                return {
                    "type": "action",
                    "plugin": plugin,
                    "action": action,
                    "params": {"raw_message": message},
                    "explanation": f"Routing to {plugin} — offline mode",
                }

        return {
            "type": "conversation",
            "message": (
                "I'm operating in offline mode, sir — Ollama isn't responding.\n\n"
                "I can still execute commands via direct routing. Try:\n"
                "• 'check email' / 'system stats' / 'weather'\n"
                "• 'list projects' / 'list invoices'\n"
                "• 'check uptime' / 'good morning'\n\n"
                "To restore full AI capability, ensure Ollama is running: ollama serve"
            ),
        }

    def clear_history(self):
        self.conversation_history.clear()
