# FILE: scripts/test_professional_flow.py
import asyncio
import sys
import os
import json
import logging
import base64
import webbrowser
from datetime import datetime
from copy import deepcopy

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
    generate_assembly_instructions,
    optimize_specs
)
from app.services.fusion_service import fuse_component_data
from app.services.physics_service import run_physics_simulation
from app.services.cad_service import generate_assets
from app.services.geometry_sim_service import run_geometric_simulation
from app.services.cost_service import generate_procurement_manifest
from app.services.schematic_service import generate_wiring_diagram

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DroneArchitect")

# --- HELPER: BASE64 ---
def file_to_b64(path):
    if not path or not os.path.exists(path): return ""
    try:
        with open(path, "rb") as f:
            return f"data:model/stl;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    except: return ""

def image_to_b64(path):
    if not path or not os.path.exists(path): return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

# --- MAIN FLOW ---
async def main():
    print("\n=======================================================")
    print("🏭  INDUSTRIAL DRONE ARCHITECT: PROFESSIONAL FLOW")
    print("=======================================================\n")

    project_id = "PRO_FLOW_TEST"
    
    # --- INITIALIZE MASTER SOURCE OF TRUTH ---
    master_log = {
        "meta": {
            "project_id": project_id,
            "timestamp_start": datetime.utcnow().isoformat(),
            "run_type": "automated_test"
        },
        "phase_1_intake": {},
        "phase_2_engineering": {},
        "phase_3_execution_history": [], # Arrays of iterations
        "phase_4_final_deliverables": {}
    }

    # 1. USER INPUT
    user_prompt = "Build a drone with 7 inch props but I want a small 5 inch frame for portability."
    logger.info(f"🗣️  Step 1: User Request: '{user_prompt}'")
    
    # Record Input
    master_log["phase_1_intake"]["user_prompt"] = user_prompt

    # 2. LLM ANALYSIS & CLARIFICATION
    logger.info("🧠 Step 2: AI Analysis...")
    analysis = await analyze_user_requirements(user_prompt)
    
    # Mocking User Answers
    answers = [
        "Question: Budget? | Answer: Unlimited",
        "Question: Battery? | Answer: 6S",
        "Question: System? | Answer: Digital"
    ]
    
    master_log["phase_1_intake"]["ai_analysis"] = analysis
    master_log["phase_1_intake"]["user_answers"] = answers
    
    logger.info("✅ Step 3: System Confirms Build Intent.")
    
    # 3. SPEC GENERATION
    logger.info("📋 Step 4: Generating Material List (BOM)...")
    final_plan = await refine_requirements(analysis, answers)
    spec_sheet = await generate_spec_sheet(final_plan)

    master_log["phase_2_engineering"]["requirements_doc"] = final_plan
    master_log["phase_2_engineering"]["initial_spec_sheet"] = spec_sheet

    # 4. SOURCING LOOP (The "Resource" Cycle)
    shopping_list = spec_sheet.get('buy_list', [])
    
    # State Variables
    bom = []
    verified = False
    iteration = 0
    max_iterations = 3
    kept_parts_cache = {} 

    while not verified and iteration < max_iterations:
        iteration += 1
        logger.info(f"\n🔄 --- ITERATION {iteration} START ---")
        
        # Init Iteration Record
        iter_record = {
            "iteration_number": iteration,
            "timestamp": datetime.utcnow().isoformat(),
            "actions": {},
            "simulations": {},
            "outcome": "pending"
        }

        # A. QUERY & SOURCE
        logger.info("🔎 Step 5: Querying Materials...")
        current_bom = []
        
        sourced_items_log = []

        for item in shopping_list:
            pt = item['part_type']
            # Check Cache
            if pt in kept_parts_cache and 'new_search_query' not in item:
                current_bom.append(kept_parts_cache[pt])
                sourced_items_log.append({"part": pt, "source": "cache", "name": kept_parts_cache[pt]['product_name']})
            else:
                # Search
                query = item.get('new_search_query', item.get('search_query'))
                logger.info(f"   🌍 Sourcing: {pt} -> '{query}'")
                part = await fuse_component_data(pt, query)
                if part:
                    current_bom.append(part)
                    kept_parts_cache[pt] = part 
                    sourced_items_log.append({"part": pt, "source": "fresh_search", "query": query, "result": part['product_name']})
                else:
                    fallback = {"part_type": pt, "product_name": "Generic", "price": 0, "engineering_specs": {}}
                    current_bom.append(fallback)
                    kept_parts_cache[pt] = fallback
                    sourced_items_log.append({"part": pt, "source": "fallback", "error": "not_found"})

        # Record BOM State for this iteration
        iter_record["bom_snapshot"] = deepcopy(current_bom)
        iter_record["sourcing_log"] = sourced_items_log

        # B. FIRST PHYSICS SIMULATION (Numerical)
        logger.info("🧮 Step 6: First Physics Simulation (Numerical)...")
        phys_report = run_physics_simulation(current_bom)
        iter_record["simulations"]["numerical"] = phys_report
        
        if phys_report['twr'] < 1.3:
            logger.error(f"❌ FAIL: TWR {phys_report['twr']} is too low.")
            
            # AI DIAGNOSIS
            logger.info("🧠 Step 11 (Early): AI Analyzing Failure...")
            fix = await optimize_specs(current_bom, phys_report)
            logger.info(f"🔧 Redesign Strategy: {fix.get('strategy')}")
            
            # Record Failure
            iter_record["outcome"] = "FAIL_NUMERICAL"
            iter_record["ai_diagnosis"] = fix
            master_log["phase_3_execution_history"].append(iter_record)
            
            # Apply Fix
            shopping_list = fix.get('replacements', [])
            continue # RESTART LOOP

        logger.info(f"✅ PASS: TWR {phys_report['twr']}")

        # C. ASSEMBLY INSTRUCTIONS 
        logger.info("📄 Step 7: Generating Assembly Instructions...")
        doc_context = {"bill_of_materials": current_bom, "engineering_notes": spec_sheet.get("engineering_notes")}
        guide = await generate_assembly_instructions(doc_context)
        # We don't save guide to history unless it's final, usually, but let's verify geometry first

        # D. CAD CREATION
        logger.info("⚙️  Step 8: Generating Full CAD...")
        cad_params = {}
        for p in current_bom:
            specs = p.get('engineering_specs', {})
            if specs.get('mounting_mm'): cad_params['motor_mounting_mm'] = specs['mounting_mm']
            if specs.get('diameter_mm'): cad_params['prop_diameter_mm'] = specs['diameter_mm']
            if specs.get('width_mm'): cad_params['camera_width_mm'] = specs['width_mm']
        
        # User Intent Injection (Forcing the failure condition on Iteration 1)
        if 'wheelbase' not in cad_params: 
            if "5 inch frame" in user_prompt and iteration == 1:
                cad_params['wheelbase'] = 225 
            else:
                 pass # Let CAD service infer safe default
                 
        cad_params['total_weight_g'] = phys_report['total_weight_g']
        
        assets = generate_assets(project_id, cad_params)
        iter_record["actions"]["generated_assets"] = assets

        # E. CAD SIMULATION (Geometric)
        logger.info("📐 Step 9: Full CAD Simulation (Geometric)...")
        geo_report = run_geometric_simulation(assets['calculated_specs'], {})
        iter_record["simulations"]["geometric"] = geo_report
        
        if geo_report['status'] == 'FAIL':
            logger.error(f"❌ FAIL: {geo_report['errors']}")
            
            # AI DIAGNOSIS
            logger.info("🧠 Step 10: AI Diagnosing Geometry Failure...")
            fix = await optimize_specs(current_bom, geo_report)
            logger.info(f"🕵️  Diagnosis: {fix.get('diagnosis')}")
            logger.info(f"🔧 Redesign Strategy: {fix.get('strategy')}")
            
            iter_record["outcome"] = "FAIL_GEOMETRIC"
            iter_record["ai_diagnosis"] = fix
            master_log["phase_3_execution_history"].append(iter_record)

            replacements = fix.get('replacements', [])
            if not replacements:
                logger.error("AI could not solve the geometry. Aborting.")
                break
            
            shopping_list = replacements
            continue # RESTART LOOP

        # SUCCESS STATE
        logger.info("✅ PASS: Geometry Verified.")
        iter_record["outcome"] = "PASS"
        master_log["phase_3_execution_history"].append(iter_record)
        verified = True

    if verified:
        # G. FINAL OUTPUT
        logger.info("📦 Step 12: Generating Final Deliverables...")
        
        schematic_path = generate_wiring_diagram(project_id, [p.get('product_name', '') for p in current_bom])
        cost = generate_procurement_manifest(current_bom)
        
        # Populate Final Deliverables in Master Log
        master_log["phase_4_final_deliverables"] = {
            "final_bom": current_bom,
            "fabrication_assets": assets,
            "assembly_guide": guide,
            "schematic_diagram_path": schematic_path,
            "procurement_manifest": cost,
            "final_physics_report": phys_report,
            "final_geometry_report": geo_report
        }
        
        # Save JSON
        master_log["meta"]["timestamp_end"] = datetime.utcnow().isoformat()
        json_path = os.path.join(OUTPUT_DIR, f"{project_id}_MASTER.json")
        with open(json_path, "w") as f: json.dump(master_log, f, indent=2)
        
        # Generate HTML
        logger.info("🖥️  Step 13: Visualization...")
        html_template = os.path.join(TEMPLATE_DIR, "animate.html")
        with open(html_template, "r") as f: html = f.read()
        
        html = html.replace('"[[FRAME_B64]]"', f'"{file_to_b64(assets.get("frame"))}"')
        html = html.replace('"[[MOTOR_B64]]"', f'"{file_to_b64(assets.get("motor"))}"')
        html = html.replace('"[[FC_B64]]"', f'"{file_to_b64(assets.get("fc"))}"')
        html = html.replace('"[[PROP_B64]]"', f'"{file_to_b64(assets.get("prop"))}"')
        html = html.replace('"[[BATTERY_B64]]"', f'"{file_to_b64(assets.get("battery"))}"')
        html = html.replace('"[[CAMERA_B64]]"', f'"{file_to_b64(assets.get("camera"))}"')
        html = html.replace('[[SCHEMATIC_B64]]', image_to_b64(schematic_path))
        html = html.replace('[[WHEELBASE]]', str(assets.get("wheelbase", 250)))
        html = html.replace('[[STEPS_JSON]]', json.dumps(guide.get("steps", [])))
        html = html.replace('[[PHYSICS_JSON]]', json.dumps(phys_report))
        html = html.replace('[[COST_JSON]]', json.dumps(cost))
        
        final_html = os.path.join(OUTPUT_DIR, f"{project_id}_dashboard.html")
        with open(final_html, "w") as f: f.write(html)
        
        print(f"\n✅ SYSTEM SUCCESS. Source of Truth: {json_path}")
        print(f"🚀 Opening Dashboard: {final_html}")
        webbrowser.open(f"file://{final_html}")
    else:
        print("\n⛔ SYSTEM FAILURE. Unable to resolve constraints after max iterations.")

if __name__ == "__main__":
    asyncio.run(main())