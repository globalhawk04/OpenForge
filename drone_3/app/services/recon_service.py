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
        # Launch options to improve success rate against simple bot detection
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()

    async def scrape_product_page(self, url: str):
        print(f"🕵️  Deep Scraping: {url}")
        page = await self.browser.new_page()
        
        # 1. Set Desktop Viewport (Crucial for Table Rendering)
        # Mobile views often hide technical spec tables behind accordions
        await page.set_viewport_size({"width": 1920, "height": 1080})
        
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        })

        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            
            # 2. Scroll to Bottom (Trigger Lazy Loading)
            # Many sites (GetFPV, RDQ) lazy load images in the description
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5) # Wait for network requests to settle

            content = await page.content()
            title = await page.title()
            soup = BeautifulSoup(content, 'html.parser')
            
            # --- STRATEGY A: STRUCTURED TABLE EXTRACTION ---
            # Extract raw <table> data before we clean the soup
            tables_data = []
            for table in soup.find_all("table"):
                rows = []
                for tr in table.find_all("tr"):
                    # Get both th and td
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    # Only keep rows that look like key-value pairs or data headers
                    if len(cells) >= 2:
                        rows.append(" : ".join(cells))
                
                if rows:
                    tables_data.append("\n".join(rows))
            
            structured_specs = "\n--- TABLE DATA ---\n".join(tables_data)

            # --- STRATEGY B: MULTI-IMAGE EXTRACTION ---
            # We want gallery images + description images (diagrams)
            images = self._extract_all_viable_images(soup, page.url)

            # --- STRATEGY C: PRICE & TEXT ---
            price = self._extract_price(soup, content) # Pass full content for regex fallback

            # Clean up DOM elements we don't need for text analysis
            for tag in soup(["script", "style", "nav", "footer", "header", "svg", "iframe", "noscript", "button", "input", "form"]):
                tag.decompose()
            
            # Extract list items specifically (often specs are in <ul>)
            ul_text = ""
            for ul in soup.find_all("ul"):
                ul_text += ul.get_text(separator="\n", strip=True) + "\n"

            # Get remaining body text
            raw_body_text = soup.get_text(separator=' ', strip=True)
            
            # Combine sources for the LLM context
            # We prioritize the UL text and Table text, then general body
            clean_text = (ul_text + "\n" + raw_body_text)[:15000] # Limit size for tokens

            return {
                "title": title,
                "text": clean_text,
                "structured_tables": structured_specs,
                "image_url": images[0] if images else None, # Primary image for UI
                "images": images, # Full list for AI analysis
                "price": price
            }

        except Exception as e:
            print(f"❌ Scrape Error ({url}): {e}")
            return None
        finally:
            await page.close()

    def _extract_all_viable_images(self, soup, base_url):
        """
        Returns a list of unique, high-quality image URLs.
        Prioritizes images that look like diagrams or main product shots.
        """
        candidates = set()
        
        # 1. Look for specific e-commerce gallery containers
        gallery_selectors = [
            '.product-gallery', '.gallery', '.woocommerce-product-gallery', 
            '#gallery', '.photos', '.images', '.product-media', '.slick-track'
        ]
        
        for selector in gallery_selectors:
            for container in soup.select(selector):
                for img in container.find_all('img'):
                    src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    if src: candidates.add(self._fix_url(src, base_url))

        # 2. Look for Description Images (Often where diagrams/pinouts live)
        desc_selectors = ['#description', '.description', '.product-description', '.content', '.tab-content']
        for selector in desc_selectors:
            for container in soup.select(selector):
                for img in container.find_all('img'):
                    src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    if src: candidates.add(self._fix_url(src, base_url))

        # 3. Fallback: Scan all large images if we found nothing
        if len(candidates) < 2:
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src')
                # Filter out obvious UI elements
                if src and not any(x in src.lower() for x in ['icon', 'logo', 'button', 'rating', 'star', 'gif', 'loader', 'pixel']):
                     candidates.add(self._fix_url(src, base_url))

        # Convert to list and limit
        return list(candidates)[:6]

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

        # Strategy 3: Common CSS Selectors
        price_selectors = [
            ".price", ".product-price", '[data-test="product-price"]',
            ".price-value", ".price--main .money", ".a-price-whole",
            ".product-info-price .price", ".special-price .price"
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

    def _fix_url(self, src, base_url):
        if not src: return None
        if src.startswith("//"): return "https:" + src
        if src.startswith("/"): return urljoin(base_url, src)
        return src