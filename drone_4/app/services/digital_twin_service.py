# FILE: app/services/digital_twin_service.py
import math
import json
import re

def _extract_float(value, default=0.0):
    """
    Robustly extracts the first number from messy strings.
    Ex: "327mm" -> 327.0
    Ex: "approx 5.5 inches" -> 5.5
    """
    if value is None: return default
    if isinstance(value, (int, float)): return float(value)
    
    # Find first integer or float
    match = re.search(r"(\d+(\.\d+)?)", str(value))
    if match:
        return float(match.group(1))
    return default

def _parse_dimensions_string(value):
    """
    Parses "20x20x10" or "30.5*30.5" into [L, W, H].
    """
    if not value: return [0, 0, 0]
    s = str(value).lower()
    # Normalize separators
    s = s.replace('*', ' ').replace('x', ' ').replace('/', ' ').replace(',', ' ').replace('mm', '')
    
    # Extract all numbers
    nums = [float(m.group()) for m in re.finditer(r"\d+(\.\d+)?", s)]
    
    # Pad to at least 3 values [L, W, H]
    while len(nums) < 3: nums.append(0.0)
    return nums[:3]

def generate_environment_config(mission_profile):
    """Decides which 'Game Level' to load."""
    mission_name = str(mission_profile.get("mission_name", "")).lower()
    primary_goal = str(mission_profile.get("primary_goal", "")).lower()
    
    env = {
        "type": "LAB",
        "sky_color": "#050505", 
        "ground_color": "#111111", 
        "obstacles": []
    }

    if any(x in mission_name or x in primary_goal for x in ["ranch", "farm", "cattle", "fence", "brush"]):
        env["type"] = "RANCH"
        env["sky_color"] = "#87CEEB"
        env["ground_color"] = "#2d4c1e"
        env["obstacles"] = [
            {"type": "TREE", "count": 30, "spread_radius": 80},
            {"type": "FENCE", "count": 1, "length": 50}
        ]
    elif any(x in mission_name or x in primary_goal for x in ["urban", "city", "police"]):
        env["type"] = "CITY"
        env["sky_color"] = "#2c3e50"
        env["ground_color"] = "#222222"
        env["obstacles"] = [{"type": "BUILDING", "count": 8, "spread_radius": 60}]

    return env

def generate_scene_graph(mission_profile, bom):
    """
    Calculates the detailed 3D Assembly Graph using refined specs.
    """
    # 1. Identify Key Components
    parts = {p['category']: p for p in bom}
    frame = parts.get('Frame_Kit', {})
    motors = parts.get('Motors', {})
    props = parts.get('Propellers', {})
    battery = parts.get('Battery', {})
    stack = parts.get('FC_Stack', {})
    camera = parts.get('Camera_VTX_Kit') or parts.get('Camera_Payload', {})

    # 2. Extract Critical Dimensions (Smart Logic)
    
    # --- FRAME ---
    # Try wheelbase_mm, then fallback to converting inches (e.g. "7 inch")
    wheelbase = _extract_float(frame.get('specs', {}).get('wheelbase_mm'))
    if wheelbase == 0:
        # Fallback: Try to guess from model name or max prop
        max_prop = _extract_float(frame.get('specs', {}).get('max_prop_size_inch'))
        if max_prop > 0: wheelbase = max_prop * 25.4 * 2.2 # Rough approximation
        else: wheelbase = 225.0 # Standard 5" default

    # --- MOTORS ---
    # Parse stator size (e.g. "2306") into physical dimensions
    motor_specs = motors.get('specs', {})
    stator = str(motor_specs.get('stator_size', ''))
    
    motor_w = 28.0 # Default
    motor_h = 15.0
    
    # Try to parse "2306" -> 23mm width, 6mm height -> Physical Bell size
    stator_match = re.search(r"(\d{2})(\d{2})", stator)
    if stator_match:
        s_w = int(stator_match.group(1))
        s_h = int(stator_match.group(2))
        motor_w = s_w + 5 # Bell is wider than stator
        motor_h = s_h + 10 # Bell + Base
    
    # --- PROPS ---
    prop_diam_inch = _extract_float(props.get('specs', {}).get('diameter_inches'))
    if prop_diam_inch == 0:
        # Try mm
        prop_diam_mm = _extract_float(props.get('specs', {}).get('diameter_mm'))
        if prop_diam_mm > 0:
            prop_radius_mm = prop_diam_mm / 2
        else:
            prop_radius_mm = 127.0 / 2 # Default 5"
    else:
        prop_radius_mm = (prop_diam_inch * 25.4) / 2

    # --- BATTERY ---
    # Parse "L x W x H" string from refinery
    bat_dim_str = battery.get('specs', {}).get('dimensions_mm')
    bat_L, bat_W, bat_H = _parse_dimensions_string(bat_dim_str)
    if bat_L == 0: 
        # Fallback based on cell count
        cells = _extract_float(battery.get('specs', {}).get('cell_count_s'), 6)
        bat_L, bat_W, bat_H = 75, 35, (10 * cells)

    # 3. Calculate Geometry
    arm_radius = wheelbase / 2 
    dx = arm_radius * 0.7071 # Cos(45)
    dy = arm_radius * 0.7071 # Sin(45)

    components = []

    # --- FRAME CORE ---
    components.append({
        "id": "frame_core",
        "type": "FRAME_CORE",
        "visuals": frame.get("visuals"),
        "dims": {"length": wheelbase/2.5, "width": 45, "thickness": 4},
        "pos": [0, 0, 0],
        "rot": [0, 0, 0]
    })

    # --- ARMS & MOTORS & PROPS ---
    quadrants = [[1, 1], [-1, 1], [-1, -1], [1, -1]]
    
    for i, (sx, sy) in enumerate(quadrants):
        motor_x = sx * dx
        motor_z = sy * dy
        
        # Arm
        arm_len = math.sqrt(motor_x**2 + motor_z**2)
        angle_rad = math.atan2(motor_z, motor_x) # Correct rotation calculation
        
        # In Three.js, rotation order matters. We want the arm pointing to the motor.
        # We rotate around Y axis (Up).
        
        components.append({
            "id": f"arm_{i+1}",
            "type": "FRAME_ARM",
            "visuals": frame.get("visuals"),
            "dims": {"length": arm_len, "width": 12, "thickness": 5},
            "pos": [0, 0, 0], 
            "rot": [0, -angle_rad, 0] 
        })

        # Motor
        motor_y = 2 + (motor_h/2)
        components.append({
            "id": f"motor_{i+1}",
            "type": "MOTOR",
            "visuals": motors.get("visuals"),
            "dims": {"radius": motor_w/2, "height": motor_h},
            "pos": [motor_x, 2, motor_z],
            "rot": [0, 0, 0]
        })

        # Prop
        prop_y = 2 + motor_h + 2 
        components.append({
            "id": f"prop_{i+1}",
            "type": "PROPELLER",
            "visuals": props.get("visuals"),
            "dims": {"radius": prop_radius_mm},
            "pos": [motor_x, prop_y, motor_z],
            "rot": [0, 0, 0],
            "is_dynamic": True
        })

    # --- STACK ---
    stack_h = 15.0
    components.append({
        "id": "stack",
        "type": "PCB_STACK",
        "visuals": stack.get("visuals"),
        "dims": {"width": 30.5, "length": 30.5, "height": stack_h},
        "pos": [0, 6, 0],
        "rot": [0, 0, 0]
    })

    # --- BATTERY ---
    components.append({
        "id": "battery",
        "type": "BATTERY",
        "visuals": battery.get("visuals"),
        "dims": {"length": bat_L, "width": bat_W, "height": bat_H},
        "pos": [0, 6 + stack_h + 5 + (bat_H/2), 0],
        "rot": [0, 0, 0]
    })

    # --- CAMERA ---
    # Parse camera dimensions if available, else default
    cam_w = 19.0 # Micro size
    if "mini" in str(camera.get('model_name', '')).lower(): cam_w = 22.0
    
    components.append({
        "id": "fpv_cam",
        "type": "CAMERA",
        "visuals": camera.get("visuals"),
        "dims": {"width": cam_w},
        "pos": [0, 10, wheelbase/3.5], # Offset forward based on frame size
        "rot": [0, 0, 0]
    })

    # --- GENERATE ENVIRONMENT ---
    # FIX: Explicitly call the function here
    env = generate_environment_config(mission_profile)

    return {
        "environment": env,
        "components": components,
        "meta": {
            "total_weight_est_g": sum([_extract_float(i.get('specs', {}).get('weight_g')) for i in bom]),
            "wheelbase": wheelbase
        }
    }