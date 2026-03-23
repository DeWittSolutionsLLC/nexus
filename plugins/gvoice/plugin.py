"""
Google Voice Plugin - Send/read SMS, make calls, check voicemail.

Uses browser automation on voice.google.com - no API needed.
Just log in once and your session persists.
"""

import asyncio
import logging
import re
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.gvoice")

GVOICE_URL = "https://voice.google.com/u/1/calls"


class GoogleVoicePlugin(BasePlugin):
    name = "gvoice"
    description = "Google Voice - send/read texts, make calls, check voicemail"
    icon = "📱"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.page = None
        self.url = config.get("url", GVOICE_URL)
        # Parse user number from URL (e.g. /u/1/ → "1")
        m = re.search(r"/u/(\d+)", self.url)
        self._user_num = m.group(1) if m else "0"

    def _gv_url(self, section: str) -> str:
        """Build a correct Google Voice URL for the given section."""
        return f"https://voice.google.com/u/{self._user_num}/{section}"

    async def connect(self) -> bool:
        if not self.browser:
            self._status_message = "No browser engine"
            return False

        try:
            self.page = await self.browser.get_page("gvoice", self.url)
            await asyncio.sleep(4)

            # URL-based login detection — more reliable than CSS selectors.
            # If we're on voice.google.com (not accounts.google.com), we're in.
            if self._check_url_logged_in():
                self._connected = True
                self._status_message = "Connected to Google Voice"
                return True

            # Not logged in yet — show message and wait for user
            self._status_message = "Log into Google Voice in the browser window"
            for _ in range(30):  # 30 × 2s = 60s max
                await asyncio.sleep(2)
                if self._check_url_logged_in():
                    await asyncio.sleep(3)  # Let the app finish loading
                    self._connected = True
                    self._status_message = "Connected to Google Voice"
                    return True

            self._status_message = "Google Voice login timed out (60s)"
            return False

        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            return False

    def _check_url_logged_in(self) -> bool:
        """Return True if the browser tab is on voice.google.com (not the login page)."""
        try:
            url = self.page.url
            return "voice.google.com" in url and "accounts.google.com" not in url
        except Exception:
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self.page or self.page.is_closed():
            return "Google Voice page not available."

        actions = {
            "send_text": self._send_text,
            "read_texts": self._read_texts,
            "read_conversation": self._read_conversation,
            "make_call": self._make_call,
            "check_voicemail": self._check_voicemail,
            "list_conversations": self._list_conversations,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown gvoice action: {action}"
        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Google Voice action '{action}' failed: {e}")
            return f"Google Voice error: {str(e)[:120]}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "send_text", "description": "Send a text/SMS message via Google Voice", "params": ["phone_number", "contact_name", "message"]},
            {"action": "read_texts", "description": "Read recent text conversations in Google Voice", "params": ["limit"]},
            {"action": "read_conversation", "description": "Read messages in a specific conversation", "params": ["contact_name", "limit"]},
            {"action": "make_call", "description": "Start a phone call via Google Voice", "params": ["phone_number", "contact_name"]},
            {"action": "check_voicemail", "description": "Check recent voicemails", "params": ["limit"]},
            {"action": "list_conversations", "description": "List all recent Google Voice conversations", "params": ["limit"]},
        ]

    # ================================================================
    # Send Text Message
    # ================================================================

    async def _send_text(self, params: dict) -> str:
        phone_number = params.get("phone_number", "")
        contact_name = params.get("contact_name", "")
        message = params.get("message", "")

        if not message:
            return "What should the text say?"
        if not phone_number and not contact_name:
            return "Who should I text? Give me a phone number or contact name."

        # Navigate to messages tab
        await self.page.goto(self._gv_url("messages"), wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Click "Send new message" button
        try:
            new_msg_btn = self.page.locator(
                'button[aria-label="Send new message"], '
                'a[gv-id="send-new-message"], '
                'button[gv-id="send-new-message"], '
                'div[gv-id="send-new-message"]'
            ).first
            await new_msg_btn.click(timeout=5000)
            await asyncio.sleep(1.5)
        except Exception:
            # Try the floating action button
            try:
                fab = self.page.locator('button[aria-label*="new"], gv-icon-button[icon="message"]').first
                await fab.click(timeout=5000)
                await asyncio.sleep(1.5)
            except Exception:
                return "Couldn't find the new message button. Make sure Google Voice is loaded in the browser."

        # Type the recipient
        recipient = phone_number or contact_name
        try:
            to_field = self.page.locator(
                'input[aria-label="Type a name or phone number"], '
                'gv-recipient-picker input, '
                'input[placeholder*="name or phone"]'
            ).first
            await to_field.click(timeout=5000)
            await to_field.fill(recipient)
            await asyncio.sleep(1.5)

            # Select the first suggestion or press Enter for phone numbers
            if phone_number:
                await self.page.keyboard.press("Enter")
            else:
                # Click first suggestion
                try:
                    suggestion = self.page.locator(
                        'gv-contact-list-item, '
                        'div[role="option"], '
                        'md-autocomplete-parent-scope md-item-content'
                    ).first
                    await suggestion.click(timeout=3000)
                except Exception:
                    await self.page.keyboard.press("Enter")

            await asyncio.sleep(1)
        except Exception as e:
            return f"Couldn't enter recipient: {str(e)[:80]}"

        # Type the message
        try:
            msg_field = self.page.locator(
                'textarea[aria-label="Type a message"], '
                'input[aria-label="Type a message"], '
                'div[contenteditable="true"][aria-label*="message"]'
            ).first
            await msg_field.click(timeout=5000)
            await msg_field.fill(message)
            await asyncio.sleep(0.5)
        except Exception as e:
            return f"Couldn't type message: {str(e)[:80]}"

        # Click send
        try:
            send_btn = self.page.locator(
                'button[aria-label="Send message"], '
                'gv-icon-button[aria-label="Send message"], '
                'button[aria-label="Send"]'
            ).first
            await send_btn.click(timeout=5000)
            await asyncio.sleep(2)
        except Exception:
            # Try pressing Enter
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(2)

        return f"Text sent to {recipient}: {message[:80]}"

    # ================================================================
    # Read Recent Texts
    # ================================================================

    async def _read_texts(self, params: dict) -> str:
        return await self._list_conversations(params)

    async def _list_conversations(self, params: dict) -> str:
        limit = int(params.get("limit", 10))

        await self.page.goto(self._gv_url("messages"), wait_until="domcontentloaded")
        await asyncio.sleep(3)

        conversations = await self.page.evaluate(f"""
            () => {{
                const results = [];
                // Try multiple selectors for conversation list items
                const selectors = [
                    'gv-conversation-list-item',
                    'div[gv-id="content"] a[href*="/messages/"]',
                    'div.gv_DISCONNECTED a',
                    'md-list-item',
                ];
                let items = [];
                for (const sel of selectors) {{
                    items = document.querySelectorAll(sel);
                    if (items.length > 0) break;
                }}

                for (let i = 0; i < Math.min(items.length, {limit}); i++) {{
                    const item = items[i];
                    const name = item.querySelector('[gv-id="contact-name"], .contact-name, span[class*="name"]')?.textContent?.trim() ||
                                 item.getAttribute('aria-label') ||
                                 item.textContent?.trim()?.split('\\n')[0]?.substring(0, 40) || '';
                    const preview = item.querySelector('[gv-id="message-text"], .message-text, span[class*="preview"]')?.textContent?.trim() ||
                                    item.textContent?.trim()?.split('\\n').slice(1).join(' ')?.substring(0, 80) || '';
                    const time = item.querySelector('[gv-id="timestamp"], .timestamp, time')?.textContent?.trim() || '';
                    if (name) {{
                        results.push({{ name: name.substring(0, 30), preview: preview.substring(0, 80), time }});
                    }}
                }}
                return results;
            }}
        """)

        if not conversations:
            return "No text conversations found. Make sure Google Voice messages tab is loaded."

        lines = ["Recent Google Voice texts:\n"]
        for c in conversations:
            lines.append(f"  {c['name']} ({c['time']})")
            if c['preview']:
                lines.append(f"    {c['preview']}")
        return "\n".join(lines)

    # ================================================================
    # Read Specific Conversation
    # ================================================================

    async def _read_conversation(self, params: dict) -> str:
        contact_name = params.get("contact_name", "")
        limit = int(params.get("limit", 10))

        if not contact_name:
            return "Which conversation? Give me a contact name."

        await self.page.goto(self._gv_url("messages"), wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Click the conversation matching the contact name
        try:
            conv = self.page.locator(f'text="{contact_name}"').first
            await conv.click(timeout=5000)
            await asyncio.sleep(2)
        except Exception:
            # Try searching
            try:
                search = self.page.locator('input[aria-label="Search"]').first
                await search.click()
                await search.fill(contact_name)
                await asyncio.sleep(2)
                result = self.page.locator(f'text="{contact_name}"').first
                await result.click(timeout=5000)
                await asyncio.sleep(2)
            except Exception:
                return f"Couldn't find conversation with '{contact_name}'"

        # Read messages
        messages = await self.page.evaluate(f"""
            () => {{
                const results = [];
                const msgElements = document.querySelectorAll(
                    'gv-text-message-item, div[gv-id="text-message"], div[class*="message-row"]'
                );
                const start = Math.max(0, msgElements.length - {limit});
                for (let i = start; i < msgElements.length; i++) {{
                    const el = msgElements[i];
                    const text = el.querySelector('[gv-id="message-text"], div[class*="text-content"]')?.textContent?.trim() ||
                                 el.textContent?.trim() || '';
                    const time = el.querySelector('[gv-id="timestamp"], time')?.textContent?.trim() || '';
                    const isMe = el.classList.contains('outgoing') ||
                                 el.querySelector('[gv-id="outgoing"]') !== null ||
                                 el.getAttribute('class')?.includes('outgoing');
                    if (text) {{
                        results.push({{
                            text: text.substring(0, 300),
                            time,
                            from_me: isMe
                        }});
                    }}
                }}
                return results;
            }}
        """)

        if not messages:
            return f"Couldn't read messages with {contact_name}. The conversation layout may have changed."

        lines = [f"Conversation with {contact_name}:\n"]
        for m in messages:
            sender = "You" if m.get("from_me") else contact_name
            lines.append(f"  [{m.get('time', '')}] {sender}: {m['text']}")
        return "\n".join(lines)

    # ================================================================
    # Make a Call
    # ================================================================

    async def _make_call(self, params: dict) -> str:
        phone_number = params.get("phone_number", "")
        contact_name = params.get("contact_name", "")

        if not phone_number and not contact_name:
            return "Who should I call? Give me a phone number or contact name."

        recipient = phone_number or contact_name

        await self.page.goto(self._gv_url("calls"), wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Log every button on the page so we know exactly what's there
        buttons_info = await self.page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                return Array.from(btns).map(b => ({
                    label: b.getAttribute('aria-label') || '',
                    text: b.textContent.trim().substring(0, 40),
                    cls: b.className.substring(0, 60)
                }));
            }
        """)
        logger.info(f"[gvoice] Buttons on calls page: {buttons_info}")

        # JavaScript-based click — works regardless of selector syntax
        clicked = await self.page.evaluate("""
            () => {
                // Try by aria-label first
                const labels = ['New call', 'Make a call', 'New Call', 'Call', 'Dialpad', 'dial'];
                for (const label of labels) {
                    const btn = document.querySelector('button[aria-label="' + label + '"]');
                    if (btn) { btn.click(); return 'label:' + label; }
                }
                // Try partial aria-label match
                for (const btn of document.querySelectorAll('button[aria-label]')) {
                    const lbl = btn.getAttribute('aria-label').toLowerCase();
                    if (lbl.includes('call') || lbl.includes('dial')) {
                        btn.click(); return 'partial:' + lbl;
                    }
                }
                // Try FAB / floating action button
                for (const sel of ['button.mat-fab', 'button.mdc-fab', 'button.mat-mdc-fab',
                                    'button[class*="fab"]', 'button[class*="Fab"]']) {
                    const btn = document.querySelector(sel);
                    if (btn) { btn.click(); return 'fab:' + sel; }
                }
                // Try mat-icon with call/phone text
                for (const icon of document.querySelectorAll('mat-icon')) {
                    const t = icon.textContent.trim();
                    if (['add_call','call','phone','dialpad'].includes(t)) {
                        const btn = icon.closest('button');
                        if (btn) { btn.click(); return 'icon:' + t; }
                    }
                }
                return null;
            }
        """)

        if not clicked:
            return (
                f"Couldn't find the new call button. "
                f"Check nexus.log for the button list — it shows every button on the page so we can add the right selector."
            )

        logger.info(f"[gvoice] Clicked dial button via: {clicked}")
        await asyncio.sleep(2)

        # Find the phone input that appeared and fill it
        filled = await self.page.evaluate(f"""
            () => {{
                const selectors = [
                    'input[aria-label*="phone"]',
                    'input[aria-label*="Phone"]',
                    'input[aria-label*="name or phone"]',
                    'input[placeholder*="phone"]',
                    'input[placeholder*="Phone"]',
                    'input[type="tel"]',
                    'input[class*="dial"]',
                    'input[class*="Dial"]',
                    'input'
                ];
                for (const sel of selectors) {{
                    const inp = document.querySelector(sel);
                    if (inp && inp.offsetParent !== null) {{
                        inp.focus();
                        inp.value = '{recipient}';
                        inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                        inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                        return sel;
                    }}
                }}
                return null;
            }}
        """)

        if not filled:
            return f"Dialer opened but couldn't find number input. Number the button via: {clicked}"

        logger.info(f"[gvoice] Filled input via: {filled}")
        await asyncio.sleep(1)

        # Press Enter or find and click a Call/Dial confirm button
        confirmed = await self.page.evaluate("""
            () => {
                for (const btn of document.querySelectorAll('button')) {
                    const lbl = (btn.getAttribute('aria-label') || '').toLowerCase();
                    const txt = btn.textContent.trim().toLowerCase();
                    if (lbl === 'call' || lbl === 'dial' || txt === 'call' || txt === 'dial') {
                        btn.click(); return 'btn:' + (lbl || txt);
                    }
                }
                return null;
            }
        """)
        if not confirmed:
            await self.page.keyboard.press("Enter")

        await asyncio.sleep(2)
        return f"Calling {recipient} via Google Voice..."

    # ================================================================
    # Check Voicemail
    # ================================================================

    async def _check_voicemail(self, params: dict) -> str:
        limit = int(params.get("limit", 5))

        await self.page.goto(self._gv_url("voicemail"), wait_until="domcontentloaded")
        await asyncio.sleep(3)

        voicemails = await self.page.evaluate(f"""
            () => {{
                const results = [];
                const items = document.querySelectorAll(
                    'gv-voicemail-list-item, div[gv-id="content"] a[href*="/voicemail/"]'
                );
                for (let i = 0; i < Math.min(items.length, {limit}); i++) {{
                    const item = items[i];
                    const name = item.querySelector('[gv-id="contact-name"], span[class*="name"]')?.textContent?.trim() ||
                                 item.getAttribute('aria-label')?.substring(0, 30) || '';
                    const transcript = item.querySelector('[gv-id="transcript"], div[class*="transcript"]')?.textContent?.trim() || '';
                    const time = item.querySelector('[gv-id="timestamp"], time')?.textContent?.trim() || '';
                    const duration = item.querySelector('[gv-id="duration"]')?.textContent?.trim() || '';
                    if (name || transcript) {{
                        results.push({{
                            name: name.substring(0, 30),
                            transcript: transcript.substring(0, 200),
                            time,
                            duration
                        }});
                    }}
                }}
                return results;
            }}
        """)

        if not voicemails:
            return "No voicemails found."

        lines = ["Voicemails:\n"]
        for vm in voicemails:
            lines.append(f"  From: {vm['name']} ({vm['time']}) {vm['duration']}")
            if vm['transcript']:
                lines.append(f"    \"{vm['transcript']}\"")
        return "\n".join(lines)