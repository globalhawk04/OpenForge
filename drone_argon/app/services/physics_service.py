# --- START OF FILE app/services/physics_service.py ---
import math
from app.services.normalizer import normalize_bom, extract_float

GRAVITY = 9.80665
AIR_DENSITY_RHO = 1.225  # kg/m^3 at sea level ISA

# Class-aware fallback masses (in grams) ONLY used if scraped specs lack weight,
# and explicitly flagged in the engineering audit log.
CLASS_FALLBACK_WEIGHTS_G = {
    "5_INCH": {"frame": 125.0, "motor": 33.0, "prop_set": 16.0, "fc_stack": 26.0, "battery": 215.0, "camera": 35.0},
    "7_INCH": {"frame": 185.0, "motor": 60.0, "prop_set": 28.0, "fc_stack": 32.0, "battery": 340.0, "camera": 40.0},
    "HEAVY_LIFT": {"frame": 650.0, "motor": 165.0, "prop_set": 90.0, "fc_stack": 65.0, "battery": 1200.0, "camera": 120.0},
}


def _detect_size_class(wheelbase_mm: float, prop_diam_in: float) -> str:
    if wheelbase_mm >= 400 or prop_diam_in >= 9.0:
        return "HEAVY_LIFT"
    if wheelbase_mm >= 280 or prop_diam_in >= 6.5:
        return "7_INCH"
    return "5_INCH"


def _calculate_auw_and_breakdown(norm_bom: list[dict], size_class: str, num_motors: int = 4) -> tuple[float, list[dict], list[str]]:
    """
    Calculates All-Up Weight (AUW) in grams with a full per-component audit trail.
    Applies an 8% structural harness/fastener/solder mass fraction.
    """
    fallbacks = CLASS_FALLBACK_WEIGHTS_G.get(size_class, CLASS_FALLBACK_WEIGHTS_G["5_INCH"])
    breakdown = []
    warnings = []
    dry_sub_total_g = 0.0

    for item in norm_bom:
        cat = item["category"].lower()
        name = item["model_name"]
        norm = item["normalized"]
        unit_w = norm["weight_g"]
        is_emp = norm["weight_is_empirical"]

        # Determine quantity multiplier
        if "motor" in cat:
            qty = num_motors
            if not is_emp or unit_w <= 0:
                unit_w = fallbacks["motor"]
                warnings.append(f"MASS_ESTIMATED: Motor '{name}' missing weight; using {unit_w}g ({size_class} baseline).")
        elif "prop" in cat:
            # Check if weight is for a single prop or a set of 4
            is_set_weight = unit_w > 18.0 and size_class != "HEAVY_LIFT"
            qty = 1 if is_set_weight else num_motors
            if not is_emp or unit_w <= 0:
                unit_w = fallbacks["prop_set"] / num_motors
                qty = num_motors
                warnings.append(f"MASS_ESTIMATED: Propeller '{name}' missing weight; using {unit_w:.1f}g/prop.")
        elif "frame" in cat:
            qty = 1
            if not is_emp or unit_w <= 0:
                unit_w = fallbacks["frame"]
                warnings.append(f"MASS_ESTIMATED: Frame '{name}' missing weight; using {unit_w}g ({size_class} baseline).")
        elif "battery" in cat:
            qty = 1
            if not is_emp or unit_w <= 0:
                # Estimate LiPo weight from Energy (Wh): ~5.8g per Wh
                wh = (norm.get("capacity_mah", 1300) / 1000.0) * norm.get("nominal_voltage_v", 22.2)
                unit_w = round(max(100.0, wh * 6.2), 1)
                warnings.append(f"MASS_ESTIMATED: Battery '{name}' weight derived from energy density ({unit_w}g).")
        elif "fc" in cat or "stack" in cat or "esc" in cat:
            qty = 1
            if not is_emp or unit_w <= 0:
                unit_w = fallbacks["fc_stack"]
                warnings.append(f"MASS_ESTIMATED: Electronics '{name}' missing weight; using {unit_w}g.")
        else:
            qty = int(item.get("quantity", 1))
            if not is_emp or unit_w <= 0:
                unit_w = 15.0

        line_total = round(unit_w * qty, 1)
        dry_sub_total_g += line_total
        breakdown.append({
            "category": item["category"],
            "model_name": name,
            "unit_weight_g": round(unit_w, 1),
            "quantity": qty,
            "total_weight_g": line_total,
            "empirical": is_emp,
        })

    # 8% Fasteners, Power Leads, Solder, Battery Strap overhead
    harness_g = round(dry_sub_total_g * 0.08, 1)
    breakdown.append({
        "category": "Hardware_Harness",
        "model_name": "M3 Fasteners, Power Pigtail, Solder & Straps (8% Mass Fraction)",
        "unit_weight_g": harness_g,
        "quantity": 1,
        "total_weight_g": harness_g,
        "empirical": True,
    })

    total_auw_g = round(dry_sub_total_g + harness_g, 1)
    return total_auw_g, breakdown, warnings


def _solve_propulsion_point(
    throttle: float,
    kv: float,
    stator_d_mm: float,
    stator_h_mm: float,
    v_nom: float,
    cells_s: int,
    prop_diam_m: float,
    prop_pitch_m: float,
    blade_count: int,
    empirical_data: dict | None = None,
) -> dict:
    """
    Computes single-motor Thrust (g), Current (A), Electrical Power (W), and RPM at a given throttle [0.1..1.0].
    Uses Tier-1 Empirical Table Interpolation if available, otherwise Tier-2 Coupled Electromechanical + Blade Element theory.
    """
    throttle = max(0.05, min(1.0, float(throttle)))

    # --- TIER 1: EMPIRICAL THRUST DATA INTERPOLATION ---
    if isinstance(empirical_data, dict):
        # Case A: Full scraped table from data_service.py: {"throttle_pct": [...], "thrust_g": [...], "amps": [...]}
        if "thrust_g" in empirical_data and isinstance(empirical_data["thrust_g"], list) and len(empirical_data["thrust_g"]) >= 2:
            t_list = empirical_data["thrust_g"]
            a_list = empirical_data.get("amps") or [t * 0.015 for t in t_list]
            max_t = float(max(t_list))
            max_a = float(max(a_list))
            thrust_g = max_t * (throttle ** 1.85)
            amps = max_a * (throttle ** 2.2)
            v_sag = v_nom - (amps * 0.012 * cells_s)
            power_w = amps * max(10.0, v_sag)
            rpm = kv * v_sag * throttle * 0.84
            return {
                "throttle_pct": int(round(throttle * 100)),
                "thrust_g": round(thrust_g, 1),
                "current_a": round(amps, 2),
                "power_w": round(power_w, 1),
                "rpm": int(round(rpm)),
                "efficiency_g_w": round(thrust_g / power_w, 2) if power_w > 0 else 0.0,
                "method": "EMPIRICAL_TABLE",
            }

        # Case B: Refinery 50%/100% points: {"50_pct_g": 1200, "100_pct_g": 3400}
        t100 = extract_float(empirical_data.get("100_pct_g"))
        if t100 > 100:
            t50 = extract_float(empirical_data.get("50_pct_g"), t100 * 0.30)
            # Fit power law T(x) = t100 * x^alpha
            alpha = math.log(max(0.1, t50 / t100)) / math.log(0.5)
            alpha = max(1.4, min(2.3, alpha))
            thrust_g = t100 * (throttle ** alpha)

    # --- TIER 2: FIRST-PRINCIPLES ELECTROMECHANICAL + AERODYNAMIC MODEL ---
    # 1. Stator Geometry & Electromagnetic Torque/Power Limit
    stator_vol_mm3 = math.pi * ((stator_d_mm / 2.0) ** 2) * stator_h_mm
    # Real brushless motors handle ~0.145 W of continuous shaft power per mm^3 of stator volume at 100% duty
    max_stator_shaft_power_w = stator_vol_mm3 * 0.145

    # 2. Propeller Non-Dimensional Aerodynamic Coefficients (UIUC / NACA multirotor empirical correlation)
    pitch_ratio = max(0.30, min(1.0, prop_pitch_m / prop_diam_m)) if prop_diam_m > 0 else 0.5
    blade_factor = (blade_count / 3.0) ** 0.72
    # Static Thrust Coefficient Ct and Power Coefficient Cp
    ct = (0.048 + 0.068 * pitch_ratio) * blade_factor
    cp = ct * (0.44 + 0.62 * pitch_ratio)

    # 3. Coupled Motor-Propeller Operating Point (Iterative RPM & Voltage Sag Solver)
    # Internal resistance per cell (~8 mOhm for high-C LiPo) + ESC/winding resistance
    r_system_ohm = (0.008 * max(1, cells_s)) + (180.0 / max(200.0, stator_vol_mm3))
    motor_eff = 0.83 - (0.08 * (1.0 - throttle))

    # Initial unloaded RPS guess
    v_loaded = v_nom
    for _ in range(5):
        # Loaded RPM accounts for back-EMF slip under aerodynamic torque load
        rpm_unloaded = kv * v_loaded * throttle
        n_rps = (rpm_unloaded * 0.80) / 60.0

        # Aerodynamic shaft power required at this RPS: P = Cp * rho * n^3 * D^5
        p_shaft_w = cp * AIR_DENSITY_RHO * (n_rps ** 3) * (prop_diam_m ** 5)

        # Apply Stator Magnetic/Thermal Saturation Cap
        if p_shaft_w > max_stator_shaft_power_w * (throttle ** 1.5):
            p_shaft_w = max_stator_shaft_power_w * (throttle ** 1.5)
            # Recompute achievable RPS from capped shaft power
            n_rps = (p_shaft_w / max(1e-6, cp * AIR_DENSITY_RHO * (prop_diam_m ** 5))) ** (1.0 / 3.0)

        p_elec_w = p_shaft_w / max(0.5, motor_eff)
        current_a = p_elec_w / max(6.0, v_loaded)
        # Update battery terminal voltage under 4-motor load
        v_loaded = max(cells_s * 3.1, v_nom - (current_a * 4.0 * r_system_ohm))

    # 4. Compute Static Thrust at converged RPS: T = Ct * rho * n^2 * D^4 (Newtons -> Grams)
    thrust_n = ct * AIR_DENSITY_RHO * (n_rps ** 2) * (prop_diam_m ** 4)
    thrust_g = (thrust_n / GRAVITY) * 1000.0
    rpm_final = n_rps * 60.0

    return {
        "throttle_pct": int(round(throttle * 100)),
        "thrust_g": round(thrust_g, 1),
        "current_a": round(current_a, 2),
        "power_w": round(p_elec_w, 1),
        "rpm": int(round(rpm_final)),
        "efficiency_g_w": round(thrust_g / p_elec_w, 2) if p_elec_w > 0 else 0.0,
        "method": "ACTUATOR_DISK_BEM",
    }


def generate_physics_config(bom: list[dict], num_motors: int = 4) -> dict:
    """
    Engineering-Grade Flight Dynamics & Propulsion Calculator.
    Computes exact AUW, Actuator-Disk Hover Power, Peukert Endurance, Disk Loading,
    Pitch Speed, and a 10-point Throttle Telemetry Curve.
    """
    print("--> 🚀 Physics Service: Running First-Principles Propulsion & Aerodynamic Analysis...")
    norm_bom = normalize_bom(bom)
    parts = {p["category"]: p for p in norm_bom}

    frame = parts.get("Frame_Kit", {})
    motor = parts.get("Motors", {})
    prop = parts.get("Propellers", {})
    battery = parts.get("Battery", {})

    f_norm = frame.get("normalized", {})
    m_norm = motor.get("normalized", {})
    p_norm = prop.get("normalized", {})
    b_norm = battery.get("normalized", {})

    wb_mm = f_norm.get("wheelbase_mm", 225.0)
    prop_diam_in = p_norm.get("diameter_inch", 5.0)
    prop_pitch_in = p_norm.get("pitch_inch", 3.7)
    blade_count = p_norm.get("blade_count", 3)
    size_class = _detect_size_class(wb_mm, prop_diam_in)

    # 1. Audit-Ready Mass Accounting
    mass_g, mass_breakdown, warnings = _calculate_auw_and_breakdown(norm_bom, size_class, num_motors)
    mass_kg = mass_g / 1000.0

    # 2. Propulsion Parameters
    kv = m_norm.get("kv", 1750.0)
    stator_d = m_norm.get("stator_d_mm", 22.0)
    stator_h = m_norm.get("stator_h_mm", 7.0)
    cells_s = b_norm.get("cells_s", 6)
    v_nom = b_norm.get("nominal_voltage_v", cells_s * 3.7)
    cap_mah = b_norm.get("capacity_mah", 1300.0)
    emp_data = m_norm.get("thrust_data")

    prop_diam_m = prop_diam_in * 0.0254
    prop_pitch_m = prop_pitch_in * 0.0254

    # 3. Generate 10-Point Single-Motor & Total-Quad Throttle Curve
    throttle_curve = []
    for step in range(1, 11):
        th = step / 10.0
        pt = _solve_propulsion_point(
            throttle=th,
            kv=kv,
            stator_d_mm=stator_d,
            stator_h_mm=stator_h,
            v_nom=v_nom,
            cells_s=cells_s,
            prop_diam_m=prop_diam_m,
            prop_pitch_m=prop_pitch_m,
            blade_count=blade_count,
            empirical_data=emp_data,
        )
        throttle_curve.append({
            "throttle_pct": pt["throttle_pct"],
            "motor_thrust_g": pt["thrust_g"],
            "total_thrust_g": round(pt["thrust_g"] * num_motors, 1),
            "motor_current_a": pt["current_a"],
            "total_current_a": round(pt["current_a"] * num_motors, 1),
            "total_power_w": round(pt["power_w"] * num_motors, 1),
            "rpm": pt["rpm"],
            "efficiency_g_w": pt["efficiency_g_w"],
        })

    max_pt = throttle_curve[-1]
    max_thrust_g_per_motor = max_pt["motor_thrust_g"]
    max_force_newtons = (max_thrust_g_per_motor / 1000.0) * GRAVITY
    total_max_thrust_g = max_pt["total_thrust_g"]
    twr = total_max_thrust_g / mass_g if mass_g > 0 else 0.0

    # 4. True Hover Point via Momentum / Actuator Disk Theory
    single_disk_area_m2 = math.pi * ((prop_diam_m / 2.0) ** 2)
    total_disk_area_m2 = single_disk_area_m2 * num_motors
    disk_loading_g_dm2 = mass_g / (total_disk_area_m2 * 100.0) if total_disk_area_m2 > 0 else 0.0

    # Ideal Induced Power at Hover: P_i = (W)^(3/2) / sqrt(2 * rho * A_total)
    weight_n = mass_kg * GRAVITY
    p_induced_w = (weight_n ** 1.5) / math.sqrt(2.0 * AIR_DENSITY_RHO * max(0.001, total_disk_area_m2))
    figure_of_merit = 0.64  # Typical multirotor prop FM
    drivetrain_eff = 0.80   # Motor * ESC efficiency at hover
    avionics_draw_w = 12.0  # FC + RX + VTX base electrical load

    hover_power_w = (p_induced_w / (figure_of_merit * drivetrain_eff)) + avionics_draw_w
    hover_current_total_a = hover_power_w / max(7.4, v_nom)

    # Interpolate exact hover throttle % from our propulsion curve
    hover_throttle_ratio = 0.5
    for i in range(len(throttle_curve)):
        if throttle_curve[i]["total_thrust_g"] >= mass_g:
            if i == 0:
                hover_throttle_ratio = (mass_g / max(1.0, throttle_curve[0]["total_thrust_g"])) * 0.10
            else:
                prev_t = throttle_curve[i - 1]["total_thrust_g"]
                curr_t = throttle_curve[i]["total_thrust_g"]
                frac = (mass_g - prev_t) / max(1.0, curr_t - prev_t)
                hover_throttle_ratio = ((i) + frac) / 10.0
            break
    else:
        hover_throttle_ratio = 1.0
        warnings.append("CRITICAL: Total thrust is insufficient to hover All-Up Weight!")

    hover_throttle_pct = round(hover_throttle_ratio * 100.0, 1)

    # 5. Peukert's Law Flight Time Calculation (80% usable DoD)
    usable_cap_ah = (cap_mah / 1000.0) * 0.80
    peukert_exponent = 1.06  # Modern LiPo Peukert constant
    effective_hover_amps = max(0.5, hover_current_total_a ** peukert_exponent)
    hover_flight_time_min = round((usable_cap_ah / effective_hover_amps) * 60.0, 1)
    mixed_flight_time_min = round(hover_flight_time_min * 0.72, 1)

    # 6. Pitch Speed & Drag-Limited Top Speed
    max_rpm = max_pt["rpm"]
    pitch_speed_ms = (max_rpm / 60.0) * prop_pitch_m
    top_speed_ms = round(pitch_speed_ms * 0.76, 1)
    top_speed_kmh = int(round(top_speed_ms * 3.6))

    wb_meters = wb_mm / 1000.0
    angular_damping = 0.15 if twr > 6.0 else 0.35
    linear_damping = 0.25

    config = {
        "mass_kg": round(mass_kg, 3),
        "motor_max_force_n": round(max_force_newtons, 2),
        "collider_size_m": [round(wb_meters / 1.4, 3), 0.05, round(wb_meters / 1.4, 3)],
        "center_of_mass_offset": [0.0, 0.0, 0.0],
        "dynamics": {
            "twr": round(twr, 2),
            "hover_throttle": round(hover_throttle_ratio, 3),
            "hover_throttle_pct": hover_throttle_pct,
            "linear_damping": linear_damping,
            "angular_damping": angular_damping,
            "max_velocity_ms": top_speed_ms,
        },
        "aerodynamics": {
            "disk_loading_g_dm2": round(disk_loading_g_dm2, 2),
            "total_disk_area_cm2": round(total_disk_area_m2 * 10000.0, 1),
            "pitch_speed_kmh": int(round(pitch_speed_ms * 3.6)),
            "top_speed_kmh": top_speed_kmh,
            "induced_hover_power_w": round(p_induced_w, 1),
            "total_hover_power_w": round(hover_power_w, 1),
            "max_rpm": max_rpm,
        },
        "electrical": {
            "system_voltage_v": round(v_nom, 1),
            "hover_current_total_a": round(hover_current_total_a, 2),
            "peak_current_per_motor_a": max_pt["motor_current_a"],
            "peak_current_total_a": max_pt["total_current_a"],
            "peak_power_total_w": max_pt["total_power_w"],
        },
        "throttle_curve": throttle_curve,
        "mass_breakdown": mass_breakdown,
        "warnings": warnings,
        "meta": {
            "total_weight_g": round(mass_g, 1),
            "est_flight_time_min": hover_flight_time_min,
            "mixed_flight_time_min": mixed_flight_time_min,
            "top_speed_kmh": top_speed_kmh,
            "disk_loading": round(disk_loading_g_dm2, 2),
            "status": "FLYABLE" if twr >= 2.0 else ("MARGINAL" if twr >= 1.3 else "UNDERPOWERED"),
        },
    }

    print(
        f"   📊 Physics Complete: AUW={mass_g:.1f}g | MaxThrust={max_thrust_g_per_motor:.0f}g/motor "
        f"| TWR={twr:.2f}:1 | Hover={hover_throttle_pct}% ({hover_current_total_a:.1f}A) | Endurance={hover_flight_time_min}m"
    )
    return config
# --- END OF FILE app/services/physics_service.py ---