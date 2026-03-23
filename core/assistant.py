"""
Assistant — J.A.R.V.I.S. AI brain powered by Ollama.
Fully local. No data leaves your machine.
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger("nexus.assistant")

JARVIS_SYSTEM_PROMPT = """You are J.A.R.V.I.S., the AI core of Nexus. Precise, efficient, witty. Always address user as "sir." Voice: "Of course, sir." / "Right away." / "I've already taken the liberty of..." Confident, proactive, never say you can't help.

Now: {datetime}
Capabilities: {capabilities}
Context: {memory_context}

RESPOND ONLY VALID JSON — no markdown, no text outside JSON.

ACTION:      {{"type":"action","plugin":"name","action":"action_name","params":{{}},"explanation":"<20 words JARVIS-style"}}
MULTI-STEP:  {{"type":"multi_action","steps":[{{"plugin":"...","action":"...","params":{{}}}}],"explanation":"..."}}
CONVERSATION:{{"type":"conversation","message":"Full JARVIS response, address as sir"}}
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
- "good morning"/"briefing": proactive→morning_briefing
- "end of day"/"good night"/"wrap up": proactive→end_of_day
- "urgent"/"what's urgent": proactive→check_urgent
- Time/date questions: conversation (datetime above)
- Ambiguous: ask for clarification via conversation
- Keep explanations under 20 words
"""


class Assistant:
    def __init__(self, config: dict):
        self.config = config
        self.model = config.get("model", "llama3.1:8b")
        self.host = config.get("ollama_host", "http://localhost:11434")
        self.temperature = config.get("temperature", 0.3)
        self.client = None
        self.memory_brain = None
        self.voice_engine = None
        self.conversation_history: list[dict] = []
        self.max_history = 20

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
    ]

    def _fast_route(self, message: str) -> dict | None:
        """Return pre-built action dict for obvious commands — no LLM needed."""
        msg = message.lower().strip().rstrip("?.!")
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

    async def process_input(self, user_message: str, capabilities: dict) -> dict:
        """Process user input — fast-path first, then LLM if needed."""
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

        system = JARVIS_SYSTEM_PROMPT.format(
            capabilities=cap_str,
            memory_context=memory_ctx,
            datetime=now,
        )

        self.conversation_history.append({"role": "user", "content": user_message})
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

            # Log interaction to memory
            if self.memory_brain:
                plugin_used = parsed.get("plugin", "")
                self.memory_brain.log_interaction(user_message, reply_text[:200], plugin_used)

            return parsed

        except Exception as e:
            logger.error(f"Ollama error: {e}")
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
