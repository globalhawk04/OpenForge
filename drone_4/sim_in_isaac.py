# FILE: tools/sim_in_isaac.py
from omni.isaac.kit import SimulationApp

# 1. Launch Isaac Sim (Headless=False to see it)
simulation_app = SimulationApp({"headless": False})

import omni
import carb
from omni.isaac.core import World
from omni.isaac.core.objects import GroundPlane
from omni.isaac.core.prims import RigidPrim
from omni.isaac.core.utils.stage import add_reference_to_stage
from pxr import Gf, UsdPhysics
import json
import os
import numpy as np

# CONFIG
CATALOG_FILE = "drone_catalog.json"
USD_EXPORT_DIR = os.path.abspath("usd_export")

def load_catalog():
    with open(CATALOG_FILE, "r") as f: return json.load(f)

def main():
    # 2. Setup World
    world = World()
    world.scene.add_default_ground_plane()
    
    # Lighting
    # (Isaac usually has a default HDRI, but we can add a sun)
    
    # 3. Load Drone Data
    catalog = load_catalog()
    if not catalog: return
    drone_data = catalog[0] # Load first drone for demo
    sku = drone_data['sku_id']
    usd_path = os.path.join(USD_EXPORT_DIR, f"{sku}.usda")
    
    if not os.path.exists(usd_path):
        print(f"❌ USD not found at {usd_path}. Run isaac_service first.")
        return

    # 4. Spawn Drone into World
    drone_prim_path = "/World/Drone"
    add_reference_to_stage(usd_path=usd_path, prim_path=drone_prim_path)
    
    # Wrap it as a RigidPrim to apply forces
    drone = RigidPrim(prim_path=drone_prim_path, name="drone_body")
    world.scene.add(drone)

    # 5. Physics Parameters
    phys_config = drone_data['technical_data']['physics_config']
    mass_kg = phys_config['mass_kg']
    max_thrust_n = phys_config['motor_max_force_n']
    
    # Reset Position
    drone.set_world_pose(position=np.array([0, 0, 1.0])) # Z-up 1 meter

    # 6. Simulation Loop
    world.reset()
    
    # Simple Controller State
    throttle = 0.0
    
    print("🚀 ISAAC SIM LAUNCHED. Press PLAY in the Viewport.")
    
    while simulation_app.is_running():
        # Step Physics
        world.step(render=True)
        
        # --- SIMPLE FLIGHT CONTROLLER LOGIC ---
        # (In a real app, integrate a PID controller here)
        
        # Hover Logic (Counteract Gravity)
        # Force = Mass * Gravity
        hover_force = mass_kg * 9.81
        
        # Apply Force to Center of Mass
        # Note: In Isaac, apply_force is global or local.
        # We want Local Z-Up force (Thrust).
        
        # Let's just make it hover + sine wave bobbing
        import time
        bob = math.sin(time.time() * 2) * 2.0
        current_thrust = hover_force + bob
        
        # Apply Force (Z-axis is index 2)
        # Apply at position (0,0,0) relative to body (COM)
        drone.apply_forces(np.array([[0, 0, current_thrust]]), is_global=False)
        
        # Visuals: Rotate props? 
        # (Requires accessing Xformable of prop prims, omitted for brevity V1)

    simulation_app.close()

if __name__ == "__main__":
    main()