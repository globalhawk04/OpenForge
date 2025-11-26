# FILE: app/services/fusion_service.py
import asyncio
from app.services.recon_service import Scraper
from app.services.vision_service import analyze_image_for_specs
from app.services.library_service import infer_motor_mounting, extract_prop_diameter
from app.services.search_service import find_components
from app.services.ai_service import generate_vision_prompt 
import json

# --- CONFIGURATION ---
DOMAIN_BLOCKLIST = ["reddit.com", "facebook.com", "youtube.com", "twitter.com", "instagram.com", "forum", "pinterest", "thingiverse", "mdpi.com", "oscarliang.com", "getfpv.com/learn"]
GENERIC_TITLE_BLOCKLIST = ["collections", "products", "category", "browse", "shop", "rc model vehicles"]

# We remove the hardcoded threshold and pass it as an argument instead
DEFAULT_VISION_CONFIDENCE = 0.6 

async def process_single_candidate(scraper, item, part_type, vision_prompt_object, min_confidence):
    """
    Processes a single search result with DYNAMIC confidence requirements.
    """
    link = item.get('link')
    title = item.get('title')
    
    if not link or not title: return None
    if any(bad_domain in link for bad_domain in DOMAIN_BLOCKLIST): return None
    if any(bad_word in title.lower() for bad_word in GENERIC_TITLE_BLOCKLIST): return None

    print(f"   Trying: {title[:40]}...")
    
    scraped_data = await scraper.scrape_product_page(link)
    if not scraped_data: return None

    final_price = scraped_data.get('price')
    # Stricter price check: Must be real number, not 0
    if not final_price or not isinstance(final_price, (int, float)) or final_price <= 0.50:
        return None

    validated_specs = {} 
    image_url = scraped_data.get('image_url')
    
    # --- VISION CHECK ---
    if image_url and vision_prompt_object:
        raw_vision_result = await analyze_image_for_specs(image_url, part_type, vision_prompt_object)
        
        if raw_vision_result and not raw_vision_result.get("error"):
            for key, data in raw_vision_result.items():
                if isinstance(data, dict):
                    confidence = data.get("confidence", 0)
                    value = data.get("value")
                    
                    # USE THE PASSED MIN_CONFIDENCE
                    if value is not None and confidence >= min_confidence:
                        validated_specs[key] = value
                    else:
                        print(f"      -> {key}: Rejected (Conf {confidence:.2f} < {min_confidence})")

            if validated_specs:
                 validated_specs["source"] = "vision"

    # Fallback to text inference if Vision failed
    engineering_specs = validated_specs.copy()
    if part_type == "Motors" and "mounting_mm" not in engineering_specs:
        inferred = infer_motor_mounting(title)
        if inferred:
            engineering_specs["mounting_mm"] = inferred
            engineering_specs["source"] = "text_inference"

    return {
        "product_name": title, "price": final_price, "source_url": link,
        "image_url": image_url, "engineering_data": engineering_specs
    }

async def fuse_component_data(part_type: str, search_query: str, search_limit: int = 5, min_confidence: float = 0.6):
    """
    Orchestrates finding and analyzing a component.
    Now accepts strictness parameters.
    """
    print(f"\n🔎 FUSION SEARCH ({part_type}): '{search_query}' (Strictness: {min_confidence*100}%)")
    
    vision_prompt_object = await generate_vision_prompt(part_type)
    if not vision_prompt_object:
        print(f"   ⚠️  Vision Prompt Generation Failed.")
        return None

    # Use the custom limit (e.g., 10 results instead of 5)
    results = find_components(search_query, limit=search_limit)
    if not results: return None

    async with Scraper() as scraper:
        # Pass the strict min_confidence down
        tasks = [process_single_candidate(scraper, res, part_type, vision_prompt_object, min_confidence) for res in results]
        candidates = await asyncio.gather(*tasks)
        
    valid_candidates = [c for c in candidates if c is not None]
    if not valid_candidates: return None

    # Rank them
    def rank_candidate(c):
        score = 0
        specs = c.get("engineering_data", {})
        # Heavily weight vision data
        if specs.get("source") == "vision": score += 20 
        if c.get("image_url"): score += 5
        score += len(specs)
        return score

    valid_candidates.sort(key=rank_candidate, reverse=True)
    best_candidate = valid_candidates[0]
    
    # FINAL SAFETY CHECK: Does it have specs?
    if not best_candidate.get("engineering_data"):
        return None

    return {
        "part_type": part_type,
        "product_name": best_candidate['product_name'],
        "price": best_candidate['price'],
        "source_url": best_candidate['source_url'],
        "engineering_specs": best_candidate['engineering_data'],
        "reference_image": best_candidate['image_url'],
        "data_source_method": best_candidate['engineering_data'].get('source', 'raw_search'),
    }