import cadquery as cq
import math

class FrameGenerator:
    """
    Parametric Frame Designer.
    Generates a Unibody 'True-X' or 'Squashed-X' frame.
    """
    def __init__(self, specs: dict):
        """
        Args:
            specs (dict): Contains:
                - wheelbase_mm: Diagonal distance motor-to-motor
                - motor_mount_mm: 9.0, 12.0, 16.0, 19.0
                - stack_mount_mm: 20.0, 25.5, 30.5
                - arm_thickness_mm: 3.0 to 6.0
        """
        self.wb = float(specs.get('wheelbase_mm', 225))
        self.motor_mount = float(specs.get('motor_mount_mm', 16.0))
        self.stack_mount = float(specs.get('stack_mount_mm', 30.5))
        self.thick = float(specs.get('arm_thickness_mm', 4.0))
        
        self.shape = None
        self.color = (0.1, 0.1, 0.1) # Carbon Fiber Black

    def generate(self):
        """Builds the geometry."""
        
        # 1. Calculate Arm Geometry
        # In a True-X, the arm angle is 45 degrees.
        # Distance from center to motor shaft = Wheelbase / 2
        radius = self.wb / 2.0
        
        # 2. Create the Center Bus (Main Body)
        # Size it to fit the stack + some protection
        body_w = self.stack_mount + 20
        center_plate = (
            cq.Workplane("XY")
            .box(body_w, body_w, 2.0) # Top/Bottom plates are usually 2mm
        )

        # 3. Create One Arm (The "Template")
        # We model the arm pointing EAST (0 degrees), then rotate it.
        arm_len = radius + 15 # Extend past motor for bumper protection
        arm_width = max(10, self.motor_mount - 2) # Adaptive width
        
        arm = (
            cq.Workplane("XY")
            .box(arm_len, arm_width, self.thick)
            .translate((arm_len/2, 0, 0)) # Shift so origin is at one end
        )
        
        # 4. Pattern the Arms (The "X" Shape)
        # We need 4 arms at 45, 135, 225, 315 degrees
        arms = (
            arm.rotate((0,0,0), (0,0,1), 45)
            .union(arm.rotate((0,0,0), (0,0,1), 135))
            .union(arm.rotate((0,0,0), (0,0,1), 225))
            .union(arm.rotate((0,0,0), (0,0,1), 315))
        )
        
        # Fuse Arms to Center Plate
        frame = center_plate.union(arms)
        
        # 5. The Drilling Operation (Subtractive Manufacturing)
        
        # A. Stack Holes (Center)
        stack_holes = (
            cq.Workplane("XY")
            .rect(self.stack_mount, self.stack_mount, forConstruction=True)
            .vertices()
            .circle(1.6) # M3 screw clearance
            .extrude(100) # Cut through everything
        )
        frame = frame.cut(stack_holes)
        
        # B. Motor Holes (Tips of Arms)
        # We need to calculate the (X,Y) coords of the 4 motors
        # x = radius * cos(45), y = radius * sin(45)
        offset = radius * 0.70710678 # cos(45)
        
        # Create a drilling tool at the motor position
        motor_drill = (
            cq.Workplane("XY")
            .rect(self.motor_mount, self.motor_mount, forConstruction=True)
            .vertices()
            .circle(1.6) # M3 screw hole
            .extrude(100)
        )
        
        # Apply drill to all 4 corners
        for x_mod in [1, -1]:
            for y_mod in [1, -1]:
                driller = motor_drill.translate((offset * x_mod, offset * y_mod, 0))
                frame = frame.cut(driller)
                
                # C. Motor Center Hole (Shaft/Clip clearance)
                center_drill = (
                    cq.Workplane("XY")
                    .circle(3.0) # 6mm diameter hole for shaft
                    .extrude(100)
                    .translate((offset * x_mod, offset * y_mod, 0))
                )
                frame = frame.cut(center_drill)

        # 6. Final Polish (Fillets)
        # Filleting complex unions can be fragile in CAD kernels. 
        # We wrap in try/except or skip for speed. 
        # frame = frame.edges("|Z").fillet(1.0) 
        
        self.shape = frame
        return self.shape

    def export_stl(self, filename):
        if self.shape:
            cq.exporters.export(self.shape, filename)

# --- TEST HARNESS ---
if __name__ == "__main__":
    print("🚜 Generating Procedural Frame...")
    
    # Simulate a 5-inch Freestyle Spec
    specs = {
        "wheelbase_mm": 225,
        "motor_mount_mm": 16.0, # Standard 2207 mount
        "stack_mount_mm": 30.5, # Standard Stack
        "arm_thickness_mm": 5.0
    }
    
    fg = FrameGenerator(specs)
    fg.generate()
    fg.export_stl("test_frame.stl")
    
    print(f"✅ Frame Generated: Wheelbase={specs['wheelbase_mm']}mm")
    print("   Check 'test_frame.stl' in your folder.")