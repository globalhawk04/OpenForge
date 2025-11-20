# FILE: scripts/live_interview.py
import asyncio
import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_service import analyze_user_requirements, refine_requirements

async def main():
    print("=========================================")
    print("Drone Architect - Live Interview Mode")
    print("=========================================")
    
    # 1. Initial Prompt
    initial_prompt = input("\n(1) What do you want to build? > ")
    if not initial_prompt: return

    print("\n...Analyzing Request...")
    analysis = await analyze_user_requirements(initial_prompt)
    
    if not analysis:
        print("❌ Error parsing requirements.")
        return

    # 2. The Clarification Loop
    questions = analysis.get("clarifying_questions", [])
    user_answers = []
    
    if questions:
        print(f"\n...I have {len(questions)} questions to refine the build...\n")
        for i, q in enumerate(questions):
            answer = input(f"({i+2}) AI: {q}\n    You: ")
            user_answers.append(f"Question: {q} | Answer: {answer}")
    else:
        print("\n...Request is clear. No questions needed.")

    # 3. Synthesis & Proposal
    print("\n...Drafting Engineering Brief...")
    final_plan = await refine_requirements(analysis, user_answers)
    
    if not final_plan:
        print("❌ Error creating final plan.")
        return

    # 4. The Approval Gate
    print("\n=========================================")
    print("       THE ARCHITECT'S PROPOSAL          ")
    print("=========================================")
    print(f"SUMMARY: {final_plan.get('build_summary')}")
    print("\nCONSTRAINTS:")
    for k, v in final_plan.get('final_constraints', {}).items():
        print(f"  - {k}: {v}")
    
    print("=========================================")
    approval = input("\nDo you approve this build plan? [Y/n] > ")
    
    if approval.lower() in ['y', 'yes', '']:
        print("\n🚀 APPROVED. Proceeding to Phase 2: Sourcing Components (Serper/Search)...")
        # This is where we would trigger the Search Service
    else:
        print("\n🛑 CANCELLED. Please restart with a more specific prompt.")

if __name__ == "__main__":
    asyncio.run(main())
