import asyncio
import sys
import os
import json
import base64
import webbrowser
import random
import time
import shutil
import subprocess
from datetime import datetime

# --- PATH SETUP ---
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "static", "generated")
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "templates")
sys.path.append(PROJECT_ROOT)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- IMPORTS ---
from app.services.ai_service import (
    analyze_user_requirements, 
    refine_requirements, 
    generate_spec_sheet, 
    generate_assembly_instructions
)
from app.services.fusion_service import fuse_component_data
from app.services.physics_service import run_physics_simulation
from app.services.cad_service import generate_assets
from app.services.cost_service import generate_procurement_manifest
from app.services.schematic_service import generate_wiring_diagram

# --- HELPER: CHECK DEPENDENCIES ---
def check_openscad():
    try:
        subprocess.run(["openscad", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

# --- HELPER: GENERATE DUMMY STL (FALLBACK) ---
def create_placeholder_stl(filepath, shape="cube"):
    name = os.path.basename(filepath)
    stl_content = f"solid {name}\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 10 0\nendloop\nendfacet\nendsolid {name}"
    with open(filepath, "w") as f:
        f.write(stl_content)
    return filepath

# --- HELPER: BASE64 ---
def file_to_b64(path):
    if not path or not os.path.exists(path): return ""
    try:
        with open(path, "rb") as f:
            return f"data:model/stl;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    except Exception as e:
        return ""

# --- HELPER: FLIGHT LOG GEN ---
def generate_flight_log(physics_report, duration_sec=10):
    twr = physics_report.get('twr', 1.0)
    hover_thr = physics_report.get('hover_throttle_percent', 50) / 100.0
    times, heights, throttles = [], [], []
    current_height = 0.0
    
    steps = duration_sec * 10
    for i in range(steps):
        t = i / 10.0
        times.append(t)
        error = 1.5 - current_height
        if twr < 1.0:
            throttle = 1.0 
            climb = -0.5 
        else:
            throttle = hover_thr + (error * 0.5)
            throttle = max(0, min(1, throttle + (random.random()-0.5)*0.05))
            climb = (throttle - hover_thr) * 2.0
        
        current_height += climb * 0.1
        if current_height < 0: current_height = 0
        
        heights.append(round(current_height, 2))
        throttles.append(round(throttle, 2))
        
    return {"time": times, "height": heights, "throttle_avg": throttles}

# --- MAIN MISSION ---
async def main():
    print("\n" + "="*60)
    print("🚀 DRONE ARCHITECT | END-TO-END MISSION")
    print("============================================================\n")

    # --- INIT MASTER RECORD ---
    master_record = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "script_version": "1.0.0"
        },
        "requirements": {},
        "engineering": {},
        "sourcing": {},
        "simulation": {},
        "fabrication": {},
        "documentation": {}
    }

    # 0. SYSTEM CHECK
    has_openscad = check_openscad()
    if not has_openscad:
        print("⚠️  WARNING: OpenSCAD is not installed.")
        print("   Using PLACEHOLDER blocks for 3D visualization.\n")
    else:
        print("✅ OpenSCAD detected.\n")

    # 1. INITIAL INTAKE
    print("👨‍✈️  USER INPUT:")
    user_prompt = input("   What are your requirements? > ")
    if not user_prompt: return

    print("\n🧠 AI: Analyzing requirements...")
    analysis = await analyze_user_requirements(user_prompt)
    
    # RECORD: INTAKE
    master_record["requirements"]["original_prompt"] = user_prompt
    master_record["requirements"]["initial_analysis"] = analysis

    # 2. INTERVIEW
    questions = analysis.get("missing_critical_info", []) or analysis.get("clarifying_questions", [])
    user_answers = []
    
    if questions:
        print(f"\n🎤 AI: I need to clarify {len(questions)} details.")
        print("-" * 50)
        for i, q in enumerate(questions):
            answer = input(f"   [{i+1}/{len(questions)}] {q}\n   You > ")
            user_answers.append(f"Question: {q} | Answer: {answer}")
        print("-" * 50)
    else:
        print("\n✅ AI: Requirements are clear.")

    # RECORD: INTERVIEW
    master_record["requirements"]["user_answers"] = user_answers

    # 3. REFINEMENT
    print("\n🧠 AI: Finalizing Engineering Plan...")
    final_plan = await refine_requirements(analysis, user_answers)

    print(f"\n📝 PLAN APPROVED: {final_plan.get('build_summary')}")
    
    # RECORD: PLAN
    master_record["engineering"]["final_plan"] = final_plan

    # 4. EXECUTION LOOP
    print("\n" + "="*30)
    print("⚙️  STARTING FABRICATION LOOP")
    print("="*30)

    # A. BOM
    print("   [1/5] Generating Bill of Materials...")
    spec_sheet = await generate_spec_sheet(final_plan)
    shopping_list = spec_sheet.get('buy_list', [])
    
    # RECORD: SPECS
    master_record["engineering"]["spec_sheet"] = spec_sheet

    # B. Sourcing
    print(f"   [2/5] Sourcing {len(shopping_list)} components...")
    final_bom = []
    cad_specs = {}

    for item in shopping_list:
        part_type = item['part_type']
        query = item.get('new_search_query') or item.get('search_query')
        print(f"         > Searching: {query}...")
        
        part = await fuse_component_data(part_type, query)
        if part:
            final_bom.append(part)
            specs = part.get('engineering_specs', {})
            if specs.get('mounting_mm'): cad_specs['motor_mounting_mm'] = specs['mounting_mm']
            if specs.get('diameter_mm'): cad_specs['prop_diameter_mm'] = specs['diameter_mm']
            if specs.get('width_mm'): cad_specs['camera_width_mm'] = specs['width_mm']
        else:
            print(f"         ⚠️ Using generic fallback for {part_type}")
            final_bom.append({"part_type": part_type, "status": "not_found", "query": query})

    # RECORD: BOM
    master_record["sourcing"]["bill_of_materials"] = final_bom

    # C. Physics
    print("   [3/5] Running Physics Simulation...")
    physics_report = run_physics_simulation(final_bom)
    flight_log = generate_flight_log(physics_report)
    
    # RECORD: SIM
    master_record["simulation"]["report"] = physics_report
    master_record["simulation"]["log_sample"] = flight_log

    # D. CAD
    print("   [4/5] Generating 3D Assets...")
    if 'wheelbase' not in cad_specs: cad_specs['wheelbase'] = cad_specs.get('prop_diameter_mm', 127) * 1.8
    
    assets = generate_assets("live_mission", cad_specs)
    
    # Fallback Logic
    for key, path in assets.items():
        if not isinstance(path, str): continue
        if key == "assembly_scad": continue
        if not path or not os.path.exists(path):
            print(f"         ⚠️  CAD failed for {key}. Generating placeholder STL.")
            if not path:
                path = os.path.join(OUTPUT_DIR, f"live_mission_{key}.stl")
                assets[key] = path
            create_placeholder_stl(path)
            
    # RECORD: CAD
    master_record["fabrication"]["specs"] = cad_specs
    master_record["fabrication"]["assets"] = assets

    # E. Documentation
    print("   [5/5] AI Writing Assembly Guide (This takes ~10s)...")
    doc_context = {
        "bill_of_materials": final_bom, 
        "engineering_notes": spec_sheet.get("engineering_notes"),
        "fabrication_specs": cad_specs
    }
    
    guide = await generate_assembly_instructions(doc_context)
    cost = generate_procurement_manifest(final_bom)
    
    # RECORD: DOCS
    master_record["documentation"]["assembly_guide"] = guide
    master_record["documentation"]["procurement"] = cost

    # --- SAVE SOURCE OF TRUTH ---
    json_path = os.path.join(OUTPUT_DIR, "mission_master_record.json")
    print(f"\n💾 SAVING SOURCE OF TRUTH: {json_path}")
    with open(json_path, "w") as f:
        json.dump(master_record, f, indent=2)

    # 5. DASHBOARD
    print("\n🖥️  COMPILING DASHBOARD...")
    template_path = os.path.join(TEMPLATE_DIR, "dashboard.html")
    
    if not os.path.exists(template_path):
        print("❌ Error: templates/dashboard.html missing.")
        return

    with open(template_path, "r") as f: html = f.read()

    # Inject Assets
    html = html.replace('"[[FRAME_B64]]"', f'"{file_to_b64(assets.get("frame"))}"')
    html = html.replace('"[[MOTOR_B64]]"', f'"{file_to_b64(assets.get("motor"))}"')
    html = html.replace('"[[FC_B64]]"', f'"{file_to_b64(assets.get("fc"))}"')
    html = html.replace('"[[PROP_B64]]"', f'"{file_to_b64(assets.get("prop"))}"')
    html = html.replace('"[[BATTERY_B64]]"', f'"{file_to_b64(assets.get("battery"))}"')
    html = html.replace('"[[CAMERA_B64]]"', f'"{file_to_b64(assets.get("camera"))}"')
    
    html = html.replace('[[WHEELBASE]]', str(assets.get("wheelbase", 200)))
    html = html.replace('[[STEPS_JSON]]', json.dumps(guide.get("steps", [])))
    html = html.replace('[[PHYSICS_JSON]]', json.dumps(physics_report))
    html = html.replace('[[COST_JSON]]', json.dumps(cost))
    html = html.replace('[[FLIGHT_LOG_JSON]]', json.dumps(flight_log))

    output_path = os.path.join(OUTPUT_DIR, "mission_dashboard.html")
    with open(output_path, "w") as f: f.write(html)

    print(f"\n✅ MISSION SUCCESS.")
    print(f"🚀 Dashboard: {output_path}")
    webbrowser.open(f"file://{output_path}")

if __name__ == "__main__":
    asyncio.run(main())