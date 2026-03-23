"""
Website Auditor Plugin — SEO, performance, and accessibility analysis.
Analyzes any URL without browser automation. Uses requests + BeautifulSoup.
"""

import logging
import time
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.website_auditor")


class WebsiteAuditorPlugin(BasePlugin):
    name = "website_auditor"
    description = "Audit any website — SEO, speed, mobile, SSL, accessibility"
    icon = "🔍"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._available = False

    async def connect(self) -> bool:
        try:
            import requests  # noqa: F401
            from bs4 import BeautifulSoup  # noqa: F401
            self._available = True
            self._connected = True
            self._status_message = "Ready to audit"
            return True
        except ImportError as e:
            self._status_message = f"Missing: {e.name} (pip install requests beautifulsoup4)"
            self._connected = False
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self._available:
            return "⚠️ Install dependencies: pip install requests beautifulsoup4"

        actions = {
            "audit_site":    self._audit_site,
            "check_speed":   self._check_speed,
            "check_seo":     self._check_seo,
            "bulk_audit":    self._bulk_audit,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown auditor action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "audit_site",  "description": "Full audit of a website — SEO, speed, mobile, SSL", "params": ["url"]},
            {"action": "check_speed", "description": "Check website response time only",                   "params": ["url"]},
            {"action": "check_seo",   "description": "SEO-specific audit — title, meta, headings, links",  "params": ["url"]},
            {"action": "bulk_audit",  "description": "Audit multiple URLs at once",                        "params": ["urls"]},
        ]

    async def _audit_site(self, params: dict) -> str:
        url = self._normalize_url(params.get("url", ""))
        if not url:
            return "⚠️ Please provide a URL to audit, sir."

        import requests
        from bs4 import BeautifulSoup

        checks = {}
        score = 0
        max_score = 0

        # 1. Availability + response time
        try:
            start = time.perf_counter()
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 Nexus-Auditor/2.0"}, allow_redirects=True)
            elapsed_ms = (time.perf_counter() - start) * 1000
            status_ok = resp.status_code == 200
            checks["availability"] = (status_ok, f"HTTP {resp.status_code}", 15)
            score += 15 if status_ok else 0
            max_score += 15
        except requests.exceptions.ConnectionError:
            return f"⚠️ Could not connect to '{url}'. Site may be down or URL is incorrect."
        except requests.exceptions.Timeout:
            return f"⚠️ '{url}' timed out after 10 seconds. Site is very slow."
        except Exception as e:
            return f"⚠️ Failed to reach '{url}': {e}"

        # Parse HTML
        soup = BeautifulSoup(resp.text, "html.parser")

        # 2. HTTPS / SSL
        is_https = url.startswith("https://")
        checks["ssl"] = (is_https, "HTTPS" if is_https else "HTTP only — no SSL", 10)
        score += 10 if is_https else 0
        max_score += 10

        # 3. Response speed
        speed_ok = elapsed_ms < 2000
        speed_label = f"{elapsed_ms:.0f}ms" + (" ✓" if speed_ok else " — slow")
        checks["speed"] = (speed_ok, speed_label, 10)
        score += 10 if speed_ok else (5 if elapsed_ms < 4000 else 0)
        max_score += 10

        # 4. Title tag
        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else ""
        title_len = len(title_text)
        title_ok = 30 <= title_len <= 60
        title_detail = f'"{title_text[:50]}{"..." if title_len > 50 else ""}" ({title_len} chars)' if title_text else "Missing"
        checks["title"] = (title_ok, title_detail, 10)
        score += 10 if title_ok else (5 if title_text else 0)
        max_score += 10

        # 5. Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        desc_content = meta_desc.get("content", "").strip() if meta_desc else ""
        desc_len = len(desc_content)
        desc_ok = 120 <= desc_len <= 160
        desc_detail = f"{desc_len} chars" if desc_content else "Missing"
        checks["meta_desc"] = (desc_ok, desc_detail, 10)
        score += 10 if desc_ok else (5 if desc_content else 0)
        max_score += 10

        # 6. Mobile viewport
        viewport = soup.find("meta", attrs={"name": "viewport"})
        viewport_ok = viewport is not None
        checks["mobile"] = (viewport_ok, "Viewport meta found" if viewport_ok else "Missing viewport meta", 10)
        score += 10 if viewport_ok else 0
        max_score += 10

        # 7. H1 heading
        h1s = soup.find_all("h1")
        h1_ok = len(h1s) == 1
        h1_detail = f"{len(h1s)} found" + (f': "{h1s[0].get_text(strip=True)[:40]}"' if h1s else "")
        checks["h1"] = (h1_ok, h1_detail, 10)
        score += 10 if h1_ok else (5 if h1s else 0)
        max_score += 10

        # 8. Image alt text
        images = soup.find_all("img")
        imgs_with_alt = sum(1 for img in images if img.get("alt", "").strip())
        img_ok = len(images) == 0 or (imgs_with_alt / len(images)) >= 0.9
        img_detail = f"{imgs_with_alt}/{len(images)} images have alt text" if images else "No images"
        checks["img_alt"] = (img_ok, img_detail, 5)
        score += 5 if img_ok else (3 if imgs_with_alt else 0)
        max_score += 5

        # 9. Canonical URL
        canonical = soup.find("link", attrs={"rel": "canonical"})
        canon_ok = canonical is not None
        checks["canonical"] = (canon_ok, "Set" if canon_ok else "Not set", 5)
        score += 5 if canon_ok else 0
        max_score += 5

        # 10. robots.txt
        try:
            robots_url = self._base_url(url) + "/robots.txt"
            r = requests.get(robots_url, timeout=4)
            robots_ok = r.status_code == 200
        except Exception:
            robots_ok = False
        checks["robots"] = (robots_ok, "Found" if robots_ok else "Not found", 5)
        score += 5 if robots_ok else 0
        max_score += 5

        # 11. Open Graph tags
        og_title = soup.find("meta", property="og:title")
        og_ok = og_title is not None
        checks["open_graph"] = (og_ok, "og:title found" if og_ok else "No OG tags", 5)
        score += 5 if og_ok else 0
        max_score += 5

        # 12. Page weight estimate
        page_kb = len(resp.content) / 1024
        weight_ok = page_kb < 500
        checks["page_size"] = (weight_ok, f"{page_kb:.0f} KB", 5)
        score += 5 if weight_ok else (3 if page_kb < 1024 else 0)
        max_score += 5

        # Format results
        pct = int(score / max_score * 100) if max_score else 0
        grade = "A+" if pct >= 90 else "A" if pct >= 80 else "B" if pct >= 70 else "C" if pct >= 60 else "D" if pct >= 50 else "F"
        bar = self._score_bar(pct)

        lines = [
            f"🔍 WEBSITE AUDIT — {url}",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"  Score:  {bar} {pct}/100  (Grade: {grade})",
            f"",
        ]

        check_labels = {
            "availability": "Availability",
            "ssl":          "SSL / HTTPS",
            "speed":        "Response Speed",
            "title":        "Page Title",
            "meta_desc":    "Meta Description",
            "mobile":       "Mobile Friendly",
            "h1":           "H1 Heading",
            "img_alt":      "Image Alt Text",
            "canonical":    "Canonical URL",
            "robots":       "robots.txt",
            "open_graph":   "Open Graph",
            "page_size":    "Page Size",
        }

        for key, (ok, detail, pts) in checks.items():
            icon = "✅" if ok else "⚠️"
            label = check_labels.get(key, key)
            lines.append(f"  {icon} {label:<18}  {detail}")

        # Summary recommendations
        issues = [k for k, (ok, _, _) in checks.items() if not ok]
        if issues:
            lines.append(f"\n📋 TOP RECOMMENDATIONS:")
            recs = {
                "ssl":        "Switch to HTTPS — free via Let's Encrypt",
                "speed":      "Optimize images, enable caching, consider a CDN",
                "title":      "Write a descriptive title (30-60 characters)",
                "meta_desc":  "Add a meta description (120-160 characters)",
                "mobile":     "Add <meta name='viewport' content='width=device-width'>",
                "h1":         "Ensure exactly one H1 heading per page",
                "img_alt":    "Add descriptive alt text to all images",
                "canonical":  "Add a canonical URL tag to prevent duplicate content",
                "robots":     "Create a robots.txt file at your domain root",
                "open_graph": "Add Open Graph tags for better social media sharing",
                "page_size":  "Compress images and minify CSS/JS to reduce page weight",
            }
            for issue in issues[:5]:
                if issue in recs:
                    lines.append(f"  • {recs[issue]}")

        return "\n".join(lines)

    async def _check_speed(self, params: dict) -> str:
        url = self._normalize_url(params.get("url", ""))
        if not url:
            return "⚠️ Please provide a URL."
        import requests
        results = []
        for i in range(3):
            try:
                start = time.perf_counter()
                requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 Nexus-Auditor/2.0"})
                elapsed = (time.perf_counter() - start) * 1000
                results.append(elapsed)
            except Exception:
                pass
        if not results:
            return f"⚠️ Could not reach {url}."
        avg = sum(results) / len(results)
        rating = "Excellent" if avg < 500 else "Good" if avg < 1000 else "Acceptable" if avg < 2000 else "Slow" if avg < 4000 else "Very slow"
        return (
            f"⚡ SPEED — {url}\n"
            f"  Average: {avg:.0f}ms over {len(results)} requests\n"
            f"  Rating:  {rating}\n"
            f"  Samples: {', '.join(f'{r:.0f}ms' for r in results)}"
        )

    async def _check_seo(self, params: dict) -> str:
        # Delegate to full audit but filter for SEO checks
        full = await self._audit_site(params)
        return full

    async def _bulk_audit(self, params: dict) -> str:
        urls = params.get("urls", [])
        if isinstance(urls, str):
            urls = [u.strip() for u in urls.split(",") if u.strip()]
        if not urls:
            return "⚠️ Please provide URLs to audit."
        lines = [f"🔍 BULK AUDIT — {len(urls)} sites\n{'─'*50}"]
        for url in urls[:5]:
            result = await self._audit_site({"url": url})
            # Extract score line only
            for line in result.split("\n"):
                if "Score:" in line or url in line:
                    lines.append(line.strip())
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _normalize_url(url: str) -> str:
        if not url:
            return ""
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    @staticmethod
    def _base_url(url: str) -> str:
        from urllib.parse import urlparse
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"

    @staticmethod
    def _score_bar(pct: int) -> str:
        filled = pct // 5
        empty = 20 - filled
        return "█" * filled + "░" * empty
