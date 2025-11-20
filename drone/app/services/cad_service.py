# FILE: app/services/cad_service.py
import os
import subprocess

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
SCAD_LIB_PATH = os.path.join(PROJECT_ROOT, "cad", "library.scad")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "static", "generated")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def render_scad(script: str, output_filename: str):
    scad_path = os.path.join(OUTPUT_DIR, f"{output_filename}.scad")
    stl_path = os.path.join(OUTPUT_DIR, f"{output_filename}.stl")
    with open(scad_path, "w") as f: f.write(script)
    try:
        # Run headless
        subprocess.run(["openscad", "-o", stl_path, scad_path], check=True)
        return stl_path
    except Exception:
        return None

def generate_assets(project_id: str, specs: dict):
    # 1. Extract Specs
    motor_mount = specs.get("motor_mounting_mm", 6.6)
    prop_diam = specs.get("prop_diameter_mm", 31.0)
    fc_mount = specs.get("fc_mounting_mm", 25.5)
    cam_width = specs.get("camera_width_mm", 14.0) 
    
    # 2. Professional Grade Logic: Fasteners
    use_inserts = specs.get("use_inserts", False)
    
    # Heuristic for screw size based on motor pattern
    if motor_mount > 15.0: 
        # M3 territory (16x16, 19x19)
        # Standard M3 hole = 3.2mm. M3 Heat-Set Insert hole = ~4.0mm
        hole_diam = 4.0 if use_inserts else 3.2
    elif motor_mount > 8.0: 
        # M2 territory (9x9, 12x12)
        # Standard M2 hole = 2.2mm. M2 Heat-Set Insert hole = ~3.2mm
        hole_diam = 3.2 if use_inserts else 2.2
    else: 
        # M1.4 territory (6.6mm Whoop)
        # Usually self-tapping into plastic
        hole_diam = 1.5

    # Battery Heuristics
    bat_l, bat_w, bat_h = 60, 12, 7 

    wheelbase = (prop_diam * 2) + 15 

    assets = {"wheelbase": wheelbase}

    # --- GENERATE FRAME ---
    # Note: We pass hole_diam as the 3rd argument to motor_mount
    frame_script = f"""
    use <{SCAD_LIB_PATH}>;
    $fn=50;
    union() {{
        frame_body({wheelbase}, 2.5);
        translate([{wheelbase/2 * 0.707}, {wheelbase/2 * 0.707}, 0]) motor_mount({motor_mount}, 2, {hole_diam});
        translate([- {wheelbase/2 * 0.707}, {wheelbase/2 * 0.707}, 0]) motor_mount({motor_mount}, 2, {hole_diam});
        translate([- {wheelbase/2 * 0.707}, - {wheelbase/2 * 0.707}, 0]) motor_mount({motor_mount}, 2, {hole_diam});
        translate([{wheelbase/2 * 0.707}, - {wheelbase/2 * 0.707}, 0]) motor_mount({motor_mount}, 2, {hole_diam});
        translate([0,0,2.5]) fc_mount({fc_mount});
    }}
    """
    assets["frame"] = render_scad(frame_script, f"{project_id}_frame")

    # --- GENERATE MOTOR ---
    # Proxies don't need the hole_diam adjustment, just visual size
    motor_script = f"use <{SCAD_LIB_PATH}>; $fn=30; proxy_motor({motor_mount + 2}, 8);"
    assets["motor"] = render_scad(motor_script, f"{project_id}_motor")

    # --- GENERATE FC ---
    fc_script = f"use <{SCAD_LIB_PATH}>; $fn=30; proxy_fc({fc_mount}, {fc_mount + 5});"
    assets["fc"] = render_scad(fc_script, f"{project_id}_fc")

    # --- GENERATE PROP ---
    prop_script = f"use <{SCAD_LIB_PATH}>; $fn=30; proxy_prop({prop_diam});"
    assets["prop"] = render_scad(prop_script, f"{project_id}_prop")
    
    # --- GENERATE BATTERY ---
    bat_script = f"use <{SCAD_LIB_PATH}>; proxy_battery({bat_l}, {bat_w}, {bat_h});"
    assets["battery"] = render_scad(bat_script, f"{project_id}_battery")
    
    # --- GENERATE CAMERA ---
    cam_script = f"use <{SCAD_LIB_PATH}>; $fn=30; proxy_camera({cam_width});"
    assets["camera"] = render_scad(cam_script, f"{project_id}_camera")

    return assets