# --- START OF FILE app/services/cad_service.py ---
import os
import logging
from app.services.normalizer import normalize_bom
from app.services.digital_twin_service import generate_scene_graph

try:
    import trimesh
except ImportError:
    trimesh = None

try:
    import cadquery as cq
    from app.cad.assembly import DroneAssembler
    from app.cad.exporter import URDFExporter
    from app.cad.components import Motor, Propeller, FlightControllerStack, Battery
    from app.cad.frame import FrameGenerator
    HAS_CADQUERY = True
except ImportError:
    cq = None
    HAS_CADQUERY = False

logger = logging.getLogger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _write_fallback_urdf(sku_dir: str, cad_specs: dict, mass_props: dict) -> str:
    """Writes a valid physics URDF using the Parallel-Axis Inertia Tensor even if CadQuery is not installed."""
    project_name = cad_specs.get("name", "drone")
    total_mass_kg = float(cad_specs.get("mass_kg") or mass_props.get("total_mass_kg") or 0.520)
    urdf_in = mass_props.get("inertia_urdf_kg_m2", {"ixx": 0.004, "iyy": 0.004, "izz": 0.007})
    cog_m = mass_props.get("cog_m", [0.0, 0.01, 0.0])

    wb_m = float(cad_specs.get("wheelbase_mm", 225.0)) / 1000.0
    offset = (wb_m / 2.0) * 0.70710678
    prop_r = (float(cad_specs.get("prop_diameter_inch", 5.0)) * 0.0254) / 2.0

    urdf_content = f"""<?xml version="1.0"?>
<robot name="{project_name}">
  <link name="base_link">
    <inertial>
      <origin rpy="0 0 0" xyz="{cog_m[0]:.4f} {cog_m[2]:.4f} {cog_m[1]:.4f}"/>
      <mass value="{max(0.1, total_mass_kg - 0.02):.4f}"/>
      <inertia ixx="{urdf_in['ixx']:.8f}" ixy="0" ixz="0" iyy="{urdf_in['iyy']:.8f}" iyz="0" izz="{urdf_in['izz']:.8f}"/>
    </inertial>
    <collision>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <geometry><box size="{wb_m*0.7:.3f} {wb_m*0.7:.3f} 0.05"/></geometry>
    </collision>
  </link>
"""
    locs = [(offset, offset), (offset, -offset), (-offset, offset), (-offset, -offset)]
    for i, name in enumerate(["prop_fl", "prop_fr", "prop_rl", "prop_rr"]):
        x, y = locs[i]
        urdf_content += f"""
  <link name="{name}">
    <inertial>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <mass value="0.005"/>
      <inertia ixx="0.00001" ixy="0" ixz="0" iyy="0.00001" iyz="0" izz="0.00002"/>
    </inertial>
    <collision>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <geometry><cylinder length="0.008" radius="{prop_r:.4f}"/></geometry>
    </collision>
  </link>
  <joint name="joint_{name}" type="continuous">
    <parent link="base_link"/>
    <child link="{name}"/>
    <origin rpy="0 0 0" xyz="{x:.5f} {y:.5f} 0.030"/>
    <axis xyz="0 0 1"/>
  </joint>
"""
    urdf_content += "</robot>\n"
    urdf_path = os.path.join(sku_dir, "drone.urdf")
    with open(urdf_path, "w") as f:
        f.write(urdf_content)
    return urdf_path


def generate_assets(project_id: str, blueprint: dict, bom: list[dict], scene_graph: dict | None = None) -> dict:
    sku_dir = os.path.join(OUTPUT_DIR, project_id)
    os.makedirs(sku_dir, exist_ok=True)

    norm_bom = normalize_bom(bom)
    parts = {p["category"]: p for p in norm_bom}

    if scene_graph is None:
        scene_graph = generate_scene_graph({"mission_name": project_id}, norm_bom)

    f_norm = parts.get("Frame_Kit", {}).get("normalized", {})
    m_norm = parts.get("Motors", {}).get("normalized", {})
    p_norm = parts.get("Propellers", {}).get("normalized", {})
    b_norm = parts.get("Battery", {}).get("normalized", {})
    s_norm = parts.get("FC_Stack", {}).get("normalized", {})

    wheelbase = f_norm.get("wheelbase_mm", 225.0)
    arm_thick = f_norm.get("arm_thickness_mm", 5.0)
    prop_diam_in = p_norm.get("diameter_inch", 5.0)
    motor_mount = (m_norm.get("motor_mount_patterns_mm") or [16.0])[0]
    stack_mount = (s_norm.get("stack_mount_patterns_mm") or [30.5])[0]
    stator_d = m_norm.get("stator_d_mm", 22.0)
    stator_h = m_norm.get("stator_h_mm", 7.0)
    cells = b_norm.get("cells_s", 6)
    cap_mah = b_norm.get("capacity_mah", 1300.0)
    mass_props = scene_graph.get("mass_properties", {})

    cad_specs = {
        "name": project_id,
        "wheelbase_mm": wheelbase,
        "arm_thickness_mm": arm_thick,
        "prop_diameter_inch": prop_diam_in,
        "motor_mount_mm": motor_mount,
        "stack_mount_mm": stack_mount,
        "stator_d_mm": stator_d,
        "stator_h_mm": stator_h,
        "battery_cells": cells,
        "battery_capacity_mah": cap_mah,
        "mass_kg": mass_props.get("total_mass_kg", 0.520),
    }

    assets = {
        "individual_parts": {},
        "assembly_files": {},
        "calculated_specs": cad_specs,
        "collision_report": {"collided": False, "colliding_parts": []},
    }

    if HAS_CADQUERY:
        print(f"--> 🏗️  CAD Service (CadQuery): Building parametric STEP, STL & URDF for {project_id}...")
        try:
            frame_stl = os.path.join(sku_dir, f"{project_id}_frame_kit.stl")
            cq.exporters.export(FrameGenerator(cad_specs).generate(), frame_stl)
            assets["individual_parts"]["Frame_Kit"] = frame_stl

            motor_stl = os.path.join(sku_dir, f"{project_id}_motors.stl")
            cq.exporters.export(Motor(stator_w=stator_d, stator_h=stator_h, mounting_mm=motor_mount).build(), motor_stl)
            assets["individual_parts"]["Motors"] = motor_stl

            prop_stl = os.path.join(sku_dir, f"{project_id}_propellers.stl")
            cq.exporters.export(Propeller(diameter_inch=prop_diam_in).build(), prop_stl)
            assets["individual_parts"]["Propellers"] = prop_stl

            stack_stl = os.path.join(sku_dir, f"{project_id}_fc_stack.stl")
            cq.exporters.export(FlightControllerStack(mounting_mm=stack_mount).build(), stack_stl)
            assets["individual_parts"]["FC_Stack"] = stack_stl

            bat_stl = os.path.join(sku_dir, f"{project_id}_battery.stl")
            cq.exporters.export(Battery(cells=cells, capacity_mah=int(cap_mah)).build(), bat_stl)
            assets["individual_parts"]["Battery"] = bat_stl

            assembler = DroneAssembler(cad_specs)
            exporter = URDFExporter(assembler, mass_properties=mass_props)
            urdf_path = exporter.export(output_dir=sku_dir)

            assets["assembly_files"]["urdf"] = urdf_path
            assets["assembly_files"]["step"] = os.path.join(sku_dir, f"{project_id}.step")
            assets["assembly_files"]["base_stl"] = os.path.join(sku_dir, "base.stl")
            assets["assembly_files"]["prop_stl"] = os.path.join(sku_dir, "prop.stl")
        except Exception as e:
            logger.error(f"❌ CadQuery Export Error for {project_id}: {e}")
            assets["assembly_files"]["urdf"] = _write_fallback_urdf(sku_dir, cad_specs, mass_props)
    else:
        print(f"--> 🏗️  CAD Service: Generating physics URDF for {project_id} (CadQuery not installed)...")
        assets["assembly_files"]["urdf"] = _write_fallback_urdf(sku_dir, cad_specs, mass_props)

    if trimesh is not None:
        try:
            collision_manager = trimesh.collision.CollisionManager()
            prop_path = assets["individual_parts"].get("Propellers")
            if prop_path and os.path.exists(prop_path):
                prop_mesh = trimesh.load_mesh(prop_path)
                offset = (wheelbase / 2.0) * 0.70710678
                positions = [[offset, offset, 25], [-offset, offset, 25], [-offset, -offset, 25], [offset, -offset, 25]]
                for i, pos in enumerate(positions):
                    T = trimesh.transformations.translation_matrix(pos)
                    collision_manager.add_object(f"Prop_{i+1}", prop_mesh, transform=T)

                is_colliding, names = collision_manager.in_collision_internal(return_names=True)
                assets["collision_report"]["collided"] = bool(is_colliding)
                if is_colliding:
                    assets["collision_report"]["colliding_parts"] = [list(pair) for pair in names]
        except Exception:
            pass

    return assets
# --- END OF FILE app/services/cad_service.py ---