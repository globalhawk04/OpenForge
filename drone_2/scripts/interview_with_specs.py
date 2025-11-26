# FILE: scripts/interview_with_specs.py
import asyncio
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_service import analyze_user_requirements, refine_requirements, generate_spec_sheet
from app.services.search_service import find_components

async def main():
    print("=========================================")
    print("Drone Architect - Live Engineer Mode")
    print("=========================================")
    
    # --- PHASE 1: INTAKE ---
    initial_prompt = input("\n(1) What do you want to build? > ")
    if not initial_prompt: return

    print("\n...Analyzing Request...")
    analysis = await analyze_user_requirements(initial_prompt)
    if not analysis: return

    # --- PHASE 1.5: CLARIFICATION ---
    questions = analysis.get("clarifying_questions", [])
    user_answers = []
    
    if questions:
        print(f"\n...I have {len(questions)} questions...\n")
        for i, q in enumerate(questions):
            answer = input(f"({i+2}) AI: {q}\n    You: ")
            user_answers.append(f"Question: {q} | Answer: {answer}")

    print("\n...Drafting Engineering Brief...")
    final_plan = await refine_requirements(analysis, user_answers)
    
    print("\n=========================================")
    print("       PROPOSAL v1.0 (Concept)           ")
    print("=========================================")
    print(f"SUMMARY: {final_plan.get('build_summary')}")
    
    if input("\nApprove Concept? [Y/n] > ").lower() not in ['y', 'yes', '']:
        return

    # --- PHASE 1.8: SPEC GENERATION (MAKE VS BUY) ---
    print("\n...Calculating 'Make vs Buy' Manifest...")
    spec_sheet = await generate_spec_sheet(final_plan)
    
    buy_list = spec_sheet.get("buy_list", [])
    print_list = spec_sheet.get("print_list", [])

    print("\n=========================================")
    print("       PROPOSAL v2.0 (BOM & Fabrication) ")
    print("=========================================")
    print(f"NOTES: {spec_sheet.get('engineering_notes')}\n")
    
    print(f"--- 🛒 TO BUY (Sourcing Agent) ---")
    print(f"{'COMPONENT':<15} | {'SEARCH QUERY':<40} | {'DATA TO EXTRACT'}")
    print("-" * 90)
    for item in buy_list:
        specs = ", ".join(item.get("critical_specs_to_extract", [])[:2])
        print(f"{item['part_type']:<15} | {item['search_query']:<40} | {specs}")

    print(f"\n--- 🖨️  TO PRINT (CAD Architect) ---")
    for item in print_list:
        print(f"* {item['part_type']}: {item['design_requirements']}")

    print("=========================================")
    if input("\nApprove Manifest? [Y/n] > ").lower() not in ['y', 'yes', '']:
        return

    # --- PHASE 2: SOURCING ---
    print("\n🚀 APPROVED. Sourcing 'Buy List' items...")
    for item in buy_list[:2]: # Demo first 2 items
        query = item['search_query']
        print(f"\n🔎 Searching for: {query}")
        results = find_components(query, limit=2)
        for res in results:
             print(f"   - found: {res['title'][:50]}... (${res['price']})")

if __name__ == "__main__":
    asyncio.run(main())