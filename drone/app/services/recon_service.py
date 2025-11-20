# FILE: app/services/recon_service.py
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import asyncio
import re

class Scraper:
    def __init__(self):
        self.playwright = None
        self.browser = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()

    async def scrape_product_page(self, url: str):
        print(f"🕵️  Scraping: {url}")
        page = await self.browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        })

        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            title = await page.title()
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # --- 1. PRICE EXTRACTION (NEW) ---
            price = self._extract_price(soup)

            # --- 2. CLEAN TEXT ---
            for tag in soup(["script", "style", "nav", "footer", "header", "svg", "iframe", "noscript", "button"]):
                tag.decompose()
            
            spec_text = ""
            for table in soup.find_all("table"):
                spec_text += table.get_text(separator=" | ", strip=True) + "\n"
            for ul in soup.find_all("ul"):
                spec_text += ul.get_text(separator="\n", strip=True) + "\n"

            if len(spec_text) < 50:
                spec_text += soup.get_text(separator=' ', strip=True)

            clean_text = " ".join(spec_text.split())[:12000] 
            
            # --- 3. IMAGE EXTRACTION ---
            image_url = self._find_best_image(soup, page.url)
            
            return {
                "title": title,
                "text": clean_text,
                "image_url": image_url,
                "price": price # Return the scraped price
            }

        except Exception as e:
            print(f"❌ Scrape Error ({url}): {e}")
            return None
        finally:
            await page.close()

    def _extract_price(self, soup):
        """
        Hunts for price in Meta Tags, JSON-LD, and Common Classes.
        """
        # Strategy 1: Meta Tags (Most Reliable)
        meta_price = soup.find("meta", property="product:price:amount") or \
                     soup.find("meta", property="og:price:amount")
        if meta_price: return meta_price.get("content")

        # Strategy 2: Common E-commerce Classes
        # Amazon, Shopify, WooCommerce patterns
        selectors = [
            "span.a-price-whole",          # Amazon
            ".price", ".product-price",    # Generic
            ".price__current", ".current-price",
            "[itemprop='price']"           # Schema.org
        ]
        
        for sel in selectors:
            element = soup.select_one(sel)
            if element:
                text = element.get_text(strip=True)
                # Extract first number pattern found (e.g. $19.99 -> 19.99)
                match = re.search(r"[\$£€]?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)", text)
                if match: return match.group(1)
        
        return None

    def _find_best_image(self, soup, base_url):
        candidates = [
            soup.find("img", {"id": "landingImage"}),
            soup.find("img", {"id": "imgBlkFront"}),
            soup.find("img", {"class": "magnifier-image"}),
            soup.find("img", {"class": "product__image"}),
            soup.find("img", attrs={"data-zoom-image": True})
        ]
        for img in candidates:
            if img:
                src = img.get("data-zoom-image") or img.get("src")
                if src: return self._fix_url(src, base_url)

        all_imgs = soup.find_all("img")
        best_src = None
        for img in all_imgs:
            src = img.get("src")
            if not src or "base64" in src or ".gif" in src: continue
            lower_src = src.lower()
            if "logo" in lower_src or "icon" in lower_src or "avatar" in lower_src: continue
            if "product" in lower_src or "main" in lower_src or "600" in lower_src:
                best_src = src
                break 
        return self._fix_url(best_src, base_url) if best_src else None

    def _fix_url(self, src, base_url):
        if not src: return None
        if src.startswith("//"): return "https:" + src
        if src.startswith("/"): return urljoin(base_url, src)
        if not src.startswith("http"): return urljoin(base_url, src)
        return src