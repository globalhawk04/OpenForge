# FILE: tools/refine_arsenal.py
import asyncio
import json
import os
import re
from playwright.async_api import async_playwright
import google.generativeai as genai
from app.config import settings

# --- CONFIG ---
ARSENAL_FILE = "drone_arsenal.json"

if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

# --- IMPROVED PROMPTS ---
AUDITOR_PROMPT = """
You are a Senior Aviation Safety Inspector. 
Audit this component for **Critical Integration Data**.

Component: {name} ({category})
Current Specs: {specs}

**MISSING CRITICAL DATA DEFINITIONS:**
1. **Mounting:** Exact hole spacing (e.g., "30.5x30.5mm"). "N/A" is NOT acceptable for Frames/FCs/Motors.
2. **Voltage:** Input range (e.g., "3-6S") or KV rating.
3. **Connectors:** Specific port types (e.g., "XT60", "JST-SH", "U.FL").
4. **Protocol:** (For RX/VTX) e.g., "ELRS", "CRSF", "DJI O3".
5. **Performance:** (For Motors) Thrust data tables or efficiency charts.

Return JSON:
{{
  "status": "PASS" or "FAIL",
  "missing_keys": ["string"],
  "reason": "string"
}}
"""

UI_NAVIGATOR_PROMPT = """
You are a QA Automation Agent. 
I need to find the **Specification Table**, **Wiring Diagram**, or **Thrust Data**.
Analyze the screenshot.

Return JSON:
{{
  "action": "CLICK" or "SCROLL" or "DONE",
  "target_text": "string (Exact text to click, e.g. 'Specifications', 'Manual', 'Read More')",
  "confidence": float
}}
"""

EXTRACTOR_PROMPT = """
You are a Forensic Engineer. 
Extract technical data from the provided **PAGE TEXT** and **SCREENSHOT**.

**CRITICAL MISSION:**
1.  **Read the Text:** Look for mounting patterns, voltages, and protocols.
2.  **Read the Image:** Look for **Thrust Tables**, **Pinout Diagrams**, or **Dimension Drawings** that might not be in the text.

**MISSING KEYS TO FIND:** {missing_keys}

**SPECIAL INSTRUCTION FOR MOTORS:**
If you see a Thrust Table in the image, extract the data for 50% and 100% throttle.
Format: "thrust_data": {{"50_pct_g": 1200, "100_pct_g": 3400, "prop": "15x5"}}

**PAGE TEXT:**
{page_text}

Return JSON:
{{
  "found_data": {{ "key": "value" }},
  "still_missing": ["key"]
}}
"""

def clean_json(text):
    if not text: return {}
    try:
        match = re.search(r"```(json)?\s*({.*})\s*```", text, re.DOTALL)
        json_str = match.group(2) if match else text
        if not match:
            s, e = text.find("{"), text.rfind("}") + 1
            if s != -1 and e != -1: json_str = text[s:e]
        return json.loads(json_str)
    except: return {}

def save_arsenal(data):
    """Helper to write to disk immediately."""
    try:
        with open(ARSENAL_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"      ❌ Save Error: {e}")

async def audit_component(model, comp):
    prompt = AUDITOR_PROMPT.format(
        name=comp.get('model_name'),
        category=comp.get('category'),
        specs=json.dumps(comp.get('specs', {}) or comp.get('engineering_specs', {}))
    )
    res = await model.generate_content_async(prompt, generation_config={"response_mime_type": "application/json"})
    return clean_json(res.text)

async def investigate_url(comp, missing_keys):
    url = comp.get('source_url')
    if not url: return None

    print(f"      🕵️  Refining: {comp['model_name'][:30]}...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # 1. VISUAL NAVIGATION (Click "Specs" tabs)
            screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
            
            # Helper to create Image object for Gemini
            import PIL.Image
            from io import BytesIO
            screenshot_img = PIL.Image.open(BytesIO(screenshot_bytes))

            vision_model = genai.GenerativeModel('gemini-2.5-pro')
            nav_resp = await vision_model.generate_content_async([
                UI_NAVIGATOR_PROMPT,
                screenshot_img
            ], generation_config={"response_mime_type": "application/json"})
            
            nav = clean_json(nav_resp.text)
            
            if nav.get('action') == 'CLICK' and nav.get('confidence', 0) > 0.8:
                try:
                    await page.get_by_text(nav['target_text'], exact=False).first.click(timeout=3000)
                    await asyncio.sleep(1)
                    # Take new screenshot after click
                    screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
                    screenshot_img = PIL.Image.open(BytesIO(screenshot_bytes))
                except: pass

            # 2. TEXT EXTRACTION
            content = await page.evaluate("""() => {
                const selectors = ['.product-description', '#description', '.tabs', '.woocommerce-Tabs-panel', 'table'];
                for (let s of selectors) {
                    const el = document.querySelector(s);
                    if (el) return el.innerText;
                }
                return document.body.innerText;
            }""")
            
            clean_text = content.replace("\n", " ")[:15000]

            # 3. MULTIMODAL EXTRACTION (Text + Image)
            extract_resp = await vision_model.generate_content_async(
                [
                    EXTRACTOR_PROMPT.format(missing_keys=missing_keys, page_text=clean_text),
                    screenshot_img # Pass the image for chart reading
                ],
                generation_config={"response_mime_type": "application/json"}
            )
            
            return clean_json(extract_resp.text)

        except Exception as e:
            print(f"      ❌ Scrape Error: {e}")
            return None
        finally:
            await browser.close()

async def run_refinery():
    print("🔬 OPENFORGE REFINERY: Improving Data Integrity...")
    
    if not os.path.exists(ARSENAL_FILE): return

    with open(ARSENAL_FILE, "r") as f:
        data = json.load(f)
    
    model = genai.GenerativeModel('gemini-2.5-pro')
    components_list = data.get("components", [])[:] 
    components_to_remove = []

    for i, comp in enumerate(components_list):
        audit = await audit_component(model, comp)
        
        if audit.get('status') == 'FAIL':
            missing = audit.get('missing_keys', [])
            investigation = await investigate_url(comp, missing)
            found_data = investigation.get('found_data') if investigation else None
            
            if investigation and isinstance(found_data, dict) and found_data:
                if 'specs' not in comp: comp['specs'] = {}
                try:
                    comp['specs'].update(found_data)
                    comp['verified'] = True
                    print(f"      ✅ Fixed {comp['model_name']}: Found {list(found_data.keys())}")
                    data["components"][i] = comp
                    save_arsenal(data)
                except Exception as e:
                    components_to_remove.append(i)
            else:
                print(f"      🗑️  CULLING {comp['model_name']}: Still missing {missing}")
                components_to_remove.append(i)

    if components_to_remove:
        cleaned_list = [c for idx, c in enumerate(data["components"]) if idx not in components_to_remove]
        data["components"] = cleaned_list
        save_arsenal(data)

    print(f"\n✅ Refinery Complete. Arsenal size: {len(data['components'])}")

if __name__ == "__main__":
    asyncio.run(run_refinery())