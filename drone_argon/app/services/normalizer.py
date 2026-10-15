# --- START OF FILE app/services/normalizer.py ---
import os
import re
from typing import Any

# Central Path Resolution (checks ./data/ first, falls back to project root)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

def resolve_data_path(filename: str) -> str:
    data_path = os.path.join(DATA_DIR, filename)
    root_path = os.path.join(PROJECT_ROOT, filename)
    if os.path.exists(data_path):
        return data_path
    if os.path.exists(root_path):
        return root_path
    return data_path


def extract_float(val: Any, default: float = 0.0) -> float:
    """Extracts the first valid floating-point number from any string or number."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(val).replace(",", ""))
    return float(match.group(0)) if match else default


def parse_weight_g(specs: dict) -> tuple[float, bool]:
    """
    Searches all known weight keys and normalizes units (g, kg, oz, lbs) into grams.
    Returns: (weight_in_grams, is_empirical)
    """
    if not isinstance(specs, dict):
        return 0.0, False

    weight_keys = [
        "weight_g", "weight", "Weight", "mass_g", "mass", "Mass",
        "net_weight", "Weight (g)", "weight_grams"
    ]
    raw_val = None
    for k in weight_keys:
        if k in specs and specs[k] is not None:
            raw_val = specs[k]
            break

    # Case-insensitive fallback scan
    if raw_val is None:
        for k, v in specs.items():
            if "weight" in k.lower() or "mass" in k.lower():
                raw_val = v
                break

    if raw_val is None:
        return 0.0, False

    if isinstance(raw_val, (int, float)):
        val = float(raw_val)
        return (val, True) if val > 0 else (0.0, False)

    s = str(raw_val).lower().strip()
    num = extract_float(s, 0.0)
    if num <= 0:
        return 0.0, False

    if "kg" in s or "kilogram" in s:
        num *= 1000.0
    elif "oz" in s or "ounce" in s:
        num *= 28.3495
    elif "lb" in s or "pound" in s:
        num *= 453.592

    return round(num, 2), True


def parse_mounting_patterns_mm(specs: dict, keys: list[str]) -> list[float]:
    """
    Extracts bolt-hole spacing patterns (e.g. '16x16 / 19*19mm' -> [16.0, 19.0],
    '30.5*30.5/25.5*25.5/20*20' -> [20.0, 25.5, 30.5]).
    """
    found = set()
    raw_strings = []

    for k in keys:
        if k in specs and specs[k]:
            raw_strings.append(str(specs[k]))

    for k, v in specs.items():
        if "mount" in k.lower() and v:
            raw_strings.append(str(v))

    combined = " | ".join(raw_strings)
    if not combined:
        return []

    # Match NxN or N*N patterns like 30.5x30.5, 25.5*25.5, 16x16, 19x19
    pairs = re.findall(r"(\d+(?:\.\d+)?)\s*[xX\*]\s*(\d+(?:\.\d+)?)", combined)
    for a, b in pairs:
        fa, fb = float(a), float(b)
        if 5.0 <= fa <= 60.0:
            found.add(fa)
        if 5.0 <= fb <= 60.0:
            found.add(fb)

    # Also check single standard numbers if no NxN pair was written
    if not found:
        for std in [6.6, 9.0, 12.0, 16.0, 19.0, 20.0, 25.0, 25.5, 30.0, 30.5]:
            if re.search(rf"\b{re.escape(str(int(std) if std.is_integer() else std))}\b", combined):
                found.add(std)

    # Standardize 25.0 -> 25.5 and 30.0 -> 30.5 for FC stacks
    normalized = set()
    for val in found:
        if val == 30.0:
            normalized.add(30.5)
        elif val == 25.0:
            normalized.add(25.5)
        else:
            normalized.add(val)

    return sorted(normalized)


def parse_dimensions_mm(val: Any) -> tuple[float, float, float]:
    """Parses dict {'length':..,'width':..,'height':..} or string '78x40x34mm' into (L, W, H)."""
    if isinstance(val, dict):
        l = extract_float(val.get("length") or val.get("l"), 0.0)
        w = extract_float(val.get("width") or val.get("w"), 0.0)
        h = extract_float(val.get("height") or val.get("h") or val.get("thickness"), 0.0)
        return (l, w, h)
    if isinstance(val, (list, tuple)) and len(val) >= 3:
        return (extract_float(val[0]), extract_float(val[1]), extract_float(val[2]))
    if not val:
        return (0.0, 0.0, 0.0)

    s = str(val).lower().replace("mm", "")
    nums = [float(m.group(0)) for m in re.finditer(r"\d+(?:\.\d+)?", s)]
    while len(nums) < 3:
        nums.append(0.0)
    return (nums[0], nums[1], nums[2])


def parse_stator_size(specs: dict, model_name: str = "") -> tuple[float, float, str]:
    """
    Returns (stator_diameter_mm, stator_height_mm, stator_code_str)
    e.g., '2809' -> (28.0, 9.0, '2809')
    """
    raw = str(specs.get("stator_size") or specs.get("stator") or "")
    for source in (raw, model_name):
        match = re.search(r"\b([0-8]\d)([0-2]\d)\b", source)
        if match:
            d = float(match.group(1))
            h = float(match.group(2))
            if 6.0 <= d <= 85.0 and 2.0 <= h <= 35.0:
                return d, h, f"{int(d):02d}{int(h):02d}"
    return 22.0, 7.0, "2207"


def parse_cell_range(specs: dict, model_name: str = "") -> tuple[int, int]:
    """Extracts (min_cells_s, max_cells_s) from strings like '3-6S', '6S', or '22.2V'."""
    combined = f"{specs.get('input_voltage_range', '')} {specs.get('cell_count_s', '')} {specs.get('cells', '')} {specs.get('voltage_v', '')} {model_name}"
    # Range like 3-6S or 4S-6S
    rng = re.search(r"(\d+)\s*[sS]?\s*[-~to]+\s*(\d+)\s*[sS]", combined)
    if rng:
        return int(rng.group(1)), int(rng.group(2))

    # Single cell count like 6S
    single = re.search(r"\b(\d{1,2})\s*[sS]\b", combined)
    if single:
        c = int(single.group(1))
        return c, c

    # Raw numeric cell_count_s
    raw_c = specs.get("cell_count_s") or specs.get("cells")
    if isinstance(raw_c, (int, float)) and 1 <= int(raw_c) <= 24:
        return int(raw_c), int(raw_c)

    # Voltage range like 0-36V or 22.2V
    v_rng = re.search(r"(\d+(?:\.\d+)?)\s*[vV]?\s*[-~to]+\s*(\d+(?:\.\d+)?)\s*[vV]", combined)
    if v_rng:
        v_min, v_max = float(v_rng.group(1)), float(v_rng.group(2))
        s_min = max(1, int(round(v_min / 3.7))) if v_min > 3.0 else 2
        s_max = max(s_min, int(round(v_max / 4.2)))
        return s_min, s_max

    return 0, 0


def parse_c_rating(specs: dict) -> tuple[float, float]:
    """Extracts (continuous_c, burst_c) from strings like '150C / 260C Burst'."""
    raw = str(specs.get("c_rating") or specs.get("discharge_rate_c") or "")
    nums = [float(m.group(0)) for m in re.finditer(r"\d+(?:\.\d+)?", raw)]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], nums[0] * 1.5
    return 75.0, 120.0


def normalize_component(item: dict) -> dict:
    """
    Guarantees consistent keys and adds a strongly-typed 'normalized' dict to a BOM component.
    """
    comp = dict(item)
    cat = comp.get("category") or comp.get("part_type") or "Unknown"
    name = comp.get("model_name") or comp.get("product_name") or f"Unnamed {cat}"
    specs = comp.get("specs") or comp.get("engineering_specs") or comp.get("engineering_data") or {}
    if not isinstance(specs, dict):
        specs = {}

    # Synchronize top-level aliases so no downstream service ever KeyErrors
    comp["category"] = cat
    comp["part_type"] = cat
    comp["model_name"] = name
    comp["product_name"] = name
    comp["specs"] = specs
    comp["engineering_specs"] = specs

    weight_g, weight_empirical = parse_weight_g(specs)
    min_s, max_s = parse_cell_range(specs, name)
    dims = parse_dimensions_mm(specs.get("dimensions_mm") or specs.get("dimensions"))

    norm = {
        "weight_g": weight_g,
        "weight_is_empirical": weight_empirical,
        "min_cells_s": min_s,
        "max_cells_s": max_s,
        "dimensions_mm": dims,
    }

    cat_lower = cat.lower()
    if "frame" in cat_lower:
        wb = extract_float(specs.get("wheelbase_mm") or specs.get("wheelbase"), 0.0)
        max_prop = extract_float(specs.get("max_prop_size_inch") or specs.get("max_prop_inch"), 0.0)
        if max_prop == 0.0:
            m = re.search(r"\b([3-9]|1[0-5])\s*(?:inch|\"|in)\b", name.lower())
            if m:
                max_prop = float(m.group(1))
            elif "7" in name:
                max_prop = 7.0
            elif "5" in name:
                max_prop = 5.1
        if wb == 0.0:
            wb = (max_prop * 25.4 * 1.8) if max_prop > 0 else 225.0

        norm.update({
            "wheelbase_mm": wb,
            "max_prop_size_inch": max_prop if max_prop > 0 else round((wb / 1.8) / 25.4, 1),
            "arm_thickness_mm": extract_float(specs.get("arm_thickness_mm"), 5.0),
            "motor_mount_patterns_mm": parse_mounting_patterns_mm(specs, ["motor_mount_mm", "motor_mounting_pattern_mm", "Mounting Pattern"]) or [16.0, 19.0],
            "stack_mount_patterns_mm": parse_mounting_patterns_mm(specs, ["electronics_mount_mm", "electronics_mounting_patterns_mm", "stack_mount_mm", "Mounting Pattern"]) or [20.0, 30.5],
            "camera_width_mm": extract_float(specs.get("fpv_camera_width_mm") or specs.get("fpv_camera_mount_width_mm"), 19.0),
        })

    elif "motor" in cat_lower:
        stator_d, stator_h, stator_code = parse_stator_size(specs, name)
        kv = extract_float(specs.get("kv_rating") or specs.get("kv"), 0.0)
        if kv == 0.0:
            m_kv = re.search(r"(\d{3,5})\s*kv", name.lower())
            kv = float(m_kv.group(1)) if m_kv else 1750.0
        mount_pats = parse_mounting_patterns_mm(specs, ["mounting_bolt_pattern_mm", "mounting_mm", "motor_mount_mm"])
        if not mount_pats:
            mount_pats = [19.0] if stator_d >= 28 else ([16.0] if stator_d >= 22 else [12.0 if stator_d >= 14 else 9.0])

        norm.update({
            "stator_d_mm": stator_d,
            "stator_h_mm": stator_h,
            "stator_code": stator_code,
            "kv": kv,
            "shaft_diameter_mm": extract_float(specs.get("shaft_diameter_mm"), 5.0 if stator_d >= 20 else 1.5),
            "motor_mount_patterns_mm": mount_pats,
            "max_current_a": extract_float(specs.get("max_current_a") or specs.get("peak_current_a"), 0.0),
            "thrust_data": specs.get("thrust_data") or specs.get("thrust_table"),
        })

    elif "prop" in cat_lower:
        diam_in = extract_float(specs.get("diameter_inches") or specs.get("diameter_inch") or specs.get("diameter_in"), 0.0)
        diam_mm = extract_float(specs.get("diameter_mm"), 0.0)
        if diam_in == 0.0 and diam_mm > 0:
            diam_in = diam_mm / 25.4
        if diam_in == 0.0:
            code_m = re.search(r"\b([3-9])(\d)(\d{2})\b", name)
            if code_m:
                diam_in = float(f"{code_m.group(1)}.{code_m.group(2)}")
            else:
                diam_in = 5.0
        pitch_in = extract_float(specs.get("pitch_inches") or specs.get("pitch_inch") or specs.get("pitch"), 0.0)
        if pitch_in == 0.0:
            code_m = re.search(r"\b([3-9])(\d)(\d{2})\b", name)
            pitch_in = float(f"{code_m.group(3)[0]}.{code_m.group(3)[1]}") if code_m else round(diam_in * 0.55, 1)

        hub_str = str(specs.get("hub_mount_type") or specs.get("shaft_mm") or "5mm")
        shaft_bore = 1.5 if "1.5" in hub_str or "t-mount" in hub_str.lower() else 5.0

        norm.update({
            "diameter_inch": round(diam_in, 2),
            "diameter_mm": round(diam_in * 25.4, 2),
            "pitch_inch": round(pitch_in, 2),
            "blade_count": int(extract_float(specs.get("blade_count") or specs.get("blades"), 3)),
            "shaft_bore_mm": shaft_bore,
        })

    elif "battery" in cat_lower:
        cells = max_s if max_s > 0 else int(extract_float(specs.get("cell_count_s") or specs.get("cells"), 6))
        cap_mah = extract_float(specs.get("capacity_mah") or specs.get("capacity"), 1300.0)
        cont_c, burst_c = parse_c_rating(specs)
        conn = str(specs.get("connector_type") or specs.get("connector") or "XT60").upper()
        norm.update({
            "cells_s": cells,
            "nominal_voltage_v": round(cells * 3.7, 2),
            "full_voltage_v": round(cells * 4.2, 2),
            "capacity_mah": cap_mah,
            "c_continuous": cont_c,
            "c_burst": burst_c,
            "max_continuous_amps": round((cap_mah / 1000.0) * cont_c, 1),
            "max_burst_amps": round((cap_mah / 1000.0) * burst_c, 1),
            "connector": "XT90" if "XT90" in conn else ("XT30" if "XT30" in conn else "XT60"),
        })

    elif "fc" in cat_lower or "stack" in cat_lower or "esc" in cat_lower:
        stack_pats = parse_mounting_patterns_mm(specs, ["mounting_pattern_mm", "mounting_mm", "mount_mm"])
        is_pixhawk = "pixhawk" in name.lower() or "cube" in name.lower()
        esc_a = extract_float(
            specs.get("continuous_current_a") or specs.get("esc_current_a") or specs.get("current_a"),
            0.0
        )
        if esc_a == 0.0:
            m_amp = re.search(r"\b(\d{2,3})\s*[aA]\b", name)
            esc_a = float(m_amp.group(1)) if m_amp else 55.0

        norm.update({
            "stack_mount_patterns_mm": stack_pats,
            "is_pixhawk_form_factor": is_pixhawk,
            "esc_continuous_current_a": esc_a,
            "uart_count": int(extract_float(specs.get("uart_count"), 5)),
            "has_9v_bec": any(x in str(specs).lower() for x in ["9v", "10v", "12v", "bec"]),
        })

    comp["normalized"] = norm
    return comp


def normalize_bom(bom: list[dict]) -> list[dict]:
    """Normalizes an entire Bill of Materials list."""
    return [normalize_component(item) for item in (bom or []) if isinstance(item, dict)]
# --- END OF FILE app/services/normalizer.py ---