"""
Plugin Manager — Auto-discovers and manages all Nexus plugins.
"""

import importlib
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger("nexus.plugins")


class BasePlugin(ABC):
    name: str = "unnamed"
    description: str = ""
    icon: str = "🔌"

    def __init__(self, config: dict, browser_engine=None):
        self.config = config
        self.browser = browser_engine
        self._connected = False
        self._status_message = "Not initialized"

    @abstractmethod
    async def execute(self, action: str, params: dict) -> str:
        ...

    @abstractmethod
    def get_capabilities(self) -> list[dict]:
        ...

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = "Ready"
        return True

    async def disconnect(self):
        self._connected = False
        self._status_message = "Disconnected"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def status(self) -> str:
        return self._status_message


class PluginManager:
    def __init__(self, config: dict, browser_engine=None):
        self.config = config
        self.browser_engine = browser_engine
        self.plugins: dict[str, BasePlugin] = {}
        self._plugin_dir = Path(__file__).parent.parent / "plugins"

    def discover_plugins(self):
        if not self._plugin_dir.exists():
            logger.warning(f"Plugin directory not found: {self._plugin_dir}")
            return

        for folder in self._plugin_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            plugin_file = folder / "plugin.py"
            if not plugin_file.exists():
                continue
            try:
                self._load_plugin(folder.name)
            except Exception as e:
                logger.error(f"Failed to load plugin '{folder.name}': {e}")

    def _load_plugin(self, folder_name: str):
        module_path = f"plugins.{folder_name}.plugin"
        module = importlib.import_module(module_path)

        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                plugin_class = attr
                break

        if plugin_class is None:
            return

        plugin_config = self.config.get(plugin_class.name, {})
        instance = plugin_class(plugin_config, browser_engine=self.browser_engine)
        self.plugins[instance.name] = instance
        logger.info(f"Loaded plugin: {instance.name} — {instance.description}")

    async def connect_all(self):
        for name, plugin in self.plugins.items():
            try:
                success = await plugin.connect()
                logger.info(f"{'✓' if success else '✗'} {name}: {plugin.status}")
            except Exception as e:
                plugin._status_message = f"Error: {e}"
                logger.error(f"✗ {name} error: {e}")

    async def disconnect_all(self):
        for plugin in self.plugins.values():
            try:
                await plugin.disconnect()
            except Exception:
                pass

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        return self.plugins.get(name)

    def get_all_capabilities(self) -> dict[str, list[dict]]:
        return {name: p.get_capabilities() for name, p in self.plugins.items()}

    def get_status_summary(self) -> list[dict]:
        return [
            {"name": p.name, "icon": p.icon, "description": p.description,
             "connected": p.is_connected, "status": p.status}
            for p in self.plugins.values()
        ]
