# FILE: app/services/geometry_sim_service.py
import math

def run_geometric_simulation(specs: dict) -> dict:
    """
    Performs spatial analysis on CAD specifications to detect physical collisions.

    This service acts as the final "stress test" for the generated geometry,
    using mathematical checks to ensure the design is physically viable.

    Args:
        specs: A dictionary containing key dimensions like 'wheelbase' and
               'prop_diameter_mm' from the CAD service.

    Returns:
        A dictionary with a 'status' (PASS/FAIL) and a list of errors.
    """
    print("--> 📐 Running Geometric Integrity Simulation...")

    report = {
        "status": "PASS",
        "errors": [],
        "warnings": [],
        "metrics": {}
    }

    # 1. Extract and sanitize core geometry specs
    wheelbase = float(specs.get('wheelbase', 0))
    prop_diam_mm = float(specs.get('prop_diameter_mm', 0))

    if wheelbase == 0 or prop_diam_mm == 0:
        report['status'] = 'FAIL'
        report['errors'].append("CRITICAL: Wheelbase or Prop Diameter is zero. Cannot perform simulation.")
        return report

    # --- CHECK 1: Propeller Collision ---
    # In a standard 'X' frame, the distance between adjacent motor shafts
    # is the side length of the square, calculated from the diagonal wheelbase.
    side_dist_between_motors = wheelbase / math.sqrt(2)

    # The gap is the distance between motors minus the diameter of one propeller.
    prop_tip_gap = side_dist_between_motors - prop_diam_mm

    if prop_tip_gap < 2.0:  # A small buffer for safety and air turbulence
        report['status'] = 'FAIL'
        report['errors'].append(f"CRITICAL: Propellers collide or have insufficient clearance. Gap is {prop_tip_gap:.2f}mm.")
    elif prop_tip_gap < 10.0:
        report['warnings'].append(f"Propeller tip clearance is very tight ({prop_tip_gap:.2f}mm). High potential for turbulence.")

    report['metrics']['prop_tip_gap_mm'] = round(prop_tip_gap, 2)

    if report['status'] == 'PASS':
        print("   ✅ Geometric validation passed.")
    else:
         print(f"   ❌ Geometric validation failed: {report['errors']}")

    return report