import pybullet as p
import numpy as np

class Aerodynamics:
    """
    Simulates the forces of air acting on the drone.
    1. Propeller Thrust (F = k * rpm^2)
    2. Reaction Torque (Yaw)
    3. Linear Drag (Air Resistance)
    """
    def __init__(self, max_thrust_g=1200.0, num_motors=4):
        # Convert grams to Newtons (1000g ~= 9.8N)
        self.max_thrust_n = (max_thrust_g / 1000.0) * 9.8
        
        # Physics Coefficients
        self.drag_coeff_xy = 0.5  # Drag when moving sideways
        self.drag_coeff_z = 1.0   # Drag when falling/climbing (flat plate)
        self.torque_ratio = 0.02  # Relationship between Thrust and Yaw Torque
        
        # Propeller Spin Directions (Standard Betaflight Quad X)
        # 0: FL (CW), 1: FR (CCW), 2: RL (CCW), 3: RR (CW)
        # Note: Directions depend on your specific build order, 
        # but opposing pairs must spin opposite ways to cancel yaw.
        self.spin_dirs = [-1, 1, 1, -1]

    def update(self, drone_id, prop_links, motor_inputs):
        """
        Apply forces for a single simulation step.
        
        Args:
            drone_id: PyBullet body ID
            prop_links: List of joint indices for the 4 props
            motor_inputs: List of 4 floats [0.0 to 1.0] (Throttle % per motor)
        """
        if len(motor_inputs) != 4:
            return

        # 1. Apply Global Drag (Wind Resistance)
        # Get Velocity in World coordinates
        lin_vel, _ = p.getBaseVelocity(drone_id)
        vx, vy, vz = lin_vel
        
        # Force is opposite to velocity: F = -C * v
        drag_x = -self.drag_coeff_xy * vx * abs(vx) # Quadratic drag
        drag_y = -self.drag_coeff_xy * vy * abs(vy)
        drag_z = -self.drag_coeff_z  * vz * abs(vz)
        
        # Apply to Center of Mass
        p.applyExternalForce(
            drone_id, 
            -1, # -1 = Base Link
            forceObj=[drag_x, drag_y, drag_z], 
            posObj=[0, 0, 0], 
            flags=p.LINK_FRAME
        )

        # 2. Apply Motor Thrust & Torque
        for i, link_idx in enumerate(prop_links):
            throttle = np.clip(motor_inputs[i], 0.0, 1.0)
            
            # Thrust Formula: F_max * throttle^2
            thrust_n = self.max_thrust_n * (throttle ** 2)
            
            # Apply Thrust Vector (Upwards relative to the prop)
            # [0, 0, thrust] applies force along the Z-axis of the PROP LINK
            p.applyExternalForce(
                drone_id,
                link_idx,
                forceObj=[0, 0, thrust_n],
                posObj=[0, 0, 0], # At the origin of the prop link
                flags=p.LINK_FRAME
            )
            
            # Apply Yaw Torque (Reaction force on the frame)
            # If prop spins CW (-1), torque on frame is CCW (+1)
            torque_z = thrust_n * self.torque_ratio * -self.spin_dirs[i]
            
            p.applyExternalTorque(
                drone_id,
                link_idx,
                torqueObj=[0, 0, torque_z],
                flags=p.LINK_FRAME
            )
            
            # 3. Visuals: Spin the prop mesh
            # We use VELOCITY_CONTROL to make them look like they are spinning
            visual_rpm = throttle * 100 # Arbitrary speed for visual effect
            p.setJointMotorControl2(
                drone_id,
                link_idx,
                controlMode=p.VELOCITY_CONTROL,
                targetVelocity=self.spin_dirs[i] * visual_rpm * 50,
                force=0.5 # Weak force, just for visuals
            )

# --- TEST HARNESS ---
if __name__ == "__main__":
    import time
    import os
    from app.sim.env import DroneSimulation
    
    print("💨 Initializing Aerodynamics Test...")
    urdf_file = os.path.abspath("static/urdf_test/drone.urdf")
    
    sim = DroneSimulation(gui=True)
    sim.setup_world()
    sim.load_drone(urdf_file)
    
    # Initialize Physics Model
    # 500g drone, 1200g thrust per motor -> ~2.4kg total thrust -> 4.8:1 TWR (Rocket ship)
    aero = Aerodynamics(max_thrust_g=1200.0) 
    
    try:
        print("🚀 TEST: Applying 40% Throttle...")
        print("   Observation: Drone should lift off gently.")
        
        for i in range(1000):
            # Throttle sequence
            if i < 100: throttle = 0.0      # Warmup
            elif i < 500: throttle = 0.35   # Hover attempt (approx 500g weight / 4800g thrust ~ 10-15%)
            else: throttle = 0.0            # Cut engines (Drop)
            
            inputs = [throttle] * 4
            
            # Run Physics
            aero.update(sim.drone_id, sim.prop_joints, inputs)
            sim.step()
            
            # Camera Follow
            pos, _ = p.getBasePositionAndOrientation(sim.drone_id)
            p.resetDebugVisualizerCamera(1.0, 45, -20, pos)
            
            time.sleep(1./240.)
            
    except KeyboardInterrupt:
        sim.close()