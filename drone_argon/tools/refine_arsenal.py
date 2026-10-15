# --- START OF FILE tools/seed.py ---
import asyncio
import json
import os
import random
import sys
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR) if os.path.basename(CURRENT_DIR) == "tools" else CURRENT_DIR
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.normalizer import resolve_data_path, normalize_component
from app.services.ai_service import call_llm_for_json
from app.services.fusion_service import fuse_component_data
from app.services.texture_service import extract_visual_dna
from app.prompts import (
    RANCHER_PERSONA_INSTRUCTION,
    REQUIREMENTS_SYSTEM_INSTRUCTION,
    ARSENAL_ENGINEER_INSTRUCTION,
    ARSENAL_SOURCER_INSTRUCTION,
    ARSENAL_SCOUT_INSTRUCTION,
)

ARSENAL_FILE = resolve_data_path("drone_arsenal.json")
AUDIT_LOG_FILE = resolve_data_path("arsenal_audit_log.json")


async def agent_rancher_needs():
    print("\n🤠 AGENT 1: Defining Autonomous Fleet Missions...")
    result = await call_llm_for_json(
        "Define the specialized robotic fleet for the ranch.",
        RANCHER_PERSONA_INSTRUCTION,
    )
    log_audit_event("RANCHER_DECISION", {"prompt": "Define fleet...", "result": result})
    if isinstance(result, dict) and "missions" in result:
        return result["missions"]
    return result if isinstance(result, list) else []


async def agent_architect_constraints(mission_profile):
    mission_name = mission_profile.get("mission_name", "Unknown")
    print(f"\n📐 AGENT 1.5 (Architect): Deriving Physics Constraints for {mission_name}...")
    context = json.dumps(mission_profile)
    result = await call_llm_for_json(f"USER REQUEST: {context}", REQUIREMENTS_SYSTEM_INSTRUCTION)
    log_audit_event("ARCHITECT_CONSTRAINTS", {"mission": mission_name, "derived_constraints": result})
    return result


async def agent_engineer_parts(mission_profile, architect_plan):
    mission_name = mission_profile.get("mission_name", "Unknown")
    print(f"\n👷 AGENT 2 (Engineer): Selecting components for {mission_name}...")
    context = {
        "mission": mission_profile,
        "constraints": architect_plan.get("technical_constraints", {}),
        "topology": architect_plan.get("topology", {}),
    }
    context_str = json.dumps(context)
    result = await call_llm_for_json(f"ENGINEERING CONTEXT: {context_str}", ARSENAL_ENGINEER_INSTRUCTION)
    log_audit_event("ENGINEER_DESIGN", {"mission": mission_name, "proposed_parts": result})
    return result


async def agent_market_scout(mission_profile):
    mission_name = mission_profile.get("mission_name", "Unknown")
    print(f"\n🕵️ AGENT 2.5 (Scout): Searching industrial solutions for {mission_name}...")
    context = json.dumps(mission_profile)
    result = await call_llm_for_json(f"MISSION PROFILE: {context}", ARSENAL_SCOUT_INSTRUCTION)
    log_audit_event("SCOUT_SEARCH", {"mission": mission_name, "found_drones": result})
    return result


async def agent_sourcer_queries(parts_structure, mission_name):
    print(f"\n🔎 AGENT 3 (Sourcer): Generating queries for {mission_name}...")
    target_models = []
    for category, items in parts_structure.items():
        if isinstance(items, list):
            for model in items:
                target_models.append(f"{category}: {model}")
    context_str = "\n".join(target_models)
    result = await call_llm_for_json(f"TARGET MODELS: {context_str}", ARSENAL_SOURCER_INSTRUCTION)
    queries = result.get("queries", []) if result else []
    log_audit_event("SOURCER_QUERIES", {"mission": mission_name, "generated_queries": queries})
    return queries


def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            pass
    if "audit" in filepath:
        return {"events": []}
    return {"components": []}


def log_audit_event(event_type, data):
    os.makedirs(os.path.dirname(os.path.abspath(AUDIT_LOG_FILE)), exist_ok=True)
    log_db = load_json(AUDIT_LOG_FILE)
    log_db.setdefault("events", []).append({
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "data": data,
    })
    with open(AUDIT_LOG_FILE, "w") as f:
        json.dump(log_db, f, indent=2)


def save_to_arsenal(new_item: dict, tags: list[str], item_type: str = "component"):
    os.makedirs(os.path.dirname(os.path.abspath(ARSENAL_FILE)), exist_ok=True)
    db = load_json(ARSENAL_FILE)

    cat = new_item.get("part_type", "").lower()
    name = new_item.get("product_name", "").lower()

    if "computer" in cat or "jetson" in name or "raspberry" in name:
        tags.append("AI_CAPABLE")
    if "sensor" in cat or "lidar" in name or "depth" in name:
        tags.append("OBSTACLE_AVOIDANCE")
    if "gps" in cat:
        tags.append("AUTONOMOUS_NAVIGATION")

    for existing in db.get("components", []):
        existing_name = existing.get("model_name", "").lower()
        if existing_name == name:
            print(f"      ⚠️  Known Item: {new_item['product_name']}. Updating specs & tags.")
            existing.setdefault("tags", [])
            for t in tags:
                if t not in existing["tags"]:
                    existing["tags"].append(t)
            if new_item.get("engineering_specs"):
                existing["specs"] = new_item["engineering_specs"]
                existing["engineering_specs"] = new_item["engineering_specs"]
            if new_item.get("visuals"):
                existing["visuals"] = new_item["visuals"]
            with open(ARSENAL_FILE, "w") as f:
                json.dump(db, f, indent=2)
            return

    entry = normalize_component({
        "type": item_type,
        "category": new_item["part_type"],
        "part_type": new_item["part_type"],
        "model_name": new_item["product_name"],
        "product_name": new_item["product_name"],
        "price_est": new_item["price"],
        "price": new_item["price"],
        "specs": new_item["engineering_specs"],
        "engineering_specs": new_item["engineering_specs"],
        "visuals": new_item.get("visuals"),
        "image_url": new_item.get("reference_image"),
        "source_url": new_item["source_url"],
        "verified": True,
        "tags": list(set(tags)),
    })

    db.setdefault("components", []).append(entry)
    with open(ARSENAL_FILE, "w") as f:
        json.dump(db, f, indent=2)
    print(f"      💾 Saved to {ARSENAL_FILE}: {entry['model_name']}")


async def run_seeder():
    print("🏭 OPENFORGE ARSENAL SEEDER V3 (Forensic Fitment Gate Enabled)")
    print("==============================================================")
    missions = await agent_rancher_needs()
    if not missions:
        print("❌ Rancher failed.")
        return

    for mission in missions:
        m_name = mission.get("mission_name", "General")
        print(f"\n🚀 MISSION CAMPAIGN: {m_name}")
        architect_plan = await agent_architect_constraints(mission)
        if not architect_plan:
            continue

        build_parts = await agent_engineer_parts(mission, architect_plan)
        buy_drones = await agent_market_scout(mission)

        full_target_list = {}
        if build_parts:
            full_target_list.update(build_parts)
        if buy_drones:
            full_target_list.update(buy_drones)
        if not full_target_list:
            continue

        query_list = await agent_sourcer_queries(full_target_list, m_name)
        if not query_list:
            continue

        for i, item in enumerate(query_list):
            category = item["part_type"]
            model = item["model_name"]
            search_query = item["search_query"]
            item_type = "complete_drone" if category == "Complete_Drone" else "component"

            print(f"\n   ⚡ Processing [{i+1}/{len(query_list)}]: {model}...")
            await asyncio.sleep(random.uniform(2.5, 5.5))

            result = await fuse_component_data(
                part_type=category,
                search_query=search_query,
                search_limit=5,
                min_confidence=0.70,
            )

            if result and result.get("engineering_specs") and result.get("price"):
                visual_dna = await extract_visual_dna(result.get("reference_image"), category)
                result["visuals"] = visual_dna
                save_to_arsenal(
                    result,
                    tags=[m_name, architect_plan.get("topology", {}).get("class", "General")],
                    item_type=item_type,
                )
                log_audit_event("VERIFICATION_SUCCESS", {
                    "model": model,
                    "url": result["source_url"],
                    "specs_found": result["engineering_specs"],
                })
            else:
                print(f"      ❌ Rejected {model} (Failed e-commerce/fitment validation gate)")

    print("\n✅ Seeding Complete.")


if __name__ == "__main__":
    asyncio.run(run_seeder())
# --- END OF FILE tools/seed.py ---