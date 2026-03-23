"""
GitHub Plugin — GitHub.com web automation via Playwright.
No PAT needed — uses your browser login session.
"""

import asyncio
import logging
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.github")


class GitHubAutoPlugin(BasePlugin):
    name = "github"
    description = "Browse GitHub repos, issues, PRs, notifications (browser)"
    icon = "🐙"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.page = None
        self.url = config.get("url", "https://github.com")
        self.username = config.get("username", "")

    async def connect(self) -> bool:
        if not self.browser:
            self._status_message = "No browser engine"
            return False

        try:
            self.page = await self.browser.get_page("github", self.url)
            await asyncio.sleep(2)

            logged_in = await self.browser.check_logged_in(
                "github",
                'img[alt*="@"], summary[aria-label="View profile"]',
                timeout=8000
            )

            if logged_in:
                self._connected = True
                self._status_message = "Logged into GitHub"
                # Try to get username
                if not self.username:
                    self.username = await self.page.evaluate("""
                        () => document.querySelector('meta[name="user-login"]')?.content || ''
                    """) or ""
                return True
            else:
                self._status_message = "⏳ Log into GitHub in the browser window"
                success = await self.browser.wait_for_user_login(
                    "github", 'img[alt*="@"], summary[aria-label="View profile"]', max_wait=180
                )
                if success:
                    self._connected = True
                    self._status_message = "Logged into GitHub"
                    return True
                self._status_message = "GitHub login timed out"
                return False

        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self.page or self.page.is_closed():
            return "❌ GitHub page not available."

        actions = {
            "check_notifications": self._check_notifications,
            "list_repos": self._list_repos,
            "list_prs": self._list_prs,
            "list_issues": self._list_issues,
            "create_issue": self._create_issue,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown GitHub action: {action}"
        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"GitHub action '{action}' failed: {e}")
            return f"❌ GitHub error: {str(e)[:100]}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "check_notifications", "description": "Check GitHub notifications", "params": []},
            {"action": "list_repos", "description": "List your GitHub repositories", "params": ["limit"]},
            {"action": "list_prs", "description": "List open pull requests", "params": ["repo"]},
            {"action": "list_issues", "description": "List issues in a repository", "params": ["repo", "state"]},
            {"action": "create_issue", "description": "Create a new issue in a repo", "params": ["repo", "title", "body"]},
        ]

    async def _check_notifications(self, params: dict) -> str:
        await self.page.goto("https://github.com/notifications", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        notifs = await self.page.evaluate("""
            () => {
                const items = document.querySelectorAll('.notifications-list-item, li.notification');
                const results = [];
                
                // Try new layout
                const rows = document.querySelectorAll('div.js-notification-group li, .notification-list-item-link');
                if (rows.length === 0) {
                    // Try alternative selectors
                    const altRows = document.querySelectorAll('.Box-row');
                    altRows.forEach(row => {
                        const title = row.querySelector('a.notification-list-item-link')?.textContent?.trim() ||
                                      row.querySelector('p')?.textContent?.trim() || '';
                        const repo = row.querySelector('.text-bold')?.textContent?.trim() || '';
                        const type = row.querySelector('.octicon')?.getAttribute('aria-label') || '';
                        if (title) results.push({ title: title.substring(0, 80), repo, type });
                    });
                }
                
                rows.forEach(row => {
                    const title = row.textContent?.trim()?.substring(0, 80) || '';
                    if (title) results.push({ title, repo: '', type: '' });
                });
                
                return results.slice(0, 15);
            }
        """)

        if not notifs:
            # Check if page says "All caught up"
            text = await self.page.text_content("body") or ""
            if "all caught up" in text.lower():
                return "✅ No unread GitHub notifications — you're all caught up!"
            return "Couldn't read notifications. The page layout may have changed."

        lines = [f"  🔔 {n['title']}" for n in notifs]
        return f"🐙 GitHub Notifications ({len(notifs)}):\n\n" + "\n".join(lines)

    async def _list_repos(self, params: dict) -> str:
        limit = int(params.get("limit", 10))
        url = f"https://github.com/{self.username}?tab=repositories" if self.username else "https://github.com/dashboard"
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        repos = await self.page.evaluate(f"""
            () => {{
                const items = document.querySelectorAll('#user-repositories-list li, div[data-filterable-for] li');
                const results = [];
                for (let i = 0; i < Math.min(items.length, {limit}); i++) {{
                    const nameEl = items[i].querySelector('a[itemprop="name codeRepository"], h3 a');
                    const name = nameEl?.textContent?.trim() || '';
                    const desc = items[i].querySelector('p[itemprop="description"], p')?.textContent?.trim() || '';
                    const lang = items[i].querySelector('[itemprop="programmingLanguage"]')?.textContent?.trim() || '';
                    if (name) results.push({{ name, desc: desc.substring(0, 80), lang }});
                }}
                return results;
            }}
        """)

        if not repos:
            return "Couldn't read repositories."

        lines = [f"  📦 {r['name']} {('(' + r['lang'] + ')') if r['lang'] else ''}\n     {r['desc']}" for r in repos]
        return f"🐙 Your repos:\n\n" + "\n".join(lines)

    async def _list_prs(self, params: dict) -> str:
        repo = params.get("repo", "")
        if repo:
            await self.page.goto(f"https://github.com/{repo}/pulls", wait_until="domcontentloaded")
        else:
            await self.page.goto("https://github.com/pulls", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        prs = await self.page.evaluate("""
            () => {
                const items = document.querySelectorAll('div[id^="issue_"]');
                const results = [];
                items.forEach(item => {
                    const title = item.querySelector('a[data-hovercard-type="pull_request"]')?.textContent?.trim() ||
                                  item.querySelector('a[id^="issue_"]')?.textContent?.trim() || '';
                    const meta = item.querySelector('.opened-by')?.textContent?.trim() || '';
                    if (title) results.push({ title: title.substring(0, 80), meta: meta.substring(0, 60) });
                });
                return results.slice(0, 10);
            }
        """)

        if not prs:
            return f"No open PRs found{' in ' + repo if repo else ''}."

        lines = [f"  🔀 {p['title']}" for p in prs]
        return f"🔀 Open PRs{' in ' + repo if repo else ''}:\n\n" + "\n".join(lines)

    async def _list_issues(self, params: dict) -> str:
        repo = params.get("repo", "")
        state = params.get("state", "open")

        if not repo:
            return "❌ Which repo? Provide the name like 'username/repo'"

        await self.page.goto(
            f"https://github.com/{repo}/issues?q=is%3Aissue+is%3A{state}",
            wait_until="domcontentloaded"
        )
        await asyncio.sleep(2)

        issues = await self.page.evaluate("""
            () => {
                const items = document.querySelectorAll('div[id^="issue_"]');
                const results = [];
                items.forEach(item => {
                    const title = item.querySelector('a[data-hovercard-type="issue"]')?.textContent?.trim() ||
                                  item.querySelector('a[id^="issue_"]')?.textContent?.trim() || '';
                    const labels = [];
                    item.querySelectorAll('a[data-name]').forEach(l => labels.push(l.textContent.trim()));
                    if (title) results.push({ title: title.substring(0, 80), labels });
                });
                return results.slice(0, 10);
            }
        """)

        if not issues:
            return f"No {state} issues in {repo}."

        lines = [f"  🔹 {iss['title']} {' '.join('[' + l + ']' for l in iss['labels'])}" for iss in issues]
        return f"📋 {state.title()} issues in {repo}:\n\n" + "\n".join(lines)

    async def _create_issue(self, params: dict) -> str:
        repo = params.get("repo", "")
        title = params.get("title", "")
        body = params.get("body", "")

        if not repo or not title:
            return "❌ Need a repo name and issue title."

        await self.page.goto(f"https://github.com/{repo}/issues/new", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Fill title
        title_input = self.page.locator('#issue_title').first
        await title_input.fill(title)

        # Fill body
        if body:
            body_input = self.page.locator('#issue_body, textarea[name="issue[body]"]').first
            await body_input.fill(body)

        # Submit
        submit_btn = self.page.locator('button[type="submit"]:has-text("Submit new issue")').first
        await submit_btn.click()
        await asyncio.sleep(2)

        return f"✅ Created issue in {repo}: {title}"
