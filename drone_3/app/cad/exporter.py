import os
import cadquery as cq
from app.cad.assembly import DroneAssembler

class URDFExporter:
    """
    Exports a DroneAssembler configuration to a URDF file + STL meshes.
    Handles unit conversion (mm -> meters) for Physics.
    """
    def __init__(self, assembler: DroneAssembler):
        self.assembler = assembler
        self.specs = assembler.specs
        
    def _get_inertia_xml(self, shape, mass_kg):
        """Calculates approximate inertia tensor from bounding box."""
        # Extract the underlying Solid from the Workplane
        solid = shape.val()
        bb = solid.BoundingBox()
        
        # Dimensions in METERS for physics calculation
        dx = (bb.xmax - bb.xmin) / 1000.0 
        dy = (bb.ymax - bb.ymin) / 1000.0
        dz = (bb.zmax - bb.zmin) / 1000.0
        
        # Solid Box Inertia Formula
        ixx = (1/12.0) * mass_kg * (dy**2 + dz**2)
        iyy = (1/12.0) * mass_kg * (dx**2 + dz**2)
        izz = (1/12.0) * mass_kg * (dx**2 + dy**2)
        
        return f'<inertia ixx="{ixx:.8f}" ixy="0" ixz="0" iyy="{iyy:.8f}" iyz="0" izz="{izz:.8f}"/>'

    def export(self, output_dir="static/urdf_test"):
        print(f"   📂 Exporting Simulation Assets to: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)
        project_name = self.specs.get("name", "drone")
        
        # --- 1. GENERATE BASE LINK (Static Parts) ---
        print("   🔨 fusing_base_link...")
        
        # Frame
        from app.cad.frame import FrameGenerator
        frame = FrameGenerator(self.specs).generate()
        
        # Stack (Center)
        from app.cad.components import FlightControllerStack, Battery, Motor
        stack = FlightControllerStack().build().translate((0,0,2))
        battery = Battery().build().translate((0,0,25))
        
        # Motors (Static Bases)
        motor_proto = Motor(mounting_mm=self.assembler.motor_mount).build()
        motor_z = self.assembler.arm_thick
        
        # Fuse Everything
        base_link = frame.union(stack).union(battery)
        
        offsets = [
            (self.assembler.offset, self.assembler.offset),
            (self.assembler.offset, -self.assembler.offset),
            (-self.assembler.offset, self.assembler.offset),
            (-self.assembler.offset, -self.assembler.offset)
        ]
        
        for x, y in offsets:
            m = motor_proto.translate((x, y, motor_z))
            base_link = base_link.union(m)

        # Export Base Mesh
        base_stl = os.path.join(output_dir, "base.stl")
        cq.exporters.export(base_link, base_stl)
        
        # Calc Base Mass (kg)
        base_mass_kg = 0.450 # 450g Frame+Electronics
        base_inertia = self._get_inertia_xml(base_link, base_mass_kg)

        # --- 2. GENERATE PROP LINK (Moving Parts) ---
        print("   💨 generating_propellers...")
        from app.cad.components import Propeller
        prop_shape = Propeller(diameter_inch=self.assembler.prop_diam).build()
        
        prop_stl = os.path.join(output_dir, "prop.stl")
        cq.exporters.export(prop_shape, prop_stl)
        
        prop_mass_kg = 0.004 # 4g per prop
        prop_inertia = self._get_inertia_xml(prop_shape, prop_mass_kg)

        # --- 3. WRITE URDF XML ---
        print("   📝 writing_urdf_definition...")
        
        # Z-height where prop sits (Arm + Motor Height)
        joint_z = motor_z + 25.0 
        
        # CRITICAL FIX: scale="0.001 0.001 0.001"
        # This tells PyBullet: "The STL is in mm, please shrink it to meters"
        urdf_content = f"""<?xml version="1.0"?>
<robot name="{project_name}">

  <link name="base_link">
    <inertial>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <mass value="{base_mass_kg}"/>
      {base_inertia}
    </inertial>
    <visual>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <geometry>
        <mesh filename="base.stl" scale="0.001 0.001 0.001"/> 
      </geometry>
      <material name="grey">
        <color rgba="0.2 0.2 0.2 1.0"/>
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
        locs = [
            (self.assembler.offset, self.assembler.offset),   # FL
            (self.assembler.offset, -self.assembler.offset),  # FR
            (-self.assembler.offset, self.assembler.offset),  # RL
            (-self.assembler.offset, -self.assembler.offset)  # RR
        ]

        for i, name in enumerate(prop_names):
            x, y = locs[i]
            
            # Convert joint location to METERS
            pos_str = f"{x/1000.0} {y/1000.0} {joint_z/1000.0}"
            
            urdf_content += f"""
  <link name="{name}">
    <inertial>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <mass value="{prop_mass_kg}"/>
      {prop_inertia}
    </inertial>
    <visual>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <geometry>
        <mesh filename="prop.stl" scale="0.001 0.001 0.001"/>
      </geometry>
      <material name="cyan">
        <color rgba="0 0.8 0.8 1.0"/>
      </material>
    </visual>
    <collision>
      <origin rpy="0 0 0" xyz="0 0 0"/>
      <geometry>
        <cylinder length="0.01" radius="{self.assembler.prop_diam * 0.0254 / 2}"/>
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

        urdf_content += "</robot>"

        urdf_path = os.path.join(output_dir, "drone.urdf")
        with open(urdf_path, "w") as f:
            f.write(urdf_content)
            
        return urdf_path