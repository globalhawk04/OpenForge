# FILE: simulation/calc_twr.py
import sys
import json
import math

def calculate_flight_characteristics(data):
    """
    Advanced Flight Physics Model.
    Calculates TWR, Hover %, Disk Loading, and Theoretical Top Speed.
    """
    weight_g = data.get("total_weight_g", 0)
    max_thrust_g = data.get("max_thrust_g", 0)
    num_motors = data.get("num_motors", 4)
    battery_cap = data.get("battery_capacity_mah", 0)
    
    # New inputs for advanced physics
    prop_diam_inch = data.get("prop_diameter_inch", 0)
    prop_pitch_inch = data.get("prop_pitch_inch", 3.0) # Default estimate
    motor_kv = data.get("motor_kv", 0)
    voltage = data.get("voltage", 0)

    if weight_g == 0: return {"error": "Weight is zero"}
    
    # 1. Basic Stats
    total_thrust = max_thrust_g * num_motors
    twr = total_thrust / weight_g
    hover_throttle_percent = (weight_g / total_thrust) * 100
    
    # 2. Flight Time (Amps estimation)
    # Weight-based heuristic for hover current
    if weight_g < 50: hover_amps = 2.5
    elif weight_g < 250: hover_amps = 6.0
    else: hover_amps = 12.0 + ((weight_g - 300)/50) # Scale up for heavy drones
    
    flight_time_min = ((battery_cap / 1000) / hover_amps) * 60 * 0.8

    # 3. Advanced: Disk Loading (g/dm^2)
    # Measures "floatiness" vs "aggressiveness"
    # Area of one prop disc in sq dm
    if prop_diam_inch > 0:
        radius_cm = (prop_diam_inch * 2.54) / 2
        area_dm2 = (math.pi * (radius_cm ** 2)) / 100
        total_disc_area = area_dm2 * num_motors
        disk_loading = weight_g / total_disc_area
    else:
        disk_loading = 0

    # 4. Advanced: Theoretical Top Speed (km/h)
    # Pitch Speed = RPM * Pitch * conversion
    if motor_kv > 0 and voltage > 0:
        rpm = motor_kv * voltage * 0.85 # Efficiency loss under load
        # inches/min -> km/h
        # (RPM * Pitch) = inches/minute
        # inches/min * 60 = inches/hour
        # inches/hour / 39370 = km/h
        pitch_speed_kmh = (rpm * prop_pitch_inch * 60) / 39370
        # Drag factor (approximated for quadcopters)
        top_speed_kmh = pitch_speed_kmh * 0.75
    else:
        top_speed_kmh = 0
    
    return {
        "total_weight_g": int(weight_g),
        "twr": round(twr, 2),
        "hover_throttle_percent": round(hover_throttle_percent, 1),
        "est_flight_time_min": round(flight_time_min, 1),
        "disk_loading": round(disk_loading, 2),
        "top_speed_kmh": int(top_speed_kmh),
        "status": "FLYABLE" if twr > 1.3 else "UNDERPOWERED"
    }

if __name__ == "__main__":
    input_data = sys.stdin.read()
    try:
        data = json.loads(input_data)
        result = calculate_flight_characteristics(data)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))