# FILE: scripts/test_physics.py
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.physics_service import run_physics_simulation

def main():
    print("=========================================")
    print("Drone Architect - Physics Sim Test")
    print("=========================================")
    
    # Mock BOM based on our Whoop search
    mock_bom = [
        {"part_type": "Motors", "product_name": "0802 19000kv"},
        {"part_type": "FC_Stack", "product_name": "AIO FC"},
        {"part_type": "Battery", "product_name": "1S 300mAh"},
        {"part_type": "Chassis", "product_name": "Printed Frame"}
    ]
    
    print("Running Simulation on BOM...")
    report = run_physics_simulation(mock_bom)
    
    if report:
        print("\n✅ FLIGHT REPORT:")
        print(json.dumps(report, indent=2))
        
        if report['twr'] > 1.5:
            print("\n🚀 RESULT: This drone WILL FLY.")
        else:
            print("\n⚠️ RESULT: Drone is too heavy!")

if __name__ == "__main__":
    main()