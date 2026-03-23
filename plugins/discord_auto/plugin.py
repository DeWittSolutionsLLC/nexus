"""
Discord Plugin — Discord web app automation via Playwright.
No bot token needed — uses your real Discord account in the browser.
"""

import asyncio
import logging
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.discord")


class DiscordAutoPlugin(BasePlugin):
    name = "discord"
    description = "Read & send Discord messages (browser automation)"
    icon = "🎮"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.page = None
        self.url = config.get("url", "https://discord.com/channels/@me")

    async def connect(self) -> bool:
        if not self.browser:
            self._status_message = "No browser engine"
            return False

        try:
            self.page = await self.browser.get_page("discord", self.url)
            await asyncio.sleep(3)

            # Discord shows a text input bar when logged in
            logged_in = await self.browser.check_logged_in(
                "discord",
                'div[class*="sidebar"], ul[aria-label="Direct Messages"]',
                timeout=10000
            )

            if logged_in:
                self._connected = True
                self._status_message = "Logged into Discord"
                return True
            else:
                self._status_message = "⏳ Log into Discord in the browser window"
                success = await self.browser.wait_for_user_login(
                    "discord",
                    'div[class*="sidebar"], ul[aria-label="Direct Messages"]',
                    max_wait=180
                )
                if success:
                    self._connected = True
                    self._status_message = "Logged into Discord"
                    return True
                self._status_message = "Discord login timed out"
                return False

        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self.page or self.page.is_closed():
            return "❌ Discord page not available."

        actions = {
            "check_messages": self._check_messages,
            "send_message": self._send_message,
            "list_servers": self._list_servers,
            "check_dms": self._check_dms,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown Discord action: {action}"
        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Discord action '{action}' failed: {e}")
            return f"❌ Discord error: {str(e)[:100]}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "check_messages", "description": "Read recent messages in a Discord channel",
             "params": ["server_name", "channel_name", "limit"]},
            {"action": "send_message", "description": "Send a message in a Discord channel or DM",
             "params": ["server_name", "channel_name", "user_name", "message"]},
            {"action": "list_servers", "description": "List Discord servers you're in", "params": []},
            {"action": "check_dms", "description": "Check recent Discord direct messages", "params": ["limit"]},
        ]

    async def _navigate_to_channel(self, server_name: str = None, channel_name: str = None) -> bool:
        """Navigate to a server channel using the Discord sidebar."""
        if server_name:
            # Click on server in the left guild bar
            servers = self.page.locator('div[data-list-id="guildsnav"] div[class*="pill"] ~ div img[alt]')
            count = await servers.count()

            # Also try the tooltip-based approach
            guild_icons = self.page.locator('div[data-list-id="guildsnav"] li[class*="pill"] div[role="treeitem"]')
            g_count = await guild_icons.count()

            found_server = False
            for i in range(g_count):
                aria = await guild_icons.nth(i).get_attribute("aria-label") or ""
                if server_name.lower() in aria.lower():
                    await guild_icons.nth(i).click()
                    await asyncio.sleep(1.5)
                    found_server = True
                    break

            if not found_server:
                return False

        if channel_name:
            # Find and click the channel in the sidebar
            channel_links = self.page.locator(f'a[aria-label*="{channel_name}" i], a[href*="/channels/"] span')
            count = await channel_links.count()
            for i in range(count):
                text = await channel_links.nth(i).text_content() or ""
                aria = await channel_links.nth(i).get_attribute("aria-label") or ""
                if channel_name.lower() in text.lower() or channel_name.lower() in aria.lower():
                    await channel_links.nth(i).click()
                    await asyncio.sleep(1.5)
                    return True
            return False

        return True

    async def _check_messages(self, params: dict) -> str:
        server_name = params.get("server_name")
        channel_name = params.get("channel_name", "general")
        limit = int(params.get("limit", 12))

        if server_name or channel_name:
            if not await self._navigate_to_channel(server_name, channel_name):
                return f"❌ Couldn't find {'server ' + server_name if server_name else ''} channel #{channel_name}"

        await asyncio.sleep(1)

        messages = await self.page.evaluate(f"""
            () => {{
                const msgList = document.querySelectorAll('li[id^="chat-messages-"]');
                const results = [];
                const start = Math.max(0, msgList.length - {limit});
                for (let i = start; i < msgList.length; i++) {{
                    const el = msgList[i];
                    const author = el.querySelector('span[class*="username"]')?.textContent || '';
                    const content = el.querySelector('div[id^="message-content-"]')?.textContent || '';
                    const time = el.querySelector('time')?.getAttribute('datetime') || '';
                    if (content || author) {{
                        results.push({{
                            author: author || '(continued)',
                            content: content.substring(0, 300),
                            time: time
                        }});
                    }}
                }}
                return results;
            }}
        """)

        if not messages:
            return f"No messages found or couldn't read the channel."

        lines = []
        for m in messages:
            time_str = m["time"][:16].replace("T", " ") if m["time"] else ""
            lines.append(f"  [{time_str}] {m['author']}: {m['content']}")

        title = f"#{channel_name}" if channel_name else "current channel"
        return f"🎮 Messages in {title}:\n\n" + "\n".join(lines)

    async def _send_message(self, params: dict) -> str:
        message = params.get("message", "")
        server_name = params.get("server_name")
        channel_name = params.get("channel_name")
        user_name = params.get("user_name")

        if not message:
            return "❌ What should I send?"

        if user_name:
            # Navigate to DMs and find user
            await self.page.goto("https://discord.com/channels/@me", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Search in DM list
            dm_items = self.page.locator('ul[aria-label="Direct Messages"] li a')
            count = await dm_items.count()
            found = False
            for i in range(count):
                text = await dm_items.nth(i).text_content() or ""
                if user_name.lower() in text.lower():
                    await dm_items.nth(i).click()
                    await asyncio.sleep(1)
                    found = True
                    break
            if not found:
                return f"❌ Couldn't find DM with '{user_name}'"

        elif server_name or channel_name:
            if not await self._navigate_to_channel(server_name, channel_name):
                return f"❌ Couldn't navigate to the channel"

        # Type and send the message
        msg_input = self.page.locator('div[role="textbox"][data-slate-editor="true"]').first
        await msg_input.click()
        await msg_input.fill(message)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(1)

        target = user_name or f"#{channel_name}" or "current channel"
        return f"✅ Message sent in {target}"

    async def _list_servers(self, params: dict) -> str:
        servers = await self.page.evaluate("""
            () => {
                const items = document.querySelectorAll(
                    'div[data-list-id="guildsnav"] li div[role="treeitem"]'
                );
                const results = [];
                items.forEach(el => {
                    const label = el.getAttribute('aria-label') || '';
                    if (label && !label.includes('Direct Messages') && !label.includes('Add a Server')) {
                        results.push(label.replace(/, \\d+ notification.*/, '').trim());
                    }
                });
                return results;
            }
        """)

        if not servers:
            return "Couldn't read server list."

        lines = [f"  🏠 {s}" for s in servers]
        return f"🎮 Your Discord servers:\n\n" + "\n".join(lines)

    async def _check_dms(self, params: dict) -> str:
        await self.page.goto("https://discord.com/channels/@me", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        dms = await self.page.evaluate("""
            () => {
                const items = document.querySelectorAll('ul[aria-label="Direct Messages"] li a');
                const results = [];
                for (let i = 0; i < Math.min(items.length, 10); i++) {
                    const name = items[i].querySelector('div[class*="name"] span')?.textContent || 
                                 items[i].textContent?.trim()?.split('\\n')[0] || '';
                    const activity = items[i].querySelector('div[class*="activity"]')?.textContent || '';
                    results.push({ name: name.substring(0, 30), activity: activity.substring(0, 60) });
                }
                return results;
            }
        """)

        if not dms:
            return "No recent DMs found."

        lines = [f"  👤 {d['name']}: {d['activity']}" for d in dms if d['name']]
        return f"📨 Recent Discord DMs:\n\n" + "\n".join(lines)
