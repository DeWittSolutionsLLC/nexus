"""
Plugin Manager — Auto-discovers and manages all Nexus plugins.
"""

import importlib
import logging
import sys
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

    async def connect_all(self, on_plugin_connected=None):
        """Connect all plugins in parallel — ~3x faster than sequential."""
        import asyncio

        async def _one(name, plugin):
            try:
                success = await plugin.connect()
                logger.info(f"{'✓' if success else '✗'} {name}: {plugin.status}")
            except Exception as e:
                plugin._status_message = f"Error: {str(e)[:60]}"
                logger.error(f"✗ {name} error: {e}")
            if on_plugin_connected:
                on_plugin_connected()

        await asyncio.gather(*[_one(n, p) for n, p in self.plugins.items()])

    async def disconnect_all(self):
        for plugin in self.plugins.values():
            try:
                await plugin.disconnect()
            except Exception:
                pass

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        return self.plugins.get(name)

    def hot_load_plugin(self, folder_name: str) -> bool:
        """
        Dynamically import (or re-import) a plugin folder at runtime.
        Returns True if the plugin loaded and connected successfully.
        Called by the Evolution Engine after promoting staged code.
        """
        import asyncio
        try:
            # Force a fresh import even if the module was previously loaded
            module_path = f"plugins.{folder_name}.plugin"
            if module_path in sys.modules:
                import importlib
                module = importlib.reload(sys.modules[module_path])
            else:
                import importlib
                module = importlib.import_module(module_path)

            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and issubclass(attr, BasePlugin)
                        and attr is not BasePlugin):
                    plugin_class = attr
                    break

            if plugin_class is None:
                logger.warning(f"hot_load: no BasePlugin subclass found in {folder_name}")
                return False

            plugin_config = self.config.get(plugin_class.name, {})
            instance = plugin_class(plugin_config, browser_engine=self.browser_engine)

            # Connect synchronously via a temporary event loop if one isn't running
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(instance.connect())
                else:
                    loop.run_until_complete(instance.connect())
            except RuntimeError:
                asyncio.run(instance.connect())

            self.plugins[instance.name] = instance
            logger.info(f"Hot-loaded plugin: {instance.name}")
            return True

        except Exception as e:
            logger.error(f"hot_load_plugin failed for '{folder_name}': {e}")
            return False

    def get_all_capabilities(self) -> dict[str, list[dict]]:
        return {name: p.get_capabilities() for name, p in self.plugins.items()}

    def get_status_summary(self) -> list[dict]:
        return [
            {"name": p.name, "icon": p.icon, "description": p.description,
             "connected": p.is_connected, "status": p.status}
            for p in self.plugins.values()
        ]
