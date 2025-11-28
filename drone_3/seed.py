# FILE: seed.py
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
    REQUIREMENTS_SYSTEM_INSTRUCTION, # NEW: The Logic Bridge
    ARSENAL_ENGINEER_INSTRUCTION, 
    ARSENAL_SOURCER_INSTRUCTION,
    ARSENAL_SCOUT_INSTRUCTION
)

ARSENAL_FILE = "drone_arsenal.json"
AUDIT_LOG_FILE = "arsenal_audit_log.json"

# --- AGENTS (The "Constraint Chain") ---

async def agent_rancher_needs():
    """
    Step 1: The Persona.
    Generates high-level mission profiles (e.g., 'Brush Busting Fence Patrol').
    """
    print("\n🤠 AGENT 1: The Rancher is defining the Autonomous Fleet...")
    result = await call_llm_for_json(
        "Define the specialized robotic fleet for the ranch.", 
        RANCHER_PERSONA_INSTRUCTION
    )
    
    log_audit_event("RANCHER_DECISION", {"prompt": "Define fleet...", "result": result})
    
    if isinstance(result, dict) and "missions" in result: return result["missions"]
    return result if isinstance(result, list) else []

async def agent_architect_constraints(mission_profile):
    """
    Step 2: The Architect (NEW).
    Translates 'Brush Busting' into 'Stator Volume > 2306' and 'Arm Thickness > 5mm'.
    """
    mission_name = mission_profile.get("mission_name", "Unknown")
    print(f"\n📐 AGENT 1.5 (Architect): Deriving Physics Constraints for {mission_name}...")
    
    # We feed the mission description to the Requirements Instruction
    context = json.dumps(mission_profile)
    result = await call_llm_for_json(f"USER REQUEST: {context}", REQUIREMENTS_SYSTEM_INSTRUCTION)
    
    log_audit_event("ARCHITECT_CONSTRAINTS", {
        "mission": mission_name,
        "derived_constraints": result
    })
    
    return result

async def agent_engineer_parts(mission_profile, architect_plan):
    """
    Step 3: The Engineer.
    Selects specific real-world models (e.g., 'T-Motor F60 Pro') that meet the Architect's constraints.
    """
    mission_name = mission_profile.get("mission_name", "Unknown")
    print(f"\n👷 AGENT 2 (Engineer): Selecting components for {mission_name}...")
    
    # Input is now the Mission + The Technical Constraints
    context = {
        "mission": mission_profile,
        "constraints": architect_plan.get("technical_constraints", {}),
        "topology": architect_plan.get("topology", {})
    }
    
    context_str = json.dumps(context)
    result = await call_llm_for_json(f"ENGINEERING CONTEXT: {context_str}", ARSENAL_ENGINEER_INSTRUCTION)
    
    log_audit_event("ENGINEER_DESIGN", {
        "mission": mission_name, 
        "context": context_str, 
        "proposed_parts": result
    })
    
    return result

async def agent_market_scout(mission_profile):
    """
    Step 3.5: The Scout.
    Looks for RTF (Ready-to-Fly) alternatives.
    """
    mission_name = mission_profile.get("mission_name", "Unknown")
    print(f"\n🕵️ AGENT 2.5 (Scout): Searching industrial solutions for {mission_name}...")
    context = json.dumps(mission_profile)
    
    result = await call_llm_for_json(f"MISSION PROFILE: {context}", ARSENAL_SCOUT_INSTRUCTION)
    
    log_audit_event("SCOUT_SEARCH", {
        "mission": mission_name, 
        "found_drones": result
    })
    
    return result

async def agent_sourcer_queries(parts_structure, mission_name):
    """
    Step 4: The Sourcer.
    Converts specific model names into targeted Google Search queries.
    """
    print(f"\n🔎 AGENT 3 (Sourcer): Generating queries for {mission_name}...")
    
    # Flatten the structure into a list of models for the prompt
    target_models = []
    for category, items in parts_structure.items():
        if isinstance(items, list):
            for model in items:
                target_models.append(f"{category}: {model}")
    
    context_str = "\n".join(target_models)
    
    # The prompt now expects specific models, not just categories
    result = await call_llm_for_json(f"TARGET MODELS: {context_str}", ARSENAL_SOURCER_INSTRUCTION)
    queries = result.get("queries", []) if result else []
    
    log_audit_event("SOURCER_QUERIES", {
        "mission": mission_name,
        "input_list": target_models,
        "generated_queries": queries
    })
    
    return queries

# --- UTILS (Unchanged) ---
def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f: return json.load(f)
        except: pass
    if "audit" in filepath: return {"events": []}
    return {"components": []}

def log_audit_event(event_type, data):
    log_db = load_json(AUDIT_LOG_FILE)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "data": data
    }
    log_db["events"].append(entry)
    with open(AUDIT_LOG_FILE, "w") as f:
        json.dump(log_db, f, indent=2)

def save_to_arsenal(new_item, tags, item_type="component"):
    db = load_json(ARSENAL_FILE)
    
    cat = new_item.get('part_type', '').lower()
    name = new_item.get('product_name', '').lower()

    # Auto-Tagging
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
            
            # Update Visuals/Specs if newer/better
            if new_item.get('engineering_specs'):
                existing['specs'] = new_item['engineering_specs']
            if new_item.get('visuals'):
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
        "tags": list(set(tags))
    }
    
    db['components'].append(entry)
    with open(ARSENAL_FILE, "w") as f: json.dump(db, f, indent=2)
    print(f"      💾 Saved: {new_item['product_name']} {tags}")

# --- MAIN EXECUTION FLOW ---
async def run_seeder():
    print("🏭 OPENFORGE ARSENAL SEEDER V2 (Logic Chain Enabled)")
    print("======================================================")
    
    missions = await agent_rancher_needs()
    if not missions: print("❌ Rancher failed."); return
    print(f"   -> Defined {len(missions)} robotic missions.")

    for mission in missions:
        m_name = mission.get("mission_name", "General")
        print(f"\n🚀 MISSION CAMPAIGN: {m_name}")
        
        # --- NEW STEP: ARCHITECT THE CONSTRAINTS ---
        architect_plan = await agent_architect_constraints(mission)
        if not architect_plan: 
            print("   ❌ Architect failed to derive constraints. Skipping.")
            continue

        print(f"   -> Constraints: {json.dumps(architect_plan.get('technical_constraints'), indent=2)}")

        # 1. Engineer & Scout (Now using Constraints)
        build_parts = await agent_engineer_parts(mission, architect_plan)
        buy_drones = await agent_market_scout(mission)
        
        full_target_list = {}
        if build_parts: full_target_list.update(build_parts)
        if buy_drones: full_target_list.update(buy_drones)

        if not full_target_list:
            print(f"   ❌ No targets generated. Skipping.")
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
            
            await asyncio.sleep(random.uniform(3.0, 7.0)) # Polite Rate Limit
            
            # --- FUSION SERVICE CALL ---
            # Uses the upgraded Recon (Deep Scrape) & Vision (Multimodal) services
            result = await fuse_component_data(
                part_type=category, 
                search_query=search_query,
                search_limit=6, 
                min_confidence=0.75 # Higher bar for automated seeding
            )
            
            # --- VALIDATION LOGIC ---
            if result and result.get('engineering_specs') and result.get('price'):
                 print(f"      🎨 Extracting Visual DNA...")
                 visual_dna = await extract_visual_dna(result['reference_image'], category)
                 result['visuals'] = visual_dna
                 
                 print(f"      ✅ Verified. Saving...")
                 save_to_arsenal(result, tags=[m_name, architect_plan.get("topology", {}).get("class", "General")], item_type=item_type)
                 
                 log_audit_event("VERIFICATION_SUCCESS", {
                     "model": model,
                     "url": result['source_url'],
                     "specs_found": result['engineering_specs']
                 })
            else:
                 reason = "Unknown"
                 if not result: reason = "No Search Results"
                 elif not result.get('engineering_specs'): reason = "Low Confidence Specs"
                 elif not result.get('price'): reason = "No Price Found"
                 
                 print(f"      ❌ Failed to verify: {model} ({reason})")
                 
                 log_audit_event("VERIFICATION_REJECTED", {
                     "model": model,
                     "reason": reason
                 })

    print("\n✅ Seeding Complete. Arsenal & Audit Logs Updated.")

if __name__ == "__main__":
    asyncio.run(run_seeder())