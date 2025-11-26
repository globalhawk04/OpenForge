# FILE: app/services/recon_service.py
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import asyncio
import re
import json

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
            
            price = self._extract_price(soup, content) # Pass full content for regex

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
            
            image_url = self._find_best_image(soup, page.url)
            
            return {
                "title": title,
                "text": clean_text,
                "image_url": image_url,
                "price": price
            }

        except Exception as e:
            print(f"❌ Scrape Error ({url}): {e}")
            return None
        finally:
            await page.close()

    def _extract_price(self, soup, content_str):
        # Strategy 1: JSON-LD (Gold Standard)
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.get_text())
                if isinstance(data, list):
                    for item in data:
                        p = self._parse_schema_price(item)
                        if p: return p
                else:
                    p = self._parse_schema_price(data)
                    if p: return p
            except: continue

        # Strategy 2: Meta Tags
        meta_price = soup.find("meta", property="product:price:amount") or \
                     soup.find("meta", property="og:price:amount")
        if meta_price and meta_price.get("content"): 
            try: return float(meta_price.get("content"))
            except: pass

        # Strategy 3: Common CSS Selectors (NEW)
        price_selectors = [
            ".price", ".product-price", '[data-test="product-price"]',
            ".price-value", ".price--main .money", ".a-price-whole",
            ".product-info-price .price",
        ]
        for selector in price_selectors:
            price_element = soup.select_one(selector)
            if price_element:
                price_text = price_element.get_text(strip=True)
                price_match = re.search(r'[\$€£]?\s*(\d+[\.,]\d{2})', price_text)
                if price_match:
                    try: return float(price_match.group(1).replace(",", ""))
                    except: pass
        
        # Strategy 4: Regex Scan on full HTML (Hail Mary)
        matches = re.findall(r'[\$€£]?\s*(\d{1,4}[,\.]\d{2})\b', content_str[:25000])
        valid_prices = [float(m.replace(",", "")) for m in matches if 0.5 < float(m.replace(",", "")) < 9999]
        if valid_prices:
            return valid_prices[0]
        
        return None

    def _parse_schema_price(self, data):
        if data.get("@type") == "Product":
            offers = data.get("offers")
            if isinstance(offers, dict) and offers.get("price"):
                return float(offers.get("price"))
            elif isinstance(offers, list) and len(offers) > 0 and offers[0].get("price"):
                return float(offers[0].get("price"))
        return None

    def _find_best_image(self, soup, base_url):
        # ... (this function remains the same and is quite robust) ...
        candidates = [
            soup.find("img", {"id": "landingImage"}),
            soup.find("img", {"class": "product-image-photo"}),
        ]
        for img in candidates:
            if img:
                src = img.get("data-src") or img.get("src")
                if src: return self._fix_url(src, base_url)

        all_imgs = soup.find_all("img")
        best_src = None
        for img in all_imgs:
            src = img.get("src")
            if not src or "base64" in src or ".gif" in src: continue
            lower_src = src.lower()
            if any(x in lower_src for x in ["logo", "icon", "avatar", "badge", "cart"]): continue
            if "product" in lower_src or "main" in lower_src or "600" in lower_src:
                best_src = src
                break 
        return self._fix_url(best_src, base_url) if best_src else None

    def _fix_url(self, src, base_url):
        if not src: return None
        if src.startswith("//"): return "https:" + src
        if src.startswith("/"): return urljoin(base_url, src)
        return src