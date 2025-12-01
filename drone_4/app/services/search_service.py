# FILE: app/services/search_service.py
from googleapiclient.discovery import build
from app.config import settings

def find_components(query: str, limit: int = 5) -> list[dict]:
    """
    Searches Google Custom Search API for drone components.
    Attempts to extract Product data (Price, Image) from PageMap (Rich Snippets).
    """
    if not settings.GOOGLE_API_KEY or not settings.GOOGLE_SEARCH_ENGINE_ID:
        print("❌ Error: GOOGLE_API_KEY or GOOGLE_SEARCH_ENGINE_ID missing.")
        return []

    print(f"🔎 Google Search: '{query}'...")

    try:
        service = build("customsearch", "v1", developerKey=settings.GOOGLE_API_KEY)
        
        # Append 'buy' or 'price' to ensure we get e-commerce results if not present
        search_query = query if "buy" in query or "price" in query else f"{query} buy"

        res = service.cse().list(
            q=search_query,
            cx=settings.GOOGLE_SEARCH_ENGINE_ID,
            num=limit if limit <= 10 else 10 # API Max is 10
        ).execute()

        results = []
        items = res.get("items", [])

        for item in items:
            # --- Data Extraction Strategies ---
            
            # 1. Extract Image from Rich Snippets (PageMap)
            image_url = None
            pagemap = item.get("pagemap", {})
            
            if "cse_image" in pagemap and len(pagemap["cse_image"]) > 0:
                image_url = pagemap["cse_image"][0].get("src")
            
            # 2. Extract Price from 'Offer' or 'Product' Schema
            price = "Check Site"
            currency = ""
            
            # Try 'offer' schema first
            offers = pagemap.get("offer", [])
            if offers:
                price = offers[0].get("price", price)
                currency = offers[0].get("pricecurrency", "$")
            
            # 3. Clean up Source
            display_link = item.get("displayLink", "Unknown")

            results.append({
                "title": item.get("title"),
                "price": f"{price} {currency}".strip(),
                "source": display_link,
                "link": item.get("link"),
                "image_url": image_url
            })

        print(f"✅ Found {len(results)} results.")
        return results

    except Exception as e:
        print(f"❌ Google Search failed: {e}")
        return []