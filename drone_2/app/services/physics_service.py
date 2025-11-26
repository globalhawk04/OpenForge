# FILE: app/services/physics_service.py
import re
import math
import numpy as np

# --- CONFIGURATION ---
GRAVITY = 9.81

# Fallback weights (in grams) if visual AI/Specs fail
FALLBACK_WEIGHTS = {
    "motors": 35.0,
    "frame_kit": 120.0,
    "fc_stack": 25.0,
    "camera_vtx_kit": 45.0, 
    "battery": 220.0, 
    "propellers": 5.0,
}

def _extract_number(text, default=0.0):
    """Robust extraction of numbers from dirty strings (e.g., 'approx 35g')."""
    if isinstance(text, (int, float)): return float(text)
    if not text: return default
    try:
        match = re.search(r"(\d+(\.\d+)?)", str(text))
        return float(match.group(1)) if match else default
    except:
        return default

def _calculate_auw(bom):
    """Calculates All-Up-Weight in Grams."""
    total_g = 0.0
    
    for item in bom:
        cat = item.get('category', '').lower()
        qty = 4 if 'motor' in cat or 'propeller' in cat else 1
        
        # Try finding weight in specs first
        weight = _extract_number(item.get('specs', {}).get('weight_g'))
        
        # Fallback to defaults
        if weight == 0:
            for k, v in FALLBACK_WEIGHTS.items():
                if k in cat:
                    weight = v
                    break
        
        total_g += (weight * qty)
        
    # Add 10% overhead for wires, straps, solder, tape
    return total_g * 1.1

def _estimate_max_thrust(motor_item, prop_item):
    """
    Estimates max thrust per motor in Grams.
    In a full production version, this would query the data_service thrust tables.
    Here we use a robust heuristic based on Stator Size and KV.
    """
    if not motor_item: return 1000.0 # Default fallback
    
    specs = motor_item.get('specs', {})
    kv = _extract_number(specs.get('kv', 1700))
    # Try to parse stator size from model name (e.g., "2207")
    model = motor_item.get('model_name', '')
    stator_match = re.search(r"(\d{4})", model)
    stator_vol = 0
    if stator_match:
        d = int(stator_match.group(1)[:2])
        h = int(stator_match.group(1)[2:])
        stator_vol = (math.pi * (d/2)**2) * h
    
    # Heuristic: Thrust scales with Stator Volume + Prop Size
    # This is a 'Game Logic' approximation to ensure the sim feels right
    # even without a scrape.
    estimated_thrust_g = 1000.0
    
    if stator_vol > 0:
        estimated_thrust_g = stator_vol * 1.5 # Rough coefficient
    
    # Adjust for KV (higher KV = more thrust usually on intended voltage)
    if kv > 2000: estimated_thrust_g *= 0.9 # High KV usually smaller props
    elif kv < 1500: estimated_thrust_g *= 1.3 # Low KV usually huge props
    
    return max(500, estimated_thrust_g)

def generate_physics_config(bom):
    """
    Generates the Physics Configuration Object for the frontend Game Engine (Cannon.js).
    Converts everything to SI Units (Meters, Kilograms, Newtons).
    """
    print("--> 🚀 Physics Service: Compiling Flight Dynamics...")
    
    # 1. Identify Parts
    frame = next((i for i in bom if i['category'] == 'Frame_Kit'), {})
    motors = next((i for i in bom if i['category'] == 'Motors'), {})
    props = next((i for i in bom if i['category'] == 'Propellers'), {})
    battery = next((i for i in bom if i['category'] == 'Battery'), {})

    # 2. Calculate Core Mass Properties
    mass_g = _calculate_auw(bom)
    mass_kg = mass_g / 1000.0
    
    # 3. Calculate Force Properties
    max_thrust_g_per_motor = _estimate_max_thrust(motors, props)
    max_force_newtons = (max_thrust_g_per_motor / 1000.0) * GRAVITY
    
    total_thrust_g = max_thrust_g_per_motor * 4
    twr = total_thrust_g / mass_g if mass_g > 0 else 0
    
    # 4. Calculate Dimensions (for Colliders)
    wb_mm = _extract_number(frame.get('specs', {}).get('wheelbase_mm'), 225)
    wb_meters = wb_mm / 1000.0
    
    # 5. Flight Characteristics (Tuning the "Feel")
    # A heavy drone (low TWR) should feel sluggish.
    # A light drone (high TWR) should feel snappy.
    
    # Angular Damping (Resistance to rotation)
    # Higher mass = higher inertia
    angular_damping = 0.1 if twr > 8 else 0.5 
    
    # Drag (Air resistance)
    linear_damping = 0.3 # Standard drag
    
    config = {
        "mass_kg": round(mass_kg, 3),
        "motor_max_force_n": round(max_force_newtons, 2),
        "collider_size_m": [wb_meters/1.5, 0.05, wb_meters/1.5], # Box collider approximation
        "center_of_mass_offset": [0, -0.02, 0], # Battery usually underslung (lower CG) or top (higher CG)
        "dynamics": {
            "twr": round(twr, 2),
            "hover_throttle": round(1.0 / twr, 2) if twr > 0 else 0.5,
            "linear_damping": linear_damping,
            "angular_damping": angular_damping,
            "max_velocity_ms": 45.0 if twr > 4 else 25.0
        },
        "meta": {
            "total_weight_g": round(mass_g, 1),
            "est_flight_time_min": _calculate_flight_time(battery, mass_g)
        }
    }
    
    print(f"   📊 Physics Ready: Mass={mass_kg}kg, MaxForce={max_force_newtons}N, TWR={twr:.1f}")
    return config

def _calculate_flight_time(battery_item, total_weight_g):
    """Rough estimate of hover time based on battery capacity."""
    mah = _extract_number(battery_item.get('specs', {}).get('capacity_mah'), 1300)
    # Heuristic: Hover amps approx (Weight / 40)
    # 500g drone -> ~12.5 Amps hover
    hover_amps = total_weight_g / 40.0
    if hover_amps <= 0: return 0
    
    hours = (mah / 1000.0) / hover_amps
    return round(hours * 60 * 0.8, 1) # 80% efficiency factor