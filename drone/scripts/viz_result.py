# FILE: scripts/visualize_result.py
import sys
import os
import json
import webbrowser
import base64

# Path setup
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.cad_service import generate_frame_stl
from app.services.physics_service import run_physics_simulation

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "templates", "visualize.html")
STATIC_DIR = os.path.join(PROJECT_ROOT, "static", "generated")

def main():
    print("=========================================")
    print("Drone Architect - VISUALIZATION GENERATOR")
    print("=========================================")

    print("[1] Loading Drone Specs...")
    
    # Mock Data simulating a Search Result
    specs = {
        "motor_mounting_mm": 6.6, 
        "prop_diameter_mm": 31.0,
        "fc_mounting_mm": 25.5
    }
    
    bom = [
        {"part_type": "Motors", "product_name": "0802 19000kv (x4)"},
        {"part_type": "FC", "product_name": "BetaFPV F4 1S 5A AIO"},
        {"part_type": "Battery", "product_name": "1S 300mAh LiPo"},
        {"part_type": "Frame", "product_name": "3D Printed Whoop Chassis"}
    ]

    print("[2] Running Physics Engine...")
    physics_report = run_physics_simulation(bom)
    
    print("[3] Generating CAD Models...")
    stl_path, png_path = generate_frame_stl("viz_demo_drone", specs)
    
    if not stl_path or not physics_report:
        print("❌ Error generating assets.")
        return

    print("[4] Embedding Assets & Building HTML...")
    
    with open(TEMPLATE_PATH, "r") as f:
        html_content = f.read()
    
    # --- THE FIX: BASE64 ENCODING ---
    # Read the STL bytes and convert to a Data URI string
    with open(stl_path, "rb") as f:
        stl_bytes = f.read()
        stl_b64 = base64.b64encode(stl_bytes).decode('utf-8')
        data_uri = f"data:model/stl;base64,{stl_b64}"
    
    # Inject Data
    # We replace the placeholder with the massive Base64 string
    html_content = html_content.replace('"[[STL_PATH]]"', f'"{data_uri}"')
    html_content = html_content.replace('[[PHYSICS_JSON]]', json.dumps(physics_report))
    html_content = html_content.replace('[[SPECS_JSON]]', json.dumps(specs))
    
    output_html_path = os.path.join(STATIC_DIR, "report_viz.html")
    
    with open(output_html_path, "w") as f:
        f.write(html_content)
        
    print(f"\n🎉 Report Generated: {output_html_path}")
    print("🚀 Opening Browser...")
    
    webbrowser.open(f"file://{output_html_path}")

if __name__ == "__main__":
    main()