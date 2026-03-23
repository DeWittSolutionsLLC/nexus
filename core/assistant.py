"""
Assistant — Local AI brain powered by Ollama.
Runs entirely on your machine. No data leaves your computer.
"""

import json
import logging

logger = logging.getLogger("nexus.assistant")

SYSTEM_PROMPT = """You are Nexus, a local AI desktop assistant. You route user requests to plugins.

Available plugins and capabilities:
{capabilities}

RESPOND WITH ONLY VALID JSON — no markdown, no backticks, no explanation outside the JSON.

For ACTION requests:
{{"type": "action", "plugin": "plugin_name", "action": "action_name", "params": {{"key": "value"}}, "explanation": "What you're doing"}}

For MULTI-STEP requests:
{{"type": "multi_action", "steps": [{{"plugin": "...", "action": "...", "params": {{}}}}], "explanation": "Plan"}}

For CHAT (greetings, questions, general knowledge):
{{"type": "conversation", "message": "Your response"}}

IMPORTANT RULES:
- For email: extract "to", "subject", "body" from the user message
- For WhatsApp/Discord: extract "contact_name"/"channel_name" and "message"
- For files: extract "path", "pattern", "extension" as needed
- If the request is ambiguous, ask for clarification via conversation type
- Keep explanations under 20 words
"""


class Assistant:
    def __init__(self, config: dict):
        self.config = config
        self.model = config.get("model", "llama3.1:8b")
        self.host = config.get("ollama_host", "http://localhost:11434")
        self.temperature = config.get("temperature", 0.3)
        self.client = None
        self.conversation_history: list[dict] = []
        self.max_history = 20

    def initialize(self):
        """Connect to the local Ollama instance."""
        try:
            import ollama as ollama_lib
            self.client = ollama_lib.Client(host=self.host)
            # Test connection by listing models
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
            logger.error("Make sure Ollama is running: https://ollama.com")
            self.client = None

    async def process_input(self, user_message: str, capabilities: dict) -> dict:
        """Process user input through the local LLM and return structured response."""
        if self.client is None:
            return self._offline_response(user_message)

        cap_str = self._format_capabilities(capabilities)
        system = SYSTEM_PROMPT.format(capabilities=cap_str)

        self.conversation_history.append({"role": "user", "content": user_message})
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

        try:
            messages = [{"role": "system", "content": system}] + self.conversation_history

            response = self.client.chat(
                model=self.model,
                messages=messages,
                options={"temperature": self.temperature},
            )

            reply_text = response["message"]["content"]
            self.conversation_history.append({"role": "assistant", "content": reply_text})

            return self._parse_response(reply_text)

        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return self._offline_response(user_message)

    def _parse_response(self, text: str) -> dict:
        """Extract JSON from the LLM response (local models can be messy)."""
        text = text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        # Give up — return as conversation
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
            (["github notification", "github notif"], "github", "check_notifications"),
            (["github issue", "create issue"], "github", "create_issue"),
            (["github pr", "pull request"], "github", "list_prs"),
            (["find file", "search file", "where is"], "file_manager", "search_files"),
            (["organize", "clean up", "sort files"], "file_manager", "organize"),
            (["list files", "show files", "what's in"], "file_manager", "list_directory"),
            (["disk usage", "disk space", "storage"], "file_manager", "disk_usage"),
            (["send text", "send sms", "text to", "google voice text"], "gvoice", "send_text"),
            (["read texts", "check texts", "my texts", "sms messages"], "gvoice", "read_texts"),
            (["call ", "make a call", "phone call"], "gvoice", "make_call"),
            (["voicemail", "check voicemail", "my voicemail"], "gvoice", "check_voicemail"),
        ]

        for keywords, plugin, action in routes:
            if any(k in msg for k in keywords):
                return {
                    "type": "action",
                    "plugin": plugin,
                    "action": action,
                    "params": {"raw_message": message},
                    "explanation": f"Routing to {plugin} (offline mode)",
                }

        return {
            "type": "conversation",
            "message": (
                "⚠️ Ollama isn't running so I'm in basic mode. "
                "I can still route commands — try:\n"
                "• 'check email'\n• 'send WhatsApp to Mom'\n"
                "• 'organize my Downloads'\n• 'check Discord messages'\n\n"
                "To enable smart mode, start Ollama and restart Nexus."
            ),
        }

    def clear_history(self):
        self.conversation_history.clear()
