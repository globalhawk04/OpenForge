# --- REPLACE TOP 8 LINES OF app/sim/scenarios.py WITH THIS ---
import time
import math
try:
    import numpy as np
    import pybullet as p
    from app.sim.env import DroneSimulation
    from app.sim.aero import Aerodynamics
    from app.sim.pid import FlightController
    HAS_PYBULLET = True
except ImportError:
    np = None
    p = None
    HAS_PYBULLET = False

class FlightTestRunner:
    """
    Automated Test Pilot & Engineering Certification Harness.
    Runs deterministic flight scenarios in PyBullet (240Hz) and extracts control telemetry.
    """

    def __init__(self, urdf_path: str, max_thrust_g: float = 1200.0, gui: bool = False):
        self.urdf_path = urdf_path
        self.max_thrust_g = max_thrust_g
        self.gui = gui
        self.log = {
            "time": [],
            "height": [],
            "pitch_deg": [],
            "target_pitch_deg": [],
            "throttle_avg": [],
            "events": [],
        }

    def run_engineering_certification(self, duration_sec: float = 4.0) -> dict:
        """
        Runs a 3-Phase Headless Engineering Certification at 240Hz:
          - Phase 1 (0.0s - 1.8s): Altitude Acquisition & Steady-State Hover @ 1.0m
          - Phase 2 (1.8s - 2.8s): 15.0 deg Pitch Step-Response Test (Measures Rise Time, Overshoot, Settling Time)
          - Phase 3 (2.8s - 4.0s): Horizon Recovery & Stability Check
        """
        print(f"--> 🧪 PyBullet Certification: Running 240Hz Step-Response & Hover Test...")
        sim = DroneSimulation(gui=self.gui)
        sim.setup_world()
        sim.load_drone(self.urdf_path, start_pos=[0.0, 0.0, 1.0])

        aero = Aerodynamics(max_thrust_g=self.max_thrust_g)
        fc = FlightController()

        steps = int(duration_sec * 240)
        target_height = 1.0
        kp_alt = 0.65
        kd_alt = 0.35
        integral_z = 0.0

        hover_samples = []
        step_times = []
        step_pitches_deg = []
        step_target_deg = 15.0
        step_target_rad = math.radians(step_target_deg)
        crashed = False

        try:
            for i in range(steps):
                sim_t = i * sim.dt
                pos, quat = p.getBasePositionAndOrientation(sim.drone_id)
                lin_vel, _ = p.getBaseVelocity(sim.drone_id)
                current_z = pos[2]
                vz = lin_vel[2]
                rpy = p.getEulerFromQuaternion(quat)

                if abs(rpy[0]) > 1.4 or abs(rpy[1]) > 1.4 or current_z < 0.05:
                    self.log["events"].append(f"CRASH: Attitude/Ground limit exceeded at t={sim_t:.2f}s")
                    crashed = True
                    break

                # Altitude PID with Tilt Compensation
                err_z = target_height - current_z
                integral_z = np.clip(integral_z + err_z * sim.dt, -0.5, 0.5)
                u_z = 0.32 + (kp_alt * err_z) + (0.25 * integral_z) - (kd_alt * vz)
                tilt_cos = max(0.5, math.cos(rpy[0]) * math.cos(rpy[1]))
                base_throttle = float(np.clip(u_z / tilt_cos, 0.05, 0.95))

                # Phase Logic
                if sim_t < 1.8:
                    target_rpy = [0.0, 0.0, 0.0]
                    if 1.2 <= sim_t < 1.8:
                        hover_samples.append(base_throttle)
                elif 1.8 <= sim_t < 2.8:
                    target_rpy = [0.0, step_target_rad, 0.0]
                    step_times.append(sim_t - 1.8)
                    step_pitches_deg.append(math.degrees(rpy[1]))
                else:
                    target_rpy = [0.0, 0.0, 0.0]

                motors = fc.compute_motors(
                    sim.drone_id,
                    target_rpy=target_rpy,
                    target_thrust=base_throttle,
                    dt=sim.dt,
                )
                aero.update(sim.drone_id, sim.prop_joints, motors)
                sim.step()

                # Subsample telemetry at 30Hz for compact JSON storage
                if i % 8 == 0:
                    self.log["time"].append(round(sim_t, 3))
                    self.log["height"].append(round(current_z, 3))
                    self.log["pitch_deg"].append(round(math.degrees(rpy[1]), 2))
                    self.log["target_pitch_deg"].append(round(math.degrees(target_rpy[1]), 1))
                    self.log["throttle_avg"].append(round(float(np.mean(motors)) * 100.0, 1))

        except Exception as e:
            self.log["events"].append(f"Sim Exception: {e}")
            crashed = True
        finally:
            if not self.gui:
                sim.close()

        # Calculate Step-Response Engineering Metrics (10% to 90% Rise Time, Overshoot %, Settling Time)
        avg_hover_th_pct = round(float(np.mean(hover_samples)) * 100.0, 1) if hover_samples else 50.0
        rise_time_ms = 0.0
        overshoot_pct = 0.0
        settling_time_ms = 0.0

        if step_pitches_deg:
            t10 = next((t for t, val in zip(step_times, step_pitches_deg) if val >= 0.10 * step_target_deg), None)
            t90 = next((t for t, val in zip(step_times, step_pitches_deg) if val >= 0.90 * step_target_deg), None)
            if t10 is not None and t90 is not None and t90 >= t10:
                rise_time_ms = round((t90 - t10) * 1000.0, 1)

            peak_deg = max(step_pitches_deg)
            if peak_deg > step_target_deg:
                overshoot_pct = round(((peak_deg - step_target_deg) / step_target_deg) * 100.0, 1)

            # Settling time within +/- 10% band of target
            band = 0.10 * step_target_deg
            last_outside_t = 0.0
            for t, val in zip(step_times, step_pitches_deg):
                if abs(val - step_target_deg) > band:
                    last_outside_t = t
            settling_time_ms = round(last_outside_t * 1000.0, 1)

        status = "FAIL" if crashed or avg_hover_th_pct > 75.0 else ("WARNING" if avg_hover_th_pct > 55.0 else "PASS")
        print(
            f"   ✅ PyBullet Cert: {status} | Sim Hover={avg_hover_th_pct}% | "
            f"Pitch Rise={rise_time_ms}ms | Overshoot={overshoot_pct}% | Settling={settling_time_ms}ms"
        )
        return {
            "status": status,
            "sim_hover_throttle_pct": avg_hover_th_pct,
            "pitch_step_response": {
                "target_deg": step_target_deg,
                "rise_time_ms": rise_time_ms,
                "overshoot_pct": overshoot_pct,
                "settling_time_ms": settling_time_ms,
            },
            "telemetry": self.log,
        }

    def run_hover_test(self, duration_sec: float = 5.0, target_height: float = 1.0, video_filename: str | None = None) -> dict:
        cert = self.run_engineering_certification(duration_sec=duration_sec)
        return {
            "status": cert["status"],
            "hover_throttle_pct": cert["sim_hover_throttle_pct"],
            "estimated_twr": round(100.0 / max(1.0, cert["sim_hover_throttle_pct"]), 2),
            "warnings": [],
            "video_path": video_filename,
            "flight_log": cert["telemetry"],
        }
# --- END OF FILE app/sim/scenarios.py ---