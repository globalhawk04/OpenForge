import time
import numpy as np
import pybullet as p
import os
from app.sim.env import DroneSimulation
from app.sim.aero import Aerodynamics
from app.sim.pid import FlightController

class FlightTestRunner:
    """
    Automated Test Pilot.
    Runs specific flight scenarios and captures telemetry + video.
    """
    def __init__(self, urdf_path, max_thrust_g=1200.0, gui=False):
        self.urdf_path = urdf_path
        self.max_thrust_g = max_thrust_g
        self.gui = gui
        
        # Telemetry Log
        self.log = {
            "time": [],
            "height": [],
            "throttle_avg": [],
            "events": []
        }
    def run_acrobatic_show(self, duration_sec=15.0, video_filename="stunt_show.mp4"):
        """
        Scenario 2: The Air Show.
        Hover -> Forward -> Barrel Roll -> Backward -> Loop-de-Loop.
        """
        print(f"🎪 Starting ACROBATIC SHOW ({duration_sec}s)...")
        
        sim = DroneSimulation(gui=self.gui)
        sim.setup_world()
        
        # Spawn high enough to do a loop without hitting the floor
        sim.load_drone(self.urdf_path, start_pos=[0, 0, 1.5])
        
        video_log_id = None
        if self.gui and video_filename:
            print(f"🎥 Recording Stunts to: {video_filename}")
            video_log_id = p.startStateLogging(p.STATE_LOGGING_VIDEO_MP4, video_filename)
        
        aero = Aerodynamics(max_thrust_g=self.max_thrust_g)
        fc = FlightController()
        
        sim_t = 0
        steps = int(duration_sec * 240)
        
        # State Variables
        kp_alt = 0.6
        target_z = 1.5
        
        print("   > T=0.0s: Warmup & Hover")
        
        try:
            for i in range(steps):
                # 1. Telemetry
                pos, quat = p.getBasePositionAndOrientation(sim.drone_id)
                current_z = pos[2]
                rpy = p.getEulerFromQuaternion(quat) # [Roll, Pitch, Yaw]
                
                # Default Control Mode: STABILIZED (PID)
                mode = "PID"
                target_rpy = [0, 0, 0]
                error_z = target_z - current_z
                # Base throttle logic for altitude hold
                base_throttle = 0.05 + (kp_alt * error_z)
                base_throttle = np.clip(base_throttle, 0.0, 1.0)

                # --- THE STUNT SCRIPT ---
                
                # A. Fly Forward (T=2s to T=4s)
                if 2.0 < sim_t < 4.0:
                    if abs(sim_t - 2.0) < 0.01: print("   > T=2.0s: Pitch Forward (Advance)")
                    target_rpy = [0, -0.3, 0] # Pitch down 0.3 rad (~17 deg)
                    base_throttle += 0.05 # Add power to maintain altitude while tilted

                # B. Brake & Hover (T=4s to T=5s)
                elif 4.0 < sim_t < 5.0:
                    target_rpy = [0, 0.2, 0] # Pitch back slightly to brake

                # C. Barrel Roll (T=5s to T=5.8s) - MANUAL OVERRIDE
                elif 5.0 < sim_t < 5.8:
                    if abs(sim_t - 5.0) < 0.01: print("   > T=5.0s: 🌪️ BARREL ROLL!")
                    mode = "MANUAL"
                    # Full Left Roll: Left motors low, Right motors high
                    # Plus extra throttle to not drop
                    # FL(0), FR(1), RL(2), RR(3)
                    # To Roll Right: Speed up Left (0,2), Slow Right (1,3)
                    override_motors = [0.1, 0.9, 0.1, 0.9] 

                # D. Stabilize (T=5.8s to T=7s)
                elif 5.8 < sim_t < 7.0:
                    pass # Default PID Hover

                # E. Fly Backward (T=7s to T=9s)
                elif 7.0 < sim_t < 9.0:
                    if abs(sim_t - 7.0) < 0.01: print("   > T=7.0s: Fly Backward (Retreat)")
                    target_rpy = [0, 0.3, 0] # Pitch up/back
                    base_throttle += 0.05

                # F. Loop-de-Loop (T=10s to T=11s) - MANUAL OVERRIDE
                elif 10.0 < sim_t < 11.0:
                    if abs(sim_t - 10.0) < 0.01: print("   > T=10.0s: ➰ LOOP-DE-LOOP!")
                    mode = "MANUAL"
                    # To Loop (Pitch Back hard):
                    # Front motors (0,1) HIGH, Rear motors (2,3) LOW
                    override_motors = [1.0, 1.0, 0.0, 0.0] 

                # G. Recover (T=11s+)
                else:
                    target_z = 1.5 # Ensure we go back to height

                # --- CONTROL MIXER ---
                if mode == "PID":
                    motors = fc.compute_motors(sim.drone_id, target_rpy, base_throttle, sim.dt)
                else:
                    motors = override_motors # Raw "Acro" input

                # Physics Update
                aero.update(sim.drone_id, sim.prop_joints, motors)
                sim.step()
                sim_t += sim.dt
                
                # Camera Tracking (Third Person)
                if self.gui:
                    # Offset camera behind the drone
                    p.resetDebugVisualizerCamera(1.5, -45, -20, pos)
                    time.sleep(1./240.)

        except Exception as e:
            print(f"❌ Sim Error: {e}")
        finally:
            if video_log_id is not None:
                p.stopStateLogging(video_log_id)
        
        # Return sim for inspection
        return {"status": "COMPLETE", "video_path": video_filename, "sim_instance": sim}
    def run_hover_test(self, duration_sec=5.0, target_height=1.0, video_filename="flight_record.mp4"):
        """
        Scenario 1: Stability Check.
        Returns the simulation object so the window can be kept open.
        """
        print(f"🧪 Starting HOVER Test ({duration_sec}s target {target_height}m)...")
        
        sim = DroneSimulation(gui=self.gui)
        sim.setup_world()
        
        # --- FIX 1: SAFER SPAWN HEIGHT ---
        # Spawning at 1.0m ensures absolutely no collision with ground on init.
        sim.load_drone(self.urdf_path, start_pos=[0, 0, 1.0])
        
        # --- FIX 2: VIDEO RECORDING ---
        video_log_id = None
        if self.gui and video_filename:
            print(f"🎥 Recording Simulation to: {video_filename}")
            video_log_id = p.startStateLogging(p.STATE_LOGGING_VIDEO_MP4, video_filename)
        
        aero = Aerodynamics(max_thrust_g=self.max_thrust_g)
        fc = FlightController()
        
        # Flight State Machine: 0=Warmup, 1=Climb, 2=Hover
        state = 0
        hover_throttles = []
        
        # PID Constants
        kp_alt = 0.5
        base_throttle = 0.0
        
        sim_t = 0
        steps = int(duration_sec * 240)
        
        crashed = False
        
        try:
            for i in range(steps):
                # 1. State Logic
                pos, quat = p.getBasePositionAndOrientation(sim.drone_id)
                current_z = pos[2]
                
                # Check for Rollover Crash
                rpy = p.getEulerFromQuaternion(quat)
                if abs(rpy[0]) > 1.5 or abs(rpy[1]) > 1.5: 
                    msg = f"CRASH: Rollover at t={sim_t:.2f}"
                    self.log['events'].append(msg)
                    print(f"💥 {msg}")
                    crashed = True
                    break

                # Altitude Logic
                error_z = target_height - current_z
                
                if state == 0: # Warmup (0.5s)
                    base_throttle = 0.05
                    if sim_t > 0.5: state = 1
                elif state == 1: # Climbing
                    base_throttle = 0.05 + (kp_alt * error_z)
                    if abs(error_z) < 0.1: state = 2
                elif state == 2: # Hovering
                    base_throttle = 0.05 + (kp_alt * error_z)
                    hover_throttles.append(base_throttle)

                base_throttle = np.clip(base_throttle, 0.0, 1.0)
                
                # 2. Flight Controller
                motors = fc.compute_motors(
                    sim.drone_id, 
                    target_rpy=[0, 0, 0], 
                    target_thrust=base_throttle, 
                    dt=sim.dt
                )
                
                # 3. Physics Step
                aero.update(sim.drone_id, sim.prop_joints, motors)
                sim.step()
                sim_t += sim.dt
                
                # Logging
                self.log['time'].append(sim_t)
                self.log['height'].append(current_z)
                self.log['throttle_avg'].append(np.mean(motors))
                
                # Visual Camera Follow
                if self.gui:
                    p.resetDebugVisualizerCamera(1.5, 45, -20, pos)
                    time.sleep(1./240.)

        except Exception as e:
            print(f"❌ Sim Error: {e}")
            crashed = True
        finally:
            if video_log_id is not None:
                p.stopStateLogging(video_log_id)
            
            # --- CRITICAL FIX: DO NOT CLOSE SIM HERE ---
            # We return the 'sim' object to the caller so they can inspect it.
            
        # Analysis
        avg_hover_th = np.mean(hover_throttles) if hover_throttles else 0.0
        twr_est = 1.0 / avg_hover_th if avg_hover_th > 0 else 0
        
        status = "PASS"
        warnings = []
        if crashed: status = "FAIL"
        elif avg_hover_th > 0.50: 
            status = "WARNING"
            warnings.append("Heavy: Hover throttle > 50%")
        elif avg_hover_th > 0.75:
            status = "FAIL"
            warnings.append("Unflyable: Hover throttle > 75%")
            
        print(f"📊 Report: Status={status} | Hover Throttle={avg_hover_th*100:.1f}%")
        
        return {
            "status": status,
            "hover_throttle_pct": round(avg_hover_th * 100, 1),
            "estimated_twr": round(twr_est, 2),
            "warnings": warnings,
            "video_path": video_filename,
            "flight_log": self.log,
            "sim_instance": sim # Return the live simulation object
        }

# --- TEST HARNESS ---
if __name__ == "__main__":
    import os
    
    # Path setup
    base_dir = "static/urdf_test"
    urdf_file = os.path.abspath(os.path.join(base_dir, "drone.urdf"))
    video_out = os.path.abspath(os.path.join(base_dir, "simulation_video.mp4"))
    
    # 1. Run the Test
    runner = FlightTestRunner(urdf_file, max_thrust_g=1200.0, gui=True)
    results = runner.run_hover_test(duration_sec=5.0, video_filename=video_out)
    
    # 2. Output Results
    print("\n" + "="*30)
    print("🚩 FLIGHT TEST REPORT")
    print("="*30)
    print(f"Status: {results['status']}")
    print(f"Video:  {results['video_path']}")
    print("="*30)
    
    # 3. KEEP WINDOW OPEN
    sim = results.get("sim_instance")
    if sim:
        print("\n👀 Simulation Paused for Inspection.")
        print("   Interact with the window (Zoom/Rotate).")
        input("   👉 PRESS ENTER TO CLOSE SIMULATION...")
        sim.close()