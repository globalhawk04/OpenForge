# FILE: scripts/test_full_pipeline.py
import asyncio
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_service import analyze_user_requirements, refine_requirements, generate_spec_sheet
# Import the new Fusion Service
from app.services.fusion_service import fuse_component_data

async def main():
    print("=========================================")
    print("Drone Architect - FUSION PIPELINE TEST")
    print("Intake -> Spec -> Multi-Source Fusion")
    print("=========================================")
    
    # --- 1. INTAKE ---
    user_prompt = "a small hand held drone"
    predefined_answers = [
        "Question: Budget? | Answer: 100 dollars",
        "Question: FPV or LOS? | Answer: looking at the drone directly",
        "Question: Indoors or Outdoors? | Answer: indoors",
        "Question: Pre-built or DIY? | Answer: assembling myself",
        "Question: Existing gear? | Answer: no"
    ]

    print(f"[1] Planning Build...")
    analysis = await analyze_user_requirements(user_prompt)
    final_plan = await refine_requirements(analysis, predefined_answers)
    spec_sheet = await generate_spec_sheet(final_plan)
    
    if not spec_sheet:
        print("❌ Planning Failed")
        return

    buy_list = spec_sheet.get("buy_list", [])
    
    final_project_data = {
        "project_summary": final_plan.get("build_summary"),
        "engineering_notes": spec_sheet.get("engineering_notes"),
        "bill_of_materials": []
    }

    # --- 2. FUSION SOURCING ---
    print(f"\n[2] ⚛️  FUSION SOURCING: Analyzing multiple sources per part...")
    
    for item in buy_list:
        part_type = item['part_type']
        query = item['search_query']
        
        # Call the Fusion Service
        # It handles the Search -> Parallel Scrape -> Merge logic internally
        composite_part = await fuse_component_data(part_type, query)
        
        if composite_part:
            final_project_data["bill_of_materials"].append(composite_part)
            # Print a nice summary of what happened
            specs = composite_part['engineering_specs']
            print(f"      🎯 Final Specs: {json.dumps(specs)}")
        else:
            print(f"      ❌ Failed to find/verify {part_type}")
            final_project_data["bill_of_materials"].append({
                "part_type": part_type,
                "status": "NOT_FOUND"
            })

    # --- 3. FINAL OUTPUT ---
    print("\n" + "="*60)
    print("FINAL COMPOSITE BOM")
    print("="*60)
    print(json.dumps(final_project_data, indent=2))

if __name__ == "__main__":
    asyncio.run(main())