# FILE: tools/design_fleet.py
import asyncio
import json
import os
import random
import re
from datetime import datetime

# Import services
from app.services.ai_service import call_llm_for_json, generate_assembly_blueprint, generate_assembly_instructions
from app.services.physics_service import generate_physics_config
from app.services.digital_twin_service import generate_scene_graph
from app.prompts import MASTER_DESIGNER_INSTRUCTION

# --- CONFIG ---
ARSENAL_FILE = "drone_arsenal.json"
CATALOG_FILE = "drone_catalog.json"

def load_arsenal():
    if not os.path.exists(ARSENAL_FILE): return []
    with open(ARSENAL_FILE, "r") as f:
        data = json.load(f)
        return data.get("components", [])

def save_catalog(catalog):
    with open(CATALOG_FILE, "w") as f:
        json.dump(catalog, f, indent=2)

def extract_float(val):
    if not val: return 0.0
    try: return float(re.sub(r"[^\d\.]", "", str(val)))
    except: return 0.0

def determine_size_class(part):
    cat = part.get('category')
    name = part.get('model_name', '').lower()
    specs = part.get('specs') or part.get('engineering_specs') or {}
    
    # FRAMES
    if cat == 'Frame_Kit':
        if "7 inch" in name or "chimera" in name or "rekon" in name: return "7_INCH"
        if "5 inch" in name or "nazgul" in name: return "5_INCH"
        if "agri" in name or "vtol" in name or "shark" in name or "alligator" in name: return "HEAVY_LIFT"
        # Spec fallback
        wb = extract_float(specs.get('wheelbase_mm'))
        if wb > 400: return "HEAVY_LIFT"
        if wb > 280: return "7_INCH"
        return "5_INCH"
    
    # MOTORS
    if cat == 'Motors':
        stator = str(specs.get('stator_size', ''))
        kv = extract_float(specs.get('kv_rating'))
        
        if "4006" in stator or "5008" in stator or "8108" in stator or "420kv" in name: return "HEAVY_LIFT"
        if kv > 0 and kv < 500: return "HEAVY_LIFT" 
        if "2806" in stator or "2809" in stator: return "7_INCH"
        if "2306" in stator and kv < 1500: return "7_INCH"
        return "5_INCH"

    # PROPS
    if cat == 'Propellers':
        d = extract_float(specs.get('diameter_inches') or specs.get('diameter_inch') or specs.get('diameter_in'))
        if d == 0:
            mm = extract_float(specs.get('diameter_mm'))
            if mm > 0: d = mm / 25.4
            
        if d >= 9: return "HEAVY_LIFT"
        if d >= 6.5: return "7_INCH"
        return "5_INCH"

    return "UNIVERSAL"

async def design_fleet():
    print("🧠 OPENFORGE DESIGNER: Initializing AI Assembly Line...")
    
    inventory = load_arsenal()
    catalog = []
    
    # 1. Bucket Components
    buckets = {
        "5_INCH": {"Motors": [], "Propellers": [], "Battery": []},
        "7_INCH": {"Motors": [], "Propellers": [], "Battery": []},
        "HEAVY_LIFT": {"Motors": [], "Propellers": [], "Battery": []},
        "UNIVERSAL": {"FC_Stack": []}
    }
    
    frames = []

    print(f"   📂 Processing {len(inventory)} components...")

    for p in inventory:
        if "forum" in p['model_name'].lower(): continue
        
        cat = p['category']
        size = determine_size_class(p)
        
        if cat == 'Frame_Kit':
            frames.append((p, size))
        elif cat == 'FC_Stack':
            buckets["UNIVERSAL"]["FC_Stack"].append(p)
        elif cat == 'Battery':
            mah = extract_float(p.get('specs', {}).get('capacity_mah'))
            if mah > 800:
                buckets["5_INCH"]["Battery"].append(p)
                buckets["7_INCH"]["Battery"].append(p) 
            if mah > 2000:
                buckets["7_INCH"]["Battery"].append(p)
                buckets["HEAVY_LIFT"]["Battery"].append(p)
            if mah > 8000:
                buckets["HEAVY_LIFT"]["Battery"].append(p)
        elif size in buckets and cat in buckets[size]:
            buckets[size][cat].append(p)

    # DEBUG: Print Bucket Status
    for cls in ["5_INCH", "7_INCH", "HEAVY_LIFT"]:
        b = buckets[cls]
        print(f"   [{cls}] Motors: {len(b['Motors'])}, Props: {len(b['Propellers'])}, Bats: {len(b['Battery'])}")

    # 2. Iterate Frames
    for frame, size_class in frames:
        if size_class == "MICRO": continue
        
        candidates = {
            "motors": buckets[size_class]["Motors"],
            "props": buckets[size_class]["Propellers"],
            "batteries": buckets[size_class]["Battery"],
            "stacks": buckets["UNIVERSAL"]["FC_Stack"]
        }
        
        # Fallback for Heavy Lift Props
        if not candidates["props"] and size_class == "HEAVY_LIFT":
             candidates["props"] = buckets["7_INCH"]["Propellers"]

        if not candidates["motors"] or not candidates["props"] or not candidates["batteries"]:
            continue

        print(f"\n🎨 Designing around Anchor: {frame['model_name'][:40]}... ({size_class})")

        # Format for Prompt
        def format_list(lst):
            return "\n".join([f"- {i['model_name']} | Specs: {i.get('specs') or i.get('engineering_specs')}" for i in lst[:10]])

        prompt = MASTER_DESIGNER_INSTRUCTION.format(
            frame_name=frame['model_name'],
            frame_specs=frame.get('specs') or frame.get('engineering_specs'),
            motors=format_list(candidates["motors"]),
            props=format_list(candidates["props"]),
            batteries=format_list(candidates["batteries"]),
            stacks=format_list(candidates["stacks"])
        )

        # 3. ASK THE AI
        design_decision = await call_llm_for_json(prompt, "You are a Drone Systems Architect.")
        
        if not design_decision:
            print("   ❌ AI Failed to design.")
            continue

        print(f"   🤔 AI Reasoning: {design_decision.get('design_reasoning')[:100]}...")

        # 4. REHYDRATE BOM
        bom = [frame]
        def find_part(name, lst):
            for x in lst:
                if x['model_name'] == name: return x
            for x in lst:
                if name[:10] in x['model_name']: return x
            return lst[0] 

        try:
            bom.append(find_part(design_decision['selected_motor_model'], candidates["motors"]))
            bom.append(find_part(design_decision['selected_prop_model'], candidates["props"]))
            bom.append(find_part(design_decision['selected_battery_model'], candidates["batteries"]))
            bom.append(find_part(design_decision['selected_stack_model'], candidates["stacks"]))
        except Exception as e:
            print(f"   ❌ Error rehydrating BOM: {e}")
            continue

        # 5. VALIDATE
        # FIX: Ensure dictionary has keys for BOTH 'part_type' (AI) and 'category' (Physics)
        ai_bom = [{
            "part_type": p['category'], 
            "category": p['category'],  # REQUIRED by physics_service
            "product_name": p['model_name'], 
            "model_name": p['model_name'], # REQUIRED by physics_service (heuristic fallback)
            "engineering_specs": p.get('specs') or p.get('engineering_specs'),
            "specs": p.get('specs') or p.get('engineering_specs'), # REQUIRED by physics_service
            "price": p.get('price_est'),
            "source_url": p.get('source_url'),
            "visuals": p.get('visuals')
        } for p in bom]

        physics = generate_physics_config(ai_bom)
        twr = physics['dynamics']['twr']
        
        print(f"   ✅ Physics Verified: TWR {twr:.2f} (Weight: {physics['meta']['total_weight_g']}g)")

        # Generate Extras
        dummy_mission = {"mission_name": "AI Design", "primary_goal": "Industrial"}
        scene_graph = generate_scene_graph(dummy_mission, ai_bom)
        
        # 6. SAVE
        sku = {
            "sku_id": f"OF-AI-{random.randint(1000,9999)}",
            "anchor_frame": frame['model_name'],
            "class": size_class,
            "ai_reasoning": design_decision.get('design_reasoning'),
            "performance": {
                "twr": twr,
                "flight_time": physics['meta']['est_flight_time_min'],
                "total_weight": physics['meta']['total_weight_g']
            },
            "bom": ai_bom,
            "technical_data": {
                "physics_config": physics,
                "scene_graph": scene_graph
            }
        }
        
        catalog.append(sku)
        save_catalog(catalog)

if __name__ == "__main__":
    asyncio.run(design_fleet())