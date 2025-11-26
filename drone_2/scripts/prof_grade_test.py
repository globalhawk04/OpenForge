# FILE: scripts/test_all_systems.py
import asyncio
import sys
import os
import json
import base64
import webbrowser
from datetime import datetime
from copy import deepcopy

# Setup Paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "static", "generated")
sys.path.append(PROJECT_ROOT)

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Import Services
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
from app.services.schematic_service import generate_wiring_diagram
from app.services.cost_service import generate_procurement_manifest

def file_to_b64(path):
    if not path or not os.path.exists(path): return ""
    with open(path, "rb") as f:
        return f"data:model/stl;base64,{base64.b64encode(f.read()).decode('utf-8')}"

def image_to_b64(path):
    if not path or not os.path.exists(path): return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

async def main():
    print("\n==================================================")
    print("🚁 DRONE ARCHITECT: MASTER SYSTEM TEST")
    print("==================================================\n")

    project_id = "master_rev_test"
    master_record = {
        "project_id": project_id,
        "created_at": datetime.utcnow().isoformat(),
        "status": "initializing",
        "user_intent": {},
        "engineering": {},
        "revisions": [],
        "sourcing": {},    # Final State
        "simulation": {},  # Final State
        "fabrication": {}, # Final State
        "assembly": {},    # Final State
        "procurement": {}  # Final State
    }

    # --- PHASE 1: INTAKE ---
    print("--- [PHASE 1] INTAKE & REQUIREMENTS ---")
    
    user_prompt = "I want to build a handheld freestyle drone with a camera for digital video"
    print(f"🗣️  User: '{user_prompt}'")
    
    answers = [
        "Question: Budget? | Answer: $400",
        "Question: Analog or Digital? | Answer: DJI O3 (Digital)",
        "Question: DIY or Prebuilt? | Answer: DIY",
        "Question: Battery? | Answer: 6S",
        "Question: Build Style? | Answer: Rugged/Durable"
    ]
    
    analysis = await analyze_user_requirements(user_prompt)
    final_plan = await refine_requirements(analysis, answers)
    spec_sheet = await generate_spec_sheet(final_plan)
    
    if not spec_sheet: return

    print(f"✅ Plan Approved: {final_plan.get('build_summary')}")
    
    # --- DATA CAPTURE: INTENT & ENGINEERING ---
    master_record["user_intent"] = {
        "original_prompt": user_prompt,
        "interview_answers": answers
    }
    master_record["engineering"] = {
        "initial_analysis": analysis,
        "final_plan": final_plan,
        "spec_sheet": spec_sheet
    }

    # Initial "To-Source" List
    current_shopping_list = spec_sheet.get("buy_list", [])
    current_bom = [] 
    
    # --- LOOP: SOURCING -> PHYSICS -> OPTIMIZATION ---
    MAX_REVISIONS = 3
    revision_count = 0
    
    # We need to track CAD specs across revisions
    cad_specs = {} 

    while revision_count < MAX_REVISIONS:
        revision_count += 1
        print(f"\n--- 🔄 REVISION {revision_count} START ---")

        # 1. Sourcing (Delta Update)
        for target_item in current_shopping_list:
            part_type = target_item['part_type']
            query = target_item.get('new_search_query') or target_item.get('search_query')
            
            print(f"🔎 Sourcing: {part_type} ('{query}')")
            new_part_data = await fuse_component_data(part_type, query)
            
            if new_part_data:
                # Remove old part if exists (Replacement Logic)
                current_bom = [p for p in current_bom if p['part_type'] != part_type]
                current_bom.append(new_part_data)
                
                # Update CAD Specs from new part
                specs = new_part_data.get('engineering_specs', {})
                if specs.get('mounting_mm'): cad_specs['motor_mounting_mm'] = specs['mounting_mm']
                if specs.get('diameter_mm'): cad_specs['prop_diameter_mm'] = specs['diameter_mm']
                if specs.get('width_mm'): cad_specs['camera_width_mm'] = specs['width_mm']
                if part_type == "FC_Stack" and not cad_specs.get('fc_mounting_mm'): cad_specs['fc_mounting_mm'] = 30.5
            else:
                print(f"   ⚠️ Failed to source {part_type}")

        # 2. Physics Validation
        print(f"\n--- [REV {revision_count}] PHYSICS CHECK ---")
        physics_report = run_physics_simulation(current_bom)
        
        twr = physics_report.get('twr', 0)
        print(f"📊 TWR: {twr} | Hover: {physics_report.get('hover_throttle_percent')}%")
        
        # Save Revision State
        rev_record = {
            "revision_id": revision_count,
            "timestamp": datetime.utcnow().isoformat(),
            "bom_snapshot": deepcopy(current_bom),
            "physics_snapshot": physics_report,
            "status": "pass" if twr >= 1.5 else "fail"
        }
        master_record["revisions"].append(rev_record)

        # 3. Decision Gate
        if twr >= 1.5:
            print("✅ Physics Check Passed. Freezing Design.")
            break
        
        if revision_count == MAX_REVISIONS:
            print("⛔ Max revisions reached. Proceeding with best effort.")
            break

        # 4. AI Optimization
        print("❌ System Underpowered. Calling Optimization Agent...")
        optimization_plan = await optimize_specs(current_bom, physics_report)
        
        if not optimization_plan:
            print("⚠️ Agent failed to provide plan. Stopping.")
            break
            
        print(f"🧠 Diagnosis: {optimization_plan.get('diagnosis')}")
        print(f"🔧 Strategy: {optimization_plan.get('strategy')}")
        
        current_shopping_list = optimization_plan.get("replacements", [])
        if not current_shopping_list:
            print("⚠️ Agent suggested no changes. Stopping.")
            break

    # --- DATA CAPTURE: FINAL SOURCING & SIMULATION ---
    master_record["sourcing"] = {
        "bill_of_materials": current_bom,
        "extracted_cad_params": cad_specs
    }
    master_record["simulation"] = physics_report

    # --- PHASE 4: CAD ---
    print("\n--- [PHASE 4] GENERATIVE CAD ---")
    constraints = final_plan.get('final_constraints', {})
    fastening = constraints.get('fastening_method', '')
    cad_specs['use_inserts'] = True if 'Insert' in fastening or 'insert' in fastening else False
    
    assets = generate_assets(project_id, cad_specs)
    master_record["fabrication"] = assets

    # --- PHASE 5: ASSEMBLY & DOCS ---
    print("\n--- [PHASE 5] INSTRUCTION GENERATION ---")
    project_context = {
        "bill_of_materials": [{"part_type": p.get('part_type'), "product_name": p.get('product_name')} for p in current_bom if p.get('product_name')],
        "engineering_notes": spec_sheet.get("engineering_notes"),
        "fabrication_specs": cad_specs
    }
    guide = await generate_assembly_instructions(project_context)
    steps = guide.get("steps", [])
    master_record["assembly"] = guide

    schematic_path = generate_wiring_diagram(project_id, [p.get('product_name', '') for p in current_bom])
    if schematic_path: master_record["assembly"]["schematic_diagram"] = schematic_path
    
    cost_report = generate_procurement_manifest(current_bom)
    master_record["procurement"] = cost_report

    # --- PHASE 6: SAVE FINAL SOURCE OF TRUTH ---
    print("\n--- [PHASE 6] SAVING DATA ---")
    master_record["status"] = "complete"
    json_path = os.path.join(OUTPUT_DIR, f"{project_id}_manifest.json")
    with open(json_path, "w") as f: json.dump(master_record, f, indent=2)
    print(f"💾 Source of Truth saved: {json_path}")

    # --- PHASE 7: VISUALIZATION ---
    template_path = os.path.join(PROJECT_ROOT, "templates", "animate.html")
    output_path = os.path.join(OUTPUT_DIR, "master_build_guide.html")
    
    with open(template_path, "r") as f: html = f.read()
    
    html = html.replace('"[[FRAME_B64]]"', f'"{file_to_b64(assets.get("frame"))}"')
    html = html.replace('"[[MOTOR_B64]]"', f'"{file_to_b64(assets.get("motor"))}"')
    html = html.replace('"[[FC_B64]]"', f'"{file_to_b64(assets.get("fc"))}"')
    html = html.replace('"[[PROP_B64]]"', f'"{file_to_b64(assets.get("prop"))}"')
    html = html.replace('"[[BATTERY_B64]]"', f'"{file_to_b64(assets.get("battery"))}"')
    html = html.replace('"[[CAMERA_B64]]"', f'"{file_to_b64(assets.get("camera"))}"')
    
    if schematic_path and os.path.exists(schematic_path):
        html = html.replace('[[SCHEMATIC_B64]]', image_to_b64(schematic_path))
    else:
        html = html.replace('[[SCHEMATIC_B64]]', "")

    html = html.replace('[[WHEELBASE]]', str(assets.get("wheelbase", 200)))
    html = html.replace('[[STEPS_JSON]]', json.dumps(steps))
    html = html.replace('[[PHYSICS_JSON]]', json.dumps(physics_report))
    html = html.replace('[[SPECS_JSON]]', json.dumps(cad_specs))
    html = html.replace('[[COST_JSON]]', json.dumps(cost_report))
    
    with open(output_path, "w") as f: f.write(html)
    webbrowser.open(f"file://{output_path}")

if __name__ == "__main__":
    asyncio.run(main())