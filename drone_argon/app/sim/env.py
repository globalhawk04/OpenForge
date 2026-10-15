import pybullet as p
import pybullet_data
import time
import os
import numpy as np

class DroneSimulation:
    """
    The Physics Sandbox.
    Wraps PyBullet to provide a clean interface for loading drones and running steps.
    """
    def __init__(self, gui=False):
        # connect(p.GUI) opens the 3D window, p.DIRECT is headless (faster)
        self.client = p.connect(p.GUI if gui else p.DIRECT)
        
        # Add default assets (like the ground plane)
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        
        self.drone_id = None
        self.dt = 1.0 / 240.0 # PyBullet default timestep
        
    def setup_world(self):
        """Sets gravity and loads the floor."""
        p.resetSimulation()
        p.setGravity(0, 0, -9.81)
        
        # Load the checkerboard floor
        self.plane_id = p.loadURDF("plane.urdf")
        
        # Set nice debug camera angle
        p.resetDebugVisualizerCamera(
            cameraDistance=1.5,
            cameraYaw=45,
            cameraPitch=-30,
            cameraTargetPosition=[0, 0, 0]
        )

    def load_drone(self, urdf_path, start_pos=[0, 0, 0.1]):
        """
        Loads the generated drone URDF.
        """
        if not os.path.exists(urdf_path):
            raise FileNotFoundError(f"URDF not found at: {urdf_path}")
        
        start_orientation = p.getQuaternionFromEuler([0, 0, 0])
        
        # Load the Robot
        # flags=p.URDF_USE_INERTIA_FROM_FILE is critical! 
        # Otherwise PyBullet re-calculates inertia based on the visual mesh volume, which is wrong.
        self.drone_id = p.loadURDF(
            urdf_path, 
            start_pos, 
            start_orientation,
            flags=p.URDF_USE_INERTIA_FROM_FILE
        )
        
        # Force visual colors (sometimes STL import loses color info)
        p.changeVisualShape(self.drone_id, -1, rgbaColor=[0.2, 0.2, 0.2, 1]) # Body Dark Grey
        
        # Scan joints to identify propellers
        self.prop_joints = []
        num_joints = p.getNumJoints(self.drone_id)
        
        print(f"   > Loaded Drone ID: {self.drone_id}. Joints found: {num_joints}")
        
        for i in range(num_joints):
            info = p.getJointInfo(self.drone_id, i)
            joint_name = info[1].decode('utf-8')
            print(f"     - Joint {i}: {joint_name}")
            
            # If it's a propeller joint, store the index for later control
            if "prop" in joint_name or "joint_" in joint_name:
                self.prop_joints.append(i)
                # Color props Cyan
                p.changeVisualShape(self.drone_id, i, rgbaColor=[0, 0.8, 0.8, 1])

    def step(self):
        """Advances the simulation by one tick."""
        p.stepSimulation()

    def close(self):
        p.disconnect()

# --- TEST HARNESS ---
if __name__ == "__main__":
    # Test loading the drone generated in the previous step
    # Note: We use the 'static/urdf_test' path from Task 1.4
    urdf_file = os.path.abspath("static/urdf_test/drone.urdf")
    
    print(f"🌍 Initializing Physics World...")
    sim = DroneSimulation(gui=True)
    sim.setup_world()
    
    try:
        print(f"🚁 Loading Drone from: {urdf_file}")
        sim.load_drone(urdf_file)
        
        print("✅ Simulation Running. You should see a drone on the ground.")
        print("   (It will fall slightly because physics is ON).")
        print("   Press Ctrl+C to exit.")
        
        while True:
            sim.step()
            time.sleep(1./240.) # Sync to real-time for viewing
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping Simulation.")
        sim.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        sim.close()
