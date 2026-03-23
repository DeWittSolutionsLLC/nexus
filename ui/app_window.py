"""App Window - Main shell connecting UI, AI, browser, voice, and plugins."""

import asyncio
import threading
import logging
import customtkinter as ctk
from ui.theme import COLORS
from ui.chat_panel import ChatPanel
from ui.sidebar import Sidebar

logger = logging.getLogger("nexus.ui")


class AppWindow:
    def __init__(self, plugin_manager, assistant, scheduler, browser_engine):
        self.plugin_manager = plugin_manager
        self.assistant = assistant
        self.scheduler = scheduler
        self.browser_engine = browser_engine
        self.voice_engine = None

        self.loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)

        self._setup_window()
        self._build_layout()

    def _setup_window(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.root = ctk.CTk()
        self.root.title("Nexus - Local AI Command Center")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)
        self.root.configure(fg_color=COLORS["bg_primary"])

    def _build_layout(self):
        self.sidebar = Sidebar(self.root, self.plugin_manager, on_quick_action=self._on_quick_action)
        self.sidebar.pack(side="left", fill="y")
        ctk.CTkFrame(self.root, fg_color=COLORS["border"], width=1).pack(side="left", fill="y")
        self.chat = ChatPanel(self.root, on_send=self._on_user_send)
        self.chat.pack(side="right", fill="both", expand=True)

    def _on_user_send(self, text: str):
        self.chat.add_loading()
        asyncio.run_coroutine_threadsafe(self._process_command(text), self.loop)

    def _on_quick_action(self, cmd: str):
        self.chat.inject_text(cmd)

    async def _process_command(self, text: str):
        try:
            capabilities = self.plugin_manager.get_all_capabilities()
            result = await self.assistant.process_input(text, capabilities)
            rtype = result.get("type", "conversation")
            speak_text = result.get("speak", "")

            if rtype == "conversation":
                msg = result.get("message", "I'm not sure how to help with that.")
                self._reply(msg, speak_text or msg[:200])

            elif rtype == "action":
                explanation = result.get("explanation", "Processing...")
                self._reply(f">> {explanation}", speak_text)
                plugin = self.plugin_manager.get_plugin(result.get("plugin", ""))
                if plugin and plugin.is_connected:
                    out = await plugin.execute(result["action"], result.get("params", {}))
                    # Speak a short summary of the result, not the whole thing
                    short = out[:150].split("\n")[0] if out else "Done."
                    self._reply(out, short)
                elif plugin:
                    self._reply(f"Warning: {plugin.name} isn't connected. Check sidebar.")
                else:
                    self._reply(f"Plugin '{result.get('plugin')}' not found.")

            elif rtype == "multi_action":
                self._reply(f">> {result.get('explanation', 'Running...')}", speak_text)
                for i, step in enumerate(result.get("steps", []), 1):
                    plugin = self.plugin_manager.get_plugin(step.get("plugin", ""))
                    if plugin and plugin.is_connected:
                        out = await plugin.execute(step["action"], step.get("params", {}))
                        self._reply(f"Step {i}: {out}")

            elif rtype == "schedule":
                task_id = self.scheduler.add_task(
                    result.get("explanation", "Task"),
                    result.get("cron", ""),
                    result.get("actions", [])
                )
                self._reply(f"Scheduled: {result.get('explanation')}\nCron: {result.get('cron')}", speak_text)

            elif rtype == "error":
                self._reply(f"Error: {result.get('message', 'Unknown error')}")

        except Exception as e:
            logger.error(f"Error: {e}")
            self._reply(f"Error: {str(e)}")

    def _reply(self, message: str, speak: str = ""):
        """Show message in chat and optionally speak it."""
        self.root.after(0, lambda: (self.chat.remove_loading(), self.chat.add_bot_message(message)))
        if speak and self.voice_engine:
            self.voice_engine.speak_async(speak)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _startup(self):
        """Start browser and connect all plugins."""
        try:
            self._update_chat("Starting browser...")
            await self.browser_engine.start()
            self._update_chat("Connecting plugins...")
            await self.plugin_manager.connect_all()
        except Exception as e:
            logger.error(f"Startup error: {e}")
            self._update_chat(f"Startup issue: {str(e)[:80]}. Some plugins may not be connected.")
        finally:
            self.root.after(0, self.sidebar.update_status)
            # Wire voice engine to mic button now that plugins are connected
            self.root.after(0, self._wire_voice)

    def _update_chat(self, msg: str):
        self.root.after(0, lambda: self.chat.add_bot_message(msg))

    def _on_voice_command(self, text: str):
        """Called from background voice thread when wake word + command is detected."""
        if text == "[wake]":
            if self.voice_engine:
                self.voice_engine.speak_async("Yes?")
            return
        self.root.after(0, lambda t=text: self._handle_voice_command(t))

    def _handle_voice_command(self, text: str):
        """Process a voice command on the main thread."""
        self.chat.add_user_message(f"[Voice] {text}")
        self.chat.add_loading()
        asyncio.run_coroutine_threadsafe(self._process_command(text), self.loop)

    def _wire_voice(self):
        """Connect the voice engine to the mic button and TTS after plugins are ready."""
        voice_plugin = self.plugin_manager.get_plugin("voice")
        if voice_plugin and hasattr(voice_plugin, "voice_engine") and voice_plugin.voice_engine:
            ve = voice_plugin.voice_engine
            self.voice_engine = ve
            self.chat.set_voice_engine(ve)
            self.assistant.voice_engine = ve
            # Start always-on wake-word listening ("Nexus, ...")
            ve.start_listening(on_command=self._on_voice_command)
            voice_plugin._status_message = "Listening for 'Nexus'"
            # Refresh sidebar to show updated status
            self.sidebar.update_status()
            # Say hello
            ve.speak_async("Nexus online. All systems ready.")
            logger.info("Voice active — TTS and wake-word listening started")

    def run(self):
        self._loop_thread.start()
        self.sidebar.update_status()
        asyncio.run_coroutine_threadsafe(self._startup(), self.loop)
        self.root.mainloop()

        # Cleanup
        asyncio.run_coroutine_threadsafe(self.browser_engine.stop(), self.loop)
        asyncio.run_coroutine_threadsafe(self.plugin_manager.disconnect_all(), self.loop)
        self.loop.call_soon_threadsafe(self.loop.stop)