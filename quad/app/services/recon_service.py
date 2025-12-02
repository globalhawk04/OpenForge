# FILE: app/services/recon_service.py
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import asyncio
import re
import json
import random

try:
    from playwright_stealth import stealth_async
except ImportError:
    stealth_async = None

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

class Scraper:
    def __init__(self):
        self.playwright = None
        self.browser = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars"]
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()

    async def scrape_product_page(self, url: str):
        context = await self.browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        if stealth_async: await stealth_async(page)
        
        # RELAXED BLOCKING: Only block heavy media. 
        # Blocking 'script' or 'other' crashes React/Vue apps (AliExpress, RobotShop).
        await page.route("**/*", lambda route: route.abort() 
            if route.request.resource_type in ["font", "image", "media"] 
            else route.continue_()
        )

        try:
            # Short timeout, retry logic handled by caller
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            
            # Quick scroll
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
            await asyncio.sleep(0.5)

            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # 1. Price
            price = self._extract_price(soup, content)

            # 2. Text Content (Limit size)
            for tag in soup(["script", "style", "nav", "footer", "svg"]): tag.decompose()
            text = soup.get_text(separator=' ', strip=True)[:10000]
            
            # 3. Tables
            tables = []
            for t in soup.find_all("table"):
                rows = [tr.get_text(":", strip=True) for tr in t.find_all("tr")]
                tables.append("\n".join(rows))
            
            # 4. Images
            images = self._extract_images(soup, url)

            return {
                "title": await page.title(),
                "text": text,
                "structured_tables": "\n".join(tables),
                "image_url": images[0] if images else None,
                "images": images,
                "price": price
            }

        except Exception as e:
            # Silence expected timeout errors
            return None
        finally:
            await page.close()
            await context.close()

    def _extract_images(self, soup, base_url):
        candidates = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src')
            if src and 'icon' not in src.lower():
                if src.startswith("//"): src = "https:" + src
                elif src.startswith("/"): src = urljoin(base_url, src)
                candidates.append(src)
        return candidates[:5]

    def _extract_price(self, soup, content_str):
        # Meta tag first
        meta = soup.find("meta", property="product:price:amount")
        if meta and meta.get("content"): return float(meta["content"])
        # Regex fallback
        match = re.search(r'[\$€£]\s?(\d{1,4}\.\d{2})', content_str[:2000])
        return float(match.group(1)) if match else None