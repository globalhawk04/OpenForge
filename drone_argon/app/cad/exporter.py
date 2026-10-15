# --- START OF FILE app/cad/exporter.py ---
import os
import cadquery as cq
from app.cad.assembly import DroneAssembler
from app.cad.frame import FrameGenerator
from app.cad.components import FlightControllerStack, Battery, Motor, Propeller


class URDFExporter:
    """
    Exports a DroneAssembler configuration to a URDF file + STL/STEP meshes.
    Uses Parallel-Axis Theorem mass & inertia properties for realistic PyBullet dynamics.
    """

    def __init__(self, assembler: DroneAssembler, mass_properties: dict | None = None):
        self.assembler = assembler
        self.specs = assembler.specs
        self.mass_properties = mass_properties or {}

    def _get_box_inertia_xml(self, shape, mass_kg: float) -> str:
        solid = shape.val()
        bb = solid.BoundingBox()
        dx = (bb.xmax - bb.xmin) / 1000.0
        dy = (bb.ymax - bb.ymin) / 1000.0
        dz = (bb.zmax - bb.zmin) / 1000.0
        ixx = (1.0 / 12.0) * mass_kg * (dy ** 2 + dz ** 2)
        iyy = (1.0 / 12.0) * mass_kg * (dx ** 2 + dz ** 2)
        izz = (1.0 / 12.0) * mass_kg * (dx ** 2 + dy ** 2)
        return f'<inertia ixx="{ixx:.8f}" ixy="0" ixz="0" iyy="{iyy:.8f}" iyz="0" izz="{izz:.8f}"/>'

    def export(self, output_dir: str = "static/urdf_test") -> str:
        os.makedirs(output_dir, exist_ok=True)
        project_name = self.specs.get("name", "drone")

        # 1. Generate Base Link Geometry (Frame + Stack + Battery + Motor Stators)
        frame = FrameGenerator(self.specs).generate()
        stack = FlightControllerStack(mounting_mm=self.specs.get("stack_mount_mm", 30.5)).build().translate((0, 0, 2))
        battery = Battery(
            cells=int(self.specs.get("battery_cells", 6)),
            capacity_mah=int(self.specs.get("battery_capacity_mah", 1300)),
        ).build().translate((0, 0, 25))

        motor_proto = Motor(
            stator_w=self.specs.get("stator_d_mm", 22),
            stator_h=self.specs.get("stator_h_mm", 7),
            mounting_mm=self.assembler.motor_mount,
        ).build()
        motor_z = self.assembler.arm_thick

        base_link = frame.union(stack).union(battery)
        offsets = [
            (self.assembler.offset, self.assembler.offset),
            (self.assembler.offset, -self.assembler.offset),
            (-self.assembler.offset, self.assembler.offset),
            (-self.assembler.offset, -self.assembler.offset),
        ]
        for x, y in offsets:
            base_link = base_link.union(motor_proto.translate((x, y, motor_z)))

        base_stl = os.path.join(output_dir, "base.stl")
        cq.exporters.export(base_link, base_stl)

        # Also export full STEP file for mechanical CAD softwares
        step_path = os.path.join(output_dir, f"{project_name}.step")
        try:
            self.assembler.build()
            self.assembler.export_step(step_path)
        except Exception:
            cq.exporters.export(base_link, step_path)

        # 2. Extract True Mass & Parallel-Axis Inertia Tensor
        total_mass_kg = float(self.specs.get("mass_kg") or self.mass_properties.get("total_mass_kg") or 0.520)
        prop_mass_kg = 0.005
        base_mass_kg = max(0.100, total_mass_kg - (4 * prop_mass_kg))

        urdf_inertia_dict = self.mass_properties.get("inertia_urdf_kg_m2")
        if urdf_inertia_dict:
            ixx = urdf_inertia_dict["ixx"]
            iyy = urdf_inertia_dict["iyy"]
            izz = urdf_inertia_dict["izz"]
            base_inertia = f'<inertia ixx="{ixx:.8f}" ixy="0" ixz="0" iyy="{iyy:.8f}" iyz="0" izz="{izz:.8f}"/>'
        else:
            base_inertia = self._get_box_inertia_xml(base_link, base_mass_kg)

        cog_m = self.mass_properties.get("cog_m", [0.0, 0.01, 0.0])
        # Map WebGL (X, Y-up, Z) to URDF (X, Y, Z-up)
        cog_urdf_str = f"{cog_m[0]:.4f} {cog_m[2]:.4f} {cog_m[1]:.4f}"

        # 3. Generate Propeller Link Mesh
        prop_shape = Propeller(diameter_inch=self.assembler.prop_diam).build()
        prop_stl = os.path.join(output_dir, "prop.stl")
        cq.exporters.export(prop_shape, prop_stl)
        prop_inertia = self._get_box_inertia_xml(prop_shape, prop_mass_kg)

        joint_z = motor_z + 25.0
        urdf_content = f"""<?xml version="1.0"?>
<robot name="{project_name}">

  <link name="base_link">
    <inertial>
      <origin rpy="0 0 0" xyz="{cog_urdf_str}"/>
      <mass value="{base_mass_kg:.4f}"/>
      {base_inertia}
    </inertial>
    <visual>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <geometry>
        <mesh filename="base.stl" scale="0.001 0.001 0.001"/>
      </geometry>
      <material name="carbon">
        <color rgba="0.18 0.18 0.20 1.0"/>
      </material>
    </visual>
    <collision>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <geometry>
        <mesh filename="base.stl" scale="0.001 0.001 0.001"/>
      </geometry>
    </collision>
  </link>
"""
        prop_names = ["prop_fl", "prop_fr", "prop_rl", "prop_rr"]
        for i, name in enumerate(prop_names):
            x, y = offsets[i]
            pos_str = f"{x / 1000.0:.5f} {y / 1000.0:.5f} {joint_z / 1000.0:.5f}"
            urdf_content += f"""
  <link name="{name}">
    <inertial>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <mass value="{prop_mass_kg:.4f}"/>
      {prop_inertia}
    </inertial>
    <visual>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <geometry>
        <mesh filename="prop.stl" scale="0.001 0.001 0.001"/>
      </geometry>
      <material name="cyan">
        <color rgba="0 0.85 0.65 0.85"/>
      </material>
    </visual>
    <collision>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <geometry>
        <cylinder length="0.008" radius="{(self.assembler.prop_diam * 0.0254) / 2.0:.4f}"/>
      </geometry>
    </collision>
  </link>

  <joint name="joint_{name}" type="continuous">
    <parent link="base_link"/>
    <child link="{name}"/>
    <origin rpy="0 0 0" xyz="{pos_str}"/>
    <axis xyz="0 0 1"/>
  </joint>
"""
        urdf_content += "</robot>\n"
        urdf_path = os.path.join(output_dir, "drone.urdf")
        with open(urdf_path, "w") as f:
            f.write(urdf_content)

        return urdf_path
# --- END OF FILE app/cad/exporter.py ---