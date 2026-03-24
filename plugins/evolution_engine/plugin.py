"""
Evolution Engine Plugin — exposes autonomous plugin creation and self-refactoring
to the JARVIS routing system.

Actions:
  create_plugin   — research, write, validate, and hot-load a new plugin
  reflect_on_code — AI analysis of core/ source with optimisation suggestions
  apply_refactors — promote staged refactors after user confirmation
  skip_refactors  — discard pending refactors
"""

import logging

from core.plugin_manager import BasePlugin
from core.evolution_engine import EvolutionEngine

logger = logging.getLogger("nexus.plugins.evolution_engine")


class EvolutionEnginePlugin(BasePlugin):
    name        = "evolution_engine"
    description = "Autonomous plugin architect and self-refactoring engine."
    icon        = "⚙"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._engine: EvolutionEngine | None = None

    def set_plugin_manager(self, plugin_manager):
        # Pull the AI config (model, ollama_host) from the top-level config,
        # not the empty "evolution_engine" slice that PluginManager passes us.
        ai_cfg = plugin_manager.config.get("ai", {})
        self._engine = EvolutionEngine(plugin_manager, ai_cfg)

    async def connect(self) -> bool:
        self._connected   = True
        self._status_message = "Ready — staging/ directory initialised"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {
                "action": "create_plugin",
                "description": "Research, generate, validate, and hot-load a new plugin",
                "params": ["description"],
            },
            {
                "action": "reflect_on_code",
                "description": "AI-powered review of core/ source with refactoring suggestions",
                "params": [],
            },
            {
                "action": "apply_refactors",
                "description": "Apply the last pending refactors after user confirmation",
                "params": [],
            },
            {
                "action": "skip_refactors",
                "description": "Discard pending refactors without applying them",
                "params": [],
            },
        ]

    async def execute(self, action: str, params: dict) -> str:
        if self._engine is None:
            return (
                "The Evolution Engine hasn't been initialised yet, sir. "
                "This is likely a startup sequencing issue — a restart should resolve it."
            )
        try:
            if action == "create_plugin":
                desc = params.get("description", params.get("raw_message", "")).strip()
                if not desc:
                    return "Please describe what the plugin should do, sir."
                return await self._engine.create_plugin(desc)

            elif action == "reflect_on_code":
                return await self._engine.reflect_on_code()

            elif action == "apply_refactors":
                return await self._engine.apply_pending_refactors()

            elif action == "skip_refactors":
                return self._engine.skip_pending_refactors()

            else:
                return f"Unknown evolution action: {action}"

        except Exception as e:
            logger.exception("EvolutionEngine error")
            return f"Evolution Engine encountered an error, sir: {e}"
