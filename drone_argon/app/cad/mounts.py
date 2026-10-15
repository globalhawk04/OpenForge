# --- START OF FILE app/cad/mounts.py ---
import math
import os

try:
    import cadquery as cq
    HAS_CADQUERY = True
except ImportError:
    cq = None
    HAS_CADQUERY = False

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
MOUNTS_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "mounts")
os.makedirs(MOUNTS_OUTPUT_DIR, exist_ok=True)

# Material Effective Densities (g/cm^3) accounting for slicer wall/infill profiles
MATERIAL_PROFILES = {
    "PETG_CF_SOLID": {
        "name": "Carbon-Fiber PETG / PAHT-CF",
        "density_g_cm3": 1.32,
        "slicer_profile": "100% Rectilinear Infill, 4 Perimeters, 0.20mm Layer",
        "color_hex": "#27272a",
    },
    "TPU_95A_FLEX": {
        "name": "TPU 95A High-Impact Elastomer",
        "density_g_cm3": 0.72,  # Effective density at 35% Gyroid infill + 3 walls
        "slicer_profile": "35% Gyroid Infill, 3 Perimeters, No Supports",
        "color_hex": "#00e5a3",
    },
}


# =============================================================================
# PURE-PYTHON PARAMETRIC SOLID -> ASCII STL KERNEL (Zero External Dependencies)
# =============================================================================
def _facet_str(v1, v2, v3) -> str:
    ux, uy, uz = v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]
    vx, vy, vz = v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    nx, ny, nz = nx / length, ny / length, nz / length
    return (
        f"  facet normal {nx:.6f} {ny:.6f} {nz:.6f}\n"
        f"    outer loop\n"
        f"      vertex {v1[0]:.4f} {v1[1]:.4f} {v1[2]:.4f}\n"
        f"      vertex {v2[0]:.4f} {v2[1]:.4f} {v2[2]:.4f}\n"
        f"      vertex {v3[0]:.4f} {v3[1]:.4f} {v3[2]:.4f}\n"
        f"    endloop\n"
        f"  endfacet\n"
    )


def _quad_facets(p1, p2, p3, p4) -> list[str]:
    return [_facet_str(p1, p2, p3), _facet_str(p1, p3, p4)]


def _box_facets(cx: float, cy: float, cz: float, lx: float, ly: float, lz: float) -> list[str]:
    hx, hy, hz = lx / 2.0, ly / 2.0, lz / 2.0
    x0, x1 = cx - hx, cx + hx
    y0, y1 = cy - hy, cy + hy
    z0, z1 = cz - hz, cz + hz

    b00 = (x0, y0, z0); b10 = (x1, y0, z0); b11 = (x1, y1, z0); b01 = (x0, y1, z0)
    t00 = (x0, y0, z1); t10 = (x1, y0, z1); t11 = (x1, y1, z1); t01 = (x0, y1, z1)

    facets = []
    facets.extend(_quad_facets(b01, b11, b10, b00))  # Bottom
    facets.extend(_quad_facets(t00, t10, t11, t01))  # Top
    facets.extend(_quad_facets(b00, b10, t10, t00))  # Front
    facets.extend(_quad_facets(b11, b01, t01, t11))  # Back
    facets.extend(_quad_facets(b01, b00, t00, t01))  # Left
    facets.extend(_quad_facets(b10, b11, t11, t10))  # Right
    return facets


def _hollow_tube_facets(
    cx: float, cy: float, z0: float, z1: float, r_outer: float, r_inner: float, segs: int = 24
) -> list[str]:
    """Generates a watertight vertical hollow cylinder / standoff boss with a through-hole."""
    facets = []
    for i in range(segs):
        a0 = (2.0 * math.pi * i) / segs
        a1 = (2.0 * math.pi * (i + 1)) / segs
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)

        ob0 = (cx + r_outer * c0, cy + r_outer * s0, z0)
        ob1 = (cx + r_outer * c1, cy + r_outer * s1, z0)
        ot0 = (cx + r_outer * c0, cy + r_outer * s0, z1)
        ot1 = (cx + r_outer * c1, cy + r_outer * s1, z1)

        ib0 = (cx + r_inner * c0, cy + r_inner * s0, z0)
        ib1 = (cx + r_inner * c1, cy + r_inner * s1, z0)
        it0 = (cx + r_inner * c0, cy + r_inner * s0, z1)
        it1 = (cx + r_inner * c1, cy + r_inner * s1, z1)

        facets.extend(_quad_facets(ob0, ob1, ot1, ot0))  # Outer wall
        facets.extend(_quad_facets(ib1, ib0, it0, it1))  # Inner bore wall
        facets.extend(_quad_facets(ot0, ot1, it1, it0))  # Top annulus
        facets.extend(_quad_facets(ib0, ib1, ob1, ob0))  # Bottom annulus
    return facets


def _write_ascii_stl(filepath: str, solid_name: str, facets: list[str]) -> str:
    content = f"solid {solid_name}\n" + "".join(facets) + f"endsolid {solid_name}\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return content


# =============================================================================
# 1. STACK ADAPTER PLATE GENERATOR (e.g. 30.5x30.5mm <-> 20x20mm / Pixhawk)
# =============================================================================
def build_stack_adapter_plate(
    sku_id: str,
    frame_pattern_mm: float = 30.5,
    stack_pattern_mm: float = 20.0,
    is_pixhawk: bool = False,
) -> dict:
    part_id = f"{sku_id}_stack_adapter_{int(frame_pattern_mm)}_to_{'pixhawk' if is_pixhawk else int(stack_pattern_mm)}"
    stl_path = os.path.join(MOUNTS_OUTPUT_DIR, f"{part_id}.stl")

    plate_thick = 2.5
    boss_height = 5.0
    outer_span = max(frame_pattern_mm, 38.0 if is_pixhawk else stack_pattern_mm) + 9.0

    facets = []
    # Cross-brace frame bars connecting outer and inner mounting bosses
    bar_w = 6.5
    facets.extend(_box_facets(0, 0, plate_thick / 2, outer_span, bar_w, plate_thick))
    facets.extend(_box_facets(0, 0, plate_thick / 2, bar_w, outer_span, plate_thick))
    facets.extend(_box_facets(0, frame_pattern_mm / 2, plate_thick / 2, frame_pattern_mm, 5.0, plate_thick))
    facets.extend(_box_facets(0, -frame_pattern_mm / 2, plate_thick / 2, frame_pattern_mm, 5.0, plate_thick))
    facets.extend(_box_facets(frame_pattern_mm / 2, 0, plate_thick / 2, 5.0, frame_pattern_mm, plate_thick))
    facets.extend(_box_facets(-frame_pattern_mm / 2, 0, plate_thick / 2, 5.0, frame_pattern_mm, plate_thick))

    # 4x Outer Frame Mounting Holes (M3 clearance = 1.6mm radius)
    fh = frame_pattern_mm / 2.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            facets.extend(_hollow_tube_facets(sx * fh, sy * fh, 0.0, plate_thick, r_outer=3.8, r_inner=1.6))

    # 4x Inner Stack / Carrier Standoff Bosses (Raised 5mm with M2.5/M3 bore)
    ih = 15.25 if is_pixhawk else (stack_pattern_mm / 2.0)
    inner_bore_r = 1.5 if stack_pattern_mm >= 25.0 or is_pixhawk else 1.15
    for sx in (-1, 1):
        for sy in (-1, 1):
            facets.extend(_hollow_tube_facets(sx * ih, sy * ih, 0.0, boss_height, r_outer=3.6, r_inner=inner_bore_r))

    stl_text = _write_ascii_stl(stl_path, part_id, facets)

    # Calculate true volume & mass (PETG-CF)
    vol_cm3 = ((outer_span * bar_w * 2 + frame_pattern_mm * 5.0 * 4) * plate_thick) / 1000.0
    mat = MATERIAL_PROFILES["PETG_CF_SOLID"]
    weight_g = round(max(3.2, vol_cm3 * mat["density_g_cm3"]), 1)

    title = (
        f"Pixhawk Vibration-Isolated Carrier Adapter ({frame_pattern_mm}mm Base)"
        if is_pixhawk
        else f"FC Stack Converter Plate ({frame_pattern_mm}x{frame_pattern_mm}mm to {stack_pattern_mm}x{stack_pattern_mm}mm)"
    )

    return {
        "id": part_id,
        "type": "STACK_ADAPTER_PLATE",
        "name": title,
        "material": mat["name"],
        "slicer_settings": mat["slicer_profile"],
        "weight_g": weight_g,
        "dims_mm": f"{outer_span:.1f} x {outer_span:.1f} x {boss_height:.1f} mm",
        "stl_filename": f"{part_id}.stl",
        "stl_path": stl_path,
        "stl_ascii": stl_text,
        "pos_mm": [0.0, 3.0, 0.0],
        "color_hex": mat["color_hex"],
    }


# =============================================================================
# 2. FPV CAMERA CAGE TPU REDUCER SPACERS (e.g. 20mm Frame -> 19mm / 14mm Cam)
# =============================================================================
def build_camera_tpu_spacers(
    sku_id: str,
    frame_cam_width_mm: float = 20.0,
    cam_width_mm: float = 19.0,
) -> dict:
    part_id = f"{sku_id}_tpu_cam_spacer_{int(frame_cam_width_mm)}_to_{int(cam_width_mm)}mm"
    stl_path = os.path.join(MOUNTS_OUTPUT_DIR, f"{part_id}.stl")

    spacer_thick = max(1.2, (frame_cam_width_mm - cam_width_mm) / 2.0)
    facets = []

    # Generate Left & Right TPU Damping Cheeks with M2 Pivot Bore
    for side_x in (-12.0, 12.0):
        # Cheek base plate + anti-rotation flange
        facets.extend(_box_facets(side_x, 0.0, spacer_thick / 2.0, 14.0, 16.0, spacer_thick))
        facets.extend(_hollow_tube_facets(side_x, 0.0, 0.0, spacer_thick + 1.5, r_outer=4.5, r_inner=1.05))

    stl_text = _write_ascii_stl(stl_path, part_id, facets)
    mat = MATERIAL_PROFILES["TPU_95A_FLEX"]
    vol_cm3 = (2.0 * 14.0 * 16.0 * spacer_thick) / 1000.0
    weight_g = round(max(1.8, vol_cm3 * mat["density_g_cm3"]), 1)

    return {
        "id": part_id,
        "type": "CAMERA_TPU_SPACER",
        "name": f"TPU Camera Vibration Spacers ({frame_cam_width_mm:.0f}mm Cage to {cam_width_mm:.0f}mm Cam)",
        "material": mat["name"],
        "slicer_settings": mat["slicer_profile"],
        "weight_g": weight_g,
        "dims_mm": f"2x ({spacer_thick:.1f}mm thick x 16mm tall, M2 Bore)",
        "stl_filename": f"{part_id}.stl",
        "stl_path": stl_path,
        "stl_ascii": stl_text,
        "pos_mm": [0.0, 11.0, 82.0],
        "color_hex": mat["color_hex"],
    }


# =============================================================================
# 3. REAR STANDOFF TPU GPS + VTX SMA ANTENNA POD
# =============================================================================
def build_gps_antenna_tpu_pod(
    sku_id: str,
    wheelbase_mm: float = 225.0,
    standoff_pitch_mm: float = 28.0,
    gps_size_mm: float = 25.0,
) -> dict:
    part_id = f"{sku_id}_tpu_gps_sma_pod_{int(gps_size_mm)}mm"
    stl_path = os.path.join(MOUNTS_OUTPUT_DIR, f"{part_id}.stl")

    facets = []
    half_pitch = standoff_pitch_mm / 2.0

    # 1. Twin Rear Standoff Slip-On Collars (5.2mm ID for M3 textured standoffs, 20mm tall)
    for sx in (-1, 1):
        facets.extend(_hollow_tube_facets(sx * half_pitch, 0.0, 0.0, 20.0, r_outer=4.8, r_inner=2.6))

    # 2. Cross-Bridge & Rear Cantilevered Arm
    facets.extend(_box_facets(0.0, 0.0, 10.0, standoff_pitch_mm, 5.0, 18.0))
    facets.extend(_box_facets(0.0, -16.0, 14.0, gps_size_mm + 4.0, 26.0, 4.0))

    # 3. GPS Ceramic Patch Pocket Walls (25x25mm or 18x18mm tray)
    wall_t = 2.0
    tray_w = gps_size_mm + 3.0
    facets.extend(_box_facets(0.0, -16.0 - tray_w / 2.0, 18.5, tray_w, wall_t, 6.0))
    facets.extend(_box_facets(0.0, -16.0 + tray_w / 2.0, 18.5, tray_w, wall_t, 6.0))
    facets.extend(_box_facets(-tray_w / 2.0, -16.0, 18.5, wall_t, tray_w, 6.0))
    facets.extend(_box_facets(tray_w / 2.0, -16.0, 18.5, wall_t, tray_w, 6.0))

    # 4. Integrated VTX Antenna Tube / SMA Collar (6.5mm ID)
    facets.extend(_hollow_tube_facets(0.0, -34.0, 6.0, 24.0, r_outer=5.8, r_inner=3.25))

    stl_text = _write_ascii_stl(stl_path, part_id, facets)
    mat = MATERIAL_PROFILES["TPU_95A_FLEX"]
    weight_g = round(11.5 if gps_size_mm >= 24.0 else 8.4, 1)

    return {
        "id": part_id,
        "type": "GPS_ANTENNA_TPU_POD",
        "name": f"TPU Rear Standoff GPS ({int(gps_size_mm)}x{int(gps_size_mm)}mm) + VTX Antenna Pod",
        "material": mat["name"],
        "slicer_settings": mat["slicer_profile"],
        "weight_g": weight_g,
        "dims_mm": f"{tray_w:.0f} x 42 x 24 mm ({standoff_pitch_mm:.0f}mm Standoff Pitch)",
        "stl_filename": f"{part_id}.stl",
        "stl_path": stl_path,
        "stl_ascii": stl_text,
        "pos_mm": [0.0, 18.0, -round(wheelbase_mm / 3.1, 1)],
        "color_hex": mat["color_hex"],
    }


def synthesize_printable_mounts(sku_id: str, norm_bom: list[dict]) -> list[dict]:
    """
    Inspects the normalized BOM and automatically generates 3D-printable STL mounts
    for any stack adapters, camera spacers, or GPS/VTX antenna pods needed.
    """
    parts = {p["category"]: p for p in norm_bom}
    frame = parts.get("Frame_Kit", {})
    fc = parts.get("FC_Stack", {})
    cam = parts.get("Camera_VTX_Kit") or parts.get("Camera_Payload") or {}

    f_norm = frame.get("normalized", {})
    fc_norm = fc.get("normalized", {})

    wb_mm = f_norm.get("wheelbase_mm", 225.0)
    f_stack_pats = set(f_norm.get("stack_mount_patterns_mm") or [30.5])
    fc_stack_pats = set(fc_norm.get("stack_mount_patterns_mm") or [30.5])
    is_pixhawk = fc_norm.get("is_pixhawk_form_factor", False)

    mounts = []

    # 1. Check if FC Stack needs an Adapter Plate to bolt onto the Frame
    if is_pixhawk or (fc_stack_pats and not f_stack_pats.intersection(fc_stack_pats)):
        frame_pat = sorted(f_stack_pats)[-1] if f_stack_pats else 30.5
        stack_pat = sorted(fc_stack_pats)[0] if fc_stack_pats else 20.0
        mounts.append(
            build_stack_adapter_plate(
                sku_id=sku_id,
                frame_pattern_mm=frame_pat,
                stack_pattern_mm=stack_pat,
                is_pixhawk=is_pixhawk,
            )
        )

    # 2. Check if FPV Camera needs TPU Cage Spacers / Vibration Reducers
    frame_cam_w = f_norm.get("camera_width_mm", 20.0)
    cam_w = 19.0 if "mini" not in str(cam.get("model_name", "")).lower() else 20.0
    if frame_cam_w >= cam_w:
        mounts.append(
            build_camera_tpu_spacers(
                sku_id=sku_id,
                frame_cam_width_mm=max(20.0, frame_cam_w),
                cam_width_mm=19.0,
            )
        )

    # 3. Always generate the Rear TPU GPS + VTX Antenna Tail Mount for Long-Range / Industrial Quads
    gps_size = 25.0 if wb_mm >= 280 else 18.0
    mounts.append(
        build_gps_antenna_tpu_pod(
            sku_id=sku_id,
            wheelbase_mm=wb_mm,
            standoff_pitch_mm=28.0 if wb_mm < 350 else 32.0,
            gps_size_mm=gps_size,
        )
    )

    return mounts
# --- END OF FILE app/cad/mounts.py ---