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

# Configure Gemini
if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

# --- PROMPTS ---
AUDITOR_PROMPT = """
You are a Data Quality Auditor for a Drone Engineering Database.
Review the current specifications for this component.
Identify CRITICAL engineering data that is currently "N/A", "null", 0, or missing.

Component Name: {name}
Category: {category}
Current Specs: {specs}

**CRITICAL FIELDS BY CATEGORY:**
- Motors: KV, Stator Size, Shaft Diameter, Mounting Pattern, Weight.
- Frame: Wheelbase, Arm Thickness, Mounting Pattern, Weight.
- FC: MCU, UART Count, Mounting Pattern, BEC Voltage.
- Battery: Cell Count, Capacity, C-Rating, Connector Type, Weight, Dimensions.

Return a JSON object:
{{
  "is_complete": boolean,
  "missing_keys": ["string", "string"],
  "reason": "string"
}}
"""

UI_NAVIGATOR_PROMPT = """
You are a QA Automation Agent. I am providing a screenshot of a product page.
My goal is to find technical specifications that might be hidden.

Look for clickable UI elements labeled: 
"Specifications", "Specs", "Technical Data", "Parameters", "Description", "Read More", or "Details".

Return a JSON object:
{{
  "found_hidden_section": boolean,
  "target_text": "string (The exact text on the button/tab to click)",
  "confidence": float (0.0 to 1.0)
}}
"""

EXTRACTOR_PROMPT = """
We have navigated to the details section of the page.
Extract the specific missing fields requested. 
If the data is still not found, return null for that field.

Missing Fields to Find: {missing_keys}
Page Text content: {page_text}

Return JSON of the found data:
{{
  "key_name": "value",
  "key_name_2": "value"
}}
"""

def clean_json(text):
    """Helper to fix Markdown JSON"""
    if not text: return {}
    try:
        match = re.search(r"```(json)?\s*({.*})\s*```", text, re.DOTALL)
        json_str = match.group(2) if match else text
        if not match:
            s, e = text.find("{"), text.rfind("}") + 1
            if s != -1 and e != -1: json_str = text[s:e]
        return json.loads(json_str)
    except: return {}

async def audit_component(model, comp):
    """Step 1: Determine what is missing."""
    prompt = AUDITOR_PROMPT.format(
        name=comp.get('model_name'),
        category=comp.get('category'),
        specs=json.dumps(comp.get('specs', {}) or comp.get('engineering_specs', {}))
    )
    res = await model.generate_content_async(prompt, generation_config={"response_mime_type": "application/json"})
    return clean_json(res.text)

async def investigate_url(comp, missing_keys):
    """Step 2 & 3: Look, Click, and Scrape."""
    url = comp.get('source_url')
    if not url: return None

    print(f"      🕵️  Investigating: {url[:60]}...")
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        # Use large viewport to prevent mobile layout hiding tabs
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(2) # Wait for JS to settle

            # --- VISION PHASE ---
            # FIX: Changed format='jpeg' to type='jpeg'
            screenshot = await page.screenshot(type="jpeg", quality=50)
            
            vision_model = genai.GenerativeModel('gemini-2.5-pro')
            vision_resp = await vision_model.generate_content_async([
                UI_NAVIGATOR_PROMPT,
                {"mime_type": "image/jpeg", "data": screenshot}
            ], generation_config={"response_mime_type": "application/json"})
            
            nav_plan = clean_json(vision_resp.text)

            # --- ACTION PHASE ---
            if nav_plan.get('found_hidden_section') and nav_plan.get('confidence', 0) > 0.7:
                target = nav_plan['target_text']
                print(f"      🖱️  AI identifies target: '{target}'")
                
                try:
                    # Robust click logic: Text match -> precise click
                    element = page.get_by_text(target, exact=False).first
                    if await element.is_visible():
                        await element.click(timeout=3000)
                        print("      ✅ Click successful. Waiting for load...")
                        await asyncio.sleep(2.0) # Wait for tab switch/AJAX
                    else:
                        print("      ⚠️  Target visible in screenshot but not found in DOM.")
                except Exception as e:
                    print(f"      ⚠️  Click failed: {e}")

            # --- EXTRACTION PHASE ---
            # Now scrape the state of the page (after potential clicks)
            # We get innerText to reduce HTML noise
            text_content = await page.evaluate("document.body.innerText")
            
            # Limit context window
            clean_text = text_content.replace("\n", " ")[:25000]

            extract_model = genai.GenerativeModel('gemini-2.5-pro')
            extract_resp = await extract_model.generate_content_async(
                EXTRACTOR_PROMPT.format(missing_keys=missing_keys, page_text=clean_text),
                generation_config={"response_mime_type": "application/json"}
            )
            
            return clean_json(extract_resp.text)

        except Exception as e:
            print(f"      ❌ Investigation Error: {e}")
            return None
        finally:
            await browser.close()

async def run_refinery():
    print("🔬 OPENFORGE DATA REFINERY: Starting Active Recon...")
    
    if not os.path.exists(ARSENAL_FILE):
        print("❌ No arsenal file found.")
        return

    with open(ARSENAL_FILE, "r") as f:
        data = json.load(f)
        components = data.get("components", [])

    model = genai.GenerativeModel('gemini-2.5-pro')
    updates_count = 0

    # Iterate through inventory
    for i, comp in enumerate(components):
        name = comp.get('model_name', 'Unknown')
        
        # 1. Audit
        audit = await audit_component(model, comp)
        
        if not audit.get('is_complete', True):
            missing = audit.get('missing_keys', [])
            print(f"\n[{i+1}/{len(components)}] ⚠️  {name[:40]}... Missing: {missing}")
            
            # 2. Investigate (Browsing Agent)
            new_data = await investigate_url(comp, missing)
            
            # 3. Merge Updates
            if new_data:
                # Get reference to specs dict (handle key naming variations)
                if 'specs' not in comp: comp['specs'] = {}
                specs = comp['specs']
                
                found_any = False
                for k, v in new_data.items():
                    # Only update if value is valid and wasn't there before
                    if v and v not in ["N/A", "null", None]:
                        specs[k] = v
                        found_any = True
                
                if found_any:
                    print(f"      ✨ UPDATED: {new_data}")
                    specs['source'] = 'active_refinery_agent'
                    comp['verified'] = True
                    updates_count += 1
                    
                    # Save immediately to prevent data loss
                    with open(ARSENAL_FILE, "w") as f:
                        json.dump(data, f, indent=2)
            else:
                print("      ❌ No new data found.")

    print(f"\n✅ Refinery Complete. Enhanced {updates_count} components.")

if __name__ == "__main__":
    asyncio.run(run_refinery())