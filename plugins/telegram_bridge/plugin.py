"""
Telegram Bridge Plugin — Control Nexus from your phone via Telegram.

Setup (one-time, ~2 minutes):
  1. Open Telegram and message @BotFather
  2. Send /newbot, follow prompts, copy the token
  3. Add token to config/settings.json under "telegram": {"bot_token": "..."}
  4. Start Nexus, message your bot /id to get your chat ID
  5. Add your chat ID to "allowed_chat_ids": [123456789]

Then text your bot from anywhere in the world to control Nexus.
Processing happens 100% on your machine.
"""

import asyncio
import json
import logging
import threading
import time

import requests as _requests

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.telegram")


class TelegramBridgePlugin(BasePlugin):
    name = "telegram"
    description = "Control Nexus from your phone via Telegram bot"
    icon = "📱"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.token: str = config.get("bot_token", "").strip()
        self.allowed_ids: list[int] = [int(x) for x in config.get("allowed_chat_ids", [])]
        self.notify_ids: list[int] = [int(x) for x in config.get("notify_chat_ids", self.allowed_ids)]

        self._offset = 0
        self._polling = False
        self._poll_thread: threading.Thread | None = None

        # Set externally after plugin discovery
        self._assistant = None
        self._plugin_manager = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # Dedicated async loop for Telegram async work
        self._tg_loop = asyncio.new_event_loop()
        self._tg_thread = threading.Thread(target=self._run_tg_loop, daemon=True, name="telegram-loop")
        self._tg_thread.start()

    def set_dependencies(self, assistant, plugin_manager):
        self._assistant = assistant
        self._plugin_manager = plugin_manager

    def _run_tg_loop(self):
        asyncio.set_event_loop(self._tg_loop)
        self._tg_loop.run_forever()

    # ── Lifecycle ──────────────────────────────────────────────

    async def connect(self) -> bool:
        if not self.token:
            self._status_message = "No token — see settings.json telegram.bot_token"
            self._connected = False
            return False

        try:
            resp = _requests.get(
                f"https://api.telegram.org/bot{self.token}/getMe",
                timeout=8,
            )
            if not resp.ok:
                self._status_message = f"Bad token (HTTP {resp.status_code})"
                self._connected = False
                return False

            bot = resp.json()["result"]
            username = bot.get("username", "unknown")
            self._connected = True
            self._status_message = f"@{username} — polling"

            self._start_polling()
            logger.info(f"Telegram bridge online as @{username}")
            return True

        except _requests.exceptions.ConnectionError:
            self._status_message = "No internet connection"
            self._connected = False
            return False
        except Exception as e:
            self._status_message = f"Error: {str(e)[:50]}"
            self._connected = False
            return False

    async def disconnect(self):
        self._polling = False
        self._connected = False
        self._status_message = "Disconnected"

    # ── Polling ────────────────────────────────────────────────

    def _start_polling(self):
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="telegram-poll")
        self._poll_thread.start()

    def _poll_loop(self):
        """Long-poll Telegram for updates in a background thread."""
        logger.info("Telegram: polling started")
        while self._polling:
            try:
                updates = self._get_updates(timeout=20)
                for update in updates:
                    self._dispatch_update(update)
            except Exception as e:
                if self._polling:
                    logger.warning(f"Telegram poll error: {e}")
                    time.sleep(5)

    def _get_updates(self, timeout: int = 20) -> list[dict]:
        resp = _requests.get(
            f"https://api.telegram.org/bot{self.token}/getUpdates",
            params={"offset": self._offset, "timeout": timeout},
            timeout=timeout + 5,
        )
        if not resp.ok:
            return []
        data = resp.json()
        updates = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    def _dispatch_update(self, update: dict):
        """Handle an incoming Telegram update (message or callback)."""
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        sender = msg.get("from", {}).get("username", str(chat_id))

        if not text:
            return

        # Security: only allowed IDs (or open if list is empty)
        if self.allowed_ids and chat_id not in self.allowed_ids:
            self._send(chat_id, "⛔ Unauthorized.")
            logger.warning(f"Telegram: unauthorized message from {chat_id} (@{sender})")
            return

        logger.info(f"Telegram: [{chat_id}] @{sender}: {text}")

        # Built-in slash commands
        if text == "/start" or text == "/help":
            self._send(
                chat_id,
                "◆ *NEXUS — J.A.R.V.I.S.* online.\n\n"
                "Send any command in plain English:\n"
                "• _check my email_\n"
                "• _system stats_\n"
                "• _what's the weather_\n"
                "• _list my projects_\n"
                "• _good morning_ (full briefing)\n\n"
                "/id — get your chat ID\n"
                "/status — quick system status",
                parse_mode="Markdown",
            )
            return

        if text == "/id":
            self._send(chat_id, f"Your chat ID: `{chat_id}`", parse_mode="Markdown")
            return

        if text == "/status":
            text = "quick status"  # Route through AI

        # Acknowledge receipt, then process
        self._send(chat_id, "◆ Processing...")
        asyncio.run_coroutine_threadsafe(
            self._process_and_reply(chat_id, text),
            self._tg_loop,
        )

    # ── Command processing ─────────────────────────────────────

    async def _process_and_reply(self, chat_id: int, text: str):
        try:
            if not (self._assistant and self._plugin_manager):
                self._send(chat_id, "⚠️ Assistant not ready yet — please wait a moment.")
                return

            caps = self._plugin_manager.get_all_capabilities()
            result = await self._assistant.process_input(text, caps)
            rtype = result.get("type", "conversation")

            if rtype == "conversation":
                reply = result.get("message", "No response.")
                self._send(chat_id, reply)

            elif rtype == "action":
                plugin_name = result.get("plugin", "")
                action = result.get("action", "")
                explanation = result.get("explanation", f"Executing {plugin_name}.{action}")
                self._send(chat_id, f">> {explanation}")

                plugin = self._plugin_manager.get_plugin(plugin_name)
                if plugin and plugin.is_connected:
                    out = await plugin.execute(action, result.get("params", {}))
                    self._send(chat_id, out)
                elif plugin:
                    self._send(chat_id, f"⚠️ {plugin_name} is not connected.")
                else:
                    self._send(chat_id, f"⚠️ Plugin '{plugin_name}' not found.")

            elif rtype == "multi_action":
                self._send(chat_id, f">> {result.get('explanation', 'Running sequence...')}")
                for i, step in enumerate(result.get("steps", []), 1):
                    plugin = self._plugin_manager.get_plugin(step.get("plugin", ""))
                    if plugin and plugin.is_connected:
                        out = await plugin.execute(step["action"], step.get("params", {}))
                        self._send(chat_id, f"Step {i}: {out}")

            else:
                self._send(chat_id, result.get("message", str(result)))

        except Exception as e:
            logger.error(f"Telegram process error: {e}", exc_info=True)
            self._send(chat_id, f"⚠️ Error: {str(e)[:200]}")

    # ── Sending ────────────────────────────────────────────────

    def _send(self, chat_id: int, text: str, parse_mode: str = ""):
        """Send a message back to Telegram. Splits long messages automatically."""
        MAX = 4000
        chunks = [text[i:i + MAX] for i in range(0, len(text), MAX)]
        for chunk in chunks:
            try:
                payload = {"chat_id": chat_id, "text": chunk}
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                _requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json=payload,
                    timeout=10,
                )
            except Exception as e:
                logger.error(f"Telegram send error: {e}")

    def send_notification(self, text: str):
        """Push a notification to all configured notify chat IDs."""
        for cid in self.notify_ids:
            self._send(cid, text)

    # ── Plugin interface ───────────────────────────────────────

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "send_notification": self._exec_notify,
            "get_status":        self._exec_status,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown telegram action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {
                "action": "send_notification",
                "description": "Push a notification to your phone via Telegram",
                "params": ["message"],
            },
            {
                "action": "get_status",
                "description": "Get Telegram bridge connection status",
                "params": [],
            },
        ]

    async def _exec_notify(self, params: dict) -> str:
        msg = params.get("message", "")
        if not msg:
            return "⚠️ No message provided."
        self.send_notification(msg)
        return f"📱 Notification sent to {len(self.notify_ids)} device(s)."

    async def _exec_status(self, params: dict) -> str:
        status = "online" if self._polling else "offline"
        return (
            f"📱 Telegram Bridge\n"
            f"  Status:   {status}\n"
            f"  Bot:      {self._status_message}\n"
            f"  Allowed:  {self.allowed_ids or 'open (anyone)'}\n"
            f"  Offset:   {self._offset}"
        )
