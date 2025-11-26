# FILE: app/services/texture_service.py
import google.generativeai as genai
import PIL.Image
import requests
from io import BytesIO
import json
import re
from app.config import settings

# Configure API
if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

# --- PROMPT DEFINITION ---
VISUAL_DNA_PROMPT = """
You are a 3D Graphics Artist and Material Specialist.
Your task is to analyze the product image and extract the "Visual DNA" required to render this object realistically in a PBR (Physically Based Rendering) engine like Three.js.

Focus on the MAIN structural component (e.g., the bell of a motor, the arm of a frame, the heat sink of a VTX).

**ANALYSIS REQUIREMENTS:**
1.  **Primary Color:** Identify the dominant hex color.
2.  **Material Type:** What is it made of? (e.g., Anodized Aluminum, Carbon Fiber, PCB, injection molded plastic).
3.  **Surface Finish:** How does light react to it? (Matte, Glossy, Metallic, Anodized).
4.  **Emissive:** Does it have LEDs or screens that emit light?

**OUTPUT SCHEMA (JSON ONLY):**
You must strictly output the following JSON structure. Do not include markdown formatting.

{
  "primary_color_hex": "#RRGGBB",
  "secondary_color_hex": "#RRGGBB" or null,
  "material_type": "string (enum: CARBON_FIBER, ALUMINUM, PLASTIC, PCB, STEEL, GOLD, COPPER)",
  "surface_finish": "string (enum: MATTE, SATIN, GLOSSY, ANODIZED, BRUSHED)",
  "texture_pattern": "string (enum: NONE, WEAVE, KNURLED, GRAIN)",
  "is_emissive": boolean,
  "emissive_color_hex": "#RRGGBB" or null
}
"""

def _clean_json_response(text: str) -> dict | None:
    """Helper to extract JSON from potential markdown wrapping."""
    try:
        # Try finding JSON block
        match = re.search(r"```(json)?\s*({.*})\s*```", text, re.DOTALL)
        json_str = match.group(2) if match else text
        
        # Fallback: Find first { and last }
        if not match:
            start, end = text.find("{"), text.rfind("}") + 1
            if start != -1 and end != -1:
                json_str = text[start:end]
        
        # Cleanup common LLM JSON errors
        json_str = json_str.replace("True", "true").replace("False", "false").replace("None", "null")
        
        return json.loads(json_str)
    except Exception as e:
        print(f"   ❌ Texture JSON Parse Error: {e}")
        return None

async def extract_visual_dna(image_url: str, part_type: str = "Component") -> dict:
    """
    Downloads an image and asks Gemini Vision to extract PBR rendering properties.
    Returns a dictionary of visual properties, or a default fallback if failed.
    """
    # Default Fallback (Grey Plastic)
    fallback_dna = {
        "primary_color_hex": "#888888",
        "secondary_color_hex": None,
        "material_type": "PLASTIC",
        "surface_finish": "MATTE",
        "texture_pattern": "NONE",
        "is_emissive": False,
        "emissive_color_hex": None
    }

    if not image_url:
        return fallback_dna

    print(f"🎨 Visual DNA: Analyzing aesthetics for {part_type}...")

    try:
        # 1. Download Image
        headers = {"User-Agent": "OpenForge/1.0"}
        response = requests.get(image_url, headers=headers, timeout=10)
        response.raise_for_status()
        img = PIL.Image.open(BytesIO(response.content))

        # 2. Call Gemini Vision
        model = genai.GenerativeModel('gemini-2.5-pro') # Or 'gemini-1.5-flash' for speed
        
        # Combine system instruction with the prompt
        full_prompt = f"Part Type Context: {part_type}\n{VISUAL_DNA_PROMPT}"
        
        response = await model.generate_content_async([full_prompt, img])
        
        # 3. Parse Result
        dna = _clean_json_response(response.text)
        
        if dna:
            print(f"   ✨ Extracted DNA: {dna.get('material_type')} / {dna.get('primary_color_hex')}")
            return dna
        else:
            print("   ⚠️  Failed to parse visual DNA, using fallback.")
            return fallback_dna

    except Exception as e:
        print(f"   ⚠️  Visual DNA Error: {e}")
        return fallback_dna