import asyncio
import sys
import os
import json
import base64
import webbrowser
import random
import time

# --- PATH SETUP ---
# Ensure we can find the 'app' module
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

# --- HELPER: BASE64 ---
def file_to_b64(path):
    if not path or not os.path.exists(path): return ""
    try:
        with open(path, "rb") as f:
            return f"data:model/stl;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    except: return ""

# --- HELPER: GENERATE FAKE FLIGHT DATA FOR DASHBOARD ---
# (Because the simple physics engine returns a summary, not a time-series log)
def generate_flight_log(physics_report, duration_sec=10):
    twr = physics_report.get('twr', 1.0)
    hover_thr = physics_report.get('hover_throttle_percent', 50) / 100.0
    times, heights, throttles = [], [], []
    current_height = 0.0
    
    steps = duration_sec * 10
    for i in range(steps):
        t = i / 10.0
        times.append(t)
        # Simulate PID hover
        error = 1.5 - current_height
        throttle = hover_thr + (error * 0.5) if twr > 1.0 else 1.0
        throttle = max(0, min(1, throttle + (random.random()-0.5)*0.05))
        
        climb = (throttle - hover_thr) * 2.0 if twr > 1.0 else -0.5
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

    # 1. INITIAL INTAKE
    print("👨‍✈️  USER INPUT:")
    user_prompt = input("   What are your requirements? > ")
    if not user_prompt: return

    print("\n🧠 AI: Analyzing requirements...")
    analysis = await analyze_user_requirements(user_prompt)
    
    if not analysis:
        print("❌ Error: AI returned no data.")
        return

    # 2. INTERVIEW MODE (The Logic You Were Missing)
    # The AI returns 'missing_critical_info' OR 'clarifying_questions'
    questions = analysis.get("missing_critical_info", [])
    if not questions:
        questions = analysis.get("clarifying_questions", [])

    user_answers = []

    if questions:
        print(f"\n🎤 AI: I need to clarify {len(questions)} details before we build.")
        print("-" * 50)
        for i, q in enumerate(questions):
            # Loop specifically through questions, waiting for input on each
            answer = input(f"   [{i+1}/{len(questions)}] {q}\n   You > ")
            user_answers.append(f"Question: {q} | Answer: {answer}")
        print("-" * 50)
    else:
        print("\n✅ AI: Requirements are clear. Proceeding.")

    # 3. REFINEMENT
    print("\n🧠 AI: Updating engineering plan with your answers...")
    final_plan = await refine_requirements(analysis, user_answers)

    print(f"\n📝 PLAN APPROVED: {final_plan.get('build_summary')}")
    print(f"   Constraints: {json.dumps(final_plan.get('final_constraints'), indent=2)}")

    # 4. EXECUTION LOOP
    print("\n" + "="*30)
    print("⚙️  STARTING FABRICATION LOOP")
    print("="*30)

    # A. Generate BOM
    print("   [1/5] generating_spec_sheet...")
    spec_sheet = await generate_spec_sheet(final_plan)
    shopping_list = spec_sheet.get('buy_list', [])

    # B. Source Parts
    print(f"   [2/5] sourcing_{len(shopping_list)}_components...")
    final_bom = []
    cad_specs = {}

    for item in shopping_list:
        part_type = item['part_type']
        query = item.get('new_search_query') or item.get('search_query')
        print(f"         > searching: {query}...")
        
        part = await fuse_component_data(part_type, query)
        if part:
            final_bom.append(part)
            # Harvest Specs for CAD
            specs = part.get('engineering_specs', {})
            if specs.get('mounting_mm'): cad_specs['motor_mounting_mm'] = specs['mounting_mm']
            if specs.get('diameter_mm'): cad_specs['prop_diameter_mm'] = specs['diameter_mm']
            if specs.get('width_mm'): cad_specs['camera_width_mm'] = specs['width_mm']
        else:
            print(f"         ⚠️ NOT FOUND: {part_type}")

    # C. Physics
    print("   [3/5] running_physics_engine...")
    physics_report = run_physics_simulation(final_bom)
    flight_log = generate_flight_log(physics_report) # Create dummy log for chart

    # D. CAD
    print("   [4/5] generating_stl_assets...")
    # Heuristic defaults if search failed
    if 'wheelbase' not in cad_specs: cad_specs['wheelbase'] = cad_specs.get('prop_diameter_mm', 127) * 1.8
    assets = generate_assets("live_mission", cad_specs)

    # E. Docs
    print("   [5/5] writing_assembly_manual...")
    doc_context = {
        "bill_of_materials": final_bom, 
        "engineering_notes": spec_sheet.get("engineering_notes"),
        "fabrication_specs": cad_specs
    }
    guide = await generate_assembly_instructions(doc_context)
    cost = generate_procurement_manifest(final_bom)

    # 5. DASHBOARD GENERATION
    print("\n🖥️  COMPILING DASHBOARD...")
    template_path = os.path.join(TEMPLATE_DIR, "dashboard.html")
    
    if not os.path.exists(template_path):
        print("❌ Error: templates/dashboard.html missing. Please create it.")
        return

    with open(template_path, "r") as f:
        html = f.read()

    # Inject Everything
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
    with open(output_path, "w") as f:
        f.write(html)

    print(f"\n✅ MISSION SUCCESS.")
    print(f"🚀 Dashboard: {output_path}")
    webbrowser.open(f"file://{output_path}")

if __name__ == "__main__":
    asyncio.run(main())