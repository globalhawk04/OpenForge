# FILE: scripts/test_all_systems.py
import asyncio
import sys
import os
import json
import base64
import webbrowser
from datetime import datetime

# Setup Paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "static", "generated")
sys.path.append(PROJECT_ROOT)

# Ensure output dir exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Import Services
from app.services.ai_service import analyze_user_requirements, refine_requirements, generate_spec_sheet, generate_assembly_instructions
from app.services.fusion_service import fuse_component_data
from app.services.physics_service import run_physics_simulation
from app.services.cad_service import generate_assets

# Helper for HTML generation
def file_to_b64(path):
    if not path or not os.path.exists(path): return ""
    with open(path, "rb") as f:
        return f"data:model/stl;base64,{base64.b64encode(f.read()).decode('utf-8')}"

async def main():
    print("\n==================================================")
    print("🚁 DRONE ARCHITECT: MASTER SYSTEM TEST")
    print("==================================================\n")

    # --- INITIALIZE SOURCE OF TRUTH ---
    project_id = "master_test_drone"
    master_record = {
        "project_id": project_id,
        "created_at": datetime.utcnow().isoformat(),
        "status": "initializing",
        "user_intent": {},
        "engineering": {},
        "sourcing": {},
        "simulation": {},
        "fabrication": {},
        "assembly": {}
    }

    # --- PHASE 1: INTAKE & REQUIREMENTS ---
    print("--- [PHASE 1] INTAKE & REQUIREMENTS ---")
    
    # 1. Simulated User Input
    # We ask for a "Rugged" build to trigger the need for hardware/inserts
    user_prompt = "I want to build a rugged 5 inch freestyle drone with a camera for digital video"
    print(f"🗣️  User: '{user_prompt}'")
    
    # 2. Simulated Interview Answers
    answers = [
        "Question: Budget? | Answer: $400",
        "Question: Analog or Digital? | Answer: DJI O3 (Digital)",
        "Question: DIY or Prebuilt? | Answer: DIY",
        "Question: Battery? | Answer: 6S",
        "Question: Build Style? | Answer: Rugged/Durable"
    ]
    
    # 3. Run Agents
    analysis = await analyze_user_requirements(user_prompt)
    final_plan = await refine_requirements(analysis, answers)
    spec_sheet = await generate_spec_sheet(final_plan)
    
    if not spec_sheet:
        print("❌ Critical Error: Requirements Planning Failed.")
        return

    print(f"✅ Plan Approved: {final_plan.get('build_summary')}")
    
    # SAVE TO RECORD
    master_record["user_intent"] = {
        "original_prompt": user_prompt,
        "interview_answers": answers
    }
    master_record["engineering"] = {
        "initial_analysis": analysis,
        "final_plan": final_plan,
        "spec_sheet": spec_sheet
    }

    buy_list = spec_sheet.get("buy_list", [])
    print(f"📋 Generated Manifest: {len(buy_list)} items to source.\n")

    # --- PHASE 2: FUSION SOURCING ---
    print("--- [PHASE 2] GLOBAL SOURCING & VERIFICATION ---")
    
    final_bom = []
    cad_specs = {} # We collect dimensions here
    
    for item in buy_list:
        part_type = item['part_type']
        query = item['search_query']
        category = item.get('category', 'Core')
        
        print(f"🔎 Sourcing [{category}]: {part_type} ('{query}')")
        
        # Skip Vision for generic hardware (screws, tape) to save time/money
        # Fusion service handles this logic, but we can optimize here too if needed
        
        # Call Fusion Service (Search -> Scrape -> Vision -> Sanitize)
        part_data = await fuse_component_data(part_type, query)
        
        if part_data:
            final_bom.append(part_data)
            specs = part_data.get('engineering_specs', {})
            
            # Collect CAD data from Core components
            if specs.get('mounting_mm'): 
                cad_specs['motor_mounting_mm'] = specs['mounting_mm']
                print(f"   📏 CAD Param: Motor Mount {specs['mounting_mm']}mm")
            
            if specs.get('diameter_mm'):
                cad_specs['prop_diameter_mm'] = specs['diameter_mm']
                print(f"   📏 CAD Param: Prop Diameter {specs['diameter_mm']}mm")
                
            if specs.get('width_mm'):
                cad_specs['camera_width_mm'] = specs['width_mm']
                print(f"   📏 CAD Param: Camera Width {specs['width_mm']}mm")
                
            # Default FC mount if not found
            if part_type == "FC_Stack" and not cad_specs.get('fc_mounting_mm'):
                # Default to 30.5 for 5-inch builds if not found
                cad_specs['fc_mounting_mm'] = 30.5 
                
        else:
            print(f"   ⚠️  Warning: Could not source {part_type}")
            # Add placeholder to BOM to track failure
            final_bom.append({"part_type": part_type, "status": "failed", "query": query})

    # SAVE TO RECORD
    master_record["sourcing"] = {
        "bill_of_materials": final_bom,
        "extracted_cad_params": cad_specs
    }

    # --- PHASE 3: PHYSICS SIMULATION ---
    print("\n--- [PHASE 3] PHYSICS VALIDATION ---")
    
    physics_report = run_physics_simulation(final_bom)
    
    if physics_report:
        print(f"📊 TWR: {physics_report['twr']} | Hover: {physics_report['hover_throttle_percent']}% | Time: {physics_report['est_flight_time_min']}min")
        master_record["simulation"] = physics_report
        if physics_report['twr'] < 1.2:
            print("❌ WARNING: DRONE IS UNDERPOWERED!")
        else:
            print("✅ Physics Check Passed.")

    # --- PHASE 4: GENERATIVE CAD ---
    print("\n--- [PHASE 4] GENERATIVE CAD ---")
    
    # Determine Fastening Strategy from Plan
    constraints = final_plan.get('final_constraints', {})
    fastening = constraints.get('fastening_method', '')
    if 'Insert' in fastening or 'insert' in fastening:
        cad_specs['use_inserts'] = True
        print("   🔩 Design Mode: Professional (Heat-Set Inserts)")
    else:
        cad_specs['use_inserts'] = False
        print("   🔩 Design Mode: Standard (Direct Thread/Pass-through)")
    
    print(f"⚙️  Generating Assets with specs: {cad_specs}")
    assets = generate_assets(project_id, cad_specs)
    
    if assets.get("frame"):
        print(f"✅ STL Generated: {os.path.basename(assets['frame'])}")
        master_record["fabrication"] = assets # Stores paths to STLs
    else:
        print("❌ CAD Generation Failed.")
        return

    # --- PHASE 5: ASSEMBLY INSTRUCTIONS ---
    print("\n--- [PHASE 5] INSTRUCTION GENERATION ---")
    
    # Prepare data for the AI Writer (Include Hardware in context)
    project_context = {
        "bill_of_materials": [
            {
                "part_type": p.get('part_type'), 
                "product_name": p.get('product_name'),
                "category": p.get('category', 'Core') # Help AI group instructions
            } for p in final_bom if p.get('product_name')
        ],
        "engineering_notes": spec_sheet.get("engineering_notes"),
        "fabrication_specs": cad_specs
    }
    
    guide = await generate_assembly_instructions(project_context)
    steps = guide.get("steps", [])
    print(f"✅ Generated {len(steps)} detailed assembly steps.")
    
    # SAVE TO RECORD
    master_record["assembly"] = guide
    master_record["status"] = "complete"

    # --- PHASE 6: SAVE SOURCE OF TRUTH ---
    print("\n--- [PHASE 6] SAVING DATA ---")
    json_path = os.path.join(OUTPUT_DIR, f"{project_id}_manifest.json")
    with open(json_path, "w") as f:
        json.dump(master_record, f, indent=2)
    print(f"💾 Source of Truth saved: {json_path}")

    # --- PHASE 7: DASHBOARD VISUALIZATION ---
    print("\n--- [PHASE 7] DASHBOARD COMPILATION ---")
    
    template_path = os.path.join(PROJECT_ROOT, "templates", "animate.html")
    output_path = os.path.join(OUTPUT_DIR, "master_build_guide.html")
    
    with open(template_path, "r") as f:
        html = f.read()
    
    # Inject Assets (Full Suite including new visualizers)
    html = html.replace('"[[FRAME_B64]]"', f'"{file_to_b64(assets.get("frame"))}"')
    html = html.replace('"[[MOTOR_B64]]"', f'"{file_to_b64(assets.get("motor"))}"')
    html = html.replace('"[[FC_B64]]"', f'"{file_to_b64(assets.get("fc"))}"')
    html = html.replace('"[[PROP_B64]]"', f'"{file_to_b64(assets.get("prop"))}"')
    html = html.replace('"[[BATTERY_B64]]"', f'"{file_to_b64(assets.get("battery"))}"')
    html = html.replace('"[[CAMERA_B64]]"', f'"{file_to_b64(assets.get("camera"))}"')
    
    # Inject Data
    html = html.replace('[[WHEELBASE]]', str(assets.get("wheelbase", 200)))
    html = html.replace('[[STEPS_JSON]]', json.dumps(steps))
    
    with open(output_path, "w") as f:
        f.write(html)
        
    print(f"🎉 SUCCESS! Dashboard ready at: {output_path}")
    print("🚀 Launching interface...")
    webbrowser.open(f"file://{output_path}")

if __name__ == "__main__":
    asyncio.run(main())