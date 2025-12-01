# FILE: main.py
import asyncio
import sys
import os
import json
import base64
import webbrowser
import random
import shutil
import subprocess
from datetime import datetime

# Import Services
from app.services.ai_service import (
    analyze_user_requirements, refine_requirements, 
    generate_spec_sheet, generate_assembly_instructions
)
from app.services.fusion_service import fuse_component_data
from app.services.physics_service import run_physics_simulation
from app.services.cad_service import generate_assets
from app.services.cost_service import generate_procurement_manifest
from app.services.schematic_service import generate_wiring_diagram

OUTPUT_DIR = os.path.abspath("output")
TEMPLATE_DIR = os.path.abspath("templates")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def check_openscad():
    try:
        subprocess.run(["openscad", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except: return False

def create_placeholder_stl(filepath):
    with open(filepath, "w") as f:
        f.write(f"solid placeholder\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 10 0\nendloop\nendfacet\nendsolid placeholder")
    return filepath

def file_to_b64(path):
    if not path or not os.path.exists(path): return ""
    try:
        with open(path, "rb") as f: return f"data:model/stl;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    except: return ""

def generate_flight_log(report):
    twr = report.get('twr', 1.0)
    hover = report.get('hover_throttle_percent', 50) / 100.0
    times, heights, throttles = [], [], []
    h = 0
    for i in range(100):
        times.append(i/10.0)
        err = 1.5 - h
        th = hover + (err * 0.5) if twr > 1.0 else 1.0
        th = max(0, min(1, th + (random.random()-0.5)*0.05))
        h += (th - hover) * 2.0 if twr > 1.0 else -0.5
        if h < 0: h = 0
        heights.append(round(h, 2)); throttles.append(round(th, 2))
    return {"time": times, "height": heights, "throttle_avg": throttles}

async def run():
    print("\n🚀 OPENFORGE SYSTEM ONLINE")
    print("==========================")
    
    # --- INIT MASTER RECORD ---
    master_record = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0"
        },
        "requirements": {},
        "engineering": {},
        "sourcing": {},
        "simulation": {},
        "fabrication": {},
        "documentation": {}
    }
    
    if not check_openscad(): print("⚠️  OpenSCAD not found. Using placeholders.")
    
    # 1. Intake
    prompt = input("\n👨‍✈️  Enter Mission Requirements > ")
    if not prompt: return
    
    analysis = await analyze_user_requirements(prompt)
    if not analysis: return
    
    master_record["requirements"]["original_prompt"] = prompt
    master_record["requirements"]["initial_analysis"] = analysis

    # 2. Clarification
    qs = analysis.get("missing_critical_info", []) or analysis.get("clarifying_questions", [])
    answers = []
    if qs:
        print(f"\n🎤 Clarification needed ({len(qs)} questions):")
        for q in qs:
            ans = input(f"   {q} > ")
            answers.append(f"Q: {q} | A: {ans}")
            
    master_record["requirements"]["user_answers"] = answers

    # 3. Planning
    plan = await refine_requirements(analysis, answers)
    print(f"\n✅ Plan Approved: {plan.get('build_summary')}")
    master_record["engineering"]["final_plan"] = plan

    # 4. Execution
    specs = await generate_spec_sheet(plan)
    master_record["engineering"]["spec_sheet"] = specs
    
    bom = []
    cad_data = {}
    
    print("\n🔎 Sourcing Components...")
    for item in specs.get('buy_list', []):
        print(f"   > Finding {item['part_type']}...")
        part = await fuse_component_data(item['part_type'], item['search_query'])
        if part:
            bom.append(part)
            s = part.get('engineering_specs', {})
            if s.get('mounting_mm'): cad_data['motor_mounting_mm'] = s['mounting_mm']
            if s.get('diameter_mm'): cad_data['prop_diameter_mm'] = s['diameter_mm']
            if s.get('width_mm'): cad_data['camera_width_mm'] = s['width_mm']
        else:
            print(f"     ⚠️  Failed to source {item['part_type']}")
            bom.append(item) # Keep placeholder
            
    master_record["sourcing"]["bill_of_materials"] = bom

    # 5. Physics & CAD
    print("\n🧪 Simulating Physics & Geometry...")
    phys = run_physics_simulation(bom)
    flight_log = generate_flight_log(phys)
    
    master_record["simulation"]["report"] = phys
    master_record["simulation"]["log_sample"] = flight_log
    
    if 'wheelbase' not in cad_data: 
        # Heuristic fallback if vision failed
        cad_data['wheelbase'] = cad_data.get('prop_diameter_mm', 127) * 1.8
        
    master_record["fabrication"]["specs"] = cad_data
        
    assets = generate_assets("mission", cad_data)
    
    # Fallbacks
    for k, v in assets.items():
        if isinstance(v, str) and (not v or not os.path.exists(v)) and k != "assembly_scad":
            path = os.path.join(OUTPUT_DIR, f"mission_{k}.stl")
            assets[k] = create_placeholder_stl(path)
            
    master_record["fabrication"]["assets"] = assets

    # 6. Docs
    print("\n📝 Finalizing Documentation...")
    guide = await generate_assembly_instructions({"bill_of_materials": bom, "engineering_notes": specs.get("engineering_notes")})
    cost = generate_procurement_manifest(bom)
    
    master_record["documentation"]["assembly_guide"] = guide
    master_record["documentation"]["procurement"] = cost
    
    # 7. Render
    with open(os.path.join(TEMPLATE_DIR, "dashboard.html"), "r") as f: html = f.read()
    
    html = html.replace('"[[FRAME_B64]]"', f'"{file_to_b64(assets.get("frame"))}"')
    html = html.replace('"[[MOTOR_B64]]"', f'"{file_to_b64(assets.get("motor"))}"')
    html = html.replace('"[[FC_B64]]"', f'"{file_to_b64(assets.get("fc"))}"')
    html = html.replace('"[[PROP_B64]]"', f'"{file_to_b64(assets.get("prop"))}"')
    html = html.replace('"[[BATTERY_B64]]"', f'"{file_to_b64(assets.get("battery"))}"')
    html = html.replace('"[[CAMERA_B64]]"', f'"{file_to_b64(assets.get("camera"))}"')
    html = html.replace('[[WHEELBASE]]', str(assets.get("wheelbase", 200)))
    html = html.replace('[[STEPS_JSON]]', json.dumps(guide.get("steps", [])))
    html = html.replace('[[PHYSICS_JSON]]', json.dumps(phys))
    html = html.replace('[[COST_JSON]]', json.dumps(cost))
    html = html.replace('[[FLIGHT_LOG_JSON]]', json.dumps(flight_log))
    
    out_path = os.path.join(OUTPUT_DIR, "dashboard.html")
    with open(out_path, "w") as f: f.write(html)
    
    # Save FULL Record
    json_path = os.path.join(OUTPUT_DIR, "master_record.json")
    print(f"\n💾 SAVING SOURCE OF TRUTH: {json_path}")
    with open(json_path, "w") as f:
        json.dump(master_record, f, indent=2)

    print(f"\n🚀 Done. Dashboard: {out_path}")
    webbrowser.open(f"file://{out_path}")

if __name__ == "__main__":
    asyncio.run(run())