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

    # -- Wire proactive agent to plugin manager --
    proactive = plugin_manager.get_plugin("proactive")
    if proactive and hasattr(proactive, "set_plugin_manager"):
        proactive.set_plugin_manager(plugin_manager)

    # -- AI Assistant --
    from core.assistant import Assistant
    assistant = Assistant(config.get("ai", {}))
    assistant.memory_brain = memory_brain
    assistant.initialize()

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