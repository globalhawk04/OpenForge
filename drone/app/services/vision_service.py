# FILE: app/services/vision_service.py
import google.generativeai as genai
import PIL.Image
import requests
from io import BytesIO
from app.config import settings
import json
import re

# Configure API
if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

async def analyze_image_for_specs(image_url: str, part_category: str) -> dict:
    """
    Downloads an image and asks Gemini Vision to extract CAD-critical dimensions.
    
    Args:
        image_url: The URL of the technical diagram/product photo.
        part_category: "MOTOR", "FC_STACK", or "CAMERA" to select the right prompt.
    """
    print(f"👁️  Vision AI Analyzing ({part_category}): {image_url}")
    
    # 1. Download Image
    try:
        # Fake User-Agent to avoid 403s on some CDNs
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(image_url, headers=headers, timeout=10)
        response.raise_for_status()
        image_bytes = response.content
        img = PIL.Image.open(BytesIO(image_bytes))
    except Exception as e:
        print(f"❌ Image Download Error: {e}")
        return {"error": "download_failed"}

    # 2. Select Engineering Prompt
    # We ask specific questions based on what part we are looking at.
    if part_category == "MOTOR":
        specific_task = """
        Look for a technical drawing showing the BOTTOM of the motor.
        Extract the 'Mounting Pattern' (distance between screw holes, usually 9mm, 12mm, 16mm, or 19mm).
        Extract the 'Shaft Diameter' (usually 1.5mm, 2mm, or 5mm).
        """
        json_structure = '{"mounting_mm": "float or null", "shaft_mm": "float or null"}'
    
    elif part_category == "FC_STACK":
        specific_task = """
        Look for the mounting holes on the board.
        Extract the 'Mounting Pattern' (distance center-to-center). Common values: 16x16, 20x20, 25.5x25.5, 30.5x30.5.
        Look for the USB port. Is it projecting from the SIDE or UP/DOWN?
        """
        json_structure = '{"mounting_mm": "float or null", "usb_orientation": "SIDE or DOWN"}'
        
    elif part_category == "CAMERA":
        specific_task = """
        Extract the width of the camera body (horizontal dimension).
        Common values: 14mm (Nano), 19mm (Micro), 20mm (DJI), 22mm (Mini).
        """
        json_structure = '{"width_mm": "float or null"}'
    
    else:
        return {"error": "unknown_category"}

    prompt = f"""
    You are a CAD Engineer converting a product image into 3D printing constraints.
    
    IMAGE ANALYSIS TASK:
    {specific_task}
    
    If the image is just a marketing photo and NOT a technical diagram, return nulls.
    If you see calipers or dimension lines, trust those numbers explicitly.
    
    OUTPUT SCHEMA (JSON ONLY):
    {json_structure}
    """

    # 3. Call Gemini Vision
    try:
        # Flash is sufficient for OCR/Diagram reading and faster/cheaper
        model = genai.GenerativeModel('gemini-2.5-pro')
        response = await model.generate_content_async([prompt, img])
        
        # Clean JSON Output
        text = response.text
        match = re.search(r"```(json)?\s*({.*})\s*```", text, re.DOTALL)
        json_str = match.group(2) if match else text
        
        # Simple cleanup for common LLM JSON errors
        json_str = json_str.replace("null", "None").replace("true", "True").replace("false", "False")
        
        # Parse
        data = eval(json_str) # Safe here because we constrained output, but json.loads is better practice
        # Let's stick to json.loads with cleanup
        return json.loads(json_str.replace("None", "null").replace("True", "true").replace("False", "false"))
        
    except Exception as e:
        print(f"❌ Vision Processing Error: {e}")
        return {"error": str(e)}