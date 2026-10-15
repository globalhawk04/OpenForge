# --- START OF FILE app/services/fusion_service.py ---
import json
import os
from app.services.recon_service import Scraper, EVIDENCE_ROOT
from app.services.vision_service import analyze_specs_multimodal, get_deterministic_vision_schema
from app.services.library_service import infer_motor_mounting, extract_prop_diameter
from app.services.search_service import find_components_async, find_components

DOMAIN_BLOCKLIST = [
    "reddit.com", "facebook.com", "youtube.com", "twitter.com", "x.com",
    "instagram.com", "forum", "pinterest", "thingiverse", "mdpi.com",
    "oscarliang.com", "getfpv.com/learn", "blog", "news",
    "docs.px4.io", "ardupilot.org", "betaflight.com", "manuals.plus",
    "manualslib.com", "github.com", "wikipedia.org", "instructables.com"
]

GENERIC_TITLE_BLOCKLIST = [
    "collections", "category", "browse",
    "rc model vehicles", "user manual", "guide (main)",
    "documentation", "wiki", "firmware"
]

CATEGORY_DEFAULT_PRICES = {
    "motors": 24.99,
    "propellers": 4.99,
    "battery": 34.99,
    "fc_stack": 79.99,
    "frame_kit": 89.99,
    "complete_drone": 499.99,
    "sensor": 59.99,
    "lidar_module": 149.99,
}


def update_human_review_index():
    """
    Rebuilds `data/evidence_archive/index.html` so a human engineer can browse all
    archived screenshots, downloaded diagrams, raw text, and extracted specs in one place.
    """
    if not os.path.exists(EVIDENCE_ROOT):
        return

    entries_html = []
    folders = sorted(
        [d for d in os.listdir(EVIDENCE_ROOT) if os.path.isdir(os.path.join(EVIDENCE_ROOT, d))],
        reverse=True,
    )

    for folder in folders[:100]:
        f_path = os.path.join(EVIDENCE_ROOT, folder)
        report_file = os.path.join(f_path, "forensic_vision_report.json")
        text_file = os.path.join(f_path, "scraped_text.txt")

        report_json = "{}"
        if os.path.exists(report_file):
            try:
                with open(report_file, "r", encoding="utf-8") as rf:
                    report_json = rf.read()
            except Exception:
                pass

        imgs = sorted([img for img in os.listdir(f_path) if img.endswith(".jpg")])
        imgs_html = "".join(
            f'<a href="{folder}/{im}" target="_blank"><img src="{folder}/{im}" style="height:130px; border-radius:4px; border:1px solid #334155;"></a>'
            for im in imgs
        )

        entries_html.append(f"""
        <div style="background:#111927; border:1px solid #1e2d42; border-radius:8px; padding:16px; margin-bottom:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <h3 style="margin:0; color:#00e5a3; font-size:15px;">📁 {folder}</h3>
                <div>
                    <a href="{folder}/scraped_text.txt" target="_blank" style="color:#38bdf8; margin-right:15px; font-size:13px;">📄 View Scraped Text & Tables</a>
                    <a href="{folder}/forensic_vision_report.json" target="_blank" style="color:#f59e0b; font-size:13px;">🔍 View Vision JSON</a>
                </div>
            </div>
            <div style="display:flex; gap:10px; overflow-x:auto; padding-bottom:10px;">{imgs_html}</div>
            <pre style="background:#080c14; color:#cbd5e1; padding:10px; border-radius:4px; font-size:11px; max-height:180px; overflow:auto; margin:8px 0 0 0;">{report_json}</pre>
        </div>
        """)

    html = f"""<!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><title>OpenForge Human Review Evidence Archive</title></head>
    <body style="background:#090d14; color:#e2e8f0; font-family:monospace; padding:24px; max-width:1200px; margin:auto;">
        <h1 style="color:#00e5a3; border-bottom:1px solid #1e2d42; padding-bottom:12px;">🕵️ OpenForge Human Review Evidence Locker ({len(folders)} Scraped Items)</h1>
        <p style="color:#8b9bb4;">Click any image to inspect full resolution, or open the Scraped Text / Vision JSON links to audit extracted specs.</p>
        {"".join(entries_html)}
    </body>
    </html>"""

    with open(os.path.join(EVIDENCE_ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def validate_critical_specs(part_type: str, specs: dict) -> bool:
    if not specs or not isinstance(specs, dict):
        return False

    pt = part_type.lower()
    if "complete_drone" in pt:
        return len(specs) >= 1

    if "motor" in pt:
        has_kv = bool(specs.get("kv_rating") or specs.get("kv"))
        has_mount = bool(specs.get("mounting_bolt_pattern_mm") or specs.get("mounting_mm") or specs.get("stator_size"))
        return has_kv and has_mount

    if "frame" in pt:
        has_wb = bool(specs.get("wheelbase_mm") or specs.get("max_prop_size_inch"))
        return has_wb

    if "fc" in pt or "stack" in pt:
        stack_type = str(specs.get("stack_type", "")).upper()
        if stack_type == "FC_ONLY" and not specs.get("continuous_current_a"):
            print("   ⚠️  Rejected FC_ONLY board for FC_Stack slot (missing integrated ESC).")
            return False
        return True

    if "battery" in pt:
        has_v = bool(specs.get("cell_count_s") or specs.get("voltage_v"))
        has_cap = bool(specs.get("capacity_mah"))
        return has_v or has_cap

    if "prop" in pt:
        return bool(specs.get("diameter_inches") or specs.get("diameter_inch") or specs.get("diameter_mm"))

    return True


async def process_single_candidate(
    scraper: Scraper,
    item: dict,
    part_type: str,
    vision_prompt_object: dict,
    min_confidence: float,
) -> dict | None:
    link = item.get("link")
    title = item.get("title")

    if not link or not title:
        return None
    if any(bad_domain in link.lower() for bad_domain in DOMAIN_BLOCKLIST):
        return None
    if any(bad_word in title.lower() for bad_word in GENERIC_TITLE_BLOCKLIST):
        return None

    print(f"   Trying: {title[:55]}...")
    scraped_data = await scraper.scrape_product_page(link, part_type=part_type)
    if not scraped_data:
        return None

    final_price = scraped_data.get("price")
    if not final_price or not isinstance(final_price, (int, float)) or final_price < 1.50:
        if scraped_data.get("structured_tables") or scraped_data.get("local_image_paths"):
            final_price = CATEGORY_DEFAULT_PRICES.get(part_type.lower(), 29.99)
        else:
            return None

    images = scraped_data.get("images", [])
    local_images = scraped_data.get("local_image_paths", [])
    evidence_dir = scraped_data.get("evidence_dir")
    text_tables = scraped_data.get("structured_tables", "")
    raw_text = scraped_data.get("text", "")
    combined_text_context = f"PRODUCT TITLE: {title}\n\n{text_tables}\n\n--- DESCRIPTION ---\n{raw_text[:4500]}"

    validated_specs = {}
    raw_vision_result = await analyze_specs_multimodal(
        combined_text_context,
        images,
        part_type,
        vision_prompt_object,
        local_image_paths=local_images,
        evidence_dir=evidence_dir,
    )

    # Update the human review HTML index after every vision analysis
    update_human_review_index()

    if raw_vision_result and not raw_vision_result.get("error"):
        for key, data in raw_vision_result.items():
            if isinstance(data, dict) and "value" in data:
                confidence = float(data.get("confidence") or 0.0)
                value = data.get("value")
                if value is not None and confidence >= min_confidence:
                    validated_specs[key] = value
            elif data is not None:
                validated_specs[key] = data

        if validated_specs:
            validated_specs["source"] = "multimodal_fusion"
            validated_specs["evidence_dir"] = evidence_dir

    engineering_specs = validated_specs.copy()
    if "motor" in part_type.lower() and not engineering_specs.get("mounting_bolt_pattern_mm"):
        inferred = infer_motor_mounting(title)
        if inferred:
            engineering_specs["mounting_bolt_pattern_mm"] = f"{int(inferred)}x{int(inferred)}"

    if "prop" in part_type.lower() and not engineering_specs.get("diameter_mm"):
        diam = extract_prop_diameter(title)
        if diam:
            engineering_specs["diameter_mm"] = diam
            engineering_specs["diameter_inches"] = round(diam / 25.4, 2)

    if not validate_critical_specs(part_type, engineering_specs):
        return None

    return {
        "product_name": title,
        "price": final_price,
        "source_url": link,
        "image_url": images[0] if images else None,
        "local_image_paths": local_images,
        "evidence_dir": evidence_dir,
        "engineering_data": engineering_specs,
        "has_tables": bool(text_tables),
    }


async def fuse_component_data(
    part_type: str,
    search_query: str,
    search_limit: int = 4,
    min_confidence: float = 0.60,
) -> dict | None:
    vision_prompt_object = get_deterministic_vision_schema(part_type)

    async with Scraper() as scraper:
        results = await find_components_async(search_query, limit=search_limit, browser=scraper.browser)
        if not results:
            return None

        valid_candidates = []
        for res in results:
            cand = await process_single_candidate(scraper, res, part_type, vision_prompt_object, min_confidence)
            if cand is not None:
                valid_candidates.append(cand)
                if len(valid_candidates) >= 2:
                    break

    if not valid_candidates:
        return None

    def rank_candidate(c: dict) -> int:
        score = 0
        specs = c.get("engineering_data", {})
        if specs.get("source") == "multimodal_fusion":
            score += 25
        if specs.get("weight_g"):
            score += 15
        if c.get("has_tables"):
            score += 10
        if c.get("image_url"):
            score += 5
        score += len(specs) * 2
        return score

    valid_candidates.sort(key=rank_candidate, reverse=True)
    best = valid_candidates[0]

    return {
        "part_type": part_type,
        "category": part_type,
        "product_name": best["product_name"],
        "model_name": best["product_name"],
        "price": best["price"],
        "source_url": best["source_url"],
        "engineering_specs": best["engineering_data"],
        "specs": best["engineering_data"],
        "reference_image": best["image_url"],
        "evidence_dir": best.get("evidence_dir"),
        "local_image_paths": best.get("local_image_paths", []),
        "data_source_method": best["engineering_data"].get("source", "multimodal_fusion"),
        "alternatives_checked": len(valid_candidates),
    }
# --- END OF FILE app/services/fusion_service.py ---