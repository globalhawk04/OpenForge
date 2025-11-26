# FILE: scripts/visualize_assembly.py
import sys
import os
import json
import webbrowser
import base64
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.cad_service import generate_assets
from app.services.ai_service import generate_assembly_instructions

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "templates", "animate.html")
STATIC_DIR = os.path.join(PROJECT_ROOT, "static", "generated")

def file_to_b64(path):
    with open(path, "rb") as f:
        return f"data:model/stl;base64,{base64.b64encode(f.read()).decode('utf-8')}"

async def main():
    print("=========================================")
    print("Drone Architect - ASSEMBLY ANIMATOR")
    print("=========================================")

    # 1. Mock Project Data
    specs = {"motor_mounting_mm": 6.6, "prop_diameter_mm": 31.0, "fc_mounting_mm": 25.5}
    
    # 2. Generate Assets
    print("[1] Generating Component Models...")
    assets = generate_assets("anim_demo", specs)
    if not assets.get("frame"):
        print("❌ CAD Failed")
        return

    # 3. Generate Instructions
    print("[2] Writing Assembly Guide...")
    # Mocking BOM for the writer
    project_data = {
        "bill_of_materials": [
            {"part_type": "Motors", "product_name": "0802 19000kv"},
            {"part_type": "FC", "product_name": "BetaFPV AIO"},
        ],
        "engineering_notes": "Whoop build."
    }
    guide = await generate_assembly_instructions(project_data)
    steps = guide.get("steps", []) if guide else []

    # 4. Build HTML
    print("[3] Building Interactive Guide...")
    
    with open(TEMPLATE_PATH, "r") as f: html = f.read()
    
    html = html.replace('"[[FRAME_B64]]"', f'"{file_to_b64(assets["frame"])}"')
    html = html.replace('"[[MOTOR_B64]]"', f'"{file_to_b64(assets["motor"])}"')
    html = html.replace('"[[FC_B64]]"', f'"{file_to_b64(assets["fc"])}"')
    html = html.replace('[[WHEELBASE]]', str(assets["wheelbase"]))
    html = html.replace('[[STEPS_JSON]]', json.dumps(steps))
    
    out_path = os.path.join(STATIC_DIR, "assembly_guide.html")
    with open(out_path, "w") as f: f.write(html)
    
    print(f"🚀 Launching: {out_path}")
    webbrowser.open(f"file://{out_path}")

if __name__ == "__main__":
    asyncio.run(main())