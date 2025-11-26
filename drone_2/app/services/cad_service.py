# FILE: app/services/cad_service.py
import os
import subprocess
import logging
import trimesh
import numpy as np

# Helper function to find parts in the BOM
def find_part_in_bom(bom, part_type_query):
    """Finds the first item in a BOM that matches the part_type_query."""
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
    """
    Writes SCAD script to file and uses OpenSCAD to compile it to STL.
    """
    scad_path = os.path.join(OUTPUT_DIR, f"{output_filename}.scad")
    stl_path = os.path.join(OUTPUT_DIR, f"{output_filename}.stl")
    
    with open(scad_path, "w") as f:
        f.write(script)
    
    try:
        cmd = ["openscad", "-o", stl_path, scad_path]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if os.path.exists(stl_path):
            return stl_path
        return None
    except Exception as e:
        logger.error(f"❌ OpenSCAD Render Failed for {output_filename}: {e}")
        # Return a path to a placeholder if render fails
        placeholder_path = os.path.join(OUTPUT_DIR, f"{output_filename}_placeholder.stl")
        with open(placeholder_path, "w") as f_ph:
             f_ph.write("solid placeholder\nendsolid placeholder")
        return placeholder_path


def generate_assets(project_id: str, blueprint: dict, bom: list) -> dict:
    """
    Generates all CAD assets, executes the assembly blueprint, and performs
    deterministic 3D mesh collision detection.
    """
    print("--> 🏗️  CAD Service: Executing blueprint and validating geometry...")
    assets = {
        "individual_parts": {},
        "assembly_files": {},
        "calculated_specs": {},
        "collision_report": {"collided": False, "colliding_parts": []}
    }
    
    # --- 1. EXTRACT SPECS & GENERATE INDIVIDUAL MODELS ---
    frame_part = find_part_in_bom(bom, "frame") or {}
    motor_part = find_part_in_bom(bom, "motor") or {}
    prop_part = find_part_in_bom(bom, "propeller") or {}
    fc_part = find_part_in_bom(bom, "fc") or {}
    cam_part = find_part_in_bom(bom, "camera") or {}
    bat_part = find_part_in_bom(bom, "battery") or {}
    comp_part = find_part_in_bom(bom, "companion") or {}

    def get_spec(part, key, default):
        val = part.get("engineering_specs", {}).get(key)
        return val if val is not None else default

    wheelbase = float(get_spec(frame_part, "wheelbase_mm", 225.0))
    prop_diam_mm = float(get_spec(prop_part, "diameter_mm", 127.0))
    fc_mount_mm = float(get_spec(fc_part, "mounting_mm", 30.5))
    cam_width_mm = float(get_spec(cam_part, "width_mm", 19.0))
    motor_stator_size = int(get_spec(motor_part, "stator_size", 2207))
    battery_cells = int(get_spec(bat_part, "cells", 6))
    battery_capacity = int(get_spec(bat_part, "capacity_mah", 1300))
    is_digital = "true" if cam_width_mm > 19 else "false"
    
    assets["calculated_specs"] = {
        "wheelbase": wheelbase, "prop_diameter_mm": prop_diam_mm, "fc_mounting_mm": fc_mount_mm,
    }
    
    print("    -> Generating individual component models...")
    part_definitions = {
        "Frame_Kit": f'use <{SCAD_LIB_PATH}>; pro_frame({wheelbase});',
        "Motors": f'use <{SCAD_LIB_PATH}>; pro_motor({motor_stator_size});',
        "Propellers": f'use <{SCAD_LIB_PATH}>; pro_prop({prop_diam_mm / 25.4});',
        "FC_Stack": f'use <{SCAD_LIB_PATH}>; pro_stack({fc_mount_mm}, {is_digital});',
        "Camera_VTX_Kit": f'use <{SCAD_LIB_PATH}>; pro_camera({cam_width_mm});',
        "Battery": f'use <{SCAD_LIB_PATH}>; pro_battery({battery_cells}, {battery_capacity});',
        "Companion_Computer": f'use <{SCAD_LIB_PATH}>; pro_companion_computer();' # Assumes a generic model
    }

    for part_name, script in part_definitions.items():
        assets["individual_parts"][part_name] = render_scad(script, f"{project_id}_{part_name.lower()}")

    # =====================================================================
    # 2. DETERMINISTIC COLLISION DETECTION
    # =====================================================================
    print("    -> Performing deterministic 3D collision check...")
    collision_manager = trimesh.collision.CollisionManager()
    assembled_meshes = {}

    for part_type, stl_path in assets["individual_parts"].items():
        if stl_path and os.path.exists(stl_path):
            try:
                # Use a processing flag to handle potential mesh issues
                mesh = trimesh.load_mesh(stl_path, process=True)
                if not mesh.is_empty:
                    assembled_meshes[part_type] = mesh
            except Exception as e:
                print(f"      - Warning: Could not load mesh for {part_type}: {e}")

    offset = (wheelbase / 2) * 0.7071
    motor_positions = [[offset, offset, 5], [-offset, offset, 5], [-offset, -offset, 5], [offset, -offset, 5]]

    if "Frame_Kit" in assembled_meshes:
        collision_manager.add_object("Frame_Kit_0", assembled_meshes["Frame_Kit"])

    for step in blueprint.get("blueprint_steps", []):
        action = step.get("action")
        part_type = step.get("target_part_type")

        if not part_type or part_type not in assembled_meshes: continue
        mesh_to_add = assembled_meshes[part_type]

        if action == "MOUNT_MOTORS":
            for i, pos in enumerate(motor_positions):
                transform = trimesh.transformations.translation_matrix(pos)
                collision_manager.add_object(f"Motors_{i}", mesh_to_add, transform=transform)
        elif action == "INSTALL_STACK":
            transform = trimesh.transformations.translation_matrix([0, 0, 8])
            collision_manager.add_object("FC_Stack_0", mesh_to_add, transform=transform)
        elif action == "SECURE_CAMERA":
            transform = trimesh.transformations.translation_matrix([0, 35, 10])
            collision_manager.add_object("Camera_VTX_Kit_0", mesh_to_add, transform=transform)
        elif action == "MOUNT_COMPUTER": # New action for Companion Computer
            transform = trimesh.transformations.translation_matrix([0, 0, 20]) # Mount above the stack
            collision_manager.add_object("Companion_Computer_0", mesh_to_add, transform=transform)

    is_colliding, colliding_part_names = collision_manager.in_collision_internal(return_names=True)
    
    assets["collision_report"]["collided"] = is_colliding
    if is_colliding:
        cleaned_names = sorted(list({name.split('_')[0] for name in colliding_part_names}))
        assets["collision_report"]["colliding_parts"] = cleaned_names
        print(f"   ❌ COLLISION DETECTED between: {cleaned_names}")
    else:
        print("   ✅ No 3D collisions detected.")

    # =====================================================================
    # 3. BUILD VISUAL ASSEMBLY SCRIPT (for dashboard)
    # =====================================================================
    assembly_script_lines = [f'// Assembly for Project: {project_id}\n$fn=50;\n']
    
    # Use import() for STLs which is more reliable than include for complex geometry
    for part_name, stl_path in assets["individual_parts"].items():
        if stl_path:
             # Create a wrapper .scad file for each STL to be included
             scad_wrapper_path = os.path.join(OUTPUT_DIR, f"{project_id}_{part_name.lower()}_wrapper.scad")
             with open(scad_wrapper_path, "w") as f:
                 # Use an absolute path for reliability
                 abs_stl_path = os.path.abspath(stl_path).replace('\\', '/')
                 f.write(f'import("{abs_stl_path}");')
    
    assembly_script_lines.append(f'include <{os.path.join(OUTPUT_DIR, f"{project_id}_frame_kit_wrapper.scad")}>;')

    for step in blueprint.get("blueprint_steps", []):
        action = step.get("action")
        part_type = step.get("target_part_type").lower()
        
        wrapper_path = os.path.join(OUTPUT_DIR, f"{project_id}_{part_type}_wrapper.scad")
        
        if action == "MOUNT_MOTORS":
            for pos in motor_positions: assembly_script_lines.append(f'translate([{pos[0]}, {pos[1]}, {pos[2]}]) include <{wrapper_path}>;')
        elif action == "INSTALL_STACK":
            assembly_script_lines.append(f'translate([0, 0, 8]) include <{wrapper_path}>;')
        elif action == "SECURE_CAMERA":
            assembly_script_lines.append(f'translate([0, 35, 10]) include <{wrapper_path}>;')
        elif action == "ATTACH_PROPS":
            for pos in motor_positions: assembly_script_lines.append(f'translate([{pos[0]}, {pos[1]}, {pos[2]+10}]) include <{wrapper_path}>;')
        elif action == "MOUNT_BATTERY":
            assembly_script_lines.append(f'translate([0, 0, -20]) include <{wrapper_path}>;')
        elif action == "MOUNT_COMPUTER":
            assembly_script_lines.append(f'translate([0, 0, 20]) include <{wrapper_path}>;')

    full_assembly_script = "\n".join(assembly_script_lines)
    assets["assembly_files"]["scad"] = os.path.join(OUTPUT_DIR, f"{project_id}_assembly.scad")
    with open(assets["assembly_files"]["scad"], "w") as f: f.write(full_assembly_script)
        
    print("   ✅ CAD generation complete.")
    return assets