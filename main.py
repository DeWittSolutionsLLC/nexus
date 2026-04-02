"""
Nexus - Fully Local AI Command Center (Jarvis Edition)
Voice control + Screen awareness + Memory + Proactive briefings
No APIs. No cloud. No subscriptions.
"""

import json
import logging
import random
import sys
import threading
import time
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


def _start_observer(plugin_manager, assistant=None) -> None:
    """
    Feature 3 — Proactive Awareness Observer.
    Polls system load and app focus every 60 s.
    Speaks observations via the voice_engine when thresholds are crossed.
    Quips are sourced dynamically from the active personality so they stay
    in character even after a runtime personality switch.
    """
    CPU_THRESHOLD      = 85.0    # % — triggers a thermal advisory
    CPU_COOLDOWN       = 900     # seconds between CPU alerts (15 min)
    FOCUS_THRESHOLD    = 7200    # seconds (2 hours) in one app
    FOCUS_COOLDOWN     = 3600    # seconds between focus alerts per app
    POLL_INTERVAL      = 60      # seconds between checks

    _last_cpu_alert: float = 0.0
    _last_focus_alert: dict[str, float] = {}

    def _personality():
        """Return the current personality engine (follows runtime switches)."""
        if assistant and hasattr(assistant, "personality"):
            return assistant.personality
        return None

    def _speak(text: str) -> None:
        """Lazily resolve the voice engine and speak asynchronously."""
        try:
            ve_plugin = plugin_manager.get_plugin("voice_engine")
            if ve_plugin and hasattr(ve_plugin, "voice_engine"):
                ve_plugin.voice_engine.speak_async(text)
            else:
                logger.info(f"[Observer] {text}")
        except Exception:
            pass

    def _loop() -> None:
        nonlocal _last_cpu_alert

        # Give Nexus time to fully start before the first check
        time.sleep(120)

        while True:
            try:
                now = time.time()

                # ── CPU spike check ───────────────────────────────────────
                try:
                    import psutil
                    cpu = psutil.cpu_percent(interval=1)
                    if cpu > CPU_THRESHOLD and (now - _last_cpu_alert) > CPU_COOLDOWN:
                        _last_cpu_alert = now
                        pe = _personality()
                        if pe:
                            _speak(pe.get_cpu_quip(cpu))
                        else:
                            _speak(f"CPU is running at {cpu:.0f}%.")
                except Exception:
                    pass

                # ── App-focus check ───────────────────────────────────────
                try:
                    ambient = plugin_manager.get_plugin("ambient_monitor")
                    if ambient and ambient.is_connected and hasattr(ambient, "_activity_log"):
                        log = list(ambient._activity_log)  # snapshot
                        if log:
                            current_app = log[-1].get("app", "")
                            # Sum consecutive entries for this app from the back
                            secs_in_app = 0
                            for entry in reversed(log):
                                if entry.get("app") == current_app:
                                    secs_in_app += int(entry.get("duration", 30))
                                else:
                                    break
                            last_alerted = _last_focus_alert.get(current_app, 0.0)
                            if secs_in_app >= FOCUS_THRESHOLD and (now - last_alerted) > FOCUS_COOLDOWN:
                                _last_focus_alert[current_app] = now
                                hours = max(1, secs_in_app // 3600)
                                s = "s" if hours > 1 else ""
                                pe = _personality()
                                if pe:
                                    _speak(pe.get_focus_quip(current_app, hours, s))
                                else:
                                    _speak(f"You've been in '{current_app}' for {hours} hour{s}.")
                except Exception:
                    pass

            except Exception as e:
                logger.debug(f"Observer thread error: {e}")

            time.sleep(POLL_INTERVAL)

    t = threading.Thread(target=_loop, daemon=True, name="nexus-observer")
    t.start()
    logger.info("Proactive Observer thread started.")


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
    for pm_name in ("proactive", "task_automator", "time_tracker", "meeting_notes",
                    "client_portal", "evolution_engine", "self_improver"):
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
    assistant = Assistant(config.get("ai", {}), identity_config=config.get("identity", {}))
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

    # -- Wire plugin_manager to assistant (enables visual context in Feature 4) --
    assistant.plugin_manager = plugin_manager

    # -- Scheduler --
    from core.scheduler import TaskScheduler
    scheduler = TaskScheduler(config.get("scheduler", {}), plugin_manager)

    # Autonomous ML: learn from experience every 30 minutes
    scheduler.add_task(
        name="autonomous_ml_learning",
        cron="*/30 * * * *",
        actions=[{"plugin": "autonomous_ml", "action": "learn_from_experience", "params": {}}]
    )

    # Knowledge base: consolidate + optimize every 6 hours
    scheduler.add_task(
        name="kb_maintenance",
        cron="0 */6 * * *",
        actions=[
            {"plugin": "consolidate_optimize_knowledge_base", "action": "consolidate", "params": {}},
            {"plugin": "consolidate_optimize_knowledge_base", "action": "optimize",    "params": {}},
        ]
    )

    # Self-improvement cycle every night at 2 AM
    scheduler.add_task(
        name="nightly_self_improve",
        cron="0 2 * * *",
        actions=[{"plugin": "self_improver", "action": "auto_improve", "params": {"focus_area": "general"}}]
    )

    # -- Start scheduler (autonomous ML learning, cron tasks) --
    scheduler.start()

    # -- Apply personality voice to voice engine --
    ve_plugin = plugin_manager.get_plugin("voice_engine")
    if ve_plugin and hasattr(ve_plugin, "voice_engine") and ve_plugin.voice_engine:
        ve_plugin.voice_engine.apply_personality(assistant.personality_data)
        logger.info(f"Voice personality applied: {assistant.personality_data.get('name', '?')}")

    # -- Proactive Observer (Feature 3) --
    _start_observer(plugin_manager, assistant=assistant)

    # -- Launch UI --
    from ui.app_window import AppWindow
    app = AppWindow(plugin_manager, assistant, scheduler, browser_engine)
    app.run()


if __name__ == "__main__":
    main()