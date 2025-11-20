# FILE: scripts/test_auto_search.py
import asyncio
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_service import analyze_user_requirements, refine_requirements, generate_spec_sheet
from app.services.search_service import find_components

async def main():
    print("=========================================")
    print("Drone Architect - SMART SEARCH TEST")
    print("=========================================")
    
    # Scenario: Beginner Indoor Drone ($100)
    user_prompt = "a small hand held drone"
    predefined_answers = [
        "Question: Budget? | Answer: 100 dollars",
        "Question: FPV or LOS? | Answer: looking at the drone directly",
        "Question: Indoors or Outdoors? | Answer: indoors",
        "Question: Pre-built or DIY? | Answer: assembling myself",
        "Question: Existing gear? | Answer: no"
    ]

    print(f"\n[1] Analyzing Request & Refining Plan...")
    analysis = await analyze_user_requirements(user_prompt)
    if not analysis: return

    final_plan = await refine_requirements(analysis, predefined_answers)
    if not final_plan: return
    
    print(f"    Summary: {final_plan.get('build_summary')}")

    print("\n[2] Generating Protocol-Aware Specs...")
    spec_sheet = await generate_spec_sheet(final_plan)
    if not spec_sheet: return

    buy_list = spec_sheet.get("buy_list", [])
    print(f"    Notes: {spec_sheet.get('engineering_notes')}")

    # --- 3. EXECUTE SEARCH ---
    print(f"\n[3] 🚀 Sourcing {len(buy_list)} Components (Top 5 Results)")
    print("=========================================")
    
    for item in buy_list:
        part_type = item['part_type']
        query = item['search_query']
        
        print(f"\n🔎 PART: {part_type.upper()}")
        print(f"   Query: '{query}'")
        
        # Request 5 results this time
        results = find_components(query, limit=5)
        
        if results:
            print(f"   ✅ Found {len(results)} options:")
            for i, res in enumerate(results):
                title = res.get('title', 'No Title')[:50]
                price = res.get('price', 'N/A')
                link = res.get('link', '#')
                
                # Print format: [1] Title | Price
                #               Link: https://...
                print(f"      [{i+1}] {title}... | {price}")
                print(f"          Link: {link}")
        else:
            print("   ❌ No results found.")

if __name__ == "__main__":
    asyncio.run(main())