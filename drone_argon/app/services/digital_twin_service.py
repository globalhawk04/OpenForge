# --- START OF FILE app/services/digital_twin_service.py ---
import math
from app.services.normalizer import normalize_bom


def generate_environment_config(mission_profile: dict | None = None) -> dict:
    mission_profile = mission_profile or {}
    mission_name = str(mission_profile.get("mission_name", "")).lower()
    primary_goal = str(mission_profile.get("primary_goal", "")).lower()

    env = {
        "type": "LAB",
        "sky_color": "#070b12",
        "ground_color": "#111622",
        "obstacles": [],
    }
    if any(x in mission_name or x in primary_goal for x in ["ranch", "farm", "cattle", "fence", "brush"]):
        env["type"] = "RANCH"
        env["sky_color"] = "#87CEEB"
        env["ground_color"] = "#2d4c1e"
        env["obstacles"] = [
            {"type": "TREE", "count": 25, "spread_radius": 90},
            {"type": "FENCE", "count": 1, "length": 60},
        ]
    elif any(x in mission_name or x in primary_goal for x in ["urban", "city", "police", "industrial"]):
        env["type"] = "CITY"
        env["sky_color"] = "#1a2634"
        env["ground_color"] = "#1c1c1c"
        env["obstacles"] = [{"type": "BUILDING", "count": 8, "spread_radius": 70}]

    return env


def _compute_parallel_axis_inertia(components: list[dict]) -> dict:
    """
    Computes exact 3D Center of Gravity (CoG) in mm and meters, and the 3x3 diagonal
    Moment of Inertia Tensor (Ixx, Iyy, Izz in kg*m^2) using the Parallel Axis Theorem.
    Note: Scene graph uses Three.js Y-Up convention: X=Right/Left, Y=Up, Z=Forward/Back.
    We provide both Y-up (WebGL) and Z-up (URDF/PyBullet) tensors.
    """
    total_mass_kg = 0.0
    wx, wy, wz = 0.0, 0.0, 0.0

    for c in components:
        m_kg = max(0.001, c.get("mass_g", 10.0) / 1000.0)
        pos = c.get("pos", [0.0, 0.0, 0.0])
        total_mass_kg += m_kg
        wx += m_kg * pos[0]
        wy += m_kg * pos[1]
        wz += m_kg * pos[2]

    if total_mass_kg <= 0:
        total_mass_kg = 0.500

    cog_mm = [wx / total_mass_kg, wy / total_mass_kg, wz / total_mass_kg]
    cog_m = [v / 1000.0 for v in cog_mm]

    ixx, iyy, izz = 0.0, 0.0, 0.0
    for c in components:
        m_kg = max(0.001, c.get("mass_g", 10.0) / 1000.0)
        dims = c.get("dims", {})
        pos = c.get("pos", [0.0, 0.0, 0.0])

        # Local bounding box dimensions in meters
        if "radius" in dims:
            r_m = (dims["radius"] * 2.0) / 1000.0
            lx, ly, lz = r_m, (dims.get("height", 10.0)) / 1000.0, r_m
        else:
            lx = dims.get("length", 30.0) / 1000.0
            ly = (dims.get("height") or dims.get("thickness") or 10.0) / 1000.0
            lz = dims.get("width", 30.0) / 1000.0

        # Local solid cuboid inertia
        i_loc_x = (1.0 / 12.0) * m_kg * (ly ** 2 + lz ** 2)
        i_loc_y = (1.0 / 12.0) * m_kg * (lx ** 2 + lz ** 2)
        i_loc_z = (1.0 / 12.0) * m_kg * (lx ** 2 + ly ** 2)

        # Parallel axis offset from CoG (in meters)
        dx = (pos[0] - cog_mm[0]) / 1000.0
        dy = (pos[1] - cog_mm[1]) / 1000.0
        dz = (pos[2] - cog_mm[2]) / 1000.0

        ixx += i_loc_x + m_kg * (dy ** 2 + dz ** 2)
        iyy += i_loc_y + m_kg * (dx ** 2 + dz ** 2)
        izz += i_loc_z + m_kg * (dx ** 2 + dy ** 2)

    return {
        "total_mass_kg": round(total_mass_kg, 4),
        "cog_mm": [round(v, 2) for v in cog_mm],
        "cog_m": [round(v, 4) for v in cog_m],
        # Three.js (Y-up: Iyy is Yaw, Ixx/Izz are Pitch/Roll)
        "inertia_webgl_kg_m2": {
            "ixx": round(ixx, 6),
            "iyy": round(iyy, 6),
            "izz": round(izz, 6),
        },
        # URDF / PyBullet (Z-up: swap Y and Z)
        "inertia_urdf_kg_m2": {
            "ixx": round(ixx, 6),
            "iyy": round(izz, 6),
            "izz": round(iyy, 6),
        },
    }


def generate_scene_graph(mission_profile: dict, bom: list[dict]) -> dict:
    """
    Constructs the 3D Assembly Graph with exact normalized dimensions, component masses,
    and Parallel-Axis Theorem inertia properties.
    """
    norm_bom = normalize_bom(bom)
    parts = {p["category"]: p for p in norm_bom}

    frame = parts.get("Frame_Kit", {})
    motors = parts.get("Motors", {})
    props = parts.get("Propellers", {})
    battery = parts.get("Battery", {})
    stack = parts.get("FC_Stack", {})
    camera = parts.get("Camera_VTX_Kit") or parts.get("Camera_Payload") or {}

    f_norm = frame.get("normalized", {})
    m_norm = motors.get("normalized", {})
    p_norm = props.get("normalized", {})
    b_norm = battery.get("normalized", {})
    s_norm = stack.get("normalized", {})

    wheelbase = f_norm.get("wheelbase_mm", 225.0)
    arm_thick = f_norm.get("arm_thickness_mm", 5.0)

    motor_w = m_norm.get("stator_d_mm", 22.0) + 5.0
    motor_h = m_norm.get("stator_h_mm", 7.0) + 10.0
    motor_mass_g = m_norm.get("weight_g") or (60.0 if wheelbase >= 280 else 33.0)

    prop_radius_mm = p_norm.get("diameter_mm", 127.0) / 2.0
    prop_mass_g = (p_norm.get("weight_g") or 16.0)
    if prop_mass_g > 15.0:
        prop_mass_g /= 4.0

    bat_L, bat_W, bat_H = b_norm.get("dimensions_mm", (0.0, 0.0, 0.0))
    if bat_L <= 0:
        cells = b_norm.get("cells_s", 6)
        bat_L, bat_W, bat_H = 78.0, 38.0, float(cells * 6.0)
    bat_mass_g = b_norm.get("weight_g") or 210.0

    frame_mass_g = f_norm.get("weight_g") or (180.0 if wheelbase >= 280 else 125.0)
    stack_mass_g = s_norm.get("weight_g") or 28.0

    arm_radius = wheelbase / 2.0
    dx = arm_radius * 0.70710678
    dz = arm_radius * 0.70710678

    components = []

    # 1. Frame Core (60% of frame mass)
    components.append({
        "id": "frame_core",
        "type": "FRAME_CORE",
        "name": frame.get("model_name", "Carbon Chassis"),
        "mass_g": round(frame_mass_g * 0.60, 1),
        "visuals": frame.get("visuals"),
        "dims": {"length": round(wheelbase / 2.4, 1), "width": 46.0, "thickness": 4.0},
        "pos": [0.0, 0.0, 0.0],
        "rot": [0.0, 0.0, 0.0],
    })

    # 2. Arms, Motors & Propellers (Quad-X layout: FL, FR, RL, RR)
    # Quadrants in Three.js (X=Right/Left, Z=Forward/Back)
    quadrants = [
        ("fl", -1, 1, "CW"),
        ("fr", 1, 1, "CCW"),
        ("rl", -1, -1, "CCW"),
        ("rr", 1, -1, "CW"),
    ]
    for i, (tag, sx, sz, spin_dir) in enumerate(quadrants):
        mx = sx * dx
        mz = sz * dz
        arm_len = math.sqrt(mx ** 2 + mz ** 2)
        angle_rad = math.atan2(mz, mx)

        components.append({
            "id": f"arm_{i+1}",
            "type": "FRAME_ARM",
            "name": f"Carbon Arm {tag.upper()}",
            "mass_g": round((frame_mass_g * 0.40) / 4.0, 1),
            "visuals": frame.get("visuals"),
            "dims": {"length": round(arm_len, 2), "width": 13.0, "thickness": arm_thick},
            "pos": [0.0, 0.0, 0.0],
            "rot": [0.0, -angle_rad, 0.0],
        })

        components.append({
            "id": f"motor_{i+1}",
            "type": "MOTOR",
            "name": f"{motors.get('model_name', 'Motor')} ({tag.upper()})",
            "mass_g": round(motor_mass_g, 1),
            "visuals": motors.get("visuals"),
            "dims": {"radius": round(motor_w / 2.0, 1), "height": round(motor_h, 1)},
            "pos": [round(mx, 2), round(2.0 + motor_h / 2.0, 2), round(mz, 2)],
            "rot": [0.0, 0.0, 0.0],
        })

        prop_y = 2.0 + motor_h + 3.0
        components.append({
            "id": f"prop_{i+1}",
            "type": "PROPELLER",
            "name": f"{props.get('model_name', 'Propeller')} ({spin_dir})",
            "mass_g": round(prop_mass_g, 1),
            "spin_dir": -1 if spin_dir == "CW" else 1,
            "visuals": props.get("visuals"),
            "dims": {"radius": round(prop_radius_mm, 2)},
            "pos": [round(mx, 2), round(prop_y, 2), round(mz, 2)],
            "rot": [0.0, 0.0, 0.0],
            "is_dynamic": True,
        })

    # 3. FC / ESC Stack
    stack_h = 16.0
    components.append({
        "id": "stack",
        "type": "PCB_STACK",
        "name": stack.get("model_name", "Flight Controller Stack"),
        "mass_g": round(stack_mass_g, 1),
        "visuals": stack.get("visuals"),
        "dims": {"width": 32.0, "length": 32.0, "height": stack_h},
        "pos": [0.0, 8.0, 0.0],
        "rot": [0.0, 0.0, 0.0],
    })

    # 4. Battery
    components.append({
        "id": "battery",
        "type": "BATTERY",
        "name": battery.get("model_name", "LiPo Battery"),
        "mass_g": round(bat_mass_g, 1),
        "visuals": battery.get("visuals"),
        "dims": {"length": bat_L, "width": bat_W, "height": bat_H},
        "pos": [0.0, round(8.0 + stack_h + 4.0 + (bat_H / 2.0), 1), 0.0],
        "rot": [0.0, 0.0, 0.0],
    })

    # 5. FPV Camera
    cam_w = f_norm.get("camera_width_mm", 19.0)
    components.append({
        "id": "fpv_cam",
        "type": "CAMERA",
        "name": camera.get("model_name", "FPV Camera"),
        "mass_g": 18.0,
        "visuals": camera.get("visuals"),
        "dims": {"width": cam_w, "height": cam_w, "length": cam_w},
        "pos": [0.0, 11.0, round(wheelbase / 3.4, 2)],
        "rot": [0.0, 0.0, 0.0],
    })

    mass_properties = _compute_parallel_axis_inertia(components)
    env = generate_environment_config(mission_profile)

    return {
        "environment": env,
        "components": components,
        "mass_properties": mass_properties,
        "meta": {
            "total_weight_est_g": round(mass_properties["total_mass_kg"] * 1000.0, 1),
            "wheelbase": wheelbase,
        },
    }
# --- END OF FILE app/services/digital_twin_service.py ---