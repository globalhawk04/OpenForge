# FILE: tools/seed_ecosystem.py
import asyncio
import json
import os
import random
from app.services.ai_service import call_llm_for_json
from app.services.fusion_service import fuse_component_data
from app.services.texture_service import extract_visual_dna

ARSENAL_FILE = "drone_arsenal.json"

# --- PROMPT: THE LOGISTICS EXPERT ---
ECOSYSTEM_PROMPT = """
You are a Drone Logistics & Integration Expert.
I have this component in my inventory: "{model_name}" ({category}).

**TASK:**
Identify 3 ESSENTIAL physical accessories required to integrate this specific part into a custom drone build.
Focus on **Interconnects** (Cables, Pigtails), **Mounts** (Adapters), or **Support Hardware**.

**RULES:**
1.  Do NOT list generic tools (screwdrivers, soldering iron).
2.  Do NOT list the main part itself.
3.  Be specific (e.g., "JST-GH 1.25mm to Silicone Wire", "U.FL to SMA Pigtail", "Micro HDMI Ribbon Cable").
4.  If the part is a standard frame or prop, return an empty list [].

**OUTPUT SCHEMA (JSON List of Strings):**
["Specific Accessory 1", "Specific Accessory 2"]
"""

async def agent_identify_needs(part):
    """Asks AI what accessories are missing for a given part."""
    # Only check complex electronics, not simple plastic/carbon parts
    if part['category'] in ['Frame_Kit', 'Propellers']:
        return []
    
    prompt = ECOSYSTEM_PROMPT.format(
        model_name=part['model_name'], 
        category=part['category']
    )
    
    # We expect a simple list of strings
    needs = await call_llm_for_json(prompt, "You are a Logistics Expert.")
    
    # Handle the raw list return
    if isinstance(needs, list): return needs
    if isinstance(needs, dict) and 'accessories' in needs: return needs['accessories']
    return []

async def seed_ecosystem():
    print("🕸️  OPENFORGE ECOSYSTEM: Hunting for Missing Interconnects...")
    
    if not os.path.exists(ARSENAL_FILE):
        print("❌ No arsenal found.")
        return

    with open(ARSENAL_FILE, "r") as f:
        data = json.load(f)
        current_inventory = data.get("components", [])

    # Create a quick lookup set of what we already have
    existing_names = {c['model_name'].lower() for c in current_inventory}
    
    new_finds = []

    # Iterate through high-value parts
    for part in current_inventory:
        # Optimization: Only check "Brains" and "Peripherals"
        if part['category'] not in ['FC_Stack', 'Companion_Computer', 'Camera_VTX_Kit', 'Lidar_Module']:
            continue

        print(f"\n🧐 Analyzing Dependencies for: {part['model_name']}...")
        
        # 1. Identify what is needed
        needed_accessories = await agent_identify_needs(part)
        
        for accessory in needed_accessories:
            # 2. Check if we already have it
            is_present = any(accessory.lower() in existing for existing in existing_names)
            
            if is_present:
                print(f"   ✅ Already have: {accessory}")
                continue
                
            print(f"   🔍 Missing Ecosystem Part: {accessory}. Hunting...")
            
            # 3. Hunt for it using Fusion Service
            # We map these to a generic 'Interconnect' category for physics, 
            # but keep the specific name for the builder.
            result = await fuse_component_data(
                part_type="Interconnect", 
                search_query=f"{accessory} drone part price",
                search_limit=3,
                min_confidence=0.60 # Lower confidence allowed for cables
            )
            
            if result:
                print(f"      ✨ FOUND: {result['product_name']}")
                
                # Tag it so we know which parent part triggered this find
                result['tags'] = ["ECOSYSTEM_AUTOFILL", f"REQ_FOR_{part['model_name']}"]
                
                # Get visuals (likely just black wire/plastic, but good to have)
                result['visuals'] = await extract_visual_dna(result['reference_image'], "Cable")
                
                new_finds.append(result)
                existing_names.add(result['product_name'].lower()) # Don't find it twice this run
                
                # Rate limit politeness
                await asyncio.sleep(random.uniform(2.0, 5.0))
            else:
                print(f"      ❌ Could not source: {accessory}")

    # 4. Save Updates
    if new_finds:
        print(f"\n💾 Saving {len(new_finds)} new ecosystem parts to Arsenal...")
        current_inventory.extend(new_finds)
        data['components'] = current_inventory
        with open(ARSENAL_FILE, "w") as f:
            json.dump(data, f, indent=2)
    else:
        print("\n✅ Ecosystem is stable. No new gaps found.")

if __name__ == "__main__":
    asyncio.run(seed_ecosystem())