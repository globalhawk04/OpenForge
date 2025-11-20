# FILE: app/services/fusion_service.py
import asyncio
from app.services.recon_service import Scraper
from app.services.vision_service import analyze_image_for_specs
from app.services.library_service import infer_motor_mounting, extract_prop_diameter
from app.services.search_service import find_components
import json

DOMAIN_BLOCKLIST = ["reddit.com", "facebook.com", "youtube.com", "twitter.com", "instagram.com", "forum", "pinterest"]

def get_vision_category(part_type: str):
    pt = part_type.upper()
    if "MOTOR" in pt: return "MOTOR"
    if "FC" in pt or "STACK" in pt or "CONTROLLER" in pt: return "FC_STACK"
    if "CAMERA" in pt: return "CAMERA"
    return None

async def process_single_candidate(scraper, item, part_type):
    link = item.get('link')
    title = item.get('title')
    search_price = item.get('price')

    if any(bad in link for bad in DOMAIN_BLOCKLIST): return None

    print(f"   Trying: {title[:40]}...")
    
    # 1. Scrape
    scraped_data = await scraper.scrape_product_page(link)
    if not scraped_data: return None

    # --- PRICE LOGIC START ---
    # Prefer scraped price, fallback to search price
    final_price = scraped_data.get('price')
    if not final_price or final_price == "Check Site":
        final_price = search_price
    # --- PRICE LOGIC END ---

    engineering_data = {}
    image_url = scraped_data.get('image_url')
    
    # 2. Vision
    vision_cat = get_vision_category(part_type)
    if image_url and vision_cat:
        vision_result = await analyze_image_for_specs(image_url, vision_cat)
        if vision_result and not vision_result.get("error"):
            engineering_data = vision_result
            engineering_data["source"] = "vision"

    # 3. Sanitize
    if part_type == "Motors" and not engineering_data.get("mounting_mm"):
        inferred = infer_motor_mounting(title)
        if inferred:
            engineering_data["mounting_mm"] = inferred
            engineering_data["source"] = "text_inference"

    if part_type == "Propellers" and not engineering_data.get("diameter_mm"):
        diam = extract_prop_diameter(title)
        if diam:
            engineering_data["diameter_mm"] = diam
            engineering_data["source"] = "text_inference"

    return {
        "product_name": title,
        "price": final_price, # Uses the improved price
        "source_url": link,
        "image_url": image_url,
        "engineering_data": engineering_data,
        "text_snippet": scraped_data['text'][:200]
    }

async def fuse_component_data(part_type: str, search_query: str):
    print(f"\n🔎 FUSION SEARCH: '{search_query}'")
    results = find_components(search_query, limit=3)
    if not results: return None

    async with Scraper() as scraper:
        tasks = [process_single_candidate(scraper, res, part_type) for res in results]
        candidates = await asyncio.gather(*tasks)
        
    valid_candidates = [c for c in candidates if c is not None]
    if not valid_candidates: return None

    best_spec_candidate = None
    for c in valid_candidates:
        specs = c['engineering_data']
        if specs.get('source') == "vision":
            best_spec_candidate = c
            break
        if specs.get('source') == "text_inference":
            best_spec_candidate = c
    
    if not best_spec_candidate:
        best_spec_candidate = valid_candidates[0]

    # Use price/link from first result (relevance), but if the first result 
    # has no price, try to find a candidate that DOES have a price.
    primary_link = valid_candidates[0]
    
    # Price Optimization: Find a candidate with a real price if primary is missing it
    if not primary_link['price'] or primary_link['price'] == "Check Site":
        for c in valid_candidates:
            if c['price'] and c['price'] != "Check Site":
                primary_link = c # Swap primary if we found a better price source
                break

    composite_part = {
        "part_type": part_type,
        "product_name": primary_link['product_name'],
        "price": primary_link['price'],
        "source_url": primary_link['source_url'],
        "engineering_specs": best_spec_candidate['engineering_data'],
        "reference_image": best_spec_candidate['image_url'],
        "data_source_method": best_spec_candidate['engineering_data'].get('source', 'raw_search'),
        "alternatives_checked": len(valid_candidates)
    }
    
    print(f"   ✅ Selected: {composite_part['product_name'][:30]}... (${composite_part['price']})")
    return composite_part