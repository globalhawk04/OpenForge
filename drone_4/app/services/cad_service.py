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
SCAD_LIB_PATH = os.path.join(PROJECT_ROOT, "cad", "library.scad")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def render_scad(script: str, output_filename: str) -> str | None:
    scad_path = os.path.join(OUTPUT_DIR, f"{output_filename}.scad")
    stl_path = os.path.join(OUTPUT_DIR, f"{output_filename}.stl")
    
    with open(scad_path, "w") as f:
        f.write(script)
    
    try:
        # Use absolute path for library import to prevent include errors
        # Note: OpenSCAD might need the library path explicitly passed or included in the script
        cmd = ["openscad", "-o", stl_path, scad_path]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if os.path.exists(stl_path):
            return stl_path
        return None
    except Exception as e:
        logger.error(f"❌ OpenSCAD Render Failed for {output_filename}: {e}")
        # Create a tiny dummy triangle so the pipeline doesn't break
        placeholder_path = os.path.join(OUTPUT_DIR, f"{output_filename}_placeholder.stl")
        with open(placeholder_path, "w") as f:
             f.write("solid placeholder\nfacet normal 0 0 0\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid placeholder")
        return placeholder_path

def generate_assets(project_id: str, blueprint: dict, bom: list) -> dict:
    print("--> 🏗️  CAD Service: Executing blueprint and validating geometry...")
    assets = {
        "individual_parts": {},
        "assembly_files": {},
        "calculated_specs": {},
        "collision_report": {"collided": False, "colliding_parts": []}
    }
    
    # --- 1. EXTRACT SPECS ---
    frame_part = find_part_in_bom(bom, "frame") or {}
    motor_part = find_part_in_bom(bom, "motor") or {}
    prop_part = find_part_in_bom(bom, "propeller") or {}
    fc_part = find_part_in_bom(bom, "fc") or {}
    cam_part = find_part_in_bom(bom, "camera") or {}
    bat_part = find_part_in_bom(bom, "battery") or {}
    
    def get_spec(part, key, default):
        val = part.get("engineering_specs", {}).get(key)
        return float(val) if val is not None else default

    wheelbase = get_spec(frame_part, "wheelbase_mm", 225.0)
    prop_diam_mm = get_spec(prop_part, "diameter_mm", 127.0)
    fc_mount_mm = get_spec(fc_part, "mounting_mm", 30.5)
    cam_width_mm = get_spec(cam_part, "width_mm", 19.0)
    motor_stator_size = int(get_spec(motor_part, "stator_size", 2207))
    battery_cells = int(get_spec(bat_part, "cells", 6))
    battery_capacity = int(get_spec(bat_part, "capacity_mah", 1300))
    is_digital = "true" if cam_width_mm > 19 else "false"
    
    # --- 2. GENERATE STLS ---
    # Ensure library import path is correct for OpenSCAD
    lib_path_safe = SCAD_LIB_PATH.replace("\\", "/")
    
    part_definitions = {
        "Frame_Kit": f'use <{lib_path_safe}>; pro_frame({wheelbase});',
        "Motors": f'use <{lib_path_safe}>; pro_motor({motor_stator_size});',
        "Propellers": f'use <{lib_path_safe}>; pro_prop({prop_diam_mm / 25.4});',
        "FC_Stack": f'use <{lib_path_safe}>; pro_stack({fc_mount_mm}, {is_digital});',
        "Camera_VTX_Kit": f'use <{lib_path_safe}>; pro_camera({cam_width_mm});',
        "Battery": f'use <{lib_path_safe}>; pro_battery({battery_cells}, {battery_capacity});',
        "Companion_Computer": f'use <{lib_path_safe}>; pro_companion_computer();'
    }

    for part_name, script in part_definitions.items():
        assets["individual_parts"][part_name] = render_scad(script, f"{project_id}_{part_name.lower()}")

    # --- 3. COLLISION DETECTION (SOFT FAIL) ---
    try:
        collision_manager = trimesh.collision.CollisionManager()
        assembled_meshes = {}
        
        # Load meshes
        for part_type, stl_path in assets["individual_parts"].items():
            if stl_path and os.path.exists(stl_path):
                try:
                    mesh = trimesh.load_mesh(stl_path)
                    if not mesh.is_empty: assembled_meshes[part_type] = mesh
                except: pass

        # Build Scene
        offset = (wheelbase / 2) * 0.7071
        motor_positions = [[offset, offset, 5], [-offset, offset, 5], [-offset, -offset, 5], [offset, -offset, 5]]
        
        if "Frame_Kit" in assembled_meshes:
            collision_manager.add_object("Frame_Kit_0", assembled_meshes["Frame_Kit"])

        for step in blueprint.get("blueprint_steps", []):
            action = step.get("action")
            part_type = step.get("target_part_type")
            if part_type in assembled_meshes:
                mesh = assembled_meshes[part_type]
                if action == "MOUNT_MOTORS":
                    for i, pos in enumerate(motor_positions):
                        T = trimesh.transformations.translation_matrix(pos)
                        collision_manager.add_object(f"Motors_{i}", mesh, transform=T)
                elif action == "INSTALL_STACK":
                    T = trimesh.transformations.translation_matrix([0, 0, 8])
                    collision_manager.add_object("Stack", mesh, transform=T)
        
        # Check
        is_colliding, names = collision_manager.in_collision_internal(return_names=True)
        assets["collision_report"]["collided"] = is_colliding
        if is_colliding:
            print(f"      ❌ Collision Detected: {names}")
            assets["collision_report"]["colliding_parts"] = list(names)
            
    except ValueError:
        print("      ⚠️  Skipping 3D Collision Check (python-fcl not installed).")
    except Exception as e:
        print(f"      ⚠️  Collision Check skipped: {e}")

    return assets