# FILE: app/services/physics_service.py
import subprocess
import json
import os
import re

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
SIM_SCRIPT_PATH = os.path.join(PROJECT_ROOT, "simulation", "calc_twr.py")

def run_physics_simulation(bom_data: list) -> dict:
    total_weight = 0.0
    max_thrust = 0.0
    battery_cap = 0
    motor_kv = 0
    voltage = 0
    prop_diam = 0
    prop_pitch = 3.0 # Default average pitch
    
    if not bom_data:
        return {"error": "BOM is empty"}

    for item in bom_data:
        # Normalize text for robust matching
        pt = str(item.get("part_type", "")).lower()
        name = str(item.get("product_name", "")).lower()
        
        # -- Weight & Specs Estimation --
        
        # 1. MOTORS
        if "motor" in pt: 
            # Estimate weight based on size heuristic
            if "2207" in name or "2306" in name:
                weight_per_motor = 35.0
                thrust_per_motor = 1200.0
            elif "1404" in name:
                weight_per_motor = 10.0
                thrust_per_motor = 300.0
            else:
                weight_per_motor = 2.5 # Whoop default
                thrust_per_motor = 40.0

            total_weight += (weight_per_motor * 4)
            
            # Extract KV (look for 4-5 digits followed by kv)
            kv_match = re.search(r"(\d{3,5})\s?kv", name)
            if kv_match:
                motor_kv = int(kv_match.group(1))
                # Refine thrust if we have KV context
                if motor_kv > 10000: max_thrust = 40.0
                elif motor_kv > 2000: max_thrust = 600.0
                else: max_thrust = 1300.0
            else:
                # If we didn't get KV, use the heuristic thrust
                max_thrust = thrust_per_motor

        # 2. FRAME / CHASSIS
        elif "frame" in pt or "chassis" in pt: 
            if "5" in name or "freestyle" in name or "volador" in name:
                total_weight += 120.0
            elif "3" in name:
                total_weight += 40.0
            else:
                total_weight += 10.0 # Whoop frame

        # 3. FLIGHT CONTROLLER
        elif "fc" in pt or "stack" in pt or "controller" in pt:
            total_weight += 15.0 if "stack" in pt else 5.0

        # 4. BATTERY
        elif "battery" in pt or "lipo" in pt:
            # Capacity
            cap_match = re.search(r"(\d{3,4})\s?mah", name)
            if cap_match: battery_cap = int(cap_match.group(1))
            
            # Cells / Voltage
            cell_match = re.search(r"(\d)s", name)
            if cell_match:
                cells = int(cell_match.group(1))
                voltage = cells * 3.7
                # Weight heuristic: approx 20g per 1000mah per cell
                # 1000mah 6S = ~160g
                weight_est = (battery_cap / 1000) * cells * 26
                total_weight += weight_est if weight_est > 0 else (cells * 10)
            else:
                 # Fallback if S count missing but it's a battery
                 total_weight += 50.0

        # 5. PROPS
        elif "prop" in pt:
            specs = item.get("engineering_specs", {})
            if specs.get("diameter_mm"):
                prop_diam = specs.get("diameter_mm") / 25.4
            total_weight += 10.0 # Set of 4 props

        # 6. CAMERA / VTX / ANTENNA
        elif "camera" in pt or "video" in pt or "vtx" in pt:
            total_weight += 35.0 if "air unit" in name or "o3" in name else 5.0
    
    # Safety Fallback: If logic failed completely, give it a base weight so math works
    if total_weight < 5: 
        total_weight = 50.0 
        
    sim_input = {
        "total_weight_g": total_weight,
        "max_thrust_g": max_thrust,
        "num_motors": 4,
        "battery_capacity_mah": battery_cap,
        "motor_kv": motor_kv,
        "voltage": voltage,
        "prop_diameter_inch": prop_diam,
        "prop_pitch_inch": prop_pitch
    }
    
    try:
        process = subprocess.Popen(
            ["python3", SIM_SCRIPT_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=json.dumps(sim_input))
        if stderr: 
            print(f"Physics STDERR: {stderr}")
            return {"error": "Simulation script error"}
            
        return json.loads(stdout)
    except Exception as e:
        print(f"Physics Exception: {e}")
        return {"error": str(e)}