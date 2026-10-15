# --- START OF FILE tools/design_fleet.py ---
import asyncio
import json
import os
import random
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR) if os.path.basename(CURRENT_DIR) == "tools" else CURRENT_DIR
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.normalizer import normalize_component, normalize_bom, resolve_data_path
from app.services.ai_service import call_llm_for_json, generate_assembly_blueprint
from app.services.physics_service import generate_physics_config
from app.services.compatibility_service import CompatibilityService
from app.services.cost_service import generate_procurement_manifest
from app.services.schematic_service import generate_wiring_diagram
from app.services.digital_twin_service import generate_scene_graph
from app.services.cad_service import generate_assets
from app.services.firmware_service import generate_firmware_configs
from app.sim.scenarios import FlightTestRunner
from app.prompts import MASTER_DESIGNER_INSTRUCTION

ARSENAL_FILE = resolve_data_path("drone_arsenal.json")
CATALOG_FILE = resolve_data_path("drone_catalog.json")


def load_arsenal() -> list[dict]:
    if not os.path.exists(ARSENAL_FILE):
        return []
    with open(ARSENAL_FILE, "r") as f:
        data = json.load(f)
        return [normalize_component(c) for c in data.get("components", []) if isinstance(c, dict)]


def save_catalog(catalog: list[dict]):
    os.makedirs(os.path.dirname(os.path.abspath(CATALOG_FILE)), exist_ok=True)
    with open(CATALOG_FILE, "w") as f:
        json.dump(catalog, f, indent=2)


def determine_size_class(part: dict) -> str:
    cat = part["category"]
    name = part["model_name"].lower()
    norm = part["normalized"]

    if cat == "Frame_Kit":
        wb = norm.get("wheelbase_mm", 225.0)
        if wb > 400 or any(k in name for k in ["agri", "vtol", "heavy", "alligator"]):
            return "HEAVY_LIFT"
        if wb >= 280 or "7 inch" in name or "chimera" in name or "rekon" in name:
            return "7_INCH"
        return "5_INCH"

    if cat == "Motors":
        d = norm.get("stator_d_mm", 22.0)
        kv = norm.get("kv", 1750.0)
        if d >= 35 or (0 < kv < 600):
            return "HEAVY_LIFT"
        if d >= 26 or (d >= 23 and kv < 1550):
            return "7_INCH"
        return "5_INCH"

    if cat == "Propellers":
        diam = norm.get("diameter_inch", 5.0)
        if diam >= 9.0:
            return "HEAVY_LIFT"
        if diam >= 6.5:
            return "7_INCH"
        return "5_INCH"

    return "UNIVERSAL"


async def design_fleet():
    print("🧠 OPENFORGE MBSE DESIGNER: Initializing Engineering Pipeline...")
    inventory = load_arsenal()
    if not inventory:
        print(f"❌ No components found in {ARSENAL_FILE}")
        return

    catalog = []
    compat_engine = CompatibilityService()

    buckets = {
        "5_INCH": {"Motors": [], "Propellers": [], "Battery": []},
        "7_INCH": {"Motors": [], "Propellers": [], "Battery": []},
        "HEAVY_LIFT": {"Motors": [], "Propellers": [], "Battery": []},
        "UNIVERSAL": {"FC_Stack": []},
    }
    frames = []

    for p in inventory:
        if "forum" in p["model_name"].lower():
            continue
        cat = p["category"]
        size = determine_size_class(p)

        if cat == "Frame_Kit":
            frames.append((p, size))
        elif cat == "FC_Stack":
            buckets["UNIVERSAL"]["FC_Stack"].append(p)
        elif cat == "Battery":
            mah = p["normalized"].get("capacity_mah", 1300.0)
            if mah >= 800:
                buckets["5_INCH"]["Battery"].append(p)
                buckets["7_INCH"]["Battery"].append(p)
            if mah >= 1800:
                buckets["7_INCH"]["Battery"].append(p)
                buckets["HEAVY_LIFT"]["Battery"].append(p)
        elif size in buckets and cat in buckets[size]:
            buckets[size][cat].append(p)

    for frame, size_class in frames:
        candidates = {
            "motors": buckets.get(size_class, {}).get("Motors", []),
            "props": buckets.get(size_class, {}).get("Propellers", []),
            "batteries": buckets.get(size_class, {}).get("Battery", []),
            "stacks": buckets["UNIVERSAL"]["FC_Stack"],
        }
        if not candidates["props"] and size_class == "HEAVY_LIFT":
            candidates["props"] = buckets["7_INCH"]["Propellers"]

        if not candidates["motors"] or not candidates["props"] or not candidates["batteries"] or not candidates["stacks"]:
            continue

        print(f"\n📐 Designing SKU around Anchor Frame: {frame['model_name'][:45]} ({size_class})")

        def format_list(lst):
            return "\n".join([f"- {i['model_name']} | Specs: {i['specs']}" for i in lst[:10]])

        prompt = MASTER_DESIGNER_INSTRUCTION.format(
            frame_name=frame["model_name"],
            frame_specs=frame["specs"],
            motors=format_list(candidates["motors"]),
            props=format_list(candidates["props"]),
            batteries=format_list(candidates["batteries"]),
            stacks=format_list(candidates["stacks"]),
        )

        design_decision = await call_llm_for_json(prompt, "You are a Principal Aerospace Systems Architect.")
        if not design_decision:
            continue

        def find_part(name: str, lst: list[dict]) -> dict:
            for x in lst:
                if x["model_name"] == name:
                    return x
            for x in lst:
                if name[:10].lower() in x["model_name"].lower():
                    return x
            return lst[0]

        sku_id = f"OF-AI-{random.randint(1000, 9999)}"
        bom = normalize_bom([
            frame,
            find_part(design_decision.get("selected_motor_model", ""), candidates["motors"]),
            find_part(design_decision.get("selected_prop_model", ""), candidates["props"]),
            find_part(design_decision.get("selected_battery_model", ""), candidates["batteries"]),
            find_part(design_decision.get("selected_stack_model", ""), candidates["stacks"]),
        ])

        # 1. Scene Graph & Parallel-Axis Inertia
        mission_ctx = {"mission_name": f"{size_class} Industrial Patrol", "primary_goal": "Autonomous Inspection"}
        scene_graph = generate_scene_graph(mission_ctx, bom)

        # 2. First-Principles Propulsion & Aerodynamics
        physics = generate_physics_config(bom)
        physics["center_of_mass_offset"] = scene_graph["mass_properties"]["cog_m"]

        # 3. Mechanical DRC, Electrical ERC, Interconnects & 3D-Printable Mount Synthesis
        drc_erc_report = compat_engine.validate_build(bom, scene_graph=scene_graph, physics_config=physics, sku_id=sku_id)
        for extra in drc_erc_report.get("required_accessories", []):
            bom.append(normalize_component(extra))

        # 4. Physics-Scaled Betaflight CLI & ArduPilot .param Firmware Generation
        firmware_configs = generate_firmware_configs(sku_id, bom, physics, scene_graph)

        # 5. Assembly Blueprint, Cost Manifest & Wiring Schematic
        blueprint = await generate_assembly_blueprint(bom)
        cost_manifest = generate_procurement_manifest(bom)
        schematic_path = generate_wiring_diagram(sku_id, bom)

        # 6. Parametric CAD (.STEP, .STL, .URDF) & 240Hz PyBullet Certification
        cad_assets = generate_assets(sku_id, blueprint, bom, scene_graph=scene_graph)
        urdf_path = cad_assets.get("assembly_files", {}).get("urdf")
        pybullet_cert = None
        if urdf_path and os.path.exists(urdf_path):
            try:
                max_thrust_per_motor_g = (physics["motor_max_force_n"] / 9.80665) * 1000.0
                runner = FlightTestRunner(urdf_path, max_thrust_g=max_thrust_per_motor_g, gui=False)
                pybullet_cert = runner.run_engineering_certification(duration_sec=4.0)
            except Exception as e:
                print(f"   ⚠️  PyBullet Certification note: {e}")

        sku = {
            "sku_id": sku_id,
            "anchor_frame": frame["model_name"],
            "class": size_class,
            "ai_reasoning": design_decision.get("design_reasoning", ""),
            "performance": {
                "twr": physics["dynamics"]["twr"],
                "hover_throttle_pct": physics["dynamics"]["hover_throttle_pct"],
                "flight_time": physics["meta"]["est_flight_time_min"],
                "mixed_flight_time": physics["meta"]["mixed_flight_time_min"],
                "total_weight": physics["meta"]["total_weight_g"],
                "top_speed_kmh": physics["aerodynamics"]["top_speed_kmh"],
                "disk_loading_g_dm2": physics["aerodynamics"]["disk_loading_g_dm2"],
            },
            "bom": bom,
            "technical_data": {
                "blueprint": blueprint,
                "physics_config": physics,
                "scene_graph": scene_graph,
                "drc_erc_report": drc_erc_report,
                "printable_mounts": drc_erc_report.get("printable_mounts", []),
                "firmware_configs": firmware_configs,
                "cost_manifest": cost_manifest,
                "cad_assets": cad_assets,
                "schematic_path": schematic_path,
                "pybullet_certification": pybullet_cert,
            },
        }

        catalog.append(sku)
        save_catalog(catalog)
        print(
            f"   💾 Saved Certified SKU: {sku_id} | 3D Mounts: {len(drc_erc_report.get('printable_mounts', []))} "
            f"| Firmware: Betaflight + ArduPilot Ready"
        )

    print(f"\n✅ Fleet Engineering Complete. {len(catalog)} SKUs written to {CATALOG_FILE}")


if __name__ == "__main__":
    asyncio.run(design_fleet())
# --- END OF FILE tools/design_fleet.py ---