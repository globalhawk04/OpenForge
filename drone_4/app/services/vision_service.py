# FILE: app/services/vision_service.py
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

async def analyze_specs_multimodal(
    text_context: str, 
    image_urls: list[str], 
    part_type: str, 
    dynamic_prompt_object: dict
) -> dict | None:
    """
    Synthesizes specifications by looking at product images/diagrams AND reading scraped HTML tables.
    Uses Gemini 1.5 (Flash or Pro) for high-context multimodal understanding.
    """
    print(f"👁️  Fusion AI: Analyzing {len(image_urls)} images + Text Data for {part_type}...")

    # 1. Download Images (Limit to 3 to optimize latency/tokens)
    # We prioritize the images found by the scraper (which puts galleries/diagrams first)
    images = []
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for url in image_urls[:3]:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                img = PIL.Image.open(BytesIO(resp.content))
                images.append(img)
        except Exception as e:
            # Continue even if one image fails
            continue

    # Logic Check: Do we have ANY data?
    if not images and len(text_context) < 50:
        return {"error": "no_data_available"}

    # 2. Construct Multimodal Prompt
    prompt_text = dynamic_prompt_object.get("prompt_text", "Extract technical specs.")
    json_schema = dynamic_prompt_object.get("json_schema", "{}")

    full_prompt = f"""
    You are a Senior Hardware Engineer validating components for an industrial drone build.
    
    **TASK:**
    Extract technical specifications for a '{part_type}' by synthesizing data from the provided IMAGES and the SCRAPED TEXT below.
    
    **SOURCES:**
    1. SCRAPED TEXT (HTML Tables & Lists):
    {text_context[:6000]} 
    
    2. IMAGES: Attached. (Look for diagrams, pinouts, or spec sheets).

    **FORENSIC INSTRUCTIONS:**
    - **Cross-Reference:** Check if the text matches the images.
    - **Prioritize Diagrams:** If the text says "Mounting: 30mm" but the image shows a ruler measuring "20mm", TRUST THE IMAGE DIAGRAM.
    - **Infer Missing Data:** If the text is missing the 'KV' rating, look for it printed on the motor bell in the photos.
    - **Strict JSON:** You MUST output valid JSON based on the schema below.
    
    **REQUIRED OUTPUT SCHEMA:**
    {json_schema}
    """

    # 3. Call Gemini Vision
    try:
        # Gemini 1.5 Flash is excellent for high-volume multimodal tasks
        model = genai.GenerativeModel('gemini-2.5-pro') 
        
        # Inputs: Prompt string + List of PIL Images
        inputs = [full_prompt] + images
        
        response = await model.generate_content_async(inputs)
        
        return _clean_and_parse_json(response.text)

    except Exception as e:
        print(f"   ❌ Vision Processing Error: {e}")
        return {"error": "vision_api_error", "details": str(e)}

def _clean_and_parse_json(raw_text):
    """Robust JSON extraction from LLM response."""
    try:
        # Find JSON block
        match = re.search(r"```(json)?\s*({.*})\s*```", raw_text, re.DOTALL)
        json_str = match.group(2) if match else raw_text
        
        # Fallback: Find first { and last }
        if not match:
            start, end = raw_text.find("{"), raw_text.rfind("}") + 1
            if start != -1 and end != -1:
                json_str = raw_text[start:end]
        
        # Fix common LLM syntax errors
        json_str = json_str.replace("True", "true").replace("False", "false").replace("None", "null")
        
        return json.loads(json_str)
    except Exception as e:
        print(f"   ❌ JSON Parse Error: {e}")
        return None