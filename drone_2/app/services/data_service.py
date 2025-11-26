# FILE: app/services/data_service.py
import asyncio
import re
from bs4 import BeautifulSoup
from app.services.search_service import find_components
from app.services.recon_service import Scraper

# A whitelist of trusted sources for motor thrust data.
# This is a critical heuristic to improve data quality.
TRUSTED_DOMAINS = [
    "miniquadtestbench.com",
    "tmotor.com",
    "flywoo.net",
    "gemfanhobby.com",
    "hqprop.com"
]

async def _parse_thrust_table(html_content: str) -> dict | None:
    """
    Parses HTML content to find and extract a thrust data table.
    Looks for tables containing keywords like 'Thrust', 'Amps', 'Throttle'.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    tables = soup.find_all('table')
    
    for table in tables:
        headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
        
        # Heuristic to identify a thrust table
        if not any(kw in str(headers) for kw in ['thrust', 'amps', 'throttle']):
            continue

        # Find the column indices for the data we need
        try:
            throttle_idx = next(i for i, h in enumerate(headers) if 'throttle' in h)
            thrust_idx = next(i for i, h in enumerate(headers) if 'thrust' in h or 'g' in h)
            amps_idx = next(i for i, h in enumerate(headers) if 'amps' in h or 'a' in h)
        except StopIteration:
            continue # This table doesn't have the required columns

        # Initialize lists to hold the parsed data
        data = {"throttle_pct": [], "thrust_g": [], "amps": []}
        
        rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) <= max(throttle_idx, thrust_idx, amps_idx):
                continue

            try:
                # Clean and convert the cell text to numbers
                throttle_val = float(re.sub(r'[^0-9.]', '', cells[throttle_idx].get_text()))
                thrust_val = float(re.sub(r'[^0-9.]', '', cells[thrust_idx].get_text()))
                amps_val = float(re.sub(r'[^0-9.]', '', cells[amps_idx].get_text()))

                # Basic sanity check on the values
                if throttle_val >= 0 and thrust_val >= 0 and amps_val >= 0:
                    data["throttle_pct"].append(throttle_val)
                    data["thrust_g"].append(thrust_val)
                    data["amps"].append(amps_val)
            except (ValueError, IndexError):
                continue # Skip rows with non-numeric or missing data

        # If we successfully parsed a reasonable amount of data, return it
        if len(data["thrust_g"]) > 5:
            return data
            
    return None


async def find_thrust_data(motor_name: str, prop_size_inch: float) -> dict | None:
    """
    Searches the web for credible thrust data for a given motor and prop combination.
    It prioritizes trusted sources and scrapes pages to find and parse test data.

    Args:
        motor_name: The product name of the motor (e.g., "T-Motor F100 2810").
        prop_size_inch: The diameter of the propeller in inches (e.g., 7.0).

    Returns:
        A dictionary representing the thrust curve, or None if no data is found.
    """
    print(f"--> 📊 Data Service: Searching for thrust data for '{motor_name}' with {prop_size_inch}\" props...")

    # Sanitize motor name for better search results
    clean_motor_name = re.sub(r'(\d{4}).*', r'\1', motor_name).strip()
    
    query = f'"{clean_motor_name}" {prop_size_inch} inch propeller thrust test data'
    search_results = find_components(query, limit=5)

    # Prioritize results from our trusted domain list
    prioritized_urls = [
        res['link'] for res in search_results if any(domain in res['link'] for domain in TRUSTED_DOMAINS)
    ]
    # Add the rest of the URLs as a fallback
    other_urls = [
        res['link'] for res in search_results if res['link'] not in prioritized_urls
    ]
    
    urls_to_check = prioritized_urls + other_urls

    async with Scraper() as scraper:
        for url in urls_to_check:
            try:
                scraped_data = await scraper.scrape_product_page(url)
                if not scraped_data or not scraped_data.get('text'):
                    continue
                
                # We need the raw HTML for table parsing, which recon_service doesn't provide.
                # A better long-term solution would be to make scrape_product_page return HTML.
                # For now, we can infer it from the text (less reliable). A direct scrape would be better.
                # Let's assume for this implementation we have a way to get the full HTML.
                # A more realistic implementation would require modifying the scraper.
                # Let's mock this by re-scraping for the full content.
                page = await scraper.browser.new_page()
                await page.goto(url, timeout=20000)
                html_content = await page.content()
                await page.close()

                thrust_table = await _parse_thrust_table(html_content)
                if thrust_table:
                    print(f"   ✅ Found and parsed credible thrust data from: {url}")
                    return thrust_table
            except Exception as e:
                print(f"   -> Could not process URL {url}: {e}")
                continue
                
    print("   ❌ No credible thrust data found after checking all sources.")
    return None