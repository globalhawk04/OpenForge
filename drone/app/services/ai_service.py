# FILE: app/services/ai_service.py
import google.generativeai as genai
import json
import re
from app.config import settings
from app.prompts import REQUIREMENTS_SYSTEM_INSTRUCTION, CONSTRAINT_MERGER_INSTRUCTION, SPEC_GENERATOR_INSTRUCTION, ASSEMBLY_GUIDE_INSTRUCTION, OPTIMIZATION_ENGINEER_INSTRUCTION 

# 1. Configure API
if not settings.GOOGLE_API_KEY:
    print("WARNING: GOOGLE_API_KEY is missing in .env")
else:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

def parse_json_garbage(text: str) -> dict | None:
    """
    Robust JSON extractor. Handles cases where LLM wraps output in markdown 
    or adds conversational filler.
    """
    if not text: 
        return None
    # Try to find JSON block within markdown ```json ... ```
    match = re.search(r"```(json)?\s*({.*})\s*```", text, re.DOTALL)
    json_str = match.group(2) if match else text
    
    # Fallback: find the first { and last }
    if not match:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end != -1:
            json_str = text[start:end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {e}. Raw Text: {text}")
        return None

async def call_llm_for_json(prompt: str, system_instruction: str) -> dict | None:
    """Generic wrapper for Gemini JSON mode"""
    try:
        # Use 'gemini-1.5-pro' or 'gemini-1.5-flash' depending on your API access
        model = genai.GenerativeModel('gemini-2.5-pro', system_instruction=system_instruction)
        
        response = await model.generate_content_async(
            prompt, 
            generation_config={"response_mime_type": "application/json"}
        )
        return parse_json_garbage(response.text)
    except Exception as e:
        print(f"LLM Call Failed: {e}")
        return None

# --- Public Agent Functions ---

async def analyze_user_requirements(user_prompt: str) -> dict:
    """
    Phase 1: Intake Agent.
    Analyzes the user's raw text to extract constraints and questions.
    """
    print(f"--> Sending request to Gemini: '{user_prompt}'")
    result = await call_llm_for_json(user_prompt, REQUIREMENTS_SYSTEM_INSTRUCTION)
    return result

async def refine_requirements(original_analysis: dict, user_answers: list[str]) -> dict:
    """
    Phase 1.5: The Synthesis.
    Takes the initial analysis and the user's answers to create a final plan.
    """
    # Construct a text blob representing the conversation state
    conversation_context = f"""
    ORIGINAL ANALYSIS:
    {json.dumps(original_analysis)}

    USER ANSWERS TO CLARIFYING QUESTIONS:
    {json.dumps(user_answers)}
    """
    
    print(f"--> Synthesizing final plan based on {len(user_answers)} answers...")
    return await call_llm_for_json(conversation_context, CONSTRAINT_MERGER_INSTRUCTION)


async def generate_spec_sheet(build_plan: dict) -> dict:
    """
    Phase 1.8: The Systems Engineer.
    Generates the technical search criteria based on the approved build plan.
    """
    print(f"--> Calculating optimal component specifications...")
    return await call_llm_for_json(json.dumps(build_plan), SPEC_GENERATOR_INSTRUCTION)

async def generate_assembly_instructions(project_data: dict) -> dict:
    print("--> Generating Assembly Guide...")
    return await call_llm_for_json(json.dumps(project_data), ASSEMBLY_GUIDE_INSTRUCTION)


async def optimize_specs(current_bom: list, physics_report: dict) -> dict:
    """
    Phase 3.5: The Optimization Engineer.
    Analyzes a failed physics report and suggests part swaps.
    """
    print("--> 🧠 AI Analyzing Physics Failure & Generating Fixes...")
    
    context = {
        "current_bom_summary": [
            {
                "part_type": item['part_type'], 
                "product_name": item.get('product_name', 'Unknown'),
                "specs": item.get('engineering_specs', {})
            } for item in current_bom
        ],
        "physics_report": physics_report
    }
    
    return await call_llm_for_json(json.dumps(context), OPTIMIZATION_ENGINEER_INSTRUCTION)