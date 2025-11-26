# FILE: tools/fabricate_catalog.py
import asyncio
import json
import os
import random
from datetime import datetime

# --- IMPORT CORE SERVICES ---
from app.services.ai_service import (
    call_llm_for_json, 
    generate_assembly_blueprint, 
    generate_assembly_instructions
)
from app.services.physics_service import generate_physics_config
from app.services.digital_twin_service import generate_scene_graph
from app.services.interconnect_service import analyze_interconnects

# --- CONFIG ---
ARSENAL_FILE = "drone_arsenal.json"
CATALOG_FILE = "drone_catalog.json"

# --- THE MARKETER PROMPT (UPDATED) ---
MARKETER_PROMPT = """
You are a Product Manager for a Drone Manufacturer.
I will give you the technical specifications of a verified drone build, including its software capabilities.

**INPUT:**
{specs}

**YOUR TASK:**
1.  **Name it:** Create a cool, market-ready model name (e.g., "Valkyrie LR-7", "Mudskipper 3").
2.  **Categorize it:** Define the primary use case (Cinematic, Freestyle, Long Range, Industrial).
3.  **Pitch it:** Write a compelling one-sentence value proposition.
4.  **Target Audience:** Who buys this?

**OUTPUT SCHEMA (JSON):**
{{
  "model_name": "string",
  "category": "string",
  "tagline": "string",
  "target_audience": "string"
}}
"""

def load_arsenal():
    if os.path.exists(ARSENAL_FILE):
        with open(ARSENAL_FILE, "r") as f:
            data = json.load(f)
            return data.get("components", [])
    return []

def load_catalog():
    if os.path.exists(CATALOG_FILE):
        try:
            with open(CATALOG_FILE, "r") as f:
                return json.load(f)
        except: pass
    return []

def save_sku_to_catalog(sku):
    catalog = load_catalog()
    
    # Prevent duplicate SKUs based on BOM Model Names
    # We filter out 'Cable' and 'Connector' from the signature so we don't duplicate based on wires
    core_bom_names = sorted([
        item['model'] for item in sku['bom'] 
        if item['category'] not in ['Cable', 'Connector', 'Wire']
    ])
    current_sig = "|".join(core_bom_names)
    
    for existing in catalog:
        existing_core = sorted([
            item['model'] for item in existing['bom'] 
            if item['category'] not in ['Cable', 'Connector', 'Wire']
        ])
        existing_sig = "|".join(existing_core)
        
        if existing_sig == current_sig:
            print(f"   ⚠️  Skipping duplicate build: {sku['marketing']['model_name']}")
            return

    catalog.append(sku)
    with open(CATALOG_FILE, "w") as f:
        json.dump(catalog, f, indent=2)
    print(f"   💾 CATALOGED: {sku['marketing']['model_name']} (ID: {sku['sku_id']})")

def format_part_for_ai(part):
    """Adapts Arsenal JSON format to the AI/Service format."""
    return {
        "part_type": part.get('category') or part.get('part_type'),
        "product_name": part.get('model_name') or part.get('product_name'),
        "engineering_specs": part.get('specs', {}),
        "visuals": part.get('visuals', {}), # Crucial for Digital Twin/Interconnects
        "reference_image": part.get('image_url'),
        "price": part.get('price_est'),
        "source_url": part.get('source_url')
    }

def determine_software_capabilities(bom):
    """Infers software capabilities based on hardware specs."""
    caps = {
        "firmware": [],
        "capabilities": []
    }
    
    # Check Flight Controller
    fc = next((p for p in bom if p['part_type'] == 'FC_Stack'), None)
    if fc:
        specs = fc['engineering_specs']
        # Heuristics based on MCU or tags
        if "f7" in str(specs).lower() or "h7" in str(specs).lower():
            caps['firmware'] = ["Betaflight 4.4+", "INAV 6.0+", "ArduPilot (Check Target)"]
        elif "f405" in str(specs).lower():
            caps['firmware'] = ["Betaflight", "INAV"]
        else:
            caps['firmware'] = ["Betaflight"]

    # Check Companion Computer
    comp = next((p for p in bom if p['part_type'] == 'Companion_Computer'), None)
    if comp:
        caps['capabilities'].append("Onboard AI / Edge Computing")
        caps['capabilities'].append("ROS 2 Humble Compatible")
        
    # Check GPS
    gps = next((p for p in bom if "GPS" in p['product_name']), None)
    if gps:
        caps['capabilities'].append("Autonomous Waypoints")
        caps['capabilities'].append("Return to Home")

    return caps

async def fabricate_products():
    print("🏭 OPENFORGE FABRICATOR: Initializing Production Line...")
    
    inventory = load_arsenal()
    
    # Segregate Inventory
    frames = [p for p in inventory if p['category'] == 'Frame_Kit']
    motors = [p for p in inventory if p['category'] == 'Motors']
    props = [p for p in inventory if p['category'] == 'Propellers']
    stacks = [p for p in inventory if p['category'] == 'FC_Stack']
    batteries = [p for p in inventory if p['category'] == 'Battery']
    cameras = [p for p in inventory if p['category'] == 'Camera_VTX_Kit']

    print(f"   Inventory: {len(frames)} Frames, {len(motors)} Motors, {len(stacks)} Stacks.")

    sku_counter = len(load_catalog()) + 1

    # --- THE COMBINATORIAL LOOP ---
    for frame in frames:
        # 1. Frame Size Logic (Limit permutations)
        frame_name = frame['model_name'].lower()
        target_prop_size = 5
        if "7 inch" in frame_name or "7-inch" in frame_name: target_prop_size = 7
        elif "3 inch" in frame_name or "3-inch" in frame_name: target_prop_size = 3
        elif "10 inch" in frame_name: target_prop_size = 10

        compatible_props = [p for p in props if str(target_prop_size) in p['model_name'] or str(target_prop_size) in str(p.get('specs'))]
        if not compatible_props: continue

        for prop in compatible_props:
            for motor in motors:
                for stack in stacks:
                    for bat in batteries:
                        
                        # --- A. BASE BOM CONSTRUCTION ---
                        raw_bom = [frame, motor, prop, stack, bat]
                        if cameras: raw_bom.append(cameras[0]) 

                        # Format for Services
                        ai_bom = [format_part_for_ai(p) for p in raw_bom]

                        print(f"\n🔧 Evaluating: {frame['model_name']} + {motor['model_name']}...")

                        # --- B. DIGITAL TWIN & INTERCONNECTS (The "Electrician" Check) ---
                        # We need the scene graph to check cable lengths
                        dummy_mission = {"mission_name": "Fabrication Test"} 
                        scene_graph = generate_scene_graph(dummy_mission, ai_bom)
                        
                        # Analyze connectivity
                        cabling_extras = analyze_interconnects(ai_bom, scene_graph)
                        
                        # Add cables to BOM
                        if cabling_extras:
                            for extra in cabling_extras:
                                formatted_extra = {
                                    "part_type": extra['part_type'],
                                    "product_name": extra['product_name'],
                                    "price": extra['price'],
                                    "source_url": extra['source_url'],
                                    "engineering_specs": {},
                                    "visuals": None,
                                    "reference_image": None
                                }
                                ai_bom.append(formatted_extra)
                            print(f"   ⚡ Added {len(cabling_extras)} interconnect items.")

                        # --- C. MASTER BUILDER (Fitment Validation) ---
                        blueprint = await generate_assembly_blueprint(ai_bom)
                        if not blueprint.get("is_buildable"):
                            print(f"   ❌ REJECTED: {blueprint.get('incompatibility_reason')}")
                            continue 

                        # --- D. PHYSICS SIMULATION (Flight Validation) ---
                        phys_bom = [{"category": p['part_type'], "specs": p['engineering_specs'], "model_name": p['product_name']} for p in ai_bom]
                        physics = generate_physics_config(phys_bom)
                        
                        twr = physics['dynamics']['twr']
                        flight_time = physics['meta']['est_flight_time_min']

                        if twr < 1.3: 
                            print(f"   ❌ REJECTED: Underpowered (TWR {twr})")
                            continue
                        if flight_time < 3.0:
                            print(f"   ❌ REJECTED: Flight time too low ({flight_time}m)")
                            continue

                        # --- E. SOFTWARE & FIRMWARE ANALYSIS ---
                        software_stack = determine_software_capabilities(ai_bom)

                        # --- F. DOCUMENTATION ---
                        print("   ✅ Verified. Generating Docs...")
                        instructions = await generate_assembly_instructions(blueprint)

                        # --- G. MARKETING ---
                        tech_summary = f"""
                        Frame: {frame['model_name']}
                        Motor: {motor['model_name']}
                        Performance: {twr} TWR, {flight_time} min flight time.
                        Firmware Support: {', '.join(software_stack['firmware'])}
                        Capabilities: {', '.join(software_stack['capabilities'])}
                        """
                        marketing = await call_llm_for_json(
                            MARKETER_PROMPT.format(specs=tech_summary),
                            "You are a Drone Product Manager."
                        )
                        if not marketing: marketing = {"model_name": f"Gen-{sku_counter}", "tagline": "Custom"}

                        # --- H. SAVE SKU ---
                        sku_record = {
                            "sku_id": f"OF-{sku_counter:06d}",
                            "created_at": datetime.now().isoformat(),
                            "marketing": marketing,
                            "software_stack": software_stack, # <--- NEW FIELD
                            "performance_metrics": {
                                "twr": twr,
                                "flight_time_minutes": flight_time,
                                "total_weight_g": physics['meta']['total_weight_g']
                            },
                            "bom": [
                                {
                                    "category": p['part_type'], 
                                    "model": p['product_name'], 
                                    "price": p['price'], 
                                    "link": p['source_url']
                                }
                                for p in ai_bom
                            ],
                            "technical_data": {
                                "blueprint": blueprint,
                                "physics_config": physics,
                                "assembly_guide": instructions,
                                "scene_graph": scene_graph # Save scene for instant rendering
                            }
                        }

                        save_sku_to_catalog(sku_record)
                        sku_counter += 1
                        
                        print("   💤 Cooling down...")
                        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(fabricate_products())