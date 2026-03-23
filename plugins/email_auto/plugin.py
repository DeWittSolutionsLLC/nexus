"""
Email Plugin — Gmail/Outlook web automation via Playwright.
No API keys needed — uses your real browser session.
"""

import asyncio
import logging
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.email")


class EmailAutoPlugin(BasePlugin):
    name = "email"
    description = "Read & send emails via Gmail (browser automation)"
    icon = "📧"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.page = None
        self.url = config.get("url", "https://mail.google.com")

    async def connect(self) -> bool:
        if not self.browser:
            self._status_message = "No browser engine"
            return False

        try:
            self.page = await self.browser.get_page("gmail", self.url)
            await asyncio.sleep(2)

            # Check if we're logged in by looking for the compose button
            logged_in = await self.browser.check_logged_in(
                "gmail", 'div[gh="cm"], div[role="navigation"]', timeout=8000
            )

            if logged_in:
                self._connected = True
                self._status_message = "Logged into Gmail"
                return True
            else:
                self._status_message = "⏳ Log into Gmail in the browser window"
                # Wait for manual login (up to 3 minutes)
                success = await self.browser.wait_for_user_login(
                    "gmail", 'div[gh="cm"], div[role="navigation"]', max_wait=180
                )
                if success:
                    self._connected = True
                    self._status_message = "Logged into Gmail"
                    return True
                self._status_message = "Gmail login timed out"
                return False

        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            logger.error(f"Gmail connect error: {e}")
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self.page or self.page.is_closed():
            return "❌ Gmail page not available. Reconnect."

        actions = {
            "check_inbox": self._check_inbox,
            "send_email": self._send_email,
            "search_emails": self._search_emails,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown email action: {action}"
        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Email action '{action}' failed: {e}")
            return f"❌ Email action failed: {str(e)[:100]}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "check_inbox", "description": "Check recent emails in Gmail inbox", "params": ["max_results"]},
            {"action": "send_email", "description": "Compose and send an email", "params": ["to", "subject", "body"]},
            {"action": "search_emails", "description": "Search Gmail for specific emails", "params": ["query"]},
        ]

    async def _check_inbox(self, params: dict) -> str:
        max_results = int(params.get("max_results", 8))

        # Navigate to inbox
        await self.page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Extract email rows from inbox
        emails = await self.page.evaluate(f"""
            () => {{
                const rows = document.querySelectorAll('tr.zA');
                const results = [];
                for (let i = 0; i < Math.min(rows.length, {max_results}); i++) {{
                    const row = rows[i];
                    const unread = row.classList.contains('zE');
                    const sender = row.querySelector('.yW span')?.getAttribute('name') || 
                                   row.querySelector('.yW span')?.textContent || '?';
                    const subject = row.querySelector('.y6 span:first-child')?.textContent || '(no subject)';
                    const snippet = row.querySelector('.y2')?.textContent || '';
                    const date = row.querySelector('.xW span')?.getAttribute('title') || 
                                 row.querySelector('.xW span')?.textContent || '';
                    results.push({{ unread, sender, subject, snippet: snippet.substring(0, 80), date }});
                }}
                return results;
            }}
        """)

        if not emails:
            return "📭 Inbox appears empty or couldn't read emails. Make sure Gmail is loaded."

        lines = []
        for e in emails:
            marker = "🔵" if e["unread"] else "  "
            lines.append(f"{marker} From: {e['sender']}\n   Subject: {e['subject']}\n   {e['snippet']}...")

        unread_count = sum(1 for e in emails if e["unread"])
        header = f"📧 Inbox ({unread_count} unread of {len(emails)} shown):"
        return header + "\n\n" + "\n\n".join(lines)

    async def _send_email(self, params: dict) -> str:
        to = params.get("to", "")
        subject = params.get("subject", "")
        body = params.get("body", "")

        if not to:
            return "❌ Who should I send this email to?"
        if not body:
            return "❌ What should the email say?"

        # Click compose button
        compose_btn = self.page.locator('div[gh="cm"]').first
        if not await compose_btn.is_visible():
            await self.page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            compose_btn = self.page.locator('div[gh="cm"]').first

        await compose_btn.click()
        await asyncio.sleep(1.5)

        # Fill in the To field
        to_field = self.page.locator('input[aria-label="To recipients"], textarea[aria-label="To recipients"]').first
        await to_field.fill(to)
        await asyncio.sleep(0.5)

        # Fill subject
        if subject:
            subject_field = self.page.locator('input[name="subjectbox"]').first
            await subject_field.fill(subject)

        # Fill body
        body_field = self.page.locator('div[aria-label="Message Body"], div[role="textbox"]').first
        await body_field.fill(body)
        await asyncio.sleep(0.5)

        # Click send
        send_btn = self.page.locator('div[aria-label*="Send"], div[data-tooltip*="Send"]').first
        await send_btn.click()
        await asyncio.sleep(2)

        return f"✅ Email sent to {to} — Subject: {subject or '(none)'}"

    async def _search_emails(self, params: dict) -> str:
        query = params.get("query", "")
        if not query:
            return "❌ What should I search for?"

        # Use Gmail search
        search_box = self.page.locator('input[aria-label="Search mail"]').first
        await search_box.click()
        await search_box.fill(query)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(3)

        # Read results
        emails = await self.page.evaluate("""
            () => {
                const rows = document.querySelectorAll('tr.zA');
                const results = [];
                for (let i = 0; i < Math.min(rows.length, 8); i++) {
                    const row = rows[i];
                    const sender = row.querySelector('.yW span')?.getAttribute('name') || 
                                   row.querySelector('.yW span')?.textContent || '?';
                    const subject = row.querySelector('.y6 span:first-child')?.textContent || '';
                    results.push({ sender, subject });
                }
                return results;
            }
        """)

        if not emails:
            return f"No results for '{query}'"

        lines = [f"  📄 {e['sender']} — {e['subject']}" for e in emails]
        return f"🔍 Search results for '{query}':\n\n" + "\n".join(lines)
