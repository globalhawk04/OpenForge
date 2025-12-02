# FILE: sim_in_isaac.py

from omni.isaac.kit import SimulationApp

# 1. Start App (Must happen before imports)
simulation_app = SimulationApp({"headless": False})

import omni
from omni.isaac.core import World
from omni.isaac.core.utils.stage import add_reference_to_stage
from omni.isaac.core.utils.viewports import set_camera_view
import os

# --- CONFIGURATION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
USD_EXPORT_DIR = os.path.join(CURRENT_DIR, "usd_export")

def main():
    world = World()
    world.scene.add_default_ground_plane()
    
    # --- 1. DYNAMIC ROBOT DISCOVERY ---
    if not os.path.exists(USD_EXPORT_DIR):
        print(f"❌ Error: Export directory not found: {USD_EXPORT_DIR}")
        simulation_app.close()
        return

    usd_files = [f for f in os.listdir(USD_EXPORT_DIR) if f.endswith(".usda")]
    
    if not usd_files:
        print(f"❌ Error: No USD files found in {USD_EXPORT_DIR}. Run forge.py first.")
        simulation_app.close()
        return

    # Sort by modification time (newest first)
    usd_files.sort(key=lambda x: os.path.getmtime(os.path.join(USD_EXPORT_DIR, x)), reverse=True)
    
    target_filename = usd_files[0]
    sku = target_filename.replace(".usda", "")
    usd_path = os.path.join(USD_EXPORT_DIR, target_filename)
    
    print(f"--> 🐕 Loading Robot: {sku}")
    print(f"    PATH: {usd_path}")

    # --- 2. ADD TO STAGE ---
    safe_sku = sku.replace("-", "_").replace(" ", "_")
    prim_path = f"/World/{safe_sku}"
    
    add_reference_to_stage(usd_path=usd_path, prim_path=prim_path)

    # Position camera for a good look
    set_camera_view(eye=[0.8, 0.8, 0.6], target=[0, 0, 0.2])
    
    world.reset()
    
    print(f"--> 🖼️  Rendering Scene. Press Ctrl+C to exit.")

    # --- 3. RENDER LOOP ---
    while simulation_app.is_running():
        # This keeps the window open and the renderer active
        # Physics (gravity) will still apply, so the robot might settle on the floor
        world.step(render=True)

    simulation_app.close()

if __name__ == "__main__":
    main()