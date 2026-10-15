# --- START OF FILE app/services/vision_service.py ---
import asyncio
import json
import os
import re
from io import BytesIO
import PIL.Image
import requests
import google.generativeai as genai
from app.config import settings

if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

FORENSIC_ASSEMBLY_SCHEMAS = {
    "Frame_Kit": {
        "wheelbase_mm": {"value": "float (diagonal motor-to-motor mm)", "confidence": "float"},
        "max_prop_size_inch": {"value": "float (max propeller diameter in inches)", "confidence": "float"},
        "arm_thickness_mm": {"value": "float (carbon arm thickness in mm, e.g. 5.0 or 6.0)", "confidence": "float"},
        "standoff_height_mm": {"value": "float (internal Z-deck height in mm, default 20-28)", "confidence": "float"},
        "motor_mount_mm": {"value": "string (e.g. '16x16' or '16x16 / 19x19')", "confidence": "float"},
        "electronics_mount_mm": {"value": "string (e.g. '30.5x30.5 / 20x20')", "confidence": "float"},
        "fpv_camera_width_mm": {"value": "float (camera cage spacing in mm: 14, 19, or 20)", "confidence": "float"},
        "weight_g": {"value": "float (total frame weight in grams)", "confidence": "float"},
    },
    "Motors": {
        "stator_size": {"value": "string (4-digit stator code, e.g. '2207', '2809')", "confidence": "float"},
        "kv_rating": {"value": "float (RPM per volt, e.g. 1750, 1250)", "confidence": "float"},
        "mounting_bolt_pattern_mm": {"value": "string (hole spacing on base, e.g. '16x16' or '19x19')", "confidence": "float"},
        "mount_thread_size": {"value": "string ('M2' or 'M3')", "confidence": "float"},
        "shaft_diameter_mm": {"value": "float (propeller shaft diameter in mm: 5.0 or 1.5)", "confidence": "float"},
        "input_voltage_range": {"value": "string (e.g. '4-6S' or '6S')", "confidence": "float"},
        "max_current_a": {"value": "float (peak current in Amps from spec/thrust table)", "confidence": "float"},
        "weight_g": {"value": "float (single motor weight in grams including wires)", "confidence": "float"},
        "thrust_data": {
            "value": {
                "50_pct_g": "float or null (thrust in grams at 50% throttle)",
                "100_pct_g": "float or null (max thrust in grams at 100% throttle)",
                "test_prop": "string or null (propeller used in test table)"
            },
            "confidence": "float"
        }
    },
    "Propellers": {
        "diameter_inches": {"value": "float (prop diameter in inches, e.g. 5.1, 7.0)", "confidence": "float"},
        "pitch_inches": {"value": "float (blade pitch in inches, e.g. 3.7, 4.3)", "confidence": "float"},
        "blade_count": {"value": "int (number of blades, e.g. 2, 3)", "confidence": "float"},
        "hub_mount_type": {"value": "string ('5mm Shaft' or '1.5mm T-Mount')", "confidence": "float"},
        "hub_thickness_mm": {"value": "float (center hub thickness in mm, typically 6.0-8.0)", "confidence": "float"},
        "weight_g": {"value": "float (weight of 1 propeller in grams)", "confidence": "float"},
    },
    "FC_Stack": {
        "stack_type": {"value": "string (MUST be 'FC_ESC_COMBO', 'FC_ONLY', 'ESC_ONLY', or 'AIO')", "confidence": "float"},
        "mounting_pattern_mm": {"value": "string (hole spacing, e.g. '30.5x30.5', '20x20', '25.5x25.5')", "confidence": "float"},
        "stack_height_mm": {"value": "float (total installed height in mm, typically 14-20mm)", "confidence": "float"},
        "continuous_current_a": {"value": "float (ESC continuous current rating in Amps per motor, or 0 if FC_ONLY)", "confidence": "float"},
        "input_voltage_range": {"value": "string (e.g. '3-6S' or '4-8S')", "confidence": "float"},
        "mcu": {"value": "string (e.g. 'STM32F722', 'STM32H743')", "confidence": "float"},
        "uart_count": {"value": "int (number of available serial UART ports)", "confidence": "float"},
        "bec_outputs": {"value": "string (e.g. '5V 3A, 9V 3A')", "confidence": "float"},
        "weight_g": {"value": "float (weight in grams)", "confidence": "float"},
    },
    "Battery": {
        "cell_count_s": {"value": "int (number of series cells, e.g. 4, 6)", "confidence": "float"},
        "capacity_mah": {"value": "float (capacity in mAh, e.g. 1300, 2200)", "confidence": "float"},
        "c_rating": {"value": "string (continuous/burst discharge C rating, e.g. '130C / 200C')", "confidence": "float"},
        "connector_type": {"value": "string (main discharge plug: 'XT30', 'XT60', 'XT90')", "confidence": "float"},
        "dimensions_mm": {
            "value": {"length": "float", "width": "float", "height": "float"},
            "confidence": "float"
        },
        "weight_g": {"value": "float (battery mass in grams)", "confidence": "float"},
    },
    "Camera_VTX_Kit": {
        "system_type": {"value": "string ('DIGITAL_HD' or 'ANALOG')", "confidence": "float"},
        "camera_width_mm": {"value": "float (camera housing width in mm: 14, 19, or 20)", "confidence": "float"},
        "vtx_mounting_mm": {"value": "string (e.g. '20x20', '25.5x25.5', '30.5x30.5')", "confidence": "float"},
        "input_voltage_range": {"value": "string (e.g. '7.4V-26.4V' or '9V')", "confidence": "float"},
        "antenna_connector": {"value": "string ('U.FL', 'MMCX', 'SMA', or 'RP-SMA')", "confidence": "float"},
        "weight_g": {"value": "float (combined weight in grams)", "confidence": "float"},
    }
}


def get_deterministic_vision_schema(part_type: str) -> dict:
    pt = part_type.lower()
    if "frame" in pt:
        schema = FORENSIC_ASSEMBLY_SCHEMAS["Frame_Kit"]
    elif "motor" in pt:
        schema = FORENSIC_ASSEMBLY_SCHEMAS["Motors"]
    elif "prop" in pt:
        schema = FORENSIC_ASSEMBLY_SCHEMAS["Propellers"]
    elif "fc" in pt or "stack" in pt or "esc" in pt:
        schema = FORENSIC_ASSEMBLY_SCHEMAS["FC_Stack"]
    elif "bat" in pt:
        schema = FORENSIC_ASSEMBLY_SCHEMAS["Battery"]
    elif "cam" in pt or "vtx" in pt or "video" in pt:
        schema = FORENSIC_ASSEMBLY_SCHEMAS["Camera_VTX_Kit"]
    else:
        schema = {
            "dimensions_mm": {"value": "string (LxWxH in mm)", "confidence": "float"},
            "input_voltage_range": {"value": "string", "confidence": "float"},
            "connector_type": {"value": "string", "confidence": "float"},
            "weight_g": {"value": "float", "confidence": "float"},
        }
    return {
        "prompt_text": f"Extract exact mechanical fitment and electrical specifications for {part_type}.",
        "json_schema": json.dumps(schema, indent=2),
    }


def _fetch_single_image_sync(url: str) -> PIL.Image.Image | None:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            return PIL.Image.open(BytesIO(resp.content))
    except Exception:
        pass
    return None


async def analyze_specs_multimodal(
    text_context: str,
    image_urls: list[str],
    part_type: str,
    dynamic_prompt_object: dict | None = None,
    local_image_paths: list[str] | None = None,
    evidence_dir: str | None = None,
) -> dict | None:
    """
    Loads the locally archived images from `evidence_dir` (or falls back to HTTP download),
    runs Gemini Vision analysis, and saves `forensic_vision_report.json` to disk for human review.
    """
    images = []

    # 1. Prefer locally archived images saved by the open Chromium browser
    if local_image_paths:
        for p in local_image_paths[:4]:
            if p and os.path.exists(p):
                try:
                    images.append(PIL.Image.open(p))
                except Exception:
                    continue

    # 2. Fallback to HTTP fetch if no local images were passed
    if not images and image_urls:
        tasks = [asyncio.to_thread(_fetch_single_image_sync, u) for u in image_urls[:3]]
        fetched = await asyncio.gather(*tasks)
        images = [img for img in fetched if img is not None]

    print(f"👁️  Fusion AI: Analyzing {len(images)} archived images + scraped text for {part_type}...")

    if not images and len(text_context) < 50:
        return {"error": "no_data_available"}

    canonical_obj = get_deterministic_vision_schema(part_type)
    json_schema = canonical_obj["json_schema"]

    full_prompt = f"""
    You are a Principal Mechanical & Avionics Hardware Engineer performing incoming inspection on a '{part_type}'.

    **CRITICAL OBJECTIVE:**
    We are physically assembling and flying this drone. Extract exact mechanical mounting dimensions, thread sizes, Z-heights, electrical ratings, and mass from the SCRAPED TEXT and the attached TECHNICAL DIAGRAMS.

    **SOURCES:**
    1. SCRAPED HTML TABLES & SPEC LISTS:
    {text_context[:8500]}

    2. ATTACHED IMAGES: (Inspect dimension drawings, caliper/ruler callouts, motor thrust tables, and PCB silkscreens).

    **FORENSIC RULES:**
    - **Trust Engineering Drawings Over Marketing Text:** If a technical blueprint image shows "19x19mm M3", use that exact value.
    - **FC Stack Disambiguation:** For `FC_Stack`, carefully check if the product includes BOTH a Flight Controller AND a 4-in-1 ESC (`FC_ESC_COMBO`) or is ONLY a standalone Flight Controller (`FC_ONLY`).
    - **Unit Discipline:** Weights MUST be numeric grams (`weight_g`). Dimensions MUST be in millimeters (`mm`) unless the key explicitly says `inches`.
    - **Confidence Scoring:** Rate your confidence (`0.0` to `1.0`) for each field.

    **REQUIRED JSON OUTPUT SCHEMA:**
    {json_schema}
    """

    try:
        model = genai.GenerativeModel("gemini-2.5-pro")
        inputs = [full_prompt] + images
        response = await model.generate_content_async(
            inputs,
            generation_config={"response_mime_type": "application/json"},
        )
        parsed = _clean_and_parse_json(response.text)

        # Save the raw AI forensic report to the human evidence folder!
        if evidence_dir and os.path.exists(evidence_dir) and parsed:
            report_path = os.path.join(evidence_dir, "forensic_vision_report.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=2)

        return parsed
    except Exception as e:
        print(f"   ❌ Vision Processing Error: {e}")
        return {"error": "vision_api_error", "details": str(e)}


def _clean_and_parse_json(raw_text: str) -> dict | None:
    if not raw_text:
        return None
    try:
        match = re.search(r"```(?:json)?\s*({.*})\s*```", raw_text, re.DOTALL)
        json_str = match.group(1) if match else raw_text
        if not match:
            start, end = raw_text.find("{"), raw_text.rfind("}") + 1
            if start != -1 and end != -1:
                json_str = raw_text[start:end]
        return json.loads(json_str)
    except Exception as e:
        print(f"   ❌ JSON Parse Error: {e}")
        return None
# --- END OF FILE app/services/vision_service.py ---