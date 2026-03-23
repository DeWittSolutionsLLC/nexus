"""
Scheduler — Recurring and one-off automated tasks via APScheduler.
"""

import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("nexus.scheduler")


class TaskScheduler:
    def __init__(self, config: dict, plugin_manager):
        self.config = config
        self.plugin_manager = plugin_manager
        tz = config.get("timezone", "America/Detroit")
        self.scheduler = AsyncIOScheduler(timezone=tz)
        self.tasks: list[dict] = []

    def start(self):
        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self):
        self.scheduler.shutdown(wait=False)

    def add_task(self, name: str, cron: str, actions: list[dict]) -> str:
        task_id = f"task_{len(self.tasks)}_{name.replace(' ', '_')[:20]}"
        trigger = CronTrigger.from_crontab(cron)
        self.scheduler.add_job(self._run_actions, trigger=trigger, args=[actions], id=task_id, name=name)
        self.tasks.append({
            "id": task_id, "name": name, "cron": cron,
            "actions": actions, "created": datetime.now().isoformat(), "enabled": True,
        })
        logger.info(f"Scheduled: {name} [{cron}]")
        return task_id

    async def _run_actions(self, actions: list[dict]):
        for spec in actions:
            plugin = self.plugin_manager.get_plugin(spec["plugin"])
            if plugin and plugin.is_connected:
                try:
                    result = await plugin.execute(spec["action"], spec.get("params", {}))
                    logger.info(f"Scheduled {spec['plugin']}.{spec['action']} → {result[:80]}")
                except Exception as e:
                    logger.error(f"Scheduled task error: {e}")

    def remove_task(self, task_id: str) -> bool:
        try:
            self.scheduler.remove_job(task_id)
            self.tasks = [t for t in self.tasks if t["id"] != task_id]
            return True
        except Exception:
            return False

    def get_tasks(self) -> list[dict]:
        return self.tasks
