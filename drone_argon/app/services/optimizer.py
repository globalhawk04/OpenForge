import copy

class EngineeringOptimizer:
    """
    The 'Brain' of the operation.
    Analyzes flight logs and suggests hardware changes.
    """
    
    def analyze_and_fix(self, current_specs, flight_report):
        """
        Input: Current CAD Specs + Physics Report
        Output: New Specs + Reasoning
        """
        new_specs = copy.deepcopy(current_specs)
        fixes = []
        status = flight_report['status']
        log = flight_report.get('flight_log', {})
        
        print(f"\n🧠 [AI ENGINEER] Analyzing Flight Data for {current_specs.get('name')}...")
        
        # --- HEURISTIC 1: WEIGHT / POWER ANALYSIS ---
        # Did we max out the throttle just to hover?
        hover_throttle = flight_report.get('hover_throttle_pct', 0)
        
        if hover_throttle > 65.0:
            reason = f"Drone is overweight (Hover requires {hover_throttle}% throttle)."
            action = "Increasing Propeller Diameter to generate more lift."
            
            # Action: 5.0" -> 5.1" -> 5.5" -> 6.0"
            current_prop = new_specs['prop_diameter_inch']
            new_specs['prop_diameter_inch'] = round(current_prop + 0.1, 1)
            
            fixes.append(f"{reason} {action}")

        # --- HEURISTIC 2: CRASH ANALYSIS ---
        # Did it crash during the stunt?
        if status == "FAIL":
            events = log.get('events', [])
            crash_reason = events[0] if events else "Unknown Crash"
            
            reason = f"Catastrophic failure detected: {crash_reason}"
            action = "Upgrading Motors (2207 -> 2306 -> 2806) for more torque authority."
            
            # Logic: Increase mounting pattern to force a larger motor model in CAD
            # (In a real app, we'd change the kv or stator_size directly)
            new_specs['name'] += "_Turbo"
            new_specs['motor_mount_mm'] = 19.0 # Force larger motor class
            
            fixes.append(f"{reason} {action}")

        # --- HEURISTIC 3: EFFICIENCY ---
        # (Optional) If it flies TOO well (10% throttle), shrink it to save money.
        if 0 < hover_throttle < 15.0:
            reason = "Drone is overpowered (Hover at <15%)."
            action = "Downsizing battery to save weight."
            fixes.append(f"{reason} {action}")

        # --- RESULT ---
        if not fixes:
            return None # No changes needed, design is perfect.
        
        # Apply Versioning
        new_specs['name'] = self._increment_version(new_specs.get('name', 'Drone_V1'))
        
        return {
            "new_specs": new_specs,
            "reasoning": fixes
        }

    def _increment_version(self, name):
        if "_V" in name:
            base, v = name.rsplit("_V", 1)
            try:
                new_v = int(v) + 1
                return f"{base}_V{new_v}"
            except:
                pass
        return f"{name}_V2"