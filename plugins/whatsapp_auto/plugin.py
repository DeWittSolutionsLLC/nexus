"""
WhatsApp Plugin — WhatsApp Web automation via Playwright.
Scan QR once, sessions persist locally.
"""

import asyncio
import logging
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.whatsapp")


class WhatsAppAutoPlugin(BasePlugin):
    name = "whatsapp"
    description = "Send & read WhatsApp messages (browser automation)"
    icon = "💬"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.page = None
        self.url = config.get("url", "https://web.whatsapp.com")

    async def connect(self) -> bool:
        if not self.browser:
            self._status_message = "No browser engine"
            return False

        try:
            self.page = await self.browser.get_page("whatsapp", self.url)
            await asyncio.sleep(3)

            # WhatsApp Web shows a search bar when logged in
            logged_in = await self.browser.check_logged_in(
                "whatsapp",
                'div[contenteditable="true"][data-tab="3"], div[aria-label="Search input textbox"]',
                timeout=8000
            )

            if logged_in:
                self._connected = True
                self._status_message = "Connected to WhatsApp"
                return True
            else:
                self._status_message = "⏳ Scan QR code in the browser to log into WhatsApp"
                success = await self.browser.wait_for_user_login(
                    "whatsapp",
                    'div[contenteditable="true"][data-tab="3"], div[aria-label="Search input textbox"]',
                    max_wait=120
                )
                if success:
                    self._connected = True
                    self._status_message = "Connected to WhatsApp"
                    return True
                self._status_message = "WhatsApp login timed out"
                return False

        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self.page or self.page.is_closed():
            return "❌ WhatsApp page not available."

        actions = {
            "send_message": self._send_message,
            "read_chat": self._read_chat,
            "list_chats": self._list_chats,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown WhatsApp action: {action}"
        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"WhatsApp action '{action}' failed: {e}")
            return f"❌ WhatsApp error: {str(e)[:100]}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "send_message", "description": "Send a WhatsApp message to a contact", "params": ["contact_name", "message"]},
            {"action": "read_chat", "description": "Read recent messages from a WhatsApp chat", "params": ["contact_name", "limit"]},
            {"action": "list_chats", "description": "List recent WhatsApp conversations", "params": ["limit"]},
        ]

    async def _open_chat(self, contact_name: str) -> bool:
        """Search for and open a chat by contact name."""
        # Click the search/new chat area
        search = self.page.locator(
            'div[contenteditable="true"][data-tab="3"], '
            'div[aria-label="Search input textbox"]'
        ).first
        await search.click()
        await asyncio.sleep(0.5)

        # Clear and type contact name
        await self.page.keyboard.press("Control+a")
        await self.page.keyboard.type(contact_name, delay=50)
        await asyncio.sleep(1.5)

        # Click the first matching chat result
        # WhatsApp renders search results as list items with the contact name
        result = self.page.locator(f'span[title*="{contact_name}" i]').first
        try:
            await result.click(timeout=5000)
            await asyncio.sleep(1)
            return True
        except Exception:
            # Try a looser match
            results = self.page.locator('div[role="listitem"] span[dir="auto"]')
            count = await results.count()
            for i in range(min(count, 5)):
                text = await results.nth(i).text_content()
                if text and contact_name.lower() in text.lower():
                    await results.nth(i).click()
                    await asyncio.sleep(1)
                    return True
            return False

    async def _send_message(self, params: dict) -> str:
        contact_name = params.get("contact_name", "")
        message = params.get("message", "")

        if not contact_name:
            return "❌ Who should I message?"
        if not message:
            return "❌ What should the message say?"

        if not await self._open_chat(contact_name):
            return f"❌ Couldn't find contact '{contact_name}'"

        # Type in the message input
        msg_box = self.page.locator(
            'div[contenteditable="true"][data-tab="10"], '
            'footer div[contenteditable="true"]'
        ).first
        await msg_box.click()
        await msg_box.fill(message)
        await asyncio.sleep(0.3)

        # Send with Enter
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(1)

        return f"✅ WhatsApp message sent to {contact_name}"

    async def _read_chat(self, params: dict) -> str:
        contact_name = params.get("contact_name", "")
        limit = int(params.get("limit", 10))

        if not contact_name:
            return "❌ Which chat should I read?"

        if not await self._open_chat(contact_name):
            return f"❌ Couldn't find chat with '{contact_name}'"

        await asyncio.sleep(1)

        # Extract messages from the chat panel
        messages = await self.page.evaluate(f"""
            () => {{
                const msgElements = document.querySelectorAll('div.message-in, div.message-out, div[data-pre-plain-text]');
                const results = [];
                
                // Fallback: get all message rows
                const rows = document.querySelectorAll('div[role="row"]');
                for (let i = Math.max(0, rows.length - {limit}); i < rows.length; i++) {{
                    const row = rows[i];
                    const text = row.querySelector('span.selectable-text')?.textContent || '';
                    const meta = row.querySelector('div[data-pre-plain-text]')?.getAttribute('data-pre-plain-text') || '';
                    const isOut = row.querySelector('.message-out') !== null;
                    if (text) {{
                        results.push({{
                            text: text.substring(0, 300),
                            meta: meta,
                            from_me: isOut
                        }});
                    }}
                }}
                return results;
            }}
        """)

        if not messages:
            return f"Couldn't read messages from {contact_name}. The chat might use a different layout."

        lines = []
        for m in messages[-limit:]:
            sender = "You" if m.get("from_me") else contact_name
            lines.append(f"  {sender}: {m['text']}")

        return f"💬 Chat with {contact_name} (last {len(lines)} messages):\n\n" + "\n".join(lines)

    async def _list_chats(self, params: dict) -> str:
        limit = int(params.get("limit", 10))

        # Make sure we're on the main chat list
        await self.page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

        chats = await self.page.evaluate(f"""
            () => {{
                const chatItems = document.querySelectorAll('div[role="listitem"]');
                const results = [];
                for (let i = 0; i < Math.min(chatItems.length, {limit}); i++) {{
                    const item = chatItems[i];
                    const name = item.querySelector('span[dir="auto"][title]')?.getAttribute('title') || '';
                    const lastMsg = item.querySelector('span[dir="ltr"]')?.textContent || 
                                    item.querySelector('div.Dvjam span')?.textContent || '';
                    const time = item.querySelector('div._aK7, div[class*="Timestamp"]')?.textContent || '';
                    const unread = item.querySelector('span[data-testid="icon-unread-count"]')?.textContent || '';
                    if (name) {{
                        results.push({{ name, lastMsg: lastMsg.substring(0, 60), time, unread }});
                    }}
                }}
                return results;
            }}
        """)

        if not chats:
            return "Couldn't read chat list. Make sure WhatsApp Web is loaded."

        lines = []
        for c in chats:
            badge = f" 🔵({c['unread']})" if c.get("unread") else ""
            preview = c["lastMsg"][:50] if c["lastMsg"] else ""
            lines.append(f"  {c['name']}{badge}: {preview}")

        return f"💬 Recent WhatsApp chats:\n\n" + "\n".join(lines)
