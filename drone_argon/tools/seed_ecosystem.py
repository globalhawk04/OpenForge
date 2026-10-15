# --- START OF FILE tools/seed_ecosystem.py ---
import asyncio
import json
import os
import random
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR) if os.path.basename(CURRENT_DIR) == "tools" else CURRENT_DIR
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.normalizer import resolve_data_path, normalize_component
from app.services.ai_service import call_llm_for_json
from app.services.fusion_service import fuse_component_data
from app.services.texture_service import extract_visual_dna

ARSENAL_FILE = resolve_data_path("drone_arsenal.json")

ECOSYSTEM_PROMPT = """
You are a Drone Logistics & Integration Expert.
I have this component in my inventory: "{model_name}" ({category}).

Identify up to 2 ESSENTIAL physical accessories required to integrate this specific part into a custom drone build.
Focus on **Interconnects** (Cables, Pigtails), **Mounts**, or **BECs**.
Return JSON: {{"accessories": ["Specific Accessory 1", "Specific Accessory 2"]}}
"""

PROPULSION_PROMPT = """
You are a Drone Propulsion Engineer.
I have this component: "{model_name}" ({category}) with specs: {specs}.

Identify the SINGLE BEST complementary component required to make this part fly efficiently:
- If Motor: Specific Propeller Model matching its stator size and KV (e.g., "Gemfan 51433 5 inch Propeller", "HQProp 7X4X3 7 inch Propeller").
- If Propeller: Compatible Brushless Motor Size & KV (e.g., "2207 1850KV Brushless Motor", "2809 1250KV Motor").
- If Frame_Kit: Recommended LiPo Battery matching its size class (e.g., "6S 1300mAh LiPo Battery XT60", "6S 3300mAh LiPo Battery").

Return JSON: {{"matches": ["Specific Complementary Component Name"]}}
"""


async def agent_identify_needs(part: dict) -> list[str]:
    category = part.get("category", "")
    model_name = part.get("model_name", "")
    specs = json.dumps(part.get("specs") or {})

    if category in ["Motors", "Propellers", "Frame_Kit"]:
        prompt = PROPULSION_PROMPT.format(model_name=model_name, category=category, specs=specs)
        system_instruction = "You are a Propulsion Engineer."
    elif category in ["FC_Stack", "Companion_Computer", "Camera_VTX_Kit", "Lidar_Module", "GPS_Module"]:
        prompt = ECOSYSTEM_PROMPT.format(model_name=model_name, category=category)
        system_instruction = "You are a Logistics Expert."
    else:
        return []

    needs = await call_llm_for_json(prompt, system_instruction)
    if isinstance(needs, list):
        return needs
    if isinstance(needs, dict):
        for key in ["accessories", "matches", "components", "parts"]:
            if isinstance(needs.get(key), list):
                return needs[key]
    return []


async def seed_ecosystem():
    print(f"🕸️  OPENFORGE ECOSYSTEM: Hunting for Dependencies in {ARSENAL_FILE}...")
    if not os.path.exists(ARSENAL_FILE):
        print(f"❌ No arsenal found at {ARSENAL_FILE}.")
        return

    with open(ARSENAL_FILE, "r") as f:
        data = json.load(f)
        current_inventory = [normalize_component(c) for c in data.get("components", []) if isinstance(c, dict)]

    existing_names = {c["model_name"].lower() for c in current_inventory}

    for part in list(current_inventory):
        if "generic" in part["model_name"].lower():
            continue

        print(f"\n🧐 Analyzing Dependencies for: {part['model_name'][:45]} ({part['category']})...")
        needed_items = await agent_identify_needs(part)

        for item_query in needed_items:
            if any(item_query.lower() in existing for existing in existing_names):
                continue

            print(f"   🔍 Missing Dependency: {item_query}. Hunting...")
            q_low = item_query.lower()
            target_category = "Interconnect"
            if "prop" in q_low:
                target_category = "Propellers"
            elif "motor" in q_low:
                target_category = "Motors"
            elif "battery" in q_low or "lipo" in q_low:
                target_category = "Battery"

            result = await fuse_component_data(
                part_type=target_category,
                search_query=f"{item_query} buy price",
                search_limit=4,
                min_confidence=0.65,
            )

            if result:
                visuals = await extract_visual_dna(result.get("reference_image"), target_category)
                entry = normalize_component({
                    "type": "component",
                    "category": target_category,
                    "part_type": target_category,
                    "model_name": result["product_name"],
                    "product_name": result["product_name"],
                    "price_est": result["price"],
                    "price": result["price"],
                    "specs": result["engineering_specs"],
                    "engineering_specs": result["engineering_specs"],
                    "visuals": visuals,
                    "image_url": result.get("reference_image"),
                    "source_url": result["source_url"],
                    "verified": True,
                    "tags": ["ECOSYSTEM_AUTOFILL", f"REQ_FOR_{part['model_name']}"],
                })

                current_inventory.append(entry)
                existing_names.add(entry["model_name"].lower())
                data["components"] = current_inventory
                with open(ARSENAL_FILE, "w") as f:
                    json.dump(data, f, indent=2)
                print(f"      💾 Saved Normalized Part: {entry['model_name']}")
                await asyncio.sleep(random.uniform(2.0, 4.0))
            else:
                print(f"      ❌ Could not source verified part for: {item_query}")

    print("\n✅ Ecosystem Dependencies Filled.")


if __name__ == "__main__":
    asyncio.run(seed_ecosystem())
# --- END OF FILE tools/seed_ecosystem.py ---