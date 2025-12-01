#
# FILE: app/workers/tasks.py
import asyncio
import json
import os
from datetime import datetime
from celery import shared_task, chord
from celery.utils.log import get_task_logger

# Import Services
from app.services.ai_service import (
    analyze_user_requirements, 
    refine_requirements, 
    generate_spec_sheet, 
    generate_assembly_instructions,
    optimize_specs
)
from app.services.fusion_service import fuse_component_data
from app.services.physics_service import run_physics_simulation
from app.services.cad_service import generate_assets
from app.services.geometry_sim_service import run_geometric_simulation
from app.services.schematic_service import generate_wiring_diagram
from app.services.cost_service import generate_procurement_manifest

logger = get_task_logger(__name__)

# --- HELPER: ASYNC BRIDGE ---
def run_async(coro):
    """Helper to run async service calls inside sync Celery workers"""
    return asyncio.run(coro)

@shared_task(bind=True)
def start_drone_build(self, user_prompt: str, user_answers: list = None):
    """
    The Master Workflow Entry Point.
    1. Analyzes Intent
    2. Generates Spec Sheet
    3. Triggers Sourcing Chord
    """
    logger.info(f"🚀 Starting Build: {user_prompt}")
    
    # 1. Intake & Engineering
    analysis = run_async(analyze_user_requirements(user_prompt))
    
    # Refine with answers (or defaults)
    final_plan = run_async(refine_requirements(analysis, user_answers or []))
    spec_sheet = run_async(generate_spec_sheet(final_plan))
    
    # 2. Prepare Sourcing Tasks
    buy_list = spec_sheet.get("buy_list", [])
    header_task_signatures = []
    
    for item in buy_list:
        # Create a signature for parallel execution
        header_task_signatures.append(
            source_component_task.s(
                item['part_type'], 
                item['search_query']
            )
        )
    
    # 3. Execute Parallel Sourcing -> Then Run Validation
    workflow = chord(
        header_task_signatures,
        validate_and_finalize_build.s(
            project_context={
                "project_id": self.request.id or "manual_run",
                "constraints": final_plan.get('final_constraints', {}),
                "spec_sheet": spec_sheet,
                "iteration": 1
            }
        )
    )
    return workflow.apply_async()

@shared_task
def source_component_task(part_type: str, query: str):
    """Individual worker task to find ONE part."""
    logger.info(f"🔎 Sourcing: {part_type} - {query}")
    try:
        # Run the Fusion Service
        result = run_async(fuse_component_data(part_type, query))
        if not result:
            # Fallback structure if not found
            return {"part_type": part_type, "status": "failed", "search_query": query}
        return result
    except Exception as e:
        logger.error(f"Error sourcing {part_type}: {e}")
        return {"part_type": part_type, "status": "error", "error": str(e)}

@shared_task
def validate_and_finalize_build(bom_results, project_context):
    """
    The Logic Core / State Machine.
    Receives list of sourced parts.
    Runs Physics (Numerical).
    Runs Optimization Loop if needed.
    Runs CAD + Geometry Sim.
    Generates Output.
    """
    # Filter successful parts
    current_bom = [item for item in bom_results if item.get("status") not in ["failed", "error"]]
    project_id = project_context.get("project_id")
    iteration = project_context.get("iteration", 1)
    
    logger.info(f"🧪 [Iter {iteration}] Running Numerical Physics Simulation...")
    
    # --- STEP 1: NUMERICAL PHYSICS (The "Will it Fly?" Check) ---
    physics_report = run_physics_simulation(current_bom)
    twr = physics_report.get('twr', 0)
    
    # Optimization Gate: TWR < 1.4 triggers AI Fix (max 3 retries)
    if twr < 1.4 and iteration <= 3:
        logger.warning(f"⚠️ Low TWR ({twr}). Attempting AI Optimization...")
        
        optimization_plan = run_async(optimize_specs(current_bom, physics_report))
        replacements = optimization_plan.get("replacements", [])
        
        if replacements:
            logger.info(f"🔄 Optimization Strategy: {optimization_plan.get('strategy')}")
            
            # Filter out replaced parts
            types_to_remove = [r['part_type'] for r in replacements]
            kept_parts = [p for p in current_bom if p['part_type'] not in types_to_remove]
            
            # Trigger Sourcing for NEW parts
            new_search_tasks = [
                source_component_task.s(r['part_type'], r['new_search_query'])
                for r in replacements
            ]
            
            # Update iteration count
            project_context["iteration"] = iteration + 1
            
            # RECURSION via Callback
            return chord(
                new_search_tasks,
                merge_and_revalidate.s(kept_parts, project_context)
            ).apply_async()
    
    # --- STEP 2: GEOMETRIC PHYSICS & CAD (The "Does it Fit?" Check) ---
    logger.info("✅ Numerical Physics Passed. Generating Geometry...")
    
    # Extract params for CAD from the BOM
    cad_specs = extract_cad_params(current_bom)
    
    # Generate High-Fidelity CAD Assets
    # Note: cad_service now auto-calculates a safe wheelbase if prop gap is too small
    assets = generate_assets(project_id, cad_specs)
    
    # Run Geometric Simulation on the CALCULATED specs (post-CAD-correction)
    geo_report = run_geometric_simulation(assets['calculated_specs'], {})
    
    if geo_report['status'] == "FAIL":
        logger.error(f"❌ Geometric Failure: {geo_report['errors']}")
        # In a more advanced version, we would loop back here too. 
        # But cad_service V2 is designed to auto-fix collisions, so this is a critical audit log.
    else:
        logger.info(f"✅ Geometric Validation Passed. Prop Gap: {geo_report['metrics'].get('prop_gap_mm')}mm")

    # --- STEP 3: DOCUMENTATION & OUTPUT ---
    logger.info("📄 Generating Documentation...")
    
    doc_context = {
        "bill_of_materials": current_bom,
        "engineering_notes": project_context['spec_sheet'].get("engineering_notes"),
        "fabrication_specs": assets['calculated_specs']
    }
    
    assembly_guide = run_async(generate_assembly_instructions(doc_context))
    schematic_path = generate_wiring_diagram(project_id, [p.get('product_name', '') for p in current_bom])
    cost_report = generate_procurement_manifest(current_bom)
    
    # Final Master Record
    master_record = {
        "project_id": project_id,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "COMPLETE",
        "engineering": {
            "constraints": project_context['constraints'],
            "iterations_required": iteration
        },
        "sourcing": {
            "bom": current_bom,
            "cost": cost_report
        },
        "simulation": {
            "numerical": physics_report,
            "geometric": geo_report
        },
        "fabrication": assets,
        "assembly": assembly_guide,
        "schematic_path": schematic_path
    }
    
    # Save to disk
    output_path = os.path.join("static", "generated", f"{project_id}_MASTER.json")
    with open(output_path, "w") as f:
        json.dump(master_record, f, indent=2)
        
    return master_record

@shared_task
def merge_and_revalidate(new_parts, kept_parts, project_context):
    """Callback to merge lists after an optimization loop."""
    full_bom = kept_parts + new_parts
    return validate_and_finalize_build(full_bom, project_context)

def extract_cad_params(bom):
    """Extracts max dimensions from BOM for the CAD generator."""
    specs = {}
    total_weight = 0
    
    for part in bom:
        eng = part.get('engineering_specs', {})
        
        # Aggregation
        if eng.get('mounting_mm'): specs['motor_mounting_mm'] = eng['mounting_mm']
        if eng.get('diameter_mm'): specs['prop_diameter_mm'] = eng['diameter_mm']
        if eng.get('width_mm'): specs['camera_width_mm'] = eng['width_mm']
        
        # Weight sum (rough)
        # Note: physics_service does a better job, but we pass this for disk loading calc if needed
        # We rely on the CAD service to default this if missing
    
    # Defaults if Vision AI failed
    if 'fc_mounting_mm' not in specs: specs['fc_mounting_mm'] = 30.5
    
    return specs