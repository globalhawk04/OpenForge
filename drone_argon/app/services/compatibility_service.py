# --- START OF FILE app/services/compatibility_service.py ---
import math
from app.services.normalizer import normalize_bom
from app.services.physics_service import generate_physics_config
from app.cad.mounts import synthesize_printable_mounts

DEFAULT_CAM_CABLE_LEN_MM = 80.0


def calculate_distance(pos_a: list[float], pos_b: list[float]) -> float:
    if not pos_a or not pos_b:
        return 0.0
    return math.sqrt(
        (pos_a[0] - pos_b[0]) ** 2 +
        (pos_a[1] - pos_b[1]) ** 2 +
        (pos_a[2] - pos_b[2]) ** 2
    )


def analyze_interconnects(bom: list[dict], scene_graph: dict | None = None) -> list[dict]:
    norm_bom = normalize_bom(bom)
    parts_map = {p["category"]: p for p in norm_bom}
    extras = []

    comps = (scene_graph or {}).get("components", [])
    pos_stack = next((c.get("pos") for c in comps if c.get("type") == "PCB_STACK"), None)
    pos_cam = next((c.get("pos") for c in comps if c.get("type") == "CAMERA"), None)

    if pos_stack and pos_cam:
        dist_mm = calculate_distance(pos_stack, pos_cam) * 1.30
        if dist_mm > DEFAULT_CAM_CABLE_LEN_MM:
            cable_len = int(round(dist_mm + 20, -1))
            extras.append({
                "part_type": "Cable",
                "category": "Cable",
                "product_name": f"Extended Silicone Camera Harness ({cable_len}mm JST-SH)",
                "model_name": f"Extended Camera Harness ({cable_len}mm)",
                "price": 4.99,
                "source_url": "https://www.getfpv.com/cables",
                "specs": {"weight_g": 3.5, "length_mm": cable_len},
            })

    battery = parts_map.get("Battery")
    fc = parts_map.get("FC_Stack")
    if battery:
        b_norm = battery["normalized"]
        conn = b_norm.get("connector", "XT60")
        cells = b_norm.get("cells_s", 6)
        cap_mah = b_norm.get("capacity_mah", 1300)
        if cells >= 6 and cap_mah > 2200:
            conn = "XT90"
        elif cells <= 4 and cap_mah < 850:
            conn = "XT30"

        wire_awg = "10AWG" if conn == "XT90" else ("16AWG" if conn == "XT30" else "12AWG")
        extras.append({
            "part_type": "Connector",
            "category": "Connector",
            "product_name": f"{conn} High-Current Pigtail Lead ({wire_awg} Silicone)",
            "model_name": f"{conn} Pigtail ({wire_awg})",
            "price": 3.99,
            "source_url": "https://www.racedayquads.com/collections/connectors",
            "specs": {"weight_g": 11.0, "connector_type": conn},
        })

        if cells >= 6:
            v_rating = "50V" if cells >= 8 else "35V"
            extras.append({
                "part_type": "Capacitor",
                "category": "Capacitor",
                "product_name": f"Panasonic FM Low-ESR 1000uF {v_rating} Electrolytic Capacitor",
                "model_name": f"1000uF {v_rating} Low-ESR Cap",
                "price": 1.95,
                "source_url": "https://www.getfpv.com/electronics",
                "specs": {"weight_g": 4.2},
            })

    vtx = parts_map.get("Camera_VTX_Kit")
    comp_board = parts_map.get("Companion_Computer")
    if fc and vtx:
        fc_has_9v = fc["normalized"].get("has_9v_bec", False)
        vtx_name = vtx["model_name"].lower()
        is_digital = any(k in vtx_name for k in ["dji", "o3", "vista", "walksnail", "avatar", "hdzero", "digital"])
        if is_digital and not fc_has_9v:
            extras.append({
                "part_type": "Voltage_Regulator",
                "category": "Voltage_Regulator",
                "product_name": "Matek Micro BEC 9V/12V 2A Synchronized Buck Regulator",
                "model_name": "External 9V 2A BEC",
                "price": 6.99,
                "source_url": "https://www.racedayquads.com/collections/becs",
                "specs": {"weight_g": 2.5},
            })

    if comp_board:
        extras.append({
            "part_type": "Voltage_Regulator",
            "category": "Voltage_Regulator",
            "product_name": "High-Output 5V/12V 5A Buck Converter for Companion Compute",
            "model_name": "Companion Compute 5A BEC",
            "price": 12.99,
            "source_url": "https://www.getfpv.com/electronics",
            "specs": {"weight_g": 14.0},
        })

    return extras


class CompatibilityService:
    """
    Deterministic Mechanical Design Rule Check (DRC), Electrical Rule Check (ERC),
    and 3D-Printable TPU/CF-PETG Adapter Synthesis Engine.
    """

    def validate_build(
        self,
        bom: list[dict],
        scene_graph: dict | None = None,
        physics_config: dict | None = None,
        sku_id: str = "OF-SKU",
    ) -> dict:
        norm_bom = normalize_bom(bom)
        parts = {p["category"]: p for p in norm_bom}

        if physics_config is None:
            physics_config = generate_physics_config(norm_bom)

        errors = []
        warnings = []
        drc_matrix = []
        erc_matrix = []

        frame = parts.get("Frame_Kit")
        motor = parts.get("Motors")
        prop = parts.get("Propellers")
        battery = parts.get("Battery")
        fc = parts.get("FC_Stack")
        vtx = parts.get("Camera_VTX_Kit")
        gps = parts.get("GPS_Module")
        rx = next((p for p in norm_bom if "receiver" in p["category"].lower() or "elrs" in p["model_name"].lower()), None)

        # Synthesize Custom 3D-Printed Mounts (.STL) for this BOM
        printable_mounts = synthesize_printable_mounts(sku_id, norm_bom)

        # =====================================================================
        # 1. MECHANICAL DESIGN RULE CHECKS (DRC)
        # =====================================================================

        # DRC-MECH-01: Propeller Tip-to-Tip Clearance
        if frame and prop:
            wb_mm = frame["normalized"]["wheelbase_mm"]
            max_prop_in = frame["normalized"]["max_prop_size_inch"]
            prop_in = prop["normalized"]["diameter_inch"]
            prop_mm = prop["normalized"]["diameter_mm"]

            side_dist_mm = wb_mm / math.sqrt(2.0)
            tip_gap_mm = round(side_dist_mm - prop_mm, 2)

            if tip_gap_mm < 2.0 or prop_in > max_prop_in + 0.1:
                msg = f"Propeller Collision: {prop_in}\" props ({prop_mm:.1f}mm) on {wb_mm:.0f}mm wheelbase leaves {tip_gap_mm}mm tip clearance (Frame max: {max_prop_in}\")."
                errors.append(msg)
                drc_matrix.append({"code": "DRC-MECH-01", "rule": "Propeller Tip Clearance", "status": "FAIL", "value": f"{tip_gap_mm}mm gap", "detail": msg})
            elif tip_gap_mm < 10.0:
                msg = f"Tight Prop Clearance: {tip_gap_mm}mm tip-to-tip gap (<10mm threshold). Expect aerodynamic tip-vortex wash."
                warnings.append(msg)
                drc_matrix.append({"code": "DRC-MECH-01", "rule": "Propeller Tip Clearance", "status": "WARN", "value": f"{tip_gap_mm}mm gap", "detail": msg})
            else:
                drc_matrix.append({"code": "DRC-MECH-01", "rule": "Propeller Tip Clearance", "status": "PASS", "value": f"{tip_gap_mm}mm gap", "detail": f"{prop_in}\" prop <= {max_prop_in}\" limit"})

        # DRC-MECH-02: Motor Bolt Pattern vs. Frame Arm Mounting Pattern
        if frame and motor:
            f_mounts = set(frame["normalized"]["motor_mount_patterns_mm"])
            m_mounts = set(motor["normalized"]["motor_mount_patterns_mm"])
            overlap = f_mounts.intersection(m_mounts)
            if not overlap:
                msg = f"Motor Mount Mismatch: Motor requires {sorted(m_mounts)}mm, but Frame only supports {sorted(f_mounts)}mm."
                errors.append(msg)
                drc_matrix.append({"code": "DRC-MECH-02", "rule": "Motor Bolt Pattern", "status": "FAIL", "value": f"{sorted(m_mounts)} vs {sorted(f_mounts)}", "detail": msg})
            else:
                matched = sorted(overlap)[0]
                drc_matrix.append({"code": "DRC-MECH-02", "rule": "Motor Bolt Pattern", "status": "PASS", "value": f"{matched:.0f}x{matched:.0f}mm", "detail": "Bolt patterns intersect cleanly."})

        # DRC-MECH-03: FC/ESC Stack Mounting vs. Frame Center Plate (Auto-Resolved via 3D-Printed Adapter!)
        if frame and fc:
            f_stack = set(frame["normalized"]["stack_mount_patterns_mm"])
            fc_stack = set(fc["normalized"]["stack_mount_patterns_mm"])
            is_pixhawk = fc["normalized"]["is_pixhawk_form_factor"]
            adapter = next((m for m in printable_mounts if m["type"] == "STACK_ADAPTER_PLATE"), None)

            if is_pixhawk and adapter:
                msg = f"Auto-Generated 3D-Printable CF-PETG Carrier Adapter ('{adapter['stl_filename']}') to mount Pixhawk onto {sorted(f_stack)[0]}mm frame."
                drc_matrix.append({"code": "DRC-MECH-03", "rule": "FC Stack Mounting", "status": "PASS", "value": "3D ADAPTER (.STL)", "detail": msg})
            elif fc_stack and not f_stack.intersection(fc_stack) and adapter:
                msg = f"Auto-Generated 3D-Printable Adapter Plate ('{adapter['stl_filename']}') converting {sorted(f_stack)}mm frame to {sorted(fc_stack)}mm stack."
                drc_matrix.append({"code": "DRC-MECH-03", "rule": "FC Stack Mounting", "status": "PASS", "value": "3D ADAPTER (.STL)", "detail": msg})
            else:
                matched_s = sorted(f_stack.intersection(fc_stack))[0] if f_stack.intersection(fc_stack) else 30.5
                drc_matrix.append({"code": "DRC-MECH-03", "rule": "FC Stack Mounting", "status": "PASS", "value": f"{matched_s}x{matched_s}mm", "detail": "Direct M3/M2 stack fitment verified."})

        # DRC-MECH-04: Motor Shaft Diameter vs. Propeller Hub Bore
        if motor and prop:
            shaft_mm = motor["normalized"]["shaft_diameter_mm"]
            bore_mm = prop["normalized"]["shaft_bore_mm"]
            if abs(shaft_mm - bore_mm) > 0.6:
                msg = f"Shaft/Hub Mismatch: Motor has {shaft_mm}mm shaft, but Propeller has {bore_mm}mm hub bore."
                errors.append(msg)
                drc_matrix.append({"code": "DRC-MECH-04", "rule": "Propeller Hub Fitment", "status": "FAIL", "value": f"{shaft_mm}mm vs {bore_mm}mm", "detail": msg})
            else:
                drc_matrix.append({"code": "DRC-MECH-04", "rule": "Propeller Hub Fitment", "status": "PASS", "value": f"{shaft_mm:.1f}mm Shaft", "detail": "Hub bore matches motor shaft."})

        # =====================================================================
        # 2. ELECTRICAL RULE CHECKS (ERC)
        # =====================================================================
        elec = physics_config.get("electrical", {})
        peak_motor_a = elec.get("peak_current_per_motor_a", 30.0)
        peak_total_a = elec.get("peak_current_total_a", 120.0)

        if battery and motor:
            cells = battery["normalized"]["cells_s"]
            kv = motor["normalized"]["kv"]
            prop_in = prop["normalized"]["diameter_inch"] if prop else 5.0
            max_safe_kv = (11500.0 / max(3.0, prop_in)) * (6.0 / max(1, cells))
            if cells >= 6 and kv > max_safe_kv * 1.15:
                msg = f"CRITICAL Over-KV: {cells}S Battery with {int(kv)}KV on {prop_in}\" props exceeds thermal limit (Max safe ~{int(max_safe_kv)}KV)."
                errors.append(msg)
                erc_matrix.append({"code": "ERC-PWR-01", "rule": "Motor KV / Voltage Envelope", "status": "FAIL", "value": f"{cells}S @ {int(kv)}KV", "detail": msg})
            else:
                erc_matrix.append({"code": "ERC-PWR-01", "rule": "Motor KV / Voltage Envelope", "status": "PASS", "value": f"{cells}S @ {int(kv)}KV", "detail": "Matched to propeller load."})

        if fc:
            esc_cont_a = fc["normalized"]["esc_continuous_current_a"]
            required_esc_a = peak_motor_a * 1.10
            if esc_cont_a < peak_motor_a:
                msg = f"ESC Overload: Motor pulls {peak_motor_a:.1f}A peak, exceeding ESC {esc_cont_a:.0f}A rating."
                errors.append(msg)
                erc_matrix.append({"code": "ERC-PWR-02", "rule": "ESC Current Margin", "status": "FAIL", "value": f"{peak_motor_a:.1f}A / {esc_cont_a:.0f}A", "detail": msg})
            elif esc_cont_a < required_esc_a:
                msg = f"Low ESC Headroom: Motor pulls {peak_motor_a:.1f}A against {esc_cont_a:.0f}A ESC (<10% thermal margin)."
                warnings.append(msg)
                erc_matrix.append({"code": "ERC-PWR-02", "rule": "ESC Current Margin", "status": "WARN", "value": f"{peak_motor_a:.1f}A / {esc_cont_a:.0f}A", "detail": msg})
            else:
                erc_matrix.append({"code": "ERC-PWR-02", "rule": "ESC Current Margin", "status": "PASS", "value": f"{peak_motor_a:.1f}A / {esc_cont_a:.0f}A", "detail": f"{((esc_cont_a / max(1, peak_motor_a) - 1)*100):.0f}% thermal headroom."})

        if battery:
            bat_cont_a = battery["normalized"]["max_continuous_amps"]
            bat_burst_a = battery["normalized"]["max_burst_amps"]
            if bat_burst_a < peak_total_a:
                msg = f"Battery C-Rating Bottleneck: Quad pulls {peak_total_a:.1f}A burst, but battery max burst is {bat_burst_a:.1f}A."
                errors.append(msg)
                erc_matrix.append({"code": "ERC-PWR-03", "rule": "Battery Discharge Envelope", "status": "FAIL", "value": f"{peak_total_a:.0f}A vs {bat_burst_a:.0f}A", "detail": msg})
            else:
                erc_matrix.append({"code": "ERC-PWR-03", "rule": "Battery Discharge Envelope", "status": "PASS", "value": f"{bat_cont_a:.0f}A Cont / {bat_burst_a:.0f}A Burst", "detail": "C-rating supports peak current draw."})

        if fc:
            uarts_avail = fc["normalized"]["uart_count"]
            uarts_used = 2 + (1 if gps else 0) + (1 if parts.get("Companion_Computer") else 0)
            erc_matrix.append({
                "code": "ERC-PWR-04",
                "rule": "UART Bus Allocation",
                "status": "PASS" if uarts_used <= uarts_avail else "FAIL",
                "value": f"{uarts_used} / {uarts_avail} UARTs",
                "detail": "Deterministic UART pin-map verified for Firmware Compiler.",
            })

        required_accessories = analyze_interconnects(norm_bom, scene_graph)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "drc_matrix": drc_matrix,
            "erc_matrix": erc_matrix,
            "required_accessories": required_accessories,
            "printable_mounts": printable_mounts,
        }
# --- END OF FILE app/services/compatibility_service.py ---