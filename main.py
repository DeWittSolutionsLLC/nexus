"""
Nexus - Fully Local AI Command Center (Jarvis Edition)
Voice control + Screen awareness + Memory + Proactive briefings
No APIs. No cloud. No subscriptions.
"""

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("nexus.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("nexus")


def load_config() -> dict:
    config_path = Path("config/settings.json")
    if not config_path.exists():
        logger.error("config/settings.json not found!")
        sys.exit(1)
    with open(config_path, "r") as f:
        return json.load(f)


def main():
    logger.info("=" * 50)
    logger.info("NEXUS - Local AI Command Center")
    logger.info("=" * 50)

    config = load_config()

    # -- Browser Engine --
    from core.browser_engine import BrowserEngine
    browser_engine = BrowserEngine(config.get("browser", {}))

    # -- Memory Brain (load early so AI has context) --
    memory_brain = None
    try:
        from plugins.memory_brain.memory import MemoryBrain
        memory_brain = MemoryBrain(config.get("memory", {}).get("memory_dir", "memory"))
        logger.info(f"Memory loaded: {len(memory_brain.contacts)} contacts, {len(memory_brain.get_open_tasks())} tasks")
    except Exception as e:
        logger.warning(f"Memory brain unavailable: {e}")

    # -- Plugin Manager --
    from core.plugin_manager import PluginManager
    plugin_manager = PluginManager(config, browser_engine=browser_engine)
    plugin_manager.discover_plugins()
    logger.info(f"Plugins: {list(plugin_manager.plugins.keys())}")

    # -- Wire plugins that need plugin_manager reference --
    for pm_name in ("proactive", "task_automator", "time_tracker", "meeting_notes", "client_portal"):
        p = plugin_manager.get_plugin(pm_name)
        if p and hasattr(p, "set_plugin_manager"):
            p.set_plugin_manager(plugin_manager)

    # -- Start background plugins --
    ambient = plugin_manager.get_plugin("ambient_monitor")
    if ambient and hasattr(ambient, "_start_monitoring"):
        pass  # started automatically in connect()

    calendar_p = plugin_manager.get_plugin("smart_calendar")
    if calendar_p and hasattr(calendar_p, "_start_reminder_thread"):
        pass  # started automatically in connect()

    # -- AI Assistant --
    from core.assistant import Assistant
    assistant = Assistant(config.get("ai", {}))
    assistant.memory_brain = memory_brain
    assistant.initialize()

    # -- Wire LLM Router to assistant for smart model switching --
    llm_router = plugin_manager.get_plugin("llm_router")
    if llm_router and hasattr(llm_router, "set_assistant"):
        llm_router.set_assistant(assistant)
        logger.info("LLM Router wired to assistant")

    # -- Wire remote-control plugins to assistant + plugin manager --
    for remote_name in ("telegram", "web_remote"):
        remote = plugin_manager.get_plugin(remote_name)
        if remote and hasattr(remote, "set_dependencies"):
            remote.set_dependencies(assistant, plugin_manager)
            logger.info(f"Wired {remote_name} to assistant")

    # -- Scheduler --
    from core.scheduler import TaskScheduler
    scheduler = TaskScheduler(config.get("scheduler", {}), plugin_manager)

    # -- Launch UI --
    from ui.app_window import AppWindow
    app = AppWindow(plugin_manager, assistant, scheduler, browser_engine)

    app.run()


if __name__ == "__main__":
    main()