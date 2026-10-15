import numpy as np
import pybullet as p

class PID:
    """
    Standard PID Controller.
    Output = (Kp * error) + (Ki * accumulated_error) + (Kd * delta_error)
    """
    def __init__(self, kp, ki, kd, i_limit=10.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.i_limit = i_limit
        
        self.prev_error = 0.0
        self.integral = 0.0

    def update(self, error, dt):
        # P Term
        p_term = self.kp * error
        
        # I Term
        self.integral += error * dt
        # Anti-windup clamping
        self.integral = np.clip(self.integral, -self.i_limit, self.i_limit)
        i_term = self.ki * self.integral
        
        # D Term
        delta_error = (error - self.prev_error) / dt if dt > 0 else 0
        d_term = self.kd * delta_error
        
        self.prev_error = error
        
        return p_term + i_term + d_term

    def reset(self):
        self.prev_error = 0.0
        self.integral = 0.0

class FlightController:
    """
    Simulates a Flight Controller (like Betaflight).
    Mixes Roll/Pitch/Yaw PID outputs into motor signals.
    """
    def __init__(self):
        # Tuned roughly for a standard 5" Freestyle Drone in PyBullet
        # Note: In a real simulation optimization loop, the AI would tune these!
        self.pid_roll = PID(kp=0.5, ki=0.0, kd=0.3)
        self.pid_pitch = PID(kp=0.5, ki=0.0, kd=0.3)
        self.pid_yaw = PID(kp=1.5, ki=0.0, kd=0.0)
        
        self.last_time = 0.0

    def compute_motors(self, drone_id, target_rpy, target_thrust, dt):
        """
        Args:
            drone_id: PyBullet Body ID
            target_rpy: [Roll, Pitch, Yaw] in radians (Target Angle)
            target_thrust: Float 0.0 to 1.0 (Base throttle)
            dt: Time step duration
        """
        # 1. Get Current State (IMU Sensor Simulation)
        pos, quat = p.getBasePositionAndOrientation(drone_id)
        current_rpy = p.getEulerFromQuaternion(quat)
        
        # 2. Calculate Errors
        # Error = Target - Current
        err_roll = target_rpy[0] - current_rpy[0]
        err_pitch = target_rpy[1] - current_rpy[1]
        err_yaw = target_rpy[2] - current_rpy[2]
        
        # 3. Run PID Loops
        # Note: We output 'correction' values. 
        # Positive Roll Correction -> Speed up Left motors, Slow down Right.
        corr_roll = self.pid_roll.update(err_roll, dt)
        corr_pitch = self.pid_pitch.update(err_pitch, dt)
        corr_yaw = self.pid_yaw.update(err_yaw, dt)
        
        # 4. Motor Mixing (Quad X Configuration)
        # FL (0): CW  | FR (1): CCW
        # RL (2): CCW | RR (3): CW
        
        # Standard Mixer Rules:
        # FL = Thrust + Roll + Pitch - Yaw
        # FR = Thrust - Roll + Pitch + Yaw
        # RL = Thrust + Roll - Pitch + Yaw
        # RR = Thrust - Roll - Pitch - Yaw
        
        m0 = target_thrust + corr_roll + corr_pitch - corr_yaw # FL
        m1 = target_thrust - corr_roll + corr_pitch + corr_yaw # FR
        m2 = target_thrust + corr_roll - corr_pitch + corr_yaw # RL
        m3 = target_thrust - corr_roll - corr_pitch - corr_yaw # RR
        
        # Clip to valid range [0.0, 1.0]
        motors = [
            np.clip(m0, 0.0, 1.0),
            np.clip(m1, 0.0, 1.0),
            np.clip(m2, 0.0, 1.0),
            np.clip(m3, 0.0, 1.0)
        ]
        
        return motors

# --- TEST HARNESS ---
if __name__ == "__main__":
    import time
    import os
    from app.sim.env import DroneSimulation
    from app.sim.aero import Aerodynamics
    
    print("🎮 Initializing Flight Controller Test...")
    urdf_file = os.path.abspath("static/urdf_test/drone.urdf")
    
    sim = DroneSimulation(gui=True)
    sim.setup_world()
    sim.load_drone(urdf_file)
    
    aero = Aerodynamics(max_thrust_g=1200.0) 
    fc = FlightController()
    
    try:
        print("🚁 HOVER TEST: Target Altitude...")
        
        # We need to find the "Hover Throttle" manually or via PID.
        # For a 500g drone with 4800g max thrust, hover is ~10-12% throttle.
        base_throttle = 0.11 
        
        for i in range(1000):
            # Target: Level Horizon (0,0,0)
            target_rpy = [0, 0, 0]
            
            # Run Flight Controller
            motors = fc.compute_motors(
                sim.drone_id, 
                target_rpy=target_rpy, 
                target_thrust=base_throttle, 
                dt=sim.dt
            )
            
            # Apply Physics
            aero.update(sim.drone_id, sim.prop_joints, motors)
            sim.step()
            
            # Camera Follow
            pos, _ = p.getBasePositionAndOrientation(sim.drone_id)
            p.resetDebugVisualizerCamera(1.0, 45, -20, pos)
            
            time.sleep(1./240.)
            
            if i % 100 == 0:
                print(f"   Step {i}: Height={pos[2]:.2f}m | Motors={np.round(motors, 2)}")
            
    except KeyboardInterrupt:
        sim.close()