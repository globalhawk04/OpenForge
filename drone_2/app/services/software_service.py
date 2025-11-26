# FILE: app/services/software_service.py
from app.services.ai_service import call_llm_for_json
from app.prompts import SOFTWARE_ARCHITECT_INSTRUCTION
import json

async def design_compute_stack(mission_profile):
    """
    Analyzes the mission to determine the necessary Brains (Software + Compute Hardware).
    """
    print("--> 🧠 Software Architect: Designing the neural system...")
    
    mission_desc = json.dumps(mission_profile)
    
    compute_plan = await call_llm_for_json(
        f"MISSION: {mission_desc}", 
        SOFTWARE_ARCHITECT_INSTRUCTION
    )
    
    if not compute_plan:
        return None

    # Logic check: Does this add hardware requirements?
    new_hardware_reqs = []
    
    # 1. The Computer Itself
    if compute_plan.get("companion_computer"):
        new_hardware_reqs.append({
            "category": "Companion_Computer",
            "search_query": compute_plan["companion_computer"] + " board dimensions specs"
        })

    # 2. The Sensors
    for sensor in compute_plan.get("required_sensors", []):
        # Map generic sensor names to search queries
        query = sensor
        cat = "Sensor"
        if "camera" in sensor.lower(): cat = "Camera_Aux"
        if "gps" in sensor.lower(): cat = "GPS_Module"
        if "lidar" in sensor.lower(): cat = "Lidar_Module"
        
        new_hardware_reqs.append({
            "category": cat,
            "search_query": f"Drone {sensor} module specs"
        })

    return {
        "stack": compute_plan,
        "hardware_additions": new_hardware_reqs
    }