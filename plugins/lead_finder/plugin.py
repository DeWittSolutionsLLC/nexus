"""
Lead Finder Plugin - Automated client acquisition for web development.

Finds businesses via Google Maps that have bad or no websites,
scores them as leads, drafts personalized outreach, and can send via Gmail.

All done through browser automation - no APIs, no cloud.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.leads")

# Where to store found leads
LEADS_FILE = "memory/leads.json"


class LeadFinderPlugin(BasePlugin):
    name = "leads"
    description = "Find web dev clients - scrapes Google Maps, scores sites, drafts outreach"
    icon = "🎯"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.page = None
        self.leads: list[dict] = []
        self.portfolio_url = config.get("portfolio_url", "")
        self.your_name = config.get("your_name", "")
        self.your_email = config.get("your_email", "")
        self._load_leads()

    def _load_leads(self):
        path = Path(LEADS_FILE)
        if path.exists():
            try:
                self.leads = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self.leads = []

    def _save_leads(self):
        Path(LEADS_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(LEADS_FILE).write_text(
            json.dumps(self.leads, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )

    async def connect(self) -> bool:
        if not self.browser:
            self._status_message = "No browser engine"
            return False
        self._connected = True
        self._status_message = f"Ready ({len(self.leads)} leads saved)"
        return True

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "find_leads": self._find_leads,
            "score_leads": self._score_leads,
            "draft_outreach": self._draft_outreach,
            "send_outreach": self._send_outreach,
            "list_leads": self._list_leads,
            "full_pipeline": self._full_pipeline,
            "clear_leads": self._clear_leads,
            "set_profile": self._set_profile,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown leads action: {action}"
        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Lead finder error: {e}")
            return f"Error: {str(e)[:150]}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "find_leads", "description": "Search Google Maps for businesses in a location/niche that need websites", "params": ["query", "location", "max_results"]},
            {"action": "score_leads", "description": "Visit each lead's website and score how good/bad it is", "params": []},
            {"action": "draft_outreach", "description": "Draft personalized cold emails for uncontacted leads", "params": ["limit"]},
            {"action": "send_outreach", "description": "Send drafted outreach emails via Gmail", "params": ["lead_id", "send_all"]},
            {"action": "list_leads", "description": "Show all found leads and their status", "params": ["status"]},
            {"action": "full_pipeline", "description": "Run the full pipeline: find leads, score them, draft emails", "params": ["query", "location", "max_results"]},
            {"action": "clear_leads", "description": "Clear all saved leads", "params": []},
            {"action": "set_profile", "description": "Set your name, email, and portfolio URL for outreach", "params": ["name", "email", "portfolio_url"]},
        ]

    # ================================================================
    # STEP 1: Find leads on Google Maps
    # ================================================================

    async def _find_leads(self, params: dict) -> str:
        query = params.get("query", "restaurant")
        location = params.get("location", "")
        max_results = int(params.get("max_results", 15))

        search_query = f"{query} in {location}" if location else query

        # Use Google Maps search URL directly - bypasses any consent/landing issues
        encoded = search_query.replace(" ", "+")
        url = f"https://www.google.com/maps/search/{encoded}"
        page = await self.browser.get_page("maps_search", url)
        await asyncio.sleep(5)

        # Accept cookies/consent if prompted
        try:
            consent = page.locator('button:has-text("Accept all"), button:has-text("Accept"), form[action*="consent"] button')
            if await consent.count() > 0:
                await consent.first.click()
                await asyncio.sleep(2)
        except Exception:
            pass

        # Wait for results to load
        try:
            await page.wait_for_selector('div[role="feed"], div[role="article"]', timeout=15000)
        except Exception:
            # Try clicking the search box and searching manually
            try:
                search_box = page.locator('input#searchboxinput, input[name="q"], input[aria-label="Search Google Maps"]').first
                await search_box.click(timeout=5000)
                await search_box.fill(search_query)
                await page.keyboard.press("Enter")
                await asyncio.sleep(5)
            except Exception as e:
                return f"Couldn't load Google Maps search. Try typing the search directly in the Maps browser tab, then ask me to 'score leads'. Error: {str(e)[:80]}"

        # Scroll the results panel to load more
        try:
            results_panel = page.locator('div[role="feed"]').first
            for _ in range(3):
                await results_panel.evaluate('el => el.scrollTop = el.scrollHeight')
                await asyncio.sleep(2)
        except Exception:
            pass

        # Extract business listings
        businesses = await page.evaluate(f"""
            () => {{
                const results = [];
                // Try multiple selectors for business listings
                const selectors = [
                    'div[role="feed"] a[href*="/maps/place/"]',
                    'a[href*="/maps/place/"][aria-label]',
                    'div[role="article"] a[href*="/maps/place/"]',
                ];
                let items = [];
                for (const sel of selectors) {{
                    items = document.querySelectorAll(sel);
                    if (items.length > 0) break;
                }}
                for (let i = 0; i < Math.min(items.length, {max_results}); i++) {{
                    const item = items[i];
                    const name = item.getAttribute('aria-label') || item.textContent?.trim()?.split('\\n')[0] || '';
                    const href = item.getAttribute('href') || '';
                    if (name && name.length > 1 && !results.find(r => r.name === name)) {{
                        results.push({{ name: name.substring(0, 80), maps_url: href }});
                    }}
                }}
                return results;
            }}
        """)

        if not businesses:
            return f"No businesses found for '{search_query}'. Try a different search."

        # Click into each business to get details
        new_leads = 0
        for biz in businesses:
            # Skip if already in our leads
            if any(l["name"] == biz["name"] for l in self.leads):
                continue

            try:
                # Click the listing
                listing = page.locator(f'a[aria-label="{biz["name"]}"]').first
                await listing.click()
                await asyncio.sleep(2)

                # Extract details from the side panel
                details = await page.evaluate("""
                    () => {
                        const panel = document.querySelector('div[role="main"]');
                        if (!panel) return {};

                        const website = panel.querySelector('a[data-item-id="authority"]')?.href || '';
                        const phone = panel.querySelector('button[data-item-id*="phone"]')?.textContent?.trim() || '';
                        const address = panel.querySelector('button[data-item-id="address"]')?.textContent?.trim() || '';
                        const rating = panel.querySelector('span[role="img"]')?.getAttribute('aria-label') || '';
                        const category = panel.querySelector('button[jsaction*="category"]')?.textContent?.trim() || '';

                        return { website, phone, address, rating, category };
                    }
                """)

                lead = {
                    "id": len(self.leads) + new_leads + 1,
                    "name": biz["name"],
                    "website": details.get("website", ""),
                    "phone": details.get("phone", ""),
                    "address": details.get("address", ""),
                    "rating": details.get("rating", ""),
                    "category": details.get("category", ""),
                    "maps_url": biz.get("maps_url", ""),
                    "search_query": search_query,
                    "found_date": datetime.now().isoformat(),
                    "website_score": None,
                    "website_issues": [],
                    "email_draft": "",
                    "status": "new",  # new -> scored -> drafted -> sent -> replied
                    "notes": "",
                }

                self.leads.append(lead)
                new_leads += 1

                # Go back to results
                await page.keyboard.press("Escape")
                await asyncio.sleep(1)

            except Exception as e:
                logger.debug(f"Couldn't get details for {biz['name']}: {e}")
                continue

        self._save_leads()
        no_site = sum(1 for l in self.leads[-new_leads:] if not l["website"])
        return (
            f"Found {new_leads} new leads for '{search_query}'.\n"
            f"  {no_site} have NO website at all.\n"
            f"  {new_leads - no_site} have websites (will score next).\n"
            f"  Total leads in database: {len(self.leads)}\n\n"
            f"Say 'score leads' to check their website quality."
        )

    # ================================================================
    # STEP 2: Score each lead's website quality
    # ================================================================

    async def _score_leads(self, params: dict) -> str:
        unscored = [l for l in self.leads if l["website_score"] is None]
        if not unscored:
            return "All leads are already scored. Find more leads first."

        page = await self.browser.get_page("lead_scorer", "about:blank")
        scored = 0

        for lead in unscored:
            if not lead["website"]:
                lead["website_score"] = 0
                lead["website_issues"] = ["NO WEBSITE - perfect prospect"]
                lead["status"] = "scored"
                scored += 1
                continue

            try:
                await page.goto(lead["website"], wait_until="domcontentloaded", timeout=10000)
                await asyncio.sleep(2)

                # Analyze the website
                analysis = await page.evaluate("""
                    () => {
                        const issues = [];
                        let score = 100;

                        // Check mobile viewport
                        const viewport = document.querySelector('meta[name="viewport"]');
                        if (!viewport) { issues.push("Not mobile responsive"); score -= 25; }

                        // Check SSL (we can only check if page loaded)
                        if (location.protocol !== 'https:') { issues.push("No SSL/HTTPS"); score -= 15; }

                        // Check for modern design signals
                        const styles = getComputedStyle(document.body);
                        const allText = document.body.innerText || '';

                        // Check if site looks outdated
                        const hasFlash = document.querySelector('embed, object');
                        if (hasFlash) { issues.push("Uses Flash (very outdated)"); score -= 30; }

                        const tables = document.querySelectorAll('table');
                        if (tables.length > 3) { issues.push("Table-based layout (outdated)"); score -= 20; }

                        // Check page load content
                        const images = document.querySelectorAll('img');
                        const brokenImages = Array.from(images).filter(i => !i.complete || i.naturalWidth === 0);
                        if (brokenImages.length > 0) { issues.push(`${brokenImages.length} broken images`); score -= 10; }

                        // Check for contact info
                        const hasPhone = /\d{3}[-.\s]?\d{3}[-.\s]?\d{4}/.test(allText);
                        const hasEmail = /@/.test(allText);
                        if (!hasPhone && !hasEmail) { issues.push("No visible contact info"); score -= 10; }

                        // Check copyright year
                        const yearMatch = allText.match(/©\s*(\d{4})/);
                        if (yearMatch && parseInt(yearMatch[1]) < 2023) {
                            issues.push(`Copyright outdated (${yearMatch[1]})`); score -= 10;
                        }

                        // Check basic SEO
                        const title = document.title;
                        const metaDesc = document.querySelector('meta[name="description"]');
                        if (!title || title.length < 10) { issues.push("Missing/bad page title"); score -= 10; }
                        if (!metaDesc) { issues.push("No meta description"); score -= 5; }

                        // Check for social media links
                        const hasSocial = document.querySelector('a[href*="facebook"], a[href*="instagram"], a[href*="twitter"], a[href*="linkedin"]');
                        if (!hasSocial) { issues.push("No social media links"); score -= 5; }

                        // Check page speed indicators
                        const totalSize = document.documentElement.outerHTML.length;
                        if (totalSize > 500000) { issues.push("Very heavy page"); score -= 10; }

                        return { score: Math.max(0, score), issues };
                    }
                """)

                lead["website_score"] = analysis.get("score", 50)
                lead["website_issues"] = analysis.get("issues", [])
                lead["status"] = "scored"
                scored += 1

            except Exception as e:
                lead["website_score"] = 10
                lead["website_issues"] = [f"Website failed to load: {str(e)[:80]}"]
                lead["status"] = "scored"
                scored += 1

        self._save_leads()

        # Summary
        hot = [l for l in self.leads if l["website_score"] is not None and l["website_score"] <= 40]
        warm = [l for l in self.leads if l["website_score"] is not None and 40 < l["website_score"] <= 70]

        lines = [f"Scored {scored} leads:\n"]
        lines.append(f"  🔥 {len(hot)} HOT leads (score 0-40 - need a new website badly)")
        lines.append(f"  🟡 {len(warm)} WARM leads (score 41-70 - could use improvement)")
        lines.append(f"\nTop prospects:")

        for lead in sorted(self.leads, key=lambda l: l.get("website_score", 100))[:8]:
            score = lead.get("website_score", "?")
            issues = ", ".join(lead.get("website_issues", [])[:3])
            site = "NO SITE" if not lead["website"] else lead["website"][:40]
            lines.append(f"  #{lead['id']} {lead['name']} (score: {score})")
            lines.append(f"     {site}")
            lines.append(f"     Issues: {issues}")

        lines.append(f"\nSay 'draft outreach' to create personalized emails.")
        return "\n".join(lines)

    # ================================================================
    # STEP 3: Draft personalized outreach emails
    # ================================================================

    async def _draft_outreach(self, params: dict) -> str:
        limit = int(params.get("limit", 5))

        # Get hot leads without drafts
        prospects = [
            l for l in self.leads
            if l.get("status") in ("scored", "new")
            and l.get("website_score") is not None
            and l.get("website_score") <= 60
            and not l.get("email_draft")
        ]
        prospects.sort(key=lambda l: l.get("website_score", 100))
        prospects = prospects[:limit]

        if not prospects:
            return "No uncontacted hot leads to draft for. Find or score more leads first."

        drafted = 0
        for lead in prospects:
            issues = lead.get("website_issues", [])
            has_site = bool(lead.get("website"))
            name = lead["name"]
            category = lead.get("category", "business")

            # Build a personalized email
            if not has_site:
                subject = f"Quick question about {name}'s online presence"
                body = (
                    f"Hi,\n\n"
                    f"I came across {name} and noticed you don't currently have a website. "
                    f"In today's market, over 80% of customers search online before visiting a {category.lower()} "
                    f"- so you're likely missing out on a lot of potential customers.\n\n"
                    f"I specialize in building modern, mobile-friendly websites for local businesses like yours. "
                    f"I'd love to show you what a professional web presence could do for {name}.\n\n"
                    f"Would you be open to a quick 10-minute call this week? No pressure at all.\n\n"
                )
            else:
                # Has a website but it's bad
                issue_text = ""
                if "Not mobile responsive" in issues:
                    issue_text = "it isn't mobile-friendly (over 60% of web traffic is mobile now)"
                elif "No SSL/HTTPS" in issues:
                    issue_text = "it's missing SSL security, which makes browsers show a 'Not Secure' warning to visitors"
                elif any("outdated" in i.lower() for i in issues):
                    issue_text = "the design could use a refresh to match today's standards"
                elif any("broken" in i.lower() for i in issues):
                    issue_text = "there are some broken elements that could be turning customers away"
                else:
                    issue_text = "there are a few things that could be improved to help you get more customers"

                subject = f"Quick thought about {name}'s website"
                body = (
                    f"Hi,\n\n"
                    f"I was looking at {name}'s website and noticed {issue_text}.\n\n"
                    f"I work with local {category.lower()} businesses to modernize their web presence "
                    f"and help them attract more customers online. A few small changes could make a big difference "
                    f"for your business.\n\n"
                    f"Would you be interested in a free, no-obligation review of your site? "
                    f"I can put together a quick report showing exactly what could be improved.\n\n"
                )

            # Add closing
            if self.portfolio_url:
                body += f"You can see some of my work at {self.portfolio_url}\n\n"
            body += f"Best regards,\n{self.your_name or 'Your Name'}"
            if self.your_email:
                body += f"\n{self.your_email}"

            lead["email_draft"] = body
            lead["email_subject"] = subject
            lead["status"] = "drafted"
            drafted += 1

        self._save_leads()

        lines = [f"Drafted {drafted} outreach emails:\n"]
        for lead in prospects[:drafted]:
            lines.append(f"  #{lead['id']} {lead['name']}")
            lines.append(f"     Subject: {lead.get('email_subject', '?')}")
            lines.append(f"     Score: {lead.get('website_score', '?')}/100")
            lines.append("")

        lines.append("Say 'send outreach' to send all, or 'send outreach lead_id 3' for one.")
        return "\n".join(lines)

    # ================================================================
    # STEP 4: Send outreach via Gmail
    # ================================================================

    async def _send_outreach(self, params: dict) -> str:
        lead_id = params.get("lead_id")
        send_all = params.get("send_all", "false").lower() == "true"

        if lead_id:
            targets = [l for l in self.leads if str(l["id"]) == str(lead_id)]
        elif send_all:
            targets = [l for l in self.leads if l.get("status") == "drafted" and l.get("email_draft")]
        else:
            targets = [l for l in self.leads if l.get("status") == "drafted" and l.get("email_draft")]

        if not targets:
            return "No drafted emails to send. Run 'draft outreach' first."

        # We need the email to send to - check if we have it from the business
        # For businesses without email, we note them for manual follow-up
        sent = 0
        manual = 0
        results = []

        email_plugin = None
        if hasattr(self, 'browser') and self.browser:
            # We'll use Gmail directly through browser automation
            pass

        for lead in targets:
            # Check if we have an email for this business
            biz_email = lead.get("email", "")

            if not biz_email:
                # Try to extract from their website
                if lead.get("website"):
                    try:
                        page = await self.browser.get_page("email_finder", lead["website"])
                        await asyncio.sleep(2)
                        found_emails = await page.evaluate("""
                            () => {
                                const text = document.body.innerText || '';
                                const html = document.body.innerHTML || '';
                                const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
                                const emails = [...new Set([...(text.match(emailRegex) || []), ...(html.match(emailRegex) || [])])];
                                // Filter out common non-business emails
                                return emails.filter(e =>
                                    !e.includes('example.com') &&
                                    !e.includes('sentry.') &&
                                    !e.includes('wixpress') &&
                                    !e.includes('@2x') &&
                                    !e.endsWith('.png') &&
                                    !e.endsWith('.jpg')
                                ).slice(0, 3);
                            }
                        """)
                        if found_emails:
                            biz_email = found_emails[0]
                            lead["email"] = biz_email
                    except Exception:
                        pass

            if biz_email:
                # Send via Gmail browser automation
                try:
                    gmail_page = await self.browser.get_page("gmail", "https://mail.google.com")
                    await asyncio.sleep(1)

                    # Click compose
                    compose = gmail_page.locator('div[gh="cm"]').first
                    await compose.click()
                    await asyncio.sleep(1.5)

                    # Fill To
                    to_field = gmail_page.locator('input[aria-label="To recipients"], textarea[aria-label="To recipients"]').first
                    await to_field.fill(biz_email)
                    await asyncio.sleep(0.5)

                    # Fill Subject
                    subj_field = gmail_page.locator('input[name="subjectbox"]').first
                    await subj_field.fill(lead.get("email_subject", f"About {lead['name']}'s website"))

                    # Fill Body
                    body_field = gmail_page.locator('div[aria-label="Message Body"], div[role="textbox"]').first
                    await body_field.fill(lead.get("email_draft", ""))
                    await asyncio.sleep(0.5)

                    # Send
                    send_btn = gmail_page.locator('div[aria-label*="Send"], div[data-tooltip*="Send"]').first
                    await send_btn.click()
                    await asyncio.sleep(2)

                    lead["status"] = "sent"
                    lead["sent_date"] = datetime.now().isoformat()
                    sent += 1
                    results.append(f"  Sent to #{lead['id']} {lead['name']} ({biz_email})")

                except Exception as e:
                    results.append(f"  Failed #{lead['id']} {lead['name']}: {str(e)[:60]}")
            else:
                lead["status"] = "no_email"
                manual += 1
                results.append(f"  #{lead['id']} {lead['name']} - no email found (use phone: {lead.get('phone', 'N/A')})")

        self._save_leads()

        summary = [f"Outreach results:\n"]
        summary.append(f"  Emails sent: {sent}")
        summary.append(f"  Need manual contact: {manual}")
        summary.append(f"\nDetails:")
        summary.extend(results)

        return "\n".join(summary)

    # ================================================================
    # Full Pipeline
    # ================================================================

    async def _full_pipeline(self, params: dict) -> str:
        query = params.get("query", "restaurant")
        location = params.get("location", "")
        max_results = int(params.get("max_results", 10))

        results = []

        # Step 1: Find
        results.append("STEP 1: Finding leads...")
        find_result = await self._find_leads({"query": query, "location": location, "max_results": max_results})
        results.append(find_result)

        # Step 2: Score
        results.append("\nSTEP 2: Scoring websites...")
        score_result = await self._score_leads({})
        results.append(score_result)

        # Step 3: Draft
        results.append("\nSTEP 3: Drafting outreach emails...")
        draft_result = await self._draft_outreach({"limit": "5"})
        results.append(draft_result)

        results.append("\nPipeline complete! Say 'send outreach' to send the emails, or 'list leads' to review them first.")
        return "\n".join(results)

    # ================================================================
    # Utility
    # ================================================================

    async def _list_leads(self, params: dict) -> str:
        status_filter = params.get("status", "")

        leads = self.leads
        if status_filter:
            leads = [l for l in leads if l.get("status") == status_filter]

        if not leads:
            return "No leads found. Say 'find leads restaurants in Detroit' to start."

        lines = [f"Leads database ({len(leads)} total):\n"]

        # Group by status
        by_status = {}
        for l in leads:
            s = l.get("status", "new")
            by_status.setdefault(s, []).append(l)

        status_icons = {"new": "🆕", "scored": "📊", "drafted": "📝", "sent": "📤", "replied": "✅", "no_email": "📞"}

        for status, group in by_status.items():
            icon = status_icons.get(status, "?")
            lines.append(f"\n{icon} {status.upper()} ({len(group)}):")
            for l in group[:5]:
                score = l.get("website_score", "?")
                site = "NO SITE" if not l.get("website") else "has site"
                lines.append(f"  #{l['id']} {l['name']} | score: {score} | {site}")
            if len(group) > 5:
                lines.append(f"  ... +{len(group)-5} more")

        return "\n".join(lines)

    async def _clear_leads(self, params: dict) -> str:
        count = len(self.leads)
        self.leads = []
        self._save_leads()
        return f"Cleared {count} leads."

    async def _set_profile(self, params: dict) -> str:
        if params.get("name"):
            self.your_name = params["name"]
        if params.get("email"):
            self.your_email = params["email"]
        if params.get("portfolio_url"):
            self.portfolio_url = params["portfolio_url"]
        return (
            f"Profile updated:\n"
            f"  Name: {self.your_name}\n"
            f"  Email: {self.your_email}\n"
            f"  Portfolio: {self.portfolio_url}"
        )