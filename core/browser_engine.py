"""
Browser Engine — Manages a single persistent Playwright Chromium instance.

All browser-based plugins share this one browser. Each plugin gets its own tab (context/page).
Login sessions persist in ./browser_data/ so you only log in once.
"""

import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger("nexus.browser")


class BrowserEngine:
    """
    Shared persistent browser instance.
    
    Uses Playwright's persistent context so cookies/sessions survive restarts.
    Each plugin requests a named page (tab) via get_page().
    """

    def __init__(self, config: dict):
        self.config = config
        self._playwright = None
        self._context: BrowserContext = None
        self._pages: dict[str, Page] = {}
        self._user_data_dir = Path(config.get("user_data_dir", "./browser_data")).resolve()

    async def start(self):
        """Launch the persistent browser."""
        self._user_data_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()

        headless = self.config.get("headless", False)
        slow_mo = self.config.get("slow_mo", 50)
        timeout = self.config.get("default_timeout", 15000)

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._user_data_dir),
            headless=headless,
            slow_mo=slow_mo,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
        self._context.set_default_timeout(timeout)

        logger.info(f"Browser started (headless={headless}, data={self._user_data_dir})")

    async def get_page(self, name: str, url: str = None) -> Page:
        """
        Get or create a named tab. If it doesn't exist, opens one and navigates to url.
        
        Args:
            name: Unique page identifier (e.g. 'gmail', 'whatsapp')
            url: URL to navigate to if creating a new page
        """
        if name in self._pages:
            page = self._pages[name]
            if not page.is_closed():
                return page

        # Create new page (tab)
        page = await self._context.new_page()
        self._pages[name] = page

        if url:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"Navigation to {url} had issues: {e}")

        return page

    async def close_page(self, name: str):
        """Close a specific tab."""
        if name in self._pages:
            page = self._pages.pop(name)
            if not page.is_closed():
                await page.close()

    async def stop(self):
        """Close the browser cleanly."""
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")

    @property
    def is_running(self) -> bool:
        return self._context is not None

    async def check_logged_in(self, name: str, indicator_selector: str, timeout: int = 5000) -> bool:
        """
        Check if a page has an active login session.
        
        Args:
            name: Page name
            indicator_selector: CSS selector that only appears when logged in
            timeout: How long to wait for the selector (ms)
        """
        if name not in self._pages:
            return False
        page = self._pages[name]
        try:
            await page.wait_for_selector(indicator_selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def wait_for_user_login(self, name: str, indicator_selector: str,
                                    check_interval: float = 2.0, max_wait: float = 300.0) -> bool:
        """
        Wait for the user to manually log in on a page.
        Checks for indicator_selector periodically.

        Args:
            max_wait: Maximum seconds to wait (default 5 minutes)
        """
        import time
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            if await self.check_logged_in(name, indicator_selector, timeout=2000):
                return True
            await asyncio.sleep(check_interval)
        return False
