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

Return JSON:
{{
  "status": "PASS" or "FAIL",
  "missing_keys": ["string"],
  "reason": "string"
}}
"""

UI_NAVIGATOR_PROMPT = """
You are a QA Automation Agent. 
I need to find the **Specification Table** or **Wiring Diagram**.
Analyze the screenshot.

Return JSON:
{{
  "action": "CLICK" or "SCROLL" or "DONE",
  "target_text": "string (Exact text to click, e.g. 'Specifications', 'Manual')",
  "confidence": float
}}
"""

EXTRACTOR_PROMPT = """
Extract technical engineering data from this text.
**Focus on Physical Interfaces and Electrical Limits.**

Missing Keys to Find: {missing_keys}
Page Text: {page_text}

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
            screenshot = await page.screenshot(type="jpeg", quality=50)
            vision_model = genai.GenerativeModel('gemini-2.5-pro')
            nav_resp = await vision_model.generate_content_async([
                UI_NAVIGATOR_PROMPT,
                {"mime_type": "image/jpeg", "data": screenshot}
            ], generation_config={"response_mime_type": "application/json"})
            
            nav = clean_json(nav_resp.text)
            
            if nav.get('action') == 'CLICK' and nav.get('confidence', 0) > 0.8:
                try:
                    await page.get_by_text(nav['target_text'], exact=False).first.click(timeout=3000)
                    await asyncio.sleep(1)
                except: pass

            # 2. TEXT EXTRACTION
            # We get specific elements to avoid header/footer noise
            content = await page.evaluate("""() => {
                // Try to find the main product description container
                const selectors = ['.product-description', '#description', '.tabs', '.woocommerce-Tabs-panel'];
                for (let s of selectors) {
                    const el = document.querySelector(s);
                    if (el) return el.innerText;
                }
                return document.body.innerText;
            }""")
            
            clean_text = content.replace("\n", " ")[:20000]

            extract_model = genai.GenerativeModel('gemini-2.5-pro')
            extract_resp = await extract_model.generate_content_async(
                EXTRACTOR_PROMPT.format(missing_keys=missing_keys, page_text=clean_text),
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
    components = data.get("components", [])
    
    keep_list = []
    
    for comp in components:
        # Audit
        audit = await audit_component(model, comp)
        
        if audit.get('status') == 'FAIL':
            missing = audit.get('missing_keys', [])
            
            # Try to fix
            investigation = await investigate_url(comp, missing)
            
            if investigation and investigation.get('found_data'):
                # Update specs
                if 'specs' not in comp: comp['specs'] = {}
                comp['specs'].update(investigation['found_data'])
                comp['verified'] = True
                print(f"      ✅ Fixed {comp['model_name']}: Found {list(investigation['found_data'].keys())}")
                keep_list.append(comp)
            else:
                # If we still can't find critical data (like mounting pattern), CULL IT.
                # Keeping bad data causes AI hallucinations later.
                print(f"      🗑️  CULLING {comp['model_name']}: Still missing {missing}")
        else:
            keep_list.append(comp)

    # Save cleaned list
    data['components'] = keep_list
    with open(ARSENAL_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ Refinery Complete. Arsenal size: {len(components)} -> {len(keep_list)}")

if __name__ == "__main__":
    asyncio.run(run_refinery())