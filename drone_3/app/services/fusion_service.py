# FILE: app/services/fusion_service.py
import asyncio
import json
from app.services.recon_service import Scraper
from app.services.vision_service import analyze_specs_multimodal  # UPDATED IMPORT
from app.services.library_service import infer_motor_mounting, extract_prop_diameter
from app.services.search_service import find_components
from app.services.ai_service import generate_vision_prompt 

# ... (Keep DOMAIN_BLOCKLIST and validate_critical_specs as they were) ...
DOMAIN_BLOCKLIST = [
    "reddit.com", "facebook.com", "youtube.com", "twitter.com", 
    "instagram.com", "forum", "pinterest", "thingiverse", "mdpi.com", 
    "oscarliang.com", "getfpv.com/learn", "blog", "news"
]
GENERIC_TITLE_BLOCKLIST = [
    "collections", "products", "category", "browse", "shop", 
    "rc model vehicles", "accessories", "parts"
]

def validate_critical_specs(part_type, specs):
    # ... (Keep existing validation logic) ...
    if not specs: return False
    pt = part_type.lower()
    if "motor" in pt:
        if not specs.get("kv_rating") and not specs.get("kv"): return False
        if not specs.get("mounting_mm") and not specs.get("stator_size"): return False
    elif "frame" in pt:
        if not specs.get("wheelbase_mm"): return False
    elif "fc" in pt or "flight" in pt:
        if not specs.get("mounting_mm") and not specs.get("mounting_pattern_mm"): return False
        if not specs.get("mcu") and not specs.get("mcu_type"): return False
    elif "battery" in pt:
        if not specs.get("cell_count_s") and not specs.get("voltage_v"): return False
        if not specs.get("capacity_mah"): return False
    elif "esc" in pt:
        if not specs.get("continuous_current_a") and not specs.get("current_a"): return False
    elif "prop" in pt:
        if not specs.get("diameter_inch") and not specs.get("diameter_mm"): return False
    return True

async def process_single_candidate(scraper, item, part_type, vision_prompt_object, min_confidence):
    link = item.get('link')
    title = item.get('title')
    
    if not link or not title: return None
    if any(bad_domain in link for bad_domain in DOMAIN_BLOCKLIST): return None
    if any(bad_word in title.lower() for bad_word in GENERIC_TITLE_BLOCKLIST): return None

    print(f"   Trying: {title[:50]}...")
    
    # 1. Deep Scrape (Now returns images list + structured tables)
    scraped_data = await scraper.scrape_product_page(link)
    if not scraped_data: return None

    final_price = scraped_data.get('price')
    # Sanity check price
    if not final_price or not isinstance(final_price, (int, float)) or final_price <= 0.50:
        return None

    # Prepare Context for Vision/AI
    images = scraped_data.get('images', [])
    text_tables = scraped_data.get('structured_tables', '')
    raw_text = scraped_data.get('text', '')
    
    # Combine structured data with general text for the LLM
    combined_text_context = f"{text_tables}\n\n--- GENERAL DESCRIPTION ---\n{raw_text[:2000]}"

    validated_specs = {} 
    
    # 2. Multimodal Vision Analysis
    if vision_prompt_object:
        # Calls the new multimodal function
        raw_vision_result = await analyze_specs_multimodal(
            combined_text_context, 
            images, 
            part_type, 
            vision_prompt_object
        )
        
        if raw_vision_result and not raw_vision_result.get("error"):
            for key, data in raw_vision_result.items():
                if isinstance(data, dict):
                    confidence = data.get("confidence", 0)
                    value = data.get("value")
                    
                    if value is not None and confidence >= min_confidence:
                        validated_specs[key] = value

            if validated_specs:
                 validated_specs["source"] = "multimodal_fusion"

    # 3. Fallback Text Inference (Regex)
    # (Only runs if specific critical keys are missing from Vision)
    engineering_specs = validated_specs.copy()

    if "motor" in part_type.lower() and "mounting_mm" not in engineering_specs:
        inferred = infer_motor_mounting(title)
        if inferred:
            engineering_specs["mounting_mm"] = inferred
            engineering_specs["source"] = "text_inference_fallback"

    if "propeller" in part_type.lower() and "diameter_mm" not in engineering_specs:
        diam = extract_prop_diameter(title)
        if diam:
            engineering_specs["diameter_mm"] = diam
            engineering_specs["source"] = "text_inference_fallback"

    # 4. Critical Spec Validation
    if not validate_critical_specs(part_type, engineering_specs):
        return None

    return {
        "product_name": title, 
        "price": final_price, 
        "source_url": link,
        "image_url": images[0] if images else None, # Main image for UI
        "engineering_data": engineering_specs,
        "has_tables": bool(text_tables) # Metadata for ranking
    }

async def fuse_component_data(part_type: str, search_query: str, search_limit: int = 5, min_confidence: float = 0.6):
    """
    Orchestrates the search, scrape, and fusion process.
    """
    # STEP 1: Get dynamic prompt
    vision_prompt_object = await generate_vision_prompt(part_type)
    if not vision_prompt_object:
        print(f"   ⚠️  Vision Prompt Generation Failed for {part_type}.")
        return None

    # STEP 2: Find candidates
    results = find_components(search_query, limit=search_limit)
    if not results: 
        return None

    # STEP 3: Process candidates in parallel
    async with Scraper() as scraper:
        tasks = [
            process_single_candidate(scraper, res, part_type, vision_prompt_object, min_confidence) 
            for res in results
        ]
        candidates = await asyncio.gather(*tasks)
        
    valid_candidates = [c for c in candidates if c is not None]
    if not valid_candidates: 
        return None

    # STEP 4: Rank and select best candidate
    def rank_candidate(c):
        score = 0
        specs = c.get("engineering_data", {})
        
        # Gold standard: Multimodal extraction succeeded
        if specs.get("source") == "multimodal_fusion": score += 20 
        
        # Silver standard: Regex worked
        if "text_inference" in specs.get("source", ""): score += 5
        
        # Bonus: We found structured tables (higher trust)
        if c.get("has_tables"): score += 10
        
        # Bonus: Image exists
        if c.get("image_url"): score += 5
        
        # Quantity of data
        score += len(specs)
        return score

    valid_candidates.sort(key=rank_candidate, reverse=True)
    best_candidate = valid_candidates[0]
    
    composite_part = {
        "part_type": part_type,
        "product_name": best_candidate['product_name'],
        "price": best_candidate['price'],
        "source_url": best_candidate['source_url'],
        "engineering_specs": best_candidate['engineering_data'],
        "reference_image": best_candidate['image_url'],
        "data_source_method": best_candidate['engineering_data'].get('source', 'raw_search'),
        "alternatives_checked": len(valid_candidates)
    }
    
    return composite_part