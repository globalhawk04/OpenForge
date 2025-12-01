# FILE: tools/seed_ecosystem.py
import asyncio
import json
import os
import random
from app.services.ai_service import call_llm_for_json
from app.services.fusion_service import fuse_component_data
from app.services.texture_service import extract_visual_dna

ARSENAL_FILE = "drone_arsenal.json"

# --- PROMPT 1: THE LOGISTICS EXPERT (Cables & Connectors) ---
ECOSYSTEM_PROMPT = """
You are a Drone Logistics & Integration Expert.
I have this component in my inventory: "{model_name}" ({category}).

**TASK:**
Identify 3 ESSENTIAL physical accessories required to integrate this specific part into a custom drone build.
Focus on **Interconnects** (Cables, Pigtails), **Mounts** (Adapters), or **Support Hardware**.

**RULES:**
1.  Do NOT list generic tools (screwdrivers, soldering iron).
2.  Do NOT list the main part itself.
3.  Be specific (e.g., "JST-GH 1.25mm to Silicone Wire", "U.FL to SMA Pigtail", "Micro HDMI Ribbon Cable", "XT60 Pigtail w/ Capacitor").
4.  If the part is a standard plastic part, return an empty list [].

**OUTPUT SCHEMA (JSON List of Strings):**
["Specific Accessory 1", "Specific Accessory 2"]
"""

# --- PROMPT 2: THE AERODYNAMICIST (Thrust & Power Matching) ---
PROPULSION_PROMPT = """
You are a Drone Propulsion Engineer.
I have this component: "{model_name}" ({category}).

**TASK:**
Identify the SINGLE BEST complementary component required to make this part fly efficiently, based on manufacturer recommendations or standard physics.

**LOGIC:**
1.  **If Motor:** Identify the **Specific Propeller Model** used in its official thrust data tables (e.g., "Gemfan 51433", "T-Motor 28x9.2 Carbon").
2.  **If Propeller:** Identify a **Compatible Motor Size** (e.g., "2207 1750KV Motor").
3.  **If Frame:** Identify the **Recommended Battery** (e.g., "6S 1300mAh LiPo", "12S 22000mAh Solid State").

**OUTPUT SCHEMA (JSON List of Strings):**
["Specific Complementary Component Name"]
"""

async def agent_identify_needs(part):
    """
    Decides which expert to consult based on the part category.
    """
    category = part.get('category', '')
    
    # Branch 1: Propulsion & Physics Matching (New Logic)
    if category in ['Motors', 'Propellers', 'Frame_Kit']:
        prompt = PROPULSION_PROMPT.format(
            model_name=part['model_name'],
            category=category
        )
        system_instruction = "You are a Propulsion Engineer."
        
    # Branch 2: Electronics & Wiring (Original Logic)
    elif category in ['FC_Stack', 'Companion_Computer', 'Camera_VTX_Kit', 'Lidar_Module', 'Video_System', 'GPS_Module']:
        prompt = ECOSYSTEM_PROMPT.format(
            model_name=part['model_name'], 
            category=category
        )
        system_instruction = "You are a Logistics Expert."
    
    # Branch 3: Ignore simple passive parts
    else:
        return []

    # Call AI
    needs = await call_llm_for_json(prompt, system_instruction)
    
    # Handle the raw list return or dict wrapper
    if isinstance(needs, list): return needs
    if isinstance(needs, dict):
        # Try to find a list inside the dict keys
        for key in ['accessories', 'components', 'parts', 'matches']:
            if key in needs and isinstance(needs[key], list):
                return needs[key]
    return []

async def seed_ecosystem():
    print("🕸️  OPENFORGE ECOSYSTEM: Hunting for Dependencies & Physics Pairs...")
    
    if not os.path.exists(ARSENAL_FILE):
        print("❌ No arsenal found.")
        return

    with open(ARSENAL_FILE, "r") as f:
        data = json.load(f)
        current_inventory = data.get("components", [])

    # Create a quick lookup set of what we already have (case insensitive)
    # We use both exact model name AND generic terms to avoid buying "Propellers" if we have "Gemfan Props"
    existing_names = {c['model_name'].lower() for c in current_inventory}
    
    # Iterate through a COPY of the list so we don't loop over items we just added
    for part in list(current_inventory):
        
        # Skip generic placeholders or unverified items to save API tokens
        if not part.get('verified', False) and "generic" in part['model_name'].lower():
            continue

        print(f"\n🧐 Analyzing Dependencies for: {part['model_name']} ({part['category']})...")
        
        # 1. Identify what is needed
        needed_items = await agent_identify_needs(part)
        
        for item_query in needed_items:
            # 2. Check if we already have it
            # Simple fuzzy check: if "XT60" is needed, and we have an "XT60 Pigtail", skip.
            is_present = any(item_query.lower() in existing for existing in existing_names)
            
            if is_present:
                # print(f"   ✅ Already have: {item_query}")
                continue
                
            print(f"   🔍 Missing Dependency: {item_query}. Hunting...")
            
            # Determine Category for Fusion Service based on query keywords
            target_category = "Interconnect"
            if "prop" in item_query.lower(): target_category = "Propellers"
            elif "motor" in item_query.lower(): target_category = "Motors"
            elif "battery" in item_query.lower() or "lipo" in item_query.lower(): target_category = "Battery"
            
            # 3. Hunt for it using Fusion Service
            result = await fuse_component_data(
                part_type=target_category, 
                search_query=f"{item_query} price specs",
                search_limit=3,
                min_confidence=0.65 
            )
            
            if result:
                print(f"      ✨ FOUND: {result['product_name']}")
                
                # Tag it so we know which parent part triggered this find
                result['tags'] = ["ECOSYSTEM_AUTOFILL", f"REQ_FOR_{part['model_name']}"]
                
                # Get visuals
                result['visuals'] = await extract_visual_dna(result['reference_image'], target_category)
                
                # --- INSTANT SAVE BLOCK ---
                # Update memory
                current_inventory.append(result)
                existing_names.add(result['product_name'].lower())
                
                # Write to disk immediately
                data['components'] = current_inventory
                with open(ARSENAL_FILE, "w") as f:
                    json.dump(data, f, indent=2)
                print(f"      💾 Saved to Arsenal immediately.")
                # --------------------------
                
                # Rate limit politeness
                await asyncio.sleep(random.uniform(2.0, 5.0))
            else:
                print(f"      ❌ Could not source: {item_query}")

    print("\n✅ Ecosystem is stable. Dependencies filled.")

if __name__ == "__main__":
    asyncio.run(seed_ecosystem())