# FILE: seed_arsenal.py
import asyncio
import json
import os
import random
from datetime import datetime
from app.services.ai_service import call_llm_for_json
from app.services.fusion_service import fuse_component_data
from app.services.texture_service import extract_visual_dna
from app.prompts import (
    RANCHER_PERSONA_INSTRUCTION, 
    ARSENAL_ENGINEER_INSTRUCTION, 
    ARSENAL_SOURCER_INSTRUCTION,
    ARSENAL_SCOUT_INSTRUCTION
)

ARSENAL_FILE = "drone_arsenal.json"
AUDIT_LOG_FILE = "arsenal_audit_log.json"

# --- AGENTS (Imported Logic) ---

async def agent_rancher_needs():
    print("\n🤠 AGENT 1: The Rancher is defining the Autonomous Fleet...")
    result = await call_llm_for_json(
        "Define the specialized robotic fleet for the ranch.", 
        RANCHER_PERSONA_INSTRUCTION
    )
    
    # Log this high-level decision
    log_audit_event("RANCHER_DECISION", {"prompt": "Define fleet...", "result": result})
    
    if isinstance(result, dict) and "missions" in result: return result["missions"]
    return result if isinstance(result, list) else []

async def agent_engineer_parts(mission_profile):
    mission_name = mission_profile.get("mission_name", "Unknown")
    print(f"\n👷 AGENT 2 (Engineer): Designing Compute & Mechanical stack for {mission_name}...")
    context = json.dumps(mission_profile)
    
    result = await call_llm_for_json(f"MISSION PROFILE: {context}", ARSENAL_ENGINEER_INSTRUCTION)
    
    log_audit_event("ENGINEER_DESIGN", {
        "mission": mission_name, 
        "context": context, 
        "proposed_parts": result
    })
    
    return result

async def agent_market_scout(mission_profile):
    mission_name = mission_profile.get("mission_name", "Unknown")
    print(f"\n🕵️ AGENT 2.5 (Scout): Searching industrial solutions for {mission_name}...")
    context = json.dumps(mission_profile)
    
    result = await call_llm_for_json(f"MISSION PROFILE: {context}", ARSENAL_SCOUT_INSTRUCTION)
    
    log_audit_event("SCOUT_SEARCH", {
        "mission": mission_name, 
        "context": context, 
        "found_drones": result
    })
    
    return result

async def agent_sourcer_queries(parts_structure, mission_name):
    print(f"\n🔎 AGENT 3 (Sourcer): Generating queries for {mission_name}...")
    context_list = []
    for category, models in parts_structure.items():
        if isinstance(models, list):
            for m in models:
                context_list.append(f"{category}: {m}")
    context_str = "\n".join(context_list)
    
    result = await call_llm_for_json(f"COMPONENT LIST: {context_str}", ARSENAL_SOURCER_INSTRUCTION)
    queries = result.get("queries", []) if result else []
    
    log_audit_event("SOURCER_QUERIES", {
        "mission": mission_name,
        "input_list": context_list,
        "generated_queries": queries
    })
    
    return queries

# --- UTILS ---
def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f: return json.load(f)
        except: pass
    # Default structure depending on file
    if "audit" in filepath: return {"events": []}
    return {"components": []}

def log_audit_event(event_type, data):
    """
    Saves raw data to the audit log for future debugging/learning.
    """
    log_db = load_json(AUDIT_LOG_FILE)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "data": data
    }
    log_db["events"].append(entry)
    
    # Write immediately to disk
    with open(AUDIT_LOG_FILE, "w") as f:
        json.dump(log_db, f, indent=2)

def save_to_arsenal(new_item, tags, item_type="component"):
    db = load_json(ARSENAL_FILE)
    
    cat = new_item.get('part_type', '').lower()
    name = new_item.get('product_name', '').lower()

    # Auto-Tagging for Intelligence
    if "computer" in cat or "jetson" in name or "raspberry" in name:
        tags.append("AI_CAPABLE")
    if "sensor" in cat or "lidar" in name or "depth" in name:
        tags.append("OBSTACLE_AVOIDANCE")
    if "gps" in cat:
        tags.append("AUTONOMOUS_NAVIGATION")

    # Duplicate Check
    for existing in db['components']:
        if existing['model_name'] == new_item['product_name']:
            print(f"      ⚠️  Known Item: {new_item['product_name']}. Updating tags.")
            if "tags" not in existing: existing["tags"] = []
            for t in tags:
                if t not in existing["tags"]: existing["tags"].append(t)
            
            # Update Visuals if missing
            if "visuals" not in existing and "visuals" in new_item:
                existing["visuals"] = new_item["visuals"]

            with open(ARSENAL_FILE, "w") as f: json.dump(db, f, indent=2)
            return

    entry = {
        "type": item_type,
        "category": new_item['part_type'],
        "model_name": new_item['product_name'],
        "price_est": new_item['price'],
        "specs": new_item['engineering_specs'],
        "visuals": new_item.get('visuals'),
        "image_url": new_item['reference_image'],
        "source_url": new_item['source_url'],
        "verified": True,
        "tags": list(set(tags)) # Dedupe tags
    }
    
    db['components'].append(entry)
    with open(ARSENAL_FILE, "w") as f: json.dump(db, f, indent=2)
    print(f"      💾 Saved: {new_item['product_name']} {tags}")

# --- MAIN EXECUTION FLOW ---
async def run_seeder():
    print("🏭 OPENFORGE ARSENAL SEEDER (AUDIT LOGGING ENABLED) INITIALIZED")
    print("==============================================================")
    
    missions = await agent_rancher_needs()
    if not missions: print("❌ Rancher failed."); return
    print(f"   -> Defined {len(missions)} robotic missions.")

    for mission in missions:
        m_name = mission.get("mission_name", "General")
        print(f"\n🚀 MISSION CAMPAIGN: {m_name}")
        print(f"   Autonomy Level: {mission.get('autonomy_level', 'Manual')}")
        
        # 1. Engineer & Scout
        build_parts = await agent_engineer_parts(mission)
        buy_drones = await agent_market_scout(mission)
        
        full_target_list = {}
        if build_parts: full_target_list.update(build_parts)
        if buy_drones: full_target_list.update(buy_drones)

        if not full_target_list:
            print(f"   ❌ No targets. Skipping.")
            log_audit_event("CAMPAIGN_SKIPPED", {"mission": m_name, "reason": "No targets generated"})
            continue
            
        # 2. Generate Queries
        query_list = await agent_sourcer_queries(full_target_list, m_name)
        if not query_list: print(f"   ❌ Sourcing failed."); continue
        
        print(f"   -> Found {len(query_list)} targets. Engaging Fusion Service...")

        # 3. Fusion Search Loop
        for i, item in enumerate(query_list):
            category = item['part_type']
            model = item['model_name']
            search_query = item['search_query']
            item_type = "complete_drone" if category == "Complete_Drone" else "component"

            print(f"\n   ⚡ Processing [{i+1}/{len(query_list)}]: {model}...")
            
            await asyncio.sleep(random.uniform(5.0, 10.0)) # Rate Limit
            
            # --- FUSION SERVICE CALL ---
            result = await fuse_component_data(
                part_type=category, 
                search_query=search_query,
                search_limit=8, 
                min_confidence=0.80
            )
            
            # --- VALIDATION LOGIC ---
            if result and result.get('engineering_specs') and result.get('price'):
                 print(f"      🎨 Extracting Visual DNA...")
                 visual_dna = await extract_visual_dna(result['reference_image'], category)
                 result['visuals'] = visual_dna
                 
                 print(f"      ✅ Verified. Saving...")
                 save_to_arsenal(result, tags=[m_name], item_type=item_type)
                 
                 # Log Success
                 log_audit_event("VERIFICATION_SUCCESS", {
                     "model": model,
                     "url": result['source_url'],
                     "specs_found": result['engineering_specs']
                 })
            else:
                 # --- REJECTION LOGGING ---
                 reason = "Unknown"
                 if not result: reason = "No Search Results Found"
                 elif not result.get('engineering_specs'): reason = "Vision AI Failed to Extract Specs (Confidence Low)"
                 elif not result.get('price'): reason = "Price Not Found"
                 
                 print(f"      ❌ Failed to verify: {model} ({reason})")
                 
                 # Log Failure in Detail for Future Learning
                 log_audit_event("VERIFICATION_REJECTED", {
                     "model": model,
                     "search_query": search_query,
                     "reason": reason,
                     "raw_result_dump": result if result else "None"
                 })

    print("\n✅ Seeding Complete. Arsenal & Audit Logs Updated.")

if __name__ == "__main__":
    asyncio.run(run_seeder())