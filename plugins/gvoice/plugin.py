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

    def _normalize_phone(self, phone: str) -> str:
        """Return E.164 format (+12485551234). Assumes US if 10 digits."""
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 10:
            digits = '1' + digits
        return '+' + digits

    def _text_url(self, phone: str) -> str:
        """Direct URL to open a specific Google Voice text conversation."""
        e164 = self._normalize_phone(phone)
        encoded = e164.replace('+', '%2B')
        return f"https://voice.google.com/u/{self._user_num}/messages?itemId=t.{encoded}"

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
            {"action": "send_text", "description": "Send a text/SMS via Google Voice — phone_number required", "params": ["phone_number", "message", "contact_name"]},
            {"action": "read_texts", "description": "List recent Google Voice text conversations", "params": ["limit"]},
            {"action": "read_conversation", "description": "Read messages in a specific conversation — use phone_number for direct navigation", "params": ["phone_number", "contact_name", "limit"]},
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
        if not phone_number:
            return "I need a phone number to send a text via Google Voice (e.g. 248-829-9534)."

        label = contact_name or phone_number

        # Navigate directly to the conversation — no button clicking needed
        await self.page.goto(self._text_url(phone_number), wait_until="domcontentloaded")
        await asyncio.sleep(2.5)

        # Find the message textarea
        try:
            msg_field = self.page.locator(
                'textarea[aria-label="Type a message"], '
                'textarea[aria-label*="message"], '
                'div[contenteditable="true"][aria-label*="message"], '
                'gv-message-input textarea'
            ).first
            await msg_field.click(timeout=6000)
            await msg_field.fill(message)
            await asyncio.sleep(0.5)
        except Exception as e:
            return f"❌ Couldn't find message input after navigating to conversation: {str(e)[:80]}"

        # Send
        try:
            send_btn = self.page.locator(
                'button[aria-label="Send message"], '
                'button[aria-label="Send"], '
                'gv-icon-button[aria-label="Send message"]'
            ).first
            await send_btn.click(timeout=4000)
        except Exception:
            await self.page.keyboard.press("Enter")

        await asyncio.sleep(1)
        return f"✅ Text sent to {label}: {message[:80]}"

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
        phone_number = params.get("phone_number", "")
        limit = int(params.get("limit", 10))

        if not contact_name and not phone_number:
            return "Which conversation? Give me a contact name or phone number."

        # Navigate directly when we have a phone number; otherwise search the list
        if phone_number:
            await self.page.goto(self._text_url(phone_number), wait_until="domcontentloaded")
            await asyncio.sleep(2.5)
            label = contact_name or phone_number
        else:
            label = contact_name
            await self.page.goto(self._gv_url("messages"), wait_until="domcontentloaded")
            await asyncio.sleep(2)
            try:
                conv = self.page.locator(f'text="{contact_name}"').first
                await conv.click(timeout=5000)
                await asyncio.sleep(2)
            except Exception:
                try:
                    search = self.page.locator('input[aria-label="Search"]').first
                    await search.click()
                    await search.fill(contact_name)
                    await asyncio.sleep(2)
                    result = self.page.locator(f'text="{contact_name}"').first
                    await result.click(timeout=5000)
                    await asyncio.sleep(2)
                except Exception:
                    return f"❌ Couldn't find conversation with '{contact_name}'"

        messages = await self.page.evaluate(f"""
            () => {{
                const results = [];

                // Primary: gv-text-message-item elements (Google Voice's own component)
                let els = document.querySelectorAll('gv-text-message-item');

                // Fallback: any element with a gv-id pointing to message text
                if (els.length === 0) {{
                    els = document.querySelectorAll('[gv-id="text-message"], div[class*="message-row"]');
                }}

                const slice = Array.from(els).slice(-{limit});
                for (const el of slice) {{
                    const text = el.querySelector('[gv-id="message-text"]')?.textContent?.trim() ||
                                 el.querySelector('div[class*="text-content"]')?.textContent?.trim() ||
                                 el.querySelector('span')?.textContent?.trim() || '';
                    const time = el.querySelector('[gv-id="timestamp"]')?.textContent?.trim() ||
                                 el.querySelector('time')?.textContent?.trim() || '';
                    const cls = el.getAttribute('class') || '';
                    const isMe = cls.includes('outgoing') || !!el.querySelector('[gv-id="outgoing"]');
                    if (text) {{
                        results.push({{ text: text.substring(0, 400), time, from_me: isMe }});
                    }}
                }}
                return results;
            }}
        """)

        if not messages:
            return f"❌ No messages found in conversation with '{label}'. The page may still be loading."

        lines = [f"Conversation with {label}:\n"]
        for m in messages:
            sender = "You" if m.get("from_me") else label
            time_str = f"[{m['time']}] " if m.get("time") else ""
            lines.append(f"  {time_str}{sender}: {m['text']}")
        return "\n".join(lines)

    # ================================================================
    # Make a Call
    # ================================================================

    async def _make_call(self, params: dict) -> str:
        phone_number = params.get("phone_number", "")
        contact_name = params.get("contact_name", "")

        if not phone_number and not contact_name:
            return "Who should I call? Give me a phone number or contact name."

        label = contact_name or phone_number

        await self.page.goto(self._gv_url("calls"), wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Click the "New call" / dialpad button
        clicked = await self.page.evaluate("""
            () => {
                // Exact aria-label matches
                for (const lbl of ['New call', 'Make a call', 'New Call', 'Dialpad', 'Call']) {
                    const btn = document.querySelector(`button[aria-label="${lbl}"]`);
                    if (btn) { btn.click(); return lbl; }
                }
                // Partial aria-label match
                for (const btn of document.querySelectorAll('button[aria-label]')) {
                    const lbl = btn.getAttribute('aria-label').toLowerCase();
                    if (lbl.includes('call') || lbl.includes('dial')) {
                        btn.click(); return lbl;
                    }
                }
                // FAB (floating action button)
                for (const sel of ['button.mat-mdc-fab', 'button.mat-fab', 'button.mdc-fab', 'button[class*="fab"]']) {
                    const btn = document.querySelector(sel);
                    if (btn) { btn.click(); return sel; }
                }
                // mat-icon fallback
                for (const icon of document.querySelectorAll('mat-icon')) {
                    if (['add_call','call','phone','dialpad'].includes(icon.textContent.trim())) {
                        const btn = icon.closest('button');
                        if (btn) { btn.click(); return 'icon:' + icon.textContent.trim(); }
                    }
                }
                return null;
            }
        """)

        if not clicked:
            return "❌ Couldn't find the new call button on the Google Voice calls page."

        logger.info(f"[gvoice] Clicked call button via: {clicked}")
        await asyncio.sleep(2)

        # Type the number into whichever input appeared
        number_to_type = self._normalize_phone(phone_number) if phone_number else contact_name
        try:
            inp = self.page.locator(
                'input[aria-label*="phone" i], '
                'input[aria-label*="name or phone" i], '
                'input[placeholder*="phone" i], '
                'input[type="tel"]'
            ).first
            await inp.click(timeout=4000)
            await inp.fill(number_to_type)
        except Exception:
            # If no input found, type directly — some dialers capture keyboard focus
            await self.page.keyboard.type(number_to_type, delay=60)

        await asyncio.sleep(1)

        # Confirm the call
        confirmed = await self.page.evaluate("""
            () => {
                for (const btn of document.querySelectorAll('button')) {
                    const lbl = (btn.getAttribute('aria-label') || '').toLowerCase();
                    const txt = btn.textContent.trim().toLowerCase();
                    if (lbl === 'call' || lbl === 'dial' || txt === 'call' || txt === 'dial') {
                        btn.click(); return true;
                    }
                }
                return false;
            }
        """)
        if not confirmed:
            await self.page.keyboard.press("Enter")

        await asyncio.sleep(2)
        return f"📞 Calling {label} via Google Voice..."

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