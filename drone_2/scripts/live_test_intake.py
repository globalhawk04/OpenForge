# FILE: scripts/live_test_intake.py
import asyncio
import sys
import os
import json

# 1. Add the project root to sys.path so we can import 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_service import analyze_user_requirements

async def main():
    print("=========================================")
    print("Drone Architect - Live Intake Test")
    print("=========================================")
    print("Type 'exit' to quit.\n")

    while True:
        user_input = input("\nUser Prompt > ")
        if user_input.lower() in ["exit", "quit"]:
            break
        
        if not user_input.strip():
            continue

        print("\n...Thinking (Calling Gemini)...")
        
        try:
            result = await analyze_user_requirements(user_input)
            
            if result:
                print("\n✅ SUCCESS! Agent Response:")
                print(json.dumps(result, indent=2))
                
                # Simple validation check
                constraints = result.get("constraints", {})
                print(f"\n[Summary] Type: {result.get('project_type')} | Budget: {constraints.get('budget_usd')}")
            else:
                print("\n❌ FAILED: Agent returned None or invalid JSON.")
                
        except Exception as e:
            print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
