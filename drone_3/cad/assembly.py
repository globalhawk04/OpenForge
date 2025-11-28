import cadquery as cq
from app.cad.components import Motor, Propeller, FlightControllerStack, Battery
from app.cad.frame import FrameGenerator

class DroneAssembler:
    """
    Virtual Assembler.
    Combines Frame, Motors, Props, and Electronics into a single CAD assembly.
    """
    def __init__(self, specs: dict):
        self.specs = specs
        self.assembly = cq.Assembly()
        
        # Extract critical dimensions
        self.wb = float(specs.get('wheelbase_mm', 225))
        self.arm_thick = float(specs.get('arm_thickness_mm', 4.0))
        self.prop_diam = float(specs.get('prop_diameter_inch', 5.0))
        self.motor_mount = float(specs.get('motor_mount_mm', 16.0))
        
        # Calculate motor positions (True-X Geometry)
        # Distance from center to motor shaft
        self.radius = self.wb / 2.0
        # X/Y offset for 45 degree arms
        self.offset = self.radius * 0.70710678 

    def build(self):
        """Constructs the full assembly hierarchy."""
        
        # 1. Generate & Add Frame (The Anchor)
        fg = FrameGenerator(self.specs)
        frame_shape = fg.generate()
        
        self.assembly.add(
            frame_shape, 
            name="chassis", 
            color=cq.Color(0.1, 0.1, 0.1, 1.0) # Black Carbon
        )

        # 2. Instantiate Components
        # We create ONE instance of each and copy it (efficient)
        motor_comp = Motor(mounting_mm=self.motor_mount)
        prop_comp = Propeller(diameter_inch=self.prop_diam)
        stack_comp = FlightControllerStack(mounting_mm=self.specs.get('stack_mount_mm', 30.5))
        batt_comp = Battery(cells=6, capacity_mah=1300)

        # 3. Place Motors & Props (FL, FR, RL, RR)
        # Z-Position: Sit on top of the arm
        motor_z = self.arm_thick
        # Prop Z-Position: Sit on top of motor shaft (approx 25mm up)
        prop_z = motor_z + 25.0 

        locations = [
            ("motor_fl", self.offset, self.offset),   # Front Left
            ("motor_fr", self.offset, -self.offset),  # Front Right
            ("motor_rl", -self.offset, self.offset),  # Rear Left
            ("motor_rr", -self.offset, -self.offset), # Rear Right
        ]

        for name, x, y in locations:
            # Add Motor
            self.assembly.add(
                motor_comp.shape,
                name=name,
                loc=cq.Location(cq.Vector(x, y, motor_z)),
                color=cq.Color(0.2, 0.2, 0.2)
            )
            
            # Add Prop (Visual Only - in Physics we simulate them)
            # We color props differently to distinguish front/back
            p_color = cq.Color(0, 1, 1, 0.5) if "f" in name else cq.Color(1, 0, 1, 0.5)
            
            self.assembly.add(
                prop_comp.shape,
                name=name.replace("motor", "prop"),
                loc=cq.Location(cq.Vector(x, y, prop_z)),
                color=p_color
            )

        # 4. Place Stack (Center)
        self.assembly.add(
            stack_comp.shape,
            name="fc_stack",
            loc=cq.Location(cq.Vector(0, 0, 2.0)), # Sit on bottom plate (2mm)
            color=cq.Color(0.1, 0.1, 0.9)
        )

        # 5. Place Battery (Top Mount)
        # Sit on top of the top plate (assume top plate is at Z=20mm for a standard frame)
        top_plate_height = 25.0 
        self.assembly.add(
            batt_comp.shape,
            name="battery",
            loc=cq.Location(cq.Vector(0, 0, top_plate_height)),
            color=cq.Color(0.9, 0.9, 0.1)
        )

        return self.assembly

    def export_step(self, filename):
        """Export to Standard STEP format for Pro CAD (SolidWorks/Fusion360)"""
        self.assembly.save(filename, exportType="STEP")

# --- TEST HARNESS ---
if __name__ == "__main__":
    print("🏭 Assembling Digital Twin...")
    
    specs = {
        "wheelbase_mm": 225,
        "motor_mount_mm": 16.0,
        "stack_mount_mm": 30.5,
        "arm_thickness_mm": 5.0,
        "prop_diameter_inch": 5.0
    }
    
    assembler = DroneAssembler(specs)
    assembler.build()
    
    # Export as STEP (Best for geometry checking)
    assembler.export_step("full_drone.step")
    print("✅ Saved 'full_drone.step'")
    print("   Open this in FreeCAD, Fusion360, or a Web STEP Viewer.")