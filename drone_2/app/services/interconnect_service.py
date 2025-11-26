# FILE: app/services/digital_twin_service.py
import math
import json

def _get_spec(item, key, default):
    """Safely extracts a float spec from the BOM item."""
    if not item or 'specs' not in item:
        return default
    val = item['specs'].get(key)
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default

def generate_environment_config(mission_profile):
    """
    Decides which 'Game Level' to load based on the mission context.
    """
    mission_name = str(mission_profile.get("mission_name", "")).lower()
    primary_goal = str(mission_profile.get("primary_goal", "")).lower()
    
    # Default: The "Lab" (Grid)
    env = {
        "type": "LAB",
        "sky_color": "#050505",
        "ground_color": "#111111",
        "obstacles": []
    }

    # Context-Aware Levels
    if any(x in mission_name or x in primary_goal for x in ["ranch", "farm", "cattle", "fence", "brush"]):
        env["type"] = "RANCH"
        env["sky_color"] = "#87CEEB" # Sky Blue
        env["ground_color"] = "#2d4c1e" # Grass Green
        env["obstacles"] = [
            {"type": "TREE", "count": 30, "spread_radius": 80},
            {"type": "FENCE", "count": 1, "length": 50} # Linear obstacle
        ]
    
    elif any(x in mission_name or x in primary_goal for x in ["urban", "city", "police", "swat", "cinema"]):
        env["type"] = "CITY"
        env["sky_color"] = "#2c3e50" # Dark Blue/Grey
        env["ground_color"] = "#222222" # Asphalt
        env["obstacles"] = [
            {"type": "BUILDING", "count": 8, "spread_radius": 60}
        ]

    return env

def generate_scene_graph(mission_profile, bom):
    """
    Calculates the detailed 3D Assembly Graph.
    This tells the frontend EXACTLY where to spawn high-fidelity procedural meshes.
    """
    print(f"--> 🎨 Digital Twin: Constructing Scene Graph for {mission_profile.get('mission_name')}...")

    # 1. Identify Key Components from BOM
    frame = next((i for i in bom if i['category'] == 'Frame_Kit'), {})
    motors = next((i for i in bom if i['category'] == 'Motors'), {})
    props = next((i for i in bom if i['category'] == 'Propellers'), {})
    battery = next((i for i in bom if i['category'] == 'Battery'), {})
    stack = next((i for i in bom if i['category'] == 'FC_Stack'), {})
    camera = next((i for i in bom if i['category'] == 'Camera_VTX_Kit'), {})

    # 2. Extract Critical Dimensions (with safe defaults)
    wheelbase = _get_spec(frame, 'wheelbase_mm', 225.0)
    
    # Motor Geometry
    motor_w = _get_spec(motors, 'width_mm', 28.0)
    motor_h = _get_spec(motors, 'height_mm', 15.0)
    
    # Prop Geometry
    prop_diam_mm = _get_spec(props, 'diameter_mm', 127.0)
    prop_radius_mm = prop_diam_mm / 2
    
    # Stack Geometry
    stack_h = 10.0 # Standard stack height

    # 3. Calculate Math for X-Frame
    # Assuming True-X or Squashed-X based on frame description could be added later.
    # For now, standard True-X geometry.
    # Distance from center to motor shaft
    arm_radius = wheelbase / 2 
    # X and Y components (45 degrees)
    dx = arm_radius * 0.7071 
    dy = arm_radius * 0.7071

    # 4. Build the Component List
    components = []

    # --- FRAME BODY ---
    # The central bus
    components.append({
        "id": "frame_core",
        "type": "FRAME_CORE",
        "visuals": frame.get("visuals"), # Use extracted "Visual DNA"
        "dims": {"length": 140, "width": 45, "thickness": 4},
        "pos": [0, 0, 0],
        "rot": [0, 0, 0]
    })

    # --- ARMS & MOTORS & PROPS (x4) ---
    # Top-Right, Top-Left, Bottom-Left, Bottom-Right
    # Signs for [x, y]
    quadrants = [[1, 1], [-1, 1], [-1, -1], [1, -1]]
    
    for i, (sx, sy) in enumerate(quadrants):
        # Arm
        # We calculate rotation to point from center to motor
        angle_rad = math.atan2(sy*dy, sx*dx)
        arm_len = math.sqrt(dx**2 + dy**2) # Distance to motor
        
        components.append({
            "id": f"arm_{i+1}",
            "type": "FRAME_ARM",
            "visuals": frame.get("visuals"),
            "dims": {"length": arm_len, "width": 12, "thickness": 4},
            "pos": [0, 0, 0], # Pivots at center
            "rot": [0, -angle_rad, 0] # Three.js uses Y-up usually, but we might rotate Z depending on setup. OpenSCAD is Z up. Three.js is Y up.
            # Let's standardize on Y-UP for Three.js.
            # Arm lies flat on XZ plane. Rotation is around Y axis.
        })

        # Motor
        motor_x = sx * dx
        motor_z = sy * dy # Using Z for depth in Three.js
        motor_y = 2 + (motor_h/2) # Sitting on top of 4mm arm (2mm half-height)
        
        components.append({
            "id": f"motor_{i+1}",
            "type": "MOTOR",
            "visuals": motors.get("visuals"),
            "dims": {"radius": motor_w/2, "height": motor_h},
            "pos": [motor_x, 2, motor_z], # Y=2 sits on top of arm
            "rot": [0, 0, 0]
        })

        # Propeller
        # Sits on top of motor
        prop_y = 2 + motor_h + 2 
        
        components.append({
            "id": f"prop_{i+1}",
            "type": "PROPELLER",
            "visuals": props.get("visuals"),
            "dims": {"radius": prop_radius_mm},
            "pos": [motor_x, prop_y, motor_z],
            "rot": [0, 0, 0],
            "is_dynamic": True # Flag for frontend to spin this
        })

    # --- STACK ---
    components.append({
        "id": "stack",
        "type": "PCB_STACK",
        "visuals": stack.get("visuals"),
        "dims": {"width": 30.5, "length": 30.5, "height": stack_h},
        "pos": [0, 6, 0], # Sits above frame
        "rot": [0, 0, 0]
    })

    # --- BATTERY ---
    # Heuristic: If "top mount" frame, put on top. If "bus" frame, put on bottom.
    # Default to Top Mount for freestyle/long range usually.
    bat_dims = {"length": 75, "width": 35, "height": 30} # Generic 6S
    
    components.append({
        "id": "battery",
        "type": "BATTERY",
        "visuals": battery.get("visuals"),
        "dims": bat_dims,
        "pos": [0, 6 + stack_h + 2 + (30/2), 0], # Sits on top of stack/top plate
        "rot": [0, 0, 0]
    })

    # --- CAMERA ---
    components.append({
        "id": "fpv_cam",
        "type": "CAMERA",
        "visuals": camera.get("visuals"),
        "dims": {"width": 19},
        "pos": [0, 10, 45], # Forward offset
        "rot": [0, 0, 0]
    })

    # 5. Assemble Final Package
    scene_data = {
        "environment": generate_environment_config(mission_profile),
        "components": components,
        "meta": {
            "total_weight_est_g": sum([_get_spec(i, 'weight_g', 0) for i in bom]),
            "wheelbase": wheelbase
        }
    }
    
    return scene_data