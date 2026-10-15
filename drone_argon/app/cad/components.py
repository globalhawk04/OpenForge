import cadquery as cq
import math

class DroneComponent:
    """Base class for all drone parts."""
    def __init__(self):
        self.shape = None
        self.mass_g = 0
        self.color = (0.5, 0.5, 0.5) # Default Grey

    def build(self) -> cq.Workplane:
        raise NotImplementedError

    def get_step_export(self, filename):
        if self.shape:
            cq.exporters.export(self.shape, filename)

class Motor(DroneComponent):
    """
    Parametric Brushless Motor.
    Generates a Bell, Base, and Shaft based on stator size.
    """
    def __init__(self, stator_w=22, stator_h=7, kv=1700, mounting_mm=16):
        super().__init__()
        self.stator_w = float(stator_w)
        self.stator_h = float(stator_h)
        self.mounting_mm = float(mounting_mm)
        self.kv = kv
        self.color = (0.2, 0.2, 0.2) # Dark Grey/Black
        self.build()

    def build(self):
        # Estimates based on standard motor geometry
        bell_diam = self.stator_w + 5  # Bell is wider than stator
        bell_height = self.stator_h + 6
        shaft_diam = 5 if self.stator_w >= 22 else 1.5
        
        # 1. The Base (Static part)
        base = (
            cq.Workplane("XY")
            .circle(bell_diam / 2)
            .extrude(3) # Base thickness
        )
        
        # 2. Mounting Holes (Cutout)
        hole_pattern = (
            cq.Workplane("XY")
            .rect(self.mounting_mm, self.mounting_mm, forConstruction=True)
            .vertices()
            .circle(1.5) # M3 screw hole radius
            .extrude(3)
        )
        base = base.cut(hole_pattern)

        # 3. The Bell (Rotating part - visual only for now)
        bell = (
            cq.Workplane("XY")
            .workplane(offset=3.5) # Gap above base
            .circle(bell_diam / 2)
            .extrude(bell_height)
        )
        
        # 4. The Shaft
        shaft = (
            cq.Workplane("XY")
            .circle(shaft_diam / 2)
            .extrude(bell_height + 15) # Stick out top and bottom
        )

        # Union all parts
        self.shape = base.union(bell).union(shaft)
        return self.shape

class Propeller(DroneComponent):
    """
    Parametric Propeller.
    Represents the SWEPT VOLUME (Cylinder) for collision checking.
    """
    def __init__(self, diameter_inch=5.0, pitch=4.3, blade_count=3):
        super().__init__()
        self.diam_mm = float(diameter_inch) * 25.4
        self.height_mm = float(pitch) * 2.5 # Rough approximation of vertical profile
        self.color = (0.0, 0.8, 0.8, 0.5) # Cyan, Semi-transparent
        self.build()

    def build(self):
        # We generate a cylinder representing the danger zone/air displacement
        self.shape = (
            cq.Workplane("XY")
            .circle(self.diam_mm / 2)
            .extrude(8) # Hub thickness / Vertical profile
        )
        # Add a center hole for the shaft
        shaft_cut = (
             cq.Workplane("XY")
             .circle(2.6) # 5mm shaft clearance
             .extrude(10)
        )
        self.shape = self.shape.cut(shaft_cut)
        return self.shape

class FlightControllerStack(DroneComponent):
    """
    Parametric FC/ESC Stack.
    Generates a tower of electronics.
    """
    def __init__(self, mounting_mm=30.5, layers=2):
        super().__init__()
        self.mounting = float(mounting_mm)
        self.layers = layers
        self.color = (0.1, 0.1, 0.8) # Blue PCB
        self.build()

    def build(self):
        board_size = self.mounting + 8 # PCB is usually larger than hole pattern
        
        # Base ESC
        esc = (
            cq.Workplane("XY")
            .box(board_size, board_size, 4) # 4mm thick
        )
        
        # FC on top
        fc = (
            cq.Workplane("XY")
            .workplane(offset=8) # Spacing
            .box(board_size, board_size, 2)
        )
        
        # Mounting Holes
        holes = (
            cq.Workplane("XY")
            .rect(self.mounting, self.mounting, forConstruction=True)
            .vertices()
            .circle(1.6) # M3
            .extrude(15)
        )
        
        stack = esc.union(fc).cut(holes)
        self.shape = stack
        return self.shape

class Battery(DroneComponent):
    """
    Parametric Lipo Battery.
    """
    def __init__(self, cells=6, capacity_mah=1300):
        super().__init__()
        self.cells = int(cells)
        self.mah = int(capacity_mah)
        self.color = (0.9, 0.9, 0.1) # Yellow wrapper
        self.build()

    def build(self):
        # Heuristic dimensions based on cell count and capacity
        # 1 cell approx 8mm thick.
        # 1000mah approx 35mm wide, 70mm long.
        
        length = 75 * (self.mah / 1300)
        width = 35 * (self.mah / 1300)
        height = self.cells * 8.0 
        
        self.shape = (
            cq.Workplane("XY")
            .box(length, width, height)
        )
        return self.shape

# --- TEST HARNESS ---
if __name__ == "__main__":
    # If run directly, generate a test motor STL
    print("Generating Test Artifacts...")
    
    m = Motor(stator_w=22, stator_h=7, mounting_mm=16)
    cq.exporters.export(m.shape, "test_motor.stl")
    print("✅ Saved test_motor.stl")
    
    p = Propeller(diameter_inch=5)
    cq.exporters.export(p.shape, "test_prop.stl")
    print("✅ Saved test_prop.stl")