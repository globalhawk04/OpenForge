# FILE: app/services/cad_service.py
import os
import subprocess
import logging
import trimesh
import numpy as np

# Helper function to find parts in the BOM
def find_part_in_bom(bom, part_type_query):
    for item in bom:
        if part_type_query.lower() in item.get("part_type", "").lower():
            return item
    return None

logger = logging.getLogger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def render_scad(script: str, output_filename: str) -> str | None:
    # Ensure filename is clean
    clean_name = output_filename.lower().replace(" ", "_")
    scad_path = os.path.join(OUTPUT_DIR, f"{clean_name}.scad")
    
    # INTERMEDIATE: Generate STL first (OpenSCAD likes this)
    stl_path = os.path.join(OUTPUT_DIR, f"{clean_name}.stl")
    # FINAL: Convert to OBJ (USD likes this)
    obj_path = os.path.join(OUTPUT_DIR, f"{clean_name}.obj")
    
    with open(scad_path, "w") as f:
        f.write(script)
    
    try:
        # 1. Run OpenSCAD -> STL
        cmd = ["openscad", "-o", stl_path, scad_path]
        
        result = subprocess.run(
            cmd, 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            timeout=30,
            text=True
        )
        
        # 2. Python Convert STL -> OBJ
        if os.path.exists(stl_path):
            print(f"      🔄 Converting to OBJ: {clean_name}...")
            mesh = trimesh.load(stl_path)
            # trimesh.load can return a Scene or a Trimesh. Handle both.
            if isinstance(mesh, trimesh.Scene):
                # If it's a scene, export the whole thing
                # We merge to ensure a single mesh for Isaac Physics
                mesh = trimesh.util.concatenate(mesh.dump())
            
            mesh.export(obj_path)
            
            if os.path.exists(obj_path):
                print(f"      ✅ Asset Ready: {clean_name}.obj")
                return obj_path
            else:
                print(f"      ❌ Trimesh conversion failed.")
                return None
        else:
            print(f"      ❌ OpenSCAD ran but NO STL created.")
            return None

    except subprocess.CalledProcessError as e:
        print(f"      ❌ OpenSCAD Execution Failed!")
        print(f"         Command: {' '.join(cmd)}")
        print(f"         Error: {e.stderr}")
        return None
    except FileNotFoundError:
        print("      ❌ OpenSCAD not found! Install it: sudo apt-get install openscad")
        return None
    except Exception as e:
        print(f"      ❌ Unknown CAD Error: {e}")
        return None

def generate_assets(project_id: str, blueprint: dict, bom: list) -> dict:
    print(f"--> 🏗️  CAD Service: Parametric generation for {project_id}...")
    assets = {
        "individual_parts": {},
        "collision_report": {"collided": False}
    }
    
    # --- 1. EXTRACT DIMENSIONS ---
    chassis_part = find_part_in_bom(bom, "chassis") or {}
    actuator_part = find_part_in_bom(bom, "actuator") or {}

    def get_spec(part, key, default):
        val = part.get("engineering_specs", {}).get(key)
        try:
            return float(val) if val is not None else default
        except:
            return default

    # Dimensions (Millimeters)
    body_length = get_spec(chassis_part, "length_mm", 240.0)
    body_width = get_spec(chassis_part, "width_mm", 120.0)
    femur_len = get_spec(chassis_part, "femur_length_mm", 100.0)
    tibia_len = get_spec(chassis_part, "tibia_length_mm", 110.0)
    
    # Servo Sizing
    servo_class = actuator_part.get("engineering_specs", {}).get("size_class", "Standard")
    is_micro = "Micro" in servo_class
    servo_w = 12.5 if is_micro else 20.0
    servo_l = 23.0 if is_micro else 40.0
    servo_h = 22.0 if is_micro else 36.0

    # --- 2. GENERATE OPENSCAD SCRIPTS ---
    
    # A. CHASSIS
    chassis_script = f"""
    $fn=50;
    module chassis() {{
        difference() {{
            cube([{body_length}, {body_width}, 45], center=true);
            cube([{body_length - 10}, {body_width - 10}, 40], center=true);
        }}
        // Servo Mounts
        for (x = [-1, 1]) for (y = [-1, 1]) {{
            translate([x * ({body_length}/2 - {servo_l}/2), y * ({body_width}/2), 0])
            rotate([90, 0, 0])
            cube([{servo_l + 4}, {servo_h + 4}, {servo_w + 4}], center=true);
        }}
    }}
    chassis();
    """

    # B. FEMUR
    femur_script = f"""
    $fn=50;
    module femur() {{
        difference() {{
            union() {{
                cylinder(h={servo_w}, r=15, center=true);
                translate([{femur_len}/2, 0, 0]) cube([{femur_len}, 10, 5], center=true);
                translate([{femur_len}, 0, 0]) cylinder(h={servo_w}, r=15, center=true);
            }}
            cylinder(h={servo_w}+2, r=3, center=true);
            translate([{femur_len}, 0, 0]) cylinder(h={servo_w}+2, r=3, center=true);
        }}
    }}
    femur();
    """

    # C. TIBIA
    tibia_script = f"""
    $fn=50;
    module tibia() {{
        union() {{
            difference() {{
                cylinder(h={servo_w}, r=12, center=true);
                cylinder(h={servo_w}+2, r=3, center=true);
            }}
            translate([0, -{tibia_len}/2, 0]) cube([8, {tibia_len}, 5], center=true);
            translate([0, -{tibia_len}, 0]) sphere(r=8);
        }}
    }}
    tibia();
    """

    # --- 3. RENDER ASSETS ---
    assets["individual_parts"]["Chassis_Kit"] = render_scad(chassis_script, f"{project_id}_chassis_kit")
    assets["individual_parts"]["Femur_Leg"] = render_scad(femur_script, f"{project_id}_femur_leg")
    assets["individual_parts"]["Tibia_Leg"] = render_scad(tibia_script, f"{project_id}_tibia_leg")

    # --- 4. COLLISION CHECK (Optional) ---
    try:
        import fcl # type: ignore
        pass
    except ImportError:
        print("      ⚠️  Collision Check skipped: No FCL Available (pip install python-fcl)")

    return assets