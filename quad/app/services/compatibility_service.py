# FILE: app/services/compatibility_service.py
import re

class CompatibilityService:
    def __init__(self):
        # Standard LiPo Voltages
        self.LIPO_CELL_VOLTAGE = 3.7
        self.LIPO_FULL_VOLTAGE = 4.2

    def validate_build(self, bom: list) -> dict:
        """
        Runs electronic and architectural checks on a Quadruped BOM.
        """
        errors = []
        warnings = []
        
        # 1. Extract Components safely
        parts = {p['part_type']: p for p in bom}
        
        # Helper to get specs
        def get_spec(part, key, default=None):
            if not part: return default
            return part.get('engineering_specs', {}).get(key, default)

        # --- CHECK A: VOLTAGE MATCHING (CRITICAL) ---
        # Did we plug a 12V battery into a 6V servo?
        battery = parts.get('Battery')
        actuators = parts.get('Actuators')
        
        if battery and actuators:
            # 1. Determine System Voltage
            bat_s = self._parse_s_rating(get_spec(battery, 'cell_count_s') or get_spec(battery, 'voltage'))
            sys_voltage = bat_s * self.LIPO_CELL_VOLTAGE
            
            # 2. Determine Servo Voltage Range
            servo_volts_str = get_spec(actuators, 'voltage_rating', '6V')
            min_v, max_v = self._parse_voltage_range(servo_volts_str)
            
            # 3. Compare
            # Only run check if we actually found a valid battery S-rating
            if bat_s > 0:
                if sys_voltage > max_v:
                    errors.append(f"CRITICAL VOLTAGE OVERLOAD: Battery is {sys_voltage}V (nominal), but Servos are rated max {max_v}V. Magic smoke imminent. Use a BEC or lower voltage battery.")
                elif sys_voltage < min_v:
                    warnings.append(f"Under-voltage: Battery provides {sys_voltage}V, servos usually need minimum {min_v}V.")

        # --- CHECK B: CONTROL ARCHITECTURE ---
        # Can the brain actually move the legs?
        controller = parts.get('Servo_Controller')
        sbc = parts.get('Single_Board_Computer')
        actuators = parts.get('Actuators')
        
        # Count degrees of freedom (DOF)
        actuator_qty = actuators.get('quantity', 12) if actuators else 12
        
        if not controller and not sbc:
            errors.append("MISSING BRAIN: No Servo Controller or Computer selected. Robot has no nervous system.")
        
        if controller:
            # Check Channel Count
            channels = self._extract_number(get_spec(controller, 'channels'))
            if channels and channels < actuator_qty:
                errors.append(f"INSUFFICIENT CHANNELS: Robot has {actuator_qty} servos, but controller only supports {int(channels)} channels.")
            
            # Check Protocol Match (PWM vs Serial)
            servo_proto = get_spec(actuators, 'protocol', 'PWM').lower()
            ctrl_proto = get_spec(controller, 'protocol', 'PWM').lower()
            
            if "serial" in servo_proto and "pwm" in ctrl_proto:
                errors.append("PROTOCOL MISMATCH: Selected Serial Bus Servos (Smart) but Controller is for PWM Servos (Dumb).")
            elif "pwm" in servo_proto and "serial" in ctrl_proto:
                errors.append("PROTOCOL MISMATCH: Selected PWM Servos but Controller is a Serial Bus Linker.")

        # --- CHECK C: KINEMATIC COMPUTE POWER ---
        # Do we have enough math power for Inverse Kinematics?
        # A microcontroller (Arduino/ESP32) is weak for full 12-DOF floating base IK.
        if not sbc:
            warnings.append("Low Compute Power: No Single Board Computer (RPi/Jetson) detected. Running Inverse Kinematics on a basic Microcontroller is difficult/limited.")

        # --- CHECK D: POWER DRAW ---
        if battery and actuators:
            # Estimate Max Current Draw (Stall)
            # Heuristic: Micro=0.8A, Standard=2.5A, Giant=5A
            servo_class = get_spec(actuators, 'size_class', 'Standard')
            amp_per_servo = 2.5
            if 'Micro' in servo_class: amp_per_servo = 0.8
            if 'Giant' in servo_class: amp_per_servo = 5.0
            
            total_stall_amps = actuator_qty * amp_per_servo
            
            # Check Battery C-Rating
            capacity_mah = self._extract_number(get_spec(battery, 'capacity_mah'))
            c_rating = self._extract_number(get_spec(battery, 'discharge_c'), 25)
            
            max_bat_amps = (capacity_mah / 1000.0) * c_rating
            
            if max_bat_amps > 0 and total_stall_amps > max_bat_amps:
                warnings.append(f"Brownout Risk: Servos can draw {total_stall_amps}A, battery only supplies {max_bat_amps:.1f}A. Robot may shut down under load.")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def _parse_s_rating(self, val):
        """Converts '3S', '11.1V' to cell count integer."""
        if not val: return 0
        s_val = str(val).lower()
        
        # Check "3S"
        if 's' in s_val and 'v' not in s_val:
            match = re.search(r"(\d+)s", s_val)
            if match: return int(match.group(1))
            
        # Check "11.1V"
        if 'v' in s_val:
            match = re.search(r"(\d+(\.\d+)?)", s_val)
            if match:
                volts = float(match.group(1))
                return int(round(volts / 3.7))
        
        return 0

    def _parse_voltage_range(self, val_str):
        """Parses '6.0-8.4V' into (6.0, 8.4)."""
        if not val_str: return (4.8, 6.0) # Default PWM range
        
        # FIX: Use simple regex without capturing groups to return strings, not tuples
        matches = re.findall(r"\d+\.?\d*", str(val_str))
        
        nums = []
        for m in matches:
            try:
                nums.append(float(m))
            except ValueError:
                pass
                
        if not nums: return (4.8, 6.0)
        if len(nums) == 1: return (nums[0], nums[0])
        
        return (min(nums), max(nums))

    def _extract_number(self, val, default=0):
        if not val: return default
        match = re.search(r"(\d+(\.\d+)?)", str(val))
        return float(match.group(1)) if match else default