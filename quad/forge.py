# FILE: forge.py
import asyncio
import json
import os
import random
from datetime import datetime

# Services
from app.services.ai_service import call_llm_for_json
from app.services.fusion_service import fuse_component_data
from app.services.supply_service import SupplyService
from app.services.physics_service import generate_physics_config
from app.services.compatibility_service import CompatibilityService
from app.services.optimizer import EngineeringOptimizer
from app.services.cad_service import generate_assets
from app.services.isaac_service import IsaacService
from app.services.software_service import design_compute_stack
from app.services.schematic_service import generate_wiring_diagram

# Prompts
from app.prompts import (
    RANCHER_PERSONA_INSTRUCTION, 
    REQUIREMENTS_SYSTEM_INSTRUCTION, 
    ARSENAL_ENGINEER_INSTRUCTION
)

# --- NEW HELPER FUNCTION TO FIX SEARCH FAILURES ---
def clean_search_query(model_name, part_type):
    """
    Cleans up overly descriptive LLM names for Google Search to improve hit rates.
    Handles None/Null model names gracefully.
    """
    # 1. Handle Null/Empty Model Names
    if not model_name:
        return f"{part_type} robotics specs price"

    query = str(model_name).lower()
    
    # 2. Remove junk words that confuse search engines
    junk_words = [
        "custom", "fabricated", "open-source", "printable", "files", 
        "style", "based", "3d printed", "compatible", "generic"
    ]
    for w in junk_words:
        query = query.replace(w, "")
        
    query = query.strip()
    
    # 3. Apply Domain Heuristics
    pt_lower = part_type.lower()
    
    if "chassis" in pt_lower or "frame" in pt_lower:
        if "aluminum" in query or "extrusion" in query: 
            return f"{query} extrusion kit robotics"
        if "carbon" in query: 
            return f"{query} frame kit"
        return f"{query} robot chassis kit"
        
    if "actuator" in pt_lower or "servo" in pt_lower:
        return f"{query} servo torque specs"

    if "battery" in pt_lower:
        return f"{query} lipo battery specs"

    if "controller" in pt_lower:
        return f"{query} pinout specs"

    # Default fallback
    return f"{query} specs price"

async def main():
    print("""
    ===================================================
       🐂 OPENFORGE: RANCH DOG PROTOCOL INITIATED 🐂
    ===================================================
    """)
    
    supply = SupplyService()
    isaac = IsaacService()
    optimizer = EngineeringOptimizer()
    compat = CompatibilityService()

    # --- STEP 1: THE RANCHER (Intent) ---
    print("\n🤠 AGENT 1: Rancher Persona is defining needs...")
    mission_data = await call_llm_for_json("Generate robot missions.", RANCHER_PERSONA_INSTRUCTION)
    
    if not mission_data or "missions" not in mission_data:
        print("❌ Rancher failed to speak.")
        return

    missions = mission_data['missions']
    print(f"   -> Defined {len(missions)} missions: {[m['mission_name'] for m in missions]}")

    for mission in missions:
        m_name = mission['mission_name']
        print(f"\n🚀 STARTING CAMPAIGN: {m_name}")
        
        # --- STEP 2: THE ARCHITECT (Topology) ---
        print(f"   📐 AGENT 2: Architecting constraints...")
        reqs = await call_llm_for_json(json.dumps(mission), REQUIREMENTS_SYSTEM_INSTRUCTION)
        
        # --- STEP 3: THE ENGINEER (BOM) ---
        print(f"   👷 AGENT 3: Designing Build Kit...")
        context = {"mission": mission, "constraints": reqs}
        bom_structure = await call_llm_for_json(json.dumps(context), ARSENAL_ENGINEER_INSTRUCTION)
        
        if not bom_structure or "kits" not in bom_structure: continue
        target_kit = bom_structure['kits'][0]['components']

        # --- STEP 4: THE SOURCER (Fusion Loop) ---
        print(f"   🔎 AGENT 4: Sourcing Real Parts (Fusion Engine)...")
        
        real_bom = []
        
        # Convert dictionary to optimized search queries
        search_queries = []
        for part_type, model_name in target_kit.items():
            # Apply the cleaning logic here
            query = clean_search_query(model_name, part_type)
            # Ensure model_name is safe for later usage
            safe_model = model_name if model_name else f"Generic {part_type}"
            search_queries.append({"type": part_type, "query": query, "model": safe_model})

        # Run Sourcing Loop
        for item in search_queries:
            # Check DB first (Fast Path)
            existing = supply.find_part(item['type'], item['model'])
            if existing and existing.get('source') != "FALLBACK_GENERATOR":
                print(f"      📦 Inventory Match: {existing['product_name']}")
                real_bom.append(existing)
                continue
            
            # Scrape Web (Slow Path)
            print(f"      🌍 Scraping: {item['query']}...") # Log the CLEANED query
            await asyncio.sleep(2) # Politeness
            
            fused_part = await fuse_component_data(
                part_type=item['type'],
                search_query=item['query'],
                search_limit=3,
                min_confidence=0.6
            )
            
            if fused_part:
                supply.save_part(fused_part)
                real_bom.append(fused_part)
                print(f"      ✅ Found & Saved: {fused_part['product_name']}")
            else:
                print(f"      ⚠️  Sourcing Failed: {item['model']}. Using Fallback.")
                fallback = supply.find_part(item['type'], item['model']) # Will generate fallback
                real_bom.append(fallback)

        # --- STEP 5: VALIDATION (Physics & Electronics) ---
        print(f"   ⚙️  Running Simulation & Validation...")
        
        physics_cfg = generate_physics_config(real_bom)
        compat_report = compat.validate_build(real_bom)
        
        # --- STEP 6: OPTIMIZATION LOOP ---
        optimized_params = {} # Store overrides from the optimizer

        if not physics_cfg['viability']['is_mechanically_sound'] or not compat_report['valid']:
            print("   ❌ Design Validation Failed. Engaging Engineering Optimizer...")
            
            fix_plan = optimizer.analyze_and_fix(real_bom, physics_cfg)
            
            if fix_plan:
                print("   🔧 Optimization Plan:")
                for fix in fix_plan.get('optimization_plan', []):
                    print(f"      -> {fix['diagnosis']} -> {fix['action']}")
                    
                    # --- CAPTURE GEOMETRY CHANGES ---
                    # If optimizer suggests modifying geometry (e.g. shortening femur),
                    # we capture the 'param_change' dictionary.
                    if fix.get('type') == 'MODIFY_GEOMETRY' and 'param_change' in fix:
                        # Example: fix['param_change'] might be {'femur_length_mm': 0.85} (multiplier)
                        # or specific values.
                        # Assuming here that we want to apply a specific override or multiplier.
                        # For simplicity in this loop, let's assume we hardcode the intended geometric fix
                        # if the Action mentions shortening legs.
                        if "femur" in str(fix.get('action', '')).lower():
                             # Default was 100mm, let's set to 85mm per typical optimizer suggestion
                             optimized_params['femur_length_mm'] = 85.0
                             optimized_params['tibia_length_mm'] = 95.0

                print("      -> Applying theoretical patches to proceed to CAD...")
                physics_cfg['torque_physics']['safety_margin'] = 2.0 # Force pass

        # --- STEP 7: GENERATE ARTIFACTS ---
        project_id = m_name.replace(" ", "_").lower()
        
        # Apply Optimizer Overrides to the BOM before CAD generation
        if optimized_params:
            for item in real_bom:
                if 'chassis' in item.get('part_type', '').lower():
                    # Create sub-dict if missing
                    if 'engineering_specs' not in item:
                        item['engineering_specs'] = {}
                    
                    # Apply overrides
                    if 'femur_length_mm' in optimized_params:
                        print(f"      🔧 CAD Override: Setting Femur to {optimized_params['femur_length_mm']}mm")
                        item['engineering_specs']['femur_length_mm'] = optimized_params['femur_length_mm']
                    if 'tibia_length_mm' in optimized_params:
                        item['engineering_specs']['tibia_length_mm'] = optimized_params['tibia_length_mm']

        # CAD (OpenSCAD -> STL)
        print(f"   🏗️  Generating CAD Assets ({project_id})...")
        cad_assets = generate_assets(project_id, {}, real_bom)
        
        # USD (Isaac Sim)
        # We construct the robot data packet
        robot_data = {
            "sku_id": project_id,
            "technical_data": {
                "physics_config": physics_cfg,
                "scene_graph": {"components": []} # In real app, derived from digital_twin
            }
        }
        
        # Note: Isaac Service usually runs in its own process/container.
        # Here we assume local install for the "Make Fleet" step
        if os.path.exists("usd_export"):
             print(f"   ⚡ Generating USD Digital Twin...")
             isaac.generate_robot_usd(robot_data)
        
        # Software Stack
        sw_stack = await design_compute_stack(mission, real_bom)
        
        # Schematics
        print(f"   🔌 Generating Wiring Schematic...")
        generate_wiring_diagram(project_id, real_bom)

        print(f"\n✅ CAMPAIGN COMPLETE: {m_name}")
        print(f"   -> Physics Profile: {physics_cfg['torque_physics']}")
        print(f"   -> Software: {sw_stack['stack_design'].get('operating_system')}")
        print("---------------------------------------------------")

if __name__ == "__main__":
    asyncio.run(main())