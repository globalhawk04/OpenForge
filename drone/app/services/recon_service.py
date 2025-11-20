# FILE: app/services/recon_service.py
from urllib.parse import urljoin

class Scraper:
    """
    [SAFE MODE] Mock Scraper for Public Demo.
    Real scraping logic has been removed for safety/compliance.
    Returns pre-validated specs for the 'Rugged 5-inch' demo scenario.
    """
    def __init__(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def scrape_product_page(self, url: str):
        print(f"🕵️  [MOCK RECON] Retrieving static data for: {url}")
        
        # We return generic text. The 'Vision Service' or 'Sanitizer' 
        # will handle the actual specs in the next step using defaults.
        return {
            "title": "Demo Component",
            "text": "Specifications: Standard mounting pattern. Voltage: 2-6S. Weight: 30g.",
            "image_url": "https://example.com/demo_diagram.jpg", # Placeholder
            "price": 25.00
        }
