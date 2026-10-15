# --- START OF FILE app/services/recon_service.py ---
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import asyncio
import os
import re
import json

from app.services.normalizer import DATA_DIR

EVIDENCE_ROOT = os.path.join(DATA_DIR, "evidence_archive")
os.makedirs(EVIDENCE_ROOT, exist_ok=True)


def _slugify(text: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", text.strip())
    return clean[:50].strip("_").lower() or "component"


class Scraper:
    def __init__(self, headless: bool | None = None):
        self.playwright = None
        self.browser = None
        if headless is None:
            has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
            self.headless = not has_display
        else:
            self.headless = headless

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def scrape_product_page(self, url: str, part_type: str = "Component") -> dict | None:
        print(f"🕵️  Deep Scraping (Extended Dwell + Archiving): {url}")
        page = await self.browser.new_page(viewport={"width": 1440, "height": 950})
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        await page.set_extra_http_headers({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        })

        try:
            # 1. Initial Navigation + Network Settle
            await page.goto(url, timeout=35000, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            await asyncio.sleep(2.0)

            title = await page.title()
            if self._is_blocked_doc_or_manual_page(url, title):
                print(f"   ⚠️  Skipped doc/manual URL: {url}")
                return None

            # 2. Auto-Click 'Specifications' / 'Technical Details' Tabs if present
            for tab_label in ["Specifications", "Specification", "Tech Specs", "Parameters", "Specs", "Details"]:
                try:
                    locator = page.get_by_text(tab_label, exact=True).first
                    if await locator.is_visible(timeout=500):
                        await locator.click(timeout=1500)
                        await asyncio.sleep(1.2)
                        break
                except Exception:
                    continue

            # 3. Progressive 4-Stage Scroll (Keeps browser open ~7s so lazy images & tables load)
            for frac in [0.25, 0.50, 0.75, 1.0]:
                await page.evaluate(f"window.scrollTo({{top: document.body.scrollHeight * {frac}, behavior: 'smooth'}})")
                await asyncio.sleep(1.5)

            # Scroll back up to product/spec area and wait for images to finish decoding
            await page.evaluate("window.scrollTo({top: document.body.scrollHeight * 0.3, behavior: 'smooth'})")
            await asyncio.sleep(1.5)
            try:
                await page.evaluate("""() => Promise.all(
                    Array.from(document.images)
                        .filter(img => !img.complete)
                        .map(img => new Promise(resolve => { img.onload = img.onerror = resolve; }))
                )""")
            except Exception:
                pass

            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")

            # --- STRATEGY A: STRUCTURED TABLE EXTRACTION ---
            tables_data = []
            for table in soup.find_all("table"):
                rows = []
                for tr in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if len(cells) >= 2:
                        rows.append(" : ".join(cells))
                if rows:
                    tables_data.append("\n".join(rows))

            structured_specs = "\n--- TABLE DATA ---\n".join(tables_data)

            # --- STRATEGY B: DIAGRAM-PRIORITIZED IMAGE EXTRACTION ---
            images = self._extract_prioritized_images(soup, page.url)

            # --- STRATEGY C: STRICT CURRENCY PRICE EXTRACTION ---
            price = self._extract_price(soup, content)

            # Clean DOM for text extraction
            for tag in soup(["script", "style", "nav", "footer", "header", "svg", "iframe", "noscript", "button", "input", "form"]):
                tag.decompose()

            ul_text = "\n".join(ul.get_text(separator="\n", strip=True) for ul in soup.find_all("ul"))
            raw_body_text = soup.get_text(separator=" ", strip=True)
            clean_text = f"{ul_text}\n\n{raw_body_text}"[:20000]

            # =================================================================
            # 4. SAVE EVIDENCE ARCHIVE TO DISK FOR HUMAN REVIEW
            # =================================================================
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder_name = f"{stamp}_{_slugify(part_type)}_{_slugify(title)}"
            evidence_dir = os.path.join(EVIDENCE_ROOT, folder_name)
            os.makedirs(evidence_dir, exist_ok=True)

            # 4A. Save Full-Page Screenshot
            screenshot_path = os.path.join(evidence_dir, "page_screenshot.jpg")
            try:
                await page.screenshot(path=screenshot_path, full_page=True, type="jpeg", quality=75)
            except Exception:
                try:
                    await page.screenshot(path=screenshot_path, full_page=False, type="jpeg", quality=75)
                except Exception:
                    screenshot_path = None

            # 4B. Download & Save Top Product/Diagram Images via Browser Context (Bypasses Cloudflare 403)
            local_image_paths = []
            for idx, img_url in enumerate(images[:4]):
                try:
                    resp = await page.request.get(img_url, timeout=10000)
                    if resp.status == 200:
                        body = await resp.body()
                        if len(body) > 1500:  # Ignore tiny tracking pixels
                            img_file = os.path.join(evidence_dir, f"img_{idx+1:02d}.jpg")
                            with open(img_file, "wb") as f:
                                f.write(body)
                            local_image_paths.append(img_file)
                except Exception:
                    continue

            # Always include the page screenshot as visual evidence if fewer than 2 images downloaded
            if screenshot_path and os.path.exists(screenshot_path) and len(local_image_paths) < 2:
                local_image_paths.append(screenshot_path)

            # 4C. Save Scraped Text & Tables for Human Review
            text_file_path = os.path.join(evidence_dir, "scraped_text.txt")
            with open(text_file_path, "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\nTITLE: {title}\nPRICE_DETECTED: {price}\n")
                f.write("=" * 80 + "\n")
                f.write("STRUCTURED HTML TABLES:\n")
                f.write((structured_specs or "(No HTML <table> tags found)") + "\n\n")
                f.write("=" * 80 + "\n")
                f.write("EXTRACTED LISTS & PAGE TEXT:\n")
                f.write(clean_text)

            tables_file_path = os.path.join(evidence_dir, "structured_tables.txt")
            with open(tables_file_path, "w", encoding="utf-8") as f:
                f.write(structured_specs or "(No HTML <table> tags found)")

            print(f"   📁 Archived {len(local_image_paths)} images + text to: {evidence_dir}")

            return {
                "title": title,
                "text": clean_text,
                "html": content,
                "structured_tables": structured_specs,
                "image_url": images[0] if images else None,
                "images": images,
                "local_image_paths": local_image_paths,
                "screenshot_path": screenshot_path,
                "text_file_path": text_file_path,
                "evidence_dir": evidence_dir,
                "price": price,
            }

        except Exception as e:
            print(f"❌ Scrape Error ({url}): {e}")
            return None
        finally:
            await page.close()

    def _is_blocked_doc_or_manual_page(self, url: str, title: str) -> bool:
        low_u = url.lower()
        low_t = (title or "").lower()
        bad_url_parts = ["docs.px4.io", "manuals.plus", "manualslib.com", "github.com", "reddit.com", "wikipedia.org"]
        if any(b in low_u for b in bad_url_parts):
            return True
        if "user manual" in low_t or "px4 guide" in low_t:
            return True
        return False

    def _extract_prioritized_images(self, soup, base_url: str) -> list[str]:
        scored_urls = {}

        def add_candidate(raw_src: str, context_hint: str, base_score: int):
            url = self._fix_url(raw_src, base_url)
            if not url:
                return
            low = (url + " " + context_hint).lower()
            if any(x in low for x in ["icon", "logo", "avatar", "badge", "rating", "star", "payment", "flag", "loader", "1x1", "pixel"]):
                return

            score = base_score
            if any(k in low for k in ["dim", "size", "diagram", "pinout", "wiring", "spec", "chart", "thrust", "mount", "drawing"]):
                score += 30
            if any(ext in low for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                score += 5
            scored_urls[url] = max(scored_urls.get(url, 0), score)

        gallery_selectors = [
            ".product-gallery", ".gallery", ".woocommerce-product-gallery",
            "#gallery", ".product-media", ".product-single__media", ".product-images"
        ]
        for sel in gallery_selectors:
            for container in soup.select(sel):
                for img in container.find_all("img"):
                    src = img.get("data-src") or img.get("data-large_image") or img.get("src")
                    alt = f"{img.get('alt', '')} {img.get('title', '')}"
                    add_candidate(src, alt, base_score=20)

        desc_selectors = ["#description", ".description", ".product-description", ".tab-content", ".rte"]
        for sel in desc_selectors:
            for container in soup.select(sel):
                for img in container.find_all("img"):
                    src = img.get("data-src") or img.get("src")
                    alt = f"{img.get('alt', '')} {img.get('title', '')}"
                    add_candidate(src, alt, base_score=25)

        if len(scored_urls) < 3:
            for img in soup.find_all("img"):
                src = img.get("data-src") or img.get("src")
                alt = f"{img.get('alt', '')} {img.get('title', '')}"
                add_candidate(src, alt, base_score=10)

        sorted_imgs = sorted(scored_urls.keys(), key=lambda u: scored_urls[u], reverse=True)
        return sorted_imgs[:5]

    def _extract_price(self, soup, content_str: str) -> float | None:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.get_text())
                items = data if isinstance(data, list) else [data]
                for item in items:
                    p = self._parse_schema_price(item)
                    if p and 1.50 <= p <= 25000.0:
                        return p
            except Exception:
                continue

        meta_price = (
            soup.find("meta", property="product:price:amount")
            or soup.find("meta", property="og:price:amount")
            or soup.find("meta", itemprop="price")
        )
        if meta_price and meta_price.get("content"):
            try:
                val = float(str(meta_price.get("content")).replace(",", "").strip())
                if 1.50 <= val <= 25000.0:
                    return val
            except Exception:
                pass

        price_selectors = [
            "[data-product-price]", ".price-item--regular", ".product-price",
            '[data-test="product-price"]', ".price--main .money", ".product-info-price .price",
            ".summary .price .amount", ".price"
        ]
        for selector in price_selectors:
            el = soup.select_one(selector)
            if el:
                txt = el.get_text(strip=True)
                m = re.search(r"[\$€£]\s*(\d{1,5}(?:,\d{3})*(?:\.\d{2}))", txt)
                if m:
                    try:
                        val = float(m.group(1).replace(",", ""))
                        if 1.50 <= val <= 25000.0:
                            return val
                    except Exception:
                        pass

        matches = re.findall(r"[\$€£]\s*(\d{1,5}(?:,\d{3})*\.\d{2})\b", content_str[:35000])
        valid = [float(m.replace(",", "")) for m in matches if 1.99 <= float(m.replace(",", "")) <= 25000.0]
        return valid[0] if valid else None

    def _parse_schema_price(self, data: dict) -> float | None:
        if not isinstance(data, dict):
            return None
        if "@graph" in data and isinstance(data["@graph"], list):
            for node in data["@graph"]:
                p = self._parse_schema_price(node)
                if p:
                    return p
        if data.get("@type") in ("Product", "IndividualProduct"):
            offers = data.get("offers")
            if isinstance(offers, dict):
                raw = offers.get("price") or offers.get("lowPrice")
                if raw:
                    return float(str(raw).replace(",", ""))
            elif isinstance(offers, list) and offers:
                raw = offers[0].get("price") or offers[0].get("lowPrice")
                if raw:
                    return float(str(raw).replace(",", ""))
        return None

    def _fix_url(self, src: str, base_url: str) -> str | None:
        if not src or src.startswith("data:"):
            return None
        src = src.strip()
        if src.startswith("//"):
            return "https:" + src
        if src.startswith("/"):
            return urljoin(base_url, src)
        return src
# --- END OF FILE app/services/recon_service.py ---