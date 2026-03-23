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

        await asyncio.sleep(1.5)

        messages = await self.page.evaluate(f"""
            () => {{
                const results = [];

                // Primary: elements with data-pre-plain-text carry sender + timestamp metadata
                // Format: "[HH:MM, DD/MM/YYYY] Sender Name: "
                const withMeta = document.querySelectorAll('[data-pre-plain-text]');
                if (withMeta.length > 0) {{
                    const slice = Array.from(withMeta).slice(-{limit});
                    for (const el of slice) {{
                        const meta = el.getAttribute('data-pre-plain-text') || '';
                        const textEl = el.querySelector('span.selectable-text') ||
                                       el.querySelector('span.copyable-text');
                        const text = textEl ? (textEl.innerText || textEl.textContent || '').trim() : '';
                        const isOut = !!el.closest('.message-out');
                        if (text) {{
                            results.push({{ text: text.substring(0, 400), meta, from_me: isOut }});
                        }}
                    }}
                    if (results.length > 0) return results;
                }}

                // Fallback: scan .message-in / .message-out bubbles directly
                const bubbles = document.querySelectorAll('.message-in, .message-out');
                const slice = Array.from(bubbles).slice(-{limit});
                for (const el of slice) {{
                    const textEl = el.querySelector('span.selectable-text') ||
                                   el.querySelector('span.copyable-text');
                    const text = textEl ? (textEl.innerText || textEl.textContent || '').trim() : '';
                    const isOut = el.classList.contains('message-out') || !!el.closest('.message-out');
                    if (text) {{
                        results.push({{ text: text.substring(0, 400), meta: '', from_me: isOut }});
                    }}
                }}
                return results;
            }}
        """)

        if not messages:
            return f"❌ No messages found in chat with '{contact_name}'. The chat may be empty or still loading."

        def parse_sender(meta: str, fallback: str) -> str:
            # meta format: "[HH:MM, DD/MM/YYYY] Sender: "
            try:
                return meta.split("] ", 1)[1].rstrip(": ").strip()
            except Exception:
                return fallback

        lines = []
        for m in messages:
            if m.get("from_me"):
                sender = "You"
            else:
                sender = parse_sender(m.get("meta", ""), contact_name)
            lines.append(f"  {sender}: {m['text']}")

        return f"💬 Chat with {contact_name} (last {len(lines)} messages):\n\n" + "\n".join(lines)

    async def _list_chats(self, params: dict) -> str:
        limit = int(params.get("limit", 10))

        # Return to the main chat list
        await self.page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

        chats = await self.page.evaluate(f"""
            () => {{
                const results = [];

                // Each chat row is a listitem; stable attributes used where possible
                const items = document.querySelectorAll('div[role="listitem"]');
                for (let i = 0; i < Math.min(items.length, {limit}); i++) {{
                    const item = items[i];

                    // Contact/group name — title attribute is the most stable
                    const name = item.querySelector('span[dir="auto"][title]')?.getAttribute('title') ||
                                 item.querySelector('span[dir="auto"]')?.textContent?.trim() || '';

                    // Last message preview
                    const lastMsg = item.querySelector('span[data-testid="last-msg-status"]')?.textContent?.trim() ||
                                    item.querySelector('div[data-testid="last-message-preview"]')?.textContent?.trim() ||
                                    item.querySelector('span[dir="ltr"]')?.textContent?.trim() || '';

                    // Timestamp
                    const time = item.querySelector('span[data-testid="cell-frame-primary-detail"]')?.textContent?.trim() ||
                                 item.querySelector('div[class*="cell-frame-primary"]')?.textContent?.trim() || '';

                    // Unread badge
                    const unread = item.querySelector('span[data-testid="icon-unread-count"]')?.textContent?.trim() || '';

                    if (name) {{
                        results.push({{ name, lastMsg: lastMsg.substring(0, 80), time, unread }});
                    }}
                }}
                return results;
            }}
        """)

        if not chats:
            return "❌ Couldn't read chat list. Make sure WhatsApp Web is fully loaded."

        lines = []
        for c in chats:
            badge = f" 🔵({c['unread']})" if c.get("unread") else ""
            time_str = f" [{c['time']}]" if c.get("time") else ""
            preview = c["lastMsg"] if c["lastMsg"] else "(no preview)"
            lines.append(f"  {c['name']}{badge}{time_str}: {preview}")

        return "💬 Recent WhatsApp chats:\n\n" + "\n".join(lines)
