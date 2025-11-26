# FILE: scripts/test_cad.py
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.cad_service import generate_frame_stl

def main():
    print("=========================================")
    print("Drone Architect - CAD Generation Test")
    print("=========================================")
    
    # Data from our previous Fusion Test (Whoop Specs)
    mock_specs = {
        "motor_mounting_mm": 6.6,  # 0802 Motors
        "prop_diameter_mm": 31.0,  # 31mm Props
        "fc_mounting_mm": 25.5     # AIO Board
    }
    
    print(f"Input Specs: {mock_specs}")
    
    stl_path = generate_frame_stl("test_whoop_01", mock_specs)
    
    if stl_path:
        print(f"\n🎉 SUCCESS! File ready at: {stl_path}")
        print("You can open this file to see your custom generated frame.")

if __name__ == "__main__":
    main()