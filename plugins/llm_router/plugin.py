"""
LLM Router Plugin — JARVIS automatically picks the best local model per task.

Fast model (llama3.2:3b)  → routing, quick answers, short responses
Smart model (llama3.1:8b) → code, writing, complex reasoning
Vision model (llava)      → image analysis

Profiles are configurable. Adds ~0ms overhead (pure Python matching).
"""

import asyncio
import logging

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.llm_router")

# Task → model profile mappings
TASK_PROFILES = {
    "fast": {
        "description": "Quick answers, routing, simple lookups",
        "keywords": ["weather", "time", "status", "stats", "check", "list", "show", "what is", "how much", "is ", "do i"],
        "model": "llama3.2:3b",
    },
    "smart": {
        "description": "Code, writing, complex reasoning, proposals",
        "keywords": ["write", "code", "design", "create", "build", "explain", "analyze", "generate", "plan", "propose", "debug", "fix"],
        "model": "llama3.1:8b",
    },
    "vision": {
        "description": "Image/screen analysis",
        "keywords": ["screen", "image", "screenshot", "see", "look at", "what's on"],
        "model": "llava",
    },
    "cad": {
        "description": "3D part design and CAD code generation",
        "keywords": ["design", "part", "cad", "3d", "stl", "bracket", "plate", "cylinder"],
        "model": "llama3.1:8b",  # needs reasoning capability
    },
}


class LLMRouterPlugin(BasePlugin):
    name = "llm_router"
    description = "Intelligent model routing — fast model for simple tasks, smart model for complex ones"
    icon = "🧠"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._ollama_host = config.get("ollama_host", "http://localhost:11434")
        self._assistant = None   # set externally
        self._available_models: list[str] = []
        self._routing_enabled = config.get("routing_enabled", True)
        self._current_profile = "smart"
        self._request_log: list[dict] = []

    def set_assistant(self, assistant):
        self._assistant = assistant

    async def connect(self) -> bool:
        loop = asyncio.get_event_loop()

        def _fetch_models():
            try:
                import ollama as ollama_lib
                client = ollama_lib.Client(host=self._ollama_host)
                models = client.list()
                return [m.model for m in models.models] if models.models else []
            except Exception:
                return []

        try:
            self._available_models = await asyncio.wait_for(
                loop.run_in_executor(None, _fetch_models), timeout=8.0
            )
            self._connected = True
            self._status_message = f"{len(self._available_models)} models available"
            logger.info(f"LLM Router: {self._available_models}")
            return True
        except Exception as e:
            self._status_message = f"Could not list models: {str(e)[:50]}"
            self._connected = True   # still connect — routing is additive
            return True

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "route":          self._route_query,
            "set_model":      self._set_model,
            "get_status":     self._get_status,
            "list_models":    self._list_models,
            "benchmark":      self._benchmark,
            "enable_routing": self._enable_routing,
            "disable_routing":self._disable_routing,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "route",           "description": "Automatically select the best model for a query", "params": ["query"]},
            {"action": "set_model",       "description": "Manually switch to a specific model", "params": ["model"]},
            {"action": "get_status",      "description": "Show current model routing status", "params": []},
            {"action": "list_models",     "description": "List all available Ollama models", "params": []},
            {"action": "benchmark",       "description": "Benchmark available models with a test prompt", "params": []},
            {"action": "enable_routing",  "description": "Enable automatic model routing", "params": []},
            {"action": "disable_routing", "description": "Disable routing — use single model", "params": []},
        ]

    # ── Core routing logic (also used by assistant directly) ─────────────────

    def select_model_for(self, query: str) -> str:
        """Return best model name for a given query. Called by assistant if wired."""
        if not self._routing_enabled or not self._available_models:
            return self._assistant.model if self._assistant else "llama3.1:8b"

        query_lower = query.lower()

        for profile_name, profile in TASK_PROFILES.items():
            if any(kw in query_lower for kw in profile["keywords"]):
                desired = profile["model"]
                # Use desired model if available, else fall back to any available
                if any(desired in m for m in self._available_models):
                    logger.debug(f"LLM Router: '{profile_name}' profile → {desired}")
                    return desired

        # Default to whatever the assistant is configured with
        return self._assistant.model if self._assistant else "llama3.1:8b"

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _route_query(self, params: dict) -> str:
        query = params.get("query", "")
        model = self.select_model_for(query)
        return f"🧠 Query: '{query[:60]}'\n   Routed to: {model}"

    async def _set_model(self, params: dict) -> str:
        model = params.get("model", "")
        if not model:
            return "❌ Please specify a model name."
        if self._assistant:
            self._assistant.model = model
        return f"✅ Model switched to '{model}', sir."

    async def _get_status(self, params: dict) -> str:
        current = self._assistant.model if self._assistant else "unknown"
        lines = [
            f"🧠 LLM Router Status\n",
            f"  Active model:    {current}",
            f"  Auto-routing:    {'ON' if self._routing_enabled else 'OFF'}",
            f"  Available models: {len(self._available_models)}",
            "",
            "Routing profiles:",
        ]
        for name, profile in TASK_PROFILES.items():
            available = any(profile["model"] in m for m in self._available_models)
            status = "✓" if available else "✗ not installed"
            lines.append(f"  {name:<8} → {profile['model']:<20} {status}")
            lines.append(f"           {profile['description']}")
        return "\n".join(lines)

    async def _list_models(self, params: dict) -> str:
        if not self._available_models:
            return "❌ No Ollama models found. Run: ollama list"
        lines = ["🧠 Available Ollama Models:\n"]
        current = self._assistant.model if self._assistant else ""
        for m in self._available_models:
            marker = "  ← active" if current in m else ""
            lines.append(f"  • {m}{marker}")
        lines.append(f"\nSay 'switch to model llama3.1:8b' to change.")
        return "\n".join(lines)

    async def _benchmark(self, params: dict) -> str:
        if not self._available_models:
            return "❌ No models available to benchmark."

        import time
        prompt = "Reply with exactly: 'benchmark ok'"
        results = []

        for model in self._available_models[:4]:   # limit to 4
            try:
                import ollama as ollama_lib
                loop = asyncio.get_event_loop()
                start = time.time()

                def _call(m=model):
                    c = ollama_lib.Client(host=self._ollama_host)
                    return c.chat(model=m, messages=[{"role": "user", "content": prompt}],
                                  options={"temperature": 0}, keep_alive="5m")

                await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=30.0)
                elapsed = time.time() - start
                results.append(f"  ✓ {model:<30} {elapsed:.1f}s")
            except asyncio.TimeoutError:
                results.append(f"  ✗ {model:<30} timeout")
            except Exception as e:
                results.append(f"  ✗ {model:<30} {str(e)[:40]}")

        return "🧠 Benchmark Results:\n\n" + "\n".join(results)

    async def _enable_routing(self, params: dict) -> str:
        self._routing_enabled = True
        return "✅ Automatic model routing enabled, sir. JARVIS will pick the best model per task."

    async def _disable_routing(self, params: dict) -> str:
        self._routing_enabled = False
        model = self._assistant.model if self._assistant else "current model"
        return f"✅ Routing disabled — using '{model}' for all tasks."
