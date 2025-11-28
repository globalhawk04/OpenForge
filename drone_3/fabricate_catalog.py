# FILE: tools/fabricate_catalog.py
import asyncio
import json
import os
import random
import re
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
from app.services.compatibility_service import CompatibilityService

# --- CONFIG ---
ARSENAL_FILE = "drone_arsenal.json"
CATALOG_FILE = "drone_catalog.json"

MARKETER_PROMPT = """
You are a Product Manager. Name this verified drone build.
**SPECS:**
{specs}

**OUTPUT (JSON):**
{{
  "model_name": "string (e.g. 'Titan X7 Long Range')",
  "category": "string (e.g. 'Industrial Inspection')",
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
            with open(CATALOG_FILE, "r") as f: return json.load(f)
        except: pass
    return []

def save_sku_to_catalog(sku):
    catalog = load_catalog()
    if any(p['marketing']['model_name'] == sku['marketing']['model_name'] for p in catalog):
        print(f"   ⚠️  Skipping duplicate name: {sku['marketing']['model_name']}")
        return
    catalog.append(sku)
    with open(CATALOG_FILE, "w") as f:
        json.dump(catalog, f, indent=2)
    print(f"   💾 CATALOGED: {sku['marketing']['model_name']}")

def extract_float(val):
    if not val: return 0.0
    try:
        # Remove common non-numeric chars but keep decimal
        clean = re.sub(r"[^\d\.]", "", str(val))
        return float(clean)
    except: return 0.0

# --- ENGINEERING LOGIC ---

def determine_size_class(part):
    """
    Categorizes parts into compatibility buckets: 
    ['MICRO', '5_INCH', '7_INCH', 'HEAVY_LIFT', 'UNKNOWN']
    """
    cat = part.get('category')
    name = part.get('model_name', '').lower()
    specs = part.get('specs') or part.get('engineering_specs') or {}
    
    # --- FRAMES ---
    if cat == 'Frame_Kit':
        if "7 inch" in name or "chimera" in name or "rekon" in name: return "7_INCH"
        if "5 inch" in name or "nazgul" in name or "source one" in name: return "5_INCH"
        if "agri" in name or "vtol" in name or "class" in name: return "HEAVY_LIFT"
        
        wb = extract_float(specs.get('wheelbase_mm'))
        if wb > 400: return "HEAVY_LIFT"
        if wb > 280: return "7_INCH"
        if wb > 180: return "5_INCH"
        return "MICRO"

    # --- MOTORS ---
    if cat == 'Motors':
        stator = str(specs.get('stator_size', ''))
        kv = extract_float(specs.get('kv_rating') or specs.get('kv'))
        
        if "4006" in stator or "5008" in stator or "8108" in stator: return "HEAVY_LIFT"
        if "2806" in stator or "2809" in stator or "2810" in stator: return "7_INCH"
        if "2306" in stator or "2207" in stator: 
            if kv < 1500: return "7_INCH"
            return "5_INCH"
        
        # Fallback if no stator size found: use Price/Name
        if "cinelifter" in name: return "7_INCH"
        if "antigravity" in name: return "HEAVY_LIFT"
        return "5_INCH" # Default

    # --- PROPS ---
    if cat == 'Propellers':
        # Check ALL possible keys
        d = extract_float(specs.get('diameter_inches') or specs.get('diameter_inch') or specs.get('diameter_in'))
        if d == 0:
            mm = extract_float(specs.get('diameter_mm'))
            d = mm / 25.4
        
        if d >= 10: return "HEAVY_LIFT"
        if d >= 6.5: return "7_INCH"
        if d >= 4.5: return "5_INCH"
        if d > 0: return "MICRO"
        
        # Text fallback
        if "1555" in name or "18x6" in name: return "HEAVY_LIFT"
        if "7037" in name: return "7_INCH"

    # --- BATTERIES ---
    if cat == 'Battery':
        mah = extract_float(specs.get('capacity_mah'))
        cells = extract_float(specs.get('cell_count_s') or specs.get('cells'))
        
        # Heavy lifts usually high capacity OR high voltage (12S+)
        if mah > 8000 or cells > 8: return "HEAVY_LIFT"
        if mah > 2500: return "7_INCH"
        if mah > 1000: return "5_INCH"
        return "MICRO"

    return "UNIVERSAL" 

def format_part_for_ai(part):
    return {
        "part_type": part.get('category'),
        "product_name": part.get('model_name'),
        "engineering_specs": part.get('specs') or part.get('engineering_specs') or {},
        "visuals": part.get('visuals', {}),
        "reference_image": part.get('image_url'),
        "price": part.get('price_est'),
        "source_url": part.get('source_url')
    }

async def fabricate_products():
    print("🏭 OPENFORGE ENGINEERING: Initializing Build Sequence...")
    
    raw_inventory = load_arsenal()
    inventory = []
    
    # 1. CLEAN
    print("   🧹 Cleaning Inventory data...")
    for p in raw_inventory:
        name = p['model_name'].lower()
        price = extract_float(p.get('price_est'))
        cat = p.get('category')
        
        if "forum" in name or "manual" in name or "support" in name: continue
        if cat == 'Frame_Kit' and price < 15: continue 
        if cat == 'Motors' and price < 10: continue
        
        inventory.append(p)

    # 2. CLASSIFY & BUCKET
    buckets = {
        "5_INCH": {"Frame_Kit": [], "Motors": [], "Propellers": [], "Battery": []},
        "7_INCH": {"Frame_Kit": [], "Motors": [], "Propellers": [], "Battery": []},
        "HEAVY_LIFT": {"Frame_Kit": [], "Motors": [], "Propellers": [], "Battery": []},
        "MICRO": {"Frame_Kit": [], "Motors": [], "Propellers": [], "Battery": []},
        "UNIVERSAL": {"FC_Stack": [], "GPS_Module": [], "Camera_Payload": [], "Companion_Computer": [], "Camera_VTX_Kit": []}
    }

    for part in inventory:
        size_class = determine_size_class(part)
        cat = part['category']
        if size_class in buckets and cat in buckets[size_class]:
            buckets[size_class][cat].append(part)
        elif cat in buckets["UNIVERSAL"]:
            buckets["UNIVERSAL"][cat].append(part)

    # 3. PRINT STATS (Debugging)
    for k, v in buckets.items():
        if k == "UNIVERSAL": continue
        counts = f"F:{len(v['Frame_Kit'])} M:{len(v['Motors'])} P:{len(v['Propellers'])} B:{len(v['Battery'])}"
        print(f"   [{k}] Inventory: {counts}")

    compatibility_engine = CompatibilityService()
    sku_counter = len(load_catalog()) + 1

    # 4. BUILD LOOP
    for size_class in ["7_INCH", "HEAVY_LIFT", "5_INCH"]:
        frames = buckets[size_class]["Frame_Kit"]
        motors = buckets[size_class]["Motors"]
        props = buckets[size_class]["Propellers"]
        batteries = buckets[size_class]["Battery"]
        
        # --- FALLBACK LOGIC ---
        # If 7-inch lacks batteries, borrow from 5-inch (parallels)
        if not batteries and size_class == "7_INCH":
            batteries = buckets["5_INCH"]["Battery"]
            print("      ℹ️  Using 5_INCH batteries for 7_INCH build.")
            
        # If Heavy Lift lacks props, check if any prop is > 10"
        if not props and size_class == "HEAVY_LIFT":
             # Last ditch check for large props that might have been misclassified
             pass

        if not frames or not motors or not props or not batteries:
            print(f"   ⚠️  Skipping Class {size_class}: Missing core components.")
            continue

        print(f"\n🏗️  Building {size_class} Drones...")

        for frame in frames:
            # Combinatorial limit
            for motor in motors[:2]:
                for prop in props[:2]:
                    # Always need a stack
                    stacks = buckets["UNIVERSAL"]["FC_Stack"]
                    if not stacks: break
                    
                    for stack in stacks[:2]:
                        for bat in batteries[:2]:
                            
                            raw_bom = [frame, motor, prop, stack, bat]
                            
                            # Add Peripherals
                            if size_class in ["7_INCH", "HEAVY_LIFT"]:
                                if buckets["UNIVERSAL"]["GPS_Module"]:
                                    raw_bom.append(random.choice(buckets["UNIVERSAL"]["GPS_Module"]))
                                if buckets["UNIVERSAL"]["Companion_Computer"]:
                                    raw_bom.append(random.choice(buckets["UNIVERSAL"]["Companion_Computer"]))
                                if buckets["UNIVERSAL"]["Camera_Payload"]:
                                    raw_bom.append(random.choice(buckets["UNIVERSAL"]["Camera_Payload"]))
                            elif buckets["UNIVERSAL"]["Camera_VTX_Kit"]:
                                raw_bom.append(random.choice(buckets["UNIVERSAL"]["Camera_VTX_Kit"]))

                            ai_bom = [format_part_for_ai(p) for p in raw_bom]
                            
                            print(f"   🔧 Evaluating: {frame['model_name'][:25]}... + {motor['model_name'][:20]}...")

                            # Gate 1: Compatibility
                            validation = compatibility_engine.validate_build(ai_bom)
                            if not validation['valid']:
                                # print(f"      ❌ Rule Rejection: {validation['errors'][0]}")
                                continue 

                            # Gate 2: AI Blueprint
                            print("      🧠 AI Engineer checking physical fitment...")
                            blueprint = await generate_assembly_blueprint(ai_bom)
                            if not blueprint.get("is_buildable"):
                                print(f"      ❌ AI Rejection: {blueprint.get('incompatibility_reason')}")
                                continue

                            # Gate 3: Digital Twin
                            dummy_mission = {"mission_name": "Fabrication", "primary_goal": "Industrial"}
                            scene_graph = generate_scene_graph(dummy_mission, ai_bom)
                            extras = analyze_interconnects(ai_bom, scene_graph)
                            for e in extras:
                                ai_bom.append({
                                    "part_type": e['part_type'],
                                    "product_name": e['product_name'],
                                    "price": e['price'],
                                    "source_url": e['source_url'],
                                    "engineering_specs": {}, "visuals": None, "reference_image": None
                                })
                            
                            # Gate 4: Physics
                            phys_bom = [{"category": p['part_type'], "specs": p['engineering_specs'], "model_name": p['product_name']} for p in ai_bom]
                            physics = generate_physics_config(phys_bom)
                            twr = physics['dynamics']['twr']
                            
                            if twr < 1.1:
                                print(f"      ❌ Physics Rejection: Underpowered (TWR {twr:.2f})")
                                continue

                            # SUCCESS
                            print(f"      ✅ DESIGN VALIDATED! TWR: {twr:.2f}")
                            
                            instructions = await generate_assembly_instructions(blueprint)
                            
                            tech_summary = f"""
                            Class: {size_class}
                            Frame: {frame['model_name']}
                            Motor: {motor['model_name']}
                            TWR: {twr:.2f}
                            """
                            marketing = await call_llm_for_json(
                                MARKETER_PROMPT.format(specs=tech_summary),
                                "You are a Drone Product Manager."
                            )
                            if not marketing: marketing = {"model_name": f"OpenForge-{sku_counter}"}

                            sku_record = {
                                "sku_id": f"OF-{sku_counter:06d}",
                                "created_at": datetime.now().isoformat(),
                                "class": size_class,
                                "marketing": marketing,
                                "performance_metrics": {
                                    "twr": twr,
                                    "flight_time_minutes": physics['meta']['est_flight_time_min'],
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
                                    "scene_graph": scene_graph 
                                }
                            }

                            save_sku_to_catalog(sku_record)
                            sku_counter += 1
                            break # One success per frame is enough for demo
                    else: continue
                    break
                else: continue
                break

if __name__ == "__main__":
    asyncio.run(fabricate_products())