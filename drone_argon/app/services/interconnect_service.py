# FILE: app/services/interconnect_service.py
import math
import re

# Standard Cable Lengths included with parts (Conservative estimates in mm)
DEFAULT_CAM_CABLE_LEN = 80 
DEFAULT_MOTOR_WIRE_LEN = 150

def calculate_distance(pos_a, pos_b):
    """Euclidean distance between two [x,y,z] points."""
    if not pos_a or not pos_b:
        return 0.0
    return math.sqrt(
        (pos_a[0] - pos_b[0])**2 + 
        (pos_a[1] - pos_b[1])**2 + 
        (pos_a[2] - pos_b[2])**2
    )

def analyze_interconnects(bom, scene_graph):
    """
    Scans the physical layout (Scene Graph) and the parts list (BOM) 
    to find missing links, short cables, incompatible connectors, or missing voltage regulators.
    
    Returns a list of extra items to add to the BOM.
    """
    extras = []
    
    # Create a quick lookup map for BOM components
    parts_map = {p.get('part_type'): p for p in bom}
    
    # =========================================================
    # 1. PHYSICAL ANALYSIS (Geometry & Cable Lengths)
    # =========================================================
    
    # The scene graph contains the calculated X/Y/Z coordinates from the CAD service
    comps = scene_graph.get('components', [])
    
    def get_pos(type_id):
        # Find the first component of this type
        found = next((c for c in comps if c['type'] == type_id), None)
        return found['pos'] if found else None

    pos_stack = get_pos('PCB_STACK')
    pos_cam = get_pos('CAMERA')
    
    # Check Camera Cable Length
    if pos_stack and pos_cam:
        # Calculate linear distance + 30% slack for wire routing/twisting
        dist_mm = calculate_distance(pos_stack, pos_cam) * 1.3
        
        if dist_mm > DEFAULT_CAM_CABLE_LEN:
            extras.append({
                "part_type": "Cable",
                "product_name": f"Extended Camera Cable ({int(dist_mm + 20)}mm)",
                "price": 4.99, 
                "source_url": "https://www.getfpv.com/cables",
                "category": "Cable",
                "model": f"Extended Camera Cable ({int(dist_mm + 20)}mm)"
            })

    # =========================================================
    # 2. POWER SYSTEM ANALYSIS (Connectors & Soldering)
    # =========================================================
    
    battery = parts_map.get('Battery')
    
    if battery:
        specs = battery.get('engineering_specs', {})
        
        # Heuristic: Determine connector based on Voltage and Capacity
        connector_type = specs.get('connector_type', '').upper()
        cell_count = float(specs.get('cell_count_s') or specs.get('cells') or 0)
        capacity = float(specs.get('capacity_mah') or 0)
        
        target_connector = "XT60" # Default for most 5"
        
        if "XT90" in connector_type or (cell_count >= 6 and capacity > 2000):
            target_connector = "XT90"
        elif "XT30" in connector_type or (cell_count <= 4 and capacity < 850):
            target_connector = "XT30"
        
        # Check if FC is a "Stack" (usually needs pigtail soldered) vs "AIO" (often has one)
        fc = parts_map.get('FC_Stack', {})
        fc_name = fc.get('product_name', '').lower()
        
        # If it's a stack, we almost always need to buy the pigtail separately
        if "stack" in fc_name or "f7" in fc_name or "h7" in fc_name:
            extras.append({
                "part_type": "Connector",
                "product_name": f"{target_connector} Pigtail with Capacitor (12AWG)",
                "price": 3.50,
                "source_url": "https://www.racedayquads.com/connectors",
                "category": "Connector",
                "model": f"{target_connector} Pigtail"
            })

    # =========================================================
    # 3. SIGNAL ANALYSIS (Receiver Wires)
    # =========================================================
    
    # If there is a separate receiver (not integrated), we need wire
    rx = next((i for i in bom if "receiver" in str(i.get('product_name', '')).lower()), None)
    if rx:
        extras.append({
            "part_type": "Wire",
            "product_name": "Silicone Wire Kit (30AWG) - 4 Colors",
            "price": 5.99,
            "source_url": "Generic",
            "category": "Wire",
            "model": "Silicone Wire Kit"
        })

    # =========================================================
    # 4. ELECTRONIC COMPATIBILITY (BECs & Regulators)
    # =========================================================
    
    fc = parts_map.get('FC_Stack')
    vtx = parts_map.get('Camera_VTX_Kit')
    
    if fc and vtx:
        fc_specs = str(fc.get('engineering_specs', {})).lower()
        vtx_name = vtx.get('product_name', '').lower()
        
        # Logic: Digital VTXs (DJI O3, Vista, Walksnail) often need clean 9V/10V.
        # Analog VTXs usually run on V_BAT (Raw Battery Voltage).
        
        is_digital = any(x in vtx_name for x in ["dji", "vista", "walksnail", "o3", "digital", "hdzero"])
        
        if is_digital:
            # Check if Flight Controller has a dedicated 9V or 10V BEC
            has_high_volt_bec = any(v in fc_specs for v in ["9v", "10v", "12v"])
            
            if not has_high_volt_bec:
                print("   ⚡ Alert: FC missing 9V BEC for Digital VTX. Adding external regulator.")
                extras.append({
                    "part_type": "Voltage_Regulator",
                    "product_name": "External 9V 2A BEC (Type-C)",
                    "price": 6.99,
                    "source_url": "https://www.racedayquads.com/becs",
                    "category": "Electronics",
                    "model": "Micro BEC 9V"
                })

    # =========================================================
    # 5. NOISE FILTERING (Capacitors)
    # =========================================================
    
    # High voltage builds (6S+) create significant electrical noise (back EMF)
    # that can damage electronics or ruin video. Always add a capacitor.
    if battery:
        cell_count = float(battery.get('engineering_specs', {}).get('cell_count_s') or 0)
        
        if cell_count >= 6:
            extras.append({
                "part_type": "Capacitor",
                "product_name": "Panasonic FM Low ESR 1000uF 35V",
                "price": 1.50,
                "source_url": "Generic",
                "category": "Electronics",
                "model": "1000uF 35V Cap"
            })

    return extras