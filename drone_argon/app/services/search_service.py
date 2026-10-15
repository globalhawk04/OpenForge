# --- START OF FILE app/services/search_service.py ---
import asyncio
import base64
import concurrent.futures
import os
import re
from urllib.parse import urlparse, parse_qs, unquote, quote_plus
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

SKIP_DOMAINS = (
    "duckduckgo.com", "bing.com", "microsoft.com", "google.com", "gstatic.com",
    "youtube.com", "reddit.com", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "pinterest.com", "wikipedia.org",
    "docs.px4.io", "manuals.plus", "manualslib.com", "github.com",
    "oscarliang.com", "mdpi.com", "researchgate.net", "arxiv.org"
)

ACADEMIC_NOISE_PATTERNS = [
    r"\bthrust\s+coefficient\b", r"\bpower\s+coefficient\b", r"\bairfoil\s+data\b",
    r"\bdischarge\s+curve\b", r"\binternal\s+resistance\b", r"\bbench\s+test\b",
    r"\bperformance\s+data\b", r"\befficiency\s+chart\b", r"\bthrust\s+table\b",
    r"\bhover\s+efficiency\b", r"\bpayload\s+curve\b", r"\ball-up\s+weight\b",
    r"\bpower-to-weight\b", r"\bwind\s+resistance\b", r"\btechnical\s+specifications\b",
    r"\bdatasheet\b", r"\bschematic\b", r"\bpinout\b", r"\bwiring\s+diagram\b",
    r"\bcurrent\s+sensor\b", r"\bflight\s+duration\b", r"\bflight\s+endurance\b",
    r"\btesting\b", r"\breview\b"
]


def clean_search_query(raw_query: str) -> str:
    q = raw_query
    for pat in ACADEMIC_NOISE_PATTERNS:
        q = re.sub(pat, " ", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+", " ", q).strip()
    if "buy" not in q.lower() and "price" not in q.lower():
        q = f"{q} specs buy"
    return q


def _unwrap_redirect_url(href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith("//"):
        href = "https:" + href

    if "duckduckgo.com/l/?" in href or "uddg=" in href:
        qs = parse_qs(urlparse(href).query)
        if "uddg" in qs and qs["uddg"]:
            return unquote(qs["uddg"][0])

    if "google.com/url?" in href or href.startswith("/url?"):
        qs = parse_qs(urlparse(href).query)
        for key in ("q", "url"):
            if key in qs and qs[key]:
                return unquote(qs[key][0])

    if "bing.com/ck/a" in href:
        qs = parse_qs(urlparse(href).query)
        u_val = qs.get("u", [""])[0]
        if u_val.startswith("a1"):
            b64_str = u_val[2:]
            b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
            try:
                decoded = base64.urlsafe_b64decode(b64_str).decode("utf-8", errors="ignore")
                if decoded.startswith("http"):
                    return decoded
            except Exception:
                pass

    return href


def _is_valid_result_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    low = url.lower()
    if any(d in low for d in SKIP_DOMAINS):
        return False
    if any(x in low for x in ["/search?", "/collections/all", "google.com", "bing.com"]):
        return False
    return True


async def find_components_async(query: str, limit: int = 5, browser=None) -> list[dict]:
    """
    Uses an OPEN Chromium Browser (Playwright) with extended dwell times so search results
    and any anti-bot challenges fully settle before extracting links.
    """
    search_query = clean_search_query(query)
    print(f"🌐 Open-Browser Search: '{search_query}'...")

    own_playwright = None
    own_browser = None
    if browser is None:
        own_playwright = await async_playwright().start()
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        own_browser = await own_playwright.chromium.launch(
            headless=not has_display,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        browser = own_browser

    results = []
    seen_urls = set()
    page = await browser.new_page(viewport={"width": 1440, "height": 900})
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    def record_hit(title: str, raw_href: str):
        clean_link = _unwrap_redirect_url(raw_href)
        if title and len(title) > 5 and _is_valid_result_url(clean_link) and clean_link not in seen_urls:
            seen_urls.add(clean_link)
            domain = urlparse(clean_link).netloc.replace("www.", "")
            results.append({
                "title": title,
                "price": "Check Site",
                "source": domain,
                "link": clean_link,
                "image_url": None,
            })

    try:
        # --- ENGINE 1: DuckDuckGo Full Browser Search (with 4s dwell + network settle) ---
        ddg_url = f"https://duckduckgo.com/?q={quote_plus(search_query)}&t=h_&ia=web"
        try:
            await page.goto(ddg_url, timeout=25000, wait_until="domcontentloaded")
            try:
                await page.wait_for_selector('a[data-testid="result-title-a"], a.result__a', timeout=8000)
            except Exception:
                pass
            await asyncio.sleep(3.5)  # Keep open so dynamic results fully populate
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            for a_tag in soup.select('a[data-testid="result-title-a"], a.result__a, article h2 a'):
                record_hit(a_tag.get_text(strip=True), a_tag.get("href", ""))
                if len(results) >= limit:
                    break
        except Exception as e:
            print(f"   ⚠️  DDG search note: {e}")

        # --- ENGINE 2: Google Open-Browser Search (If DDG found < 2) ---
        if len(results) < 2:
            google_url = f"https://www.google.com/search?q={quote_plus(search_query)}&hl=en"
            try:
                await page.goto(google_url, timeout=25000, wait_until="domcontentloaded")
                try:
                    await page.wait_for_selector("div#search h3", timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(3.5)
                g_html = await page.content()
                g_soup = BeautifulSoup(g_html, "html.parser")

                for h3 in g_soup.select("div#search h3"):
                    a_tag = h3.find_parent("a")
                    if a_tag and a_tag.get("href"):
                        record_hit(h3.get_text(strip=True), a_tag.get("href", ""))
                        if len(results) >= limit:
                            break
            except Exception as e:
                print(f"   ⚠️  Google search note: {e}")

        # --- ENGINE 3: Bing Open-Browser Search (If still < 2) ---
        if len(results) < 2:
            bing_url = f"https://www.bing.com/search?q={quote_plus(search_query)}"
            try:
                await page.goto(bing_url, timeout=25000, wait_until="domcontentloaded")
                try:
                    await page.wait_for_selector("li.b_algo h2 a", timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(3.5)
                b_html = await page.content()
                b_soup = BeautifulSoup(b_html, "html.parser")

                for a_tag in b_soup.select("li.b_algo h2 a"):
                    record_hit(a_tag.get_text(strip=True), a_tag.get("href", ""))
                    if len(results) >= limit:
                        break
            except Exception as e:
                print(f"   ⚠️  Bing search note: {e}")

        print(f"   ✅ Open-Browser Search found {len(results)} candidate URLs.")
        return results

    except Exception as e:
        print(f"   ❌ Chromium Search Error: {e}")
        return results
    finally:
        await page.close()
        if own_browser:
            await own_browser.close()
        if own_playwright:
            await own_playwright.stop()


def find_components(query: str, limit: int = 5) -> list[dict]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(find_components_async(query, limit=limit))).result()
    return asyncio.run(find_components_async(query, limit=limit))
# --- END OF FILE app/services/search_service.py ---