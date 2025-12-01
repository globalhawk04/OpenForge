# FILE: app/services/compatibility_service.py
import re

class CompatibilityService:
    def __init__(self):
        self.VOLTAGE_MAP = {
            6: {"min_kv": 1100, "max_kv": 2150},
            4: {"min_kv": 2100, "max_kv": 2900}
        }

    def validate_build(self, bom: list) -> dict:
        """
        Runs all physics and electronic checks on a proposed BOM.
        """
        errors = []
        warnings = []
        
        # 1. Extract Components safely
        parts = {p['part_type']: p for p in bom}
        
        # Helper to get specs safely
        def get_spec(part, key, default=None):
            if not part: return default
            return part.get('engineering_specs', {}).get(key, default)

        # --- CHECK A: VOLTAGE MATCHING ---
        battery = parts.get('Battery')
        motor = parts.get('Motors')
        
        if battery and motor:
            try:
                # Handle "6S", "6", 6.0
                cells_raw = get_spec(battery, 'cell_count_s', 0)
                cells = float(str(cells_raw).lower().replace('s',''))
                
                # Handle "1750", "1750KV"
                kv_raw = get_spec(motor, 'kv_rating') or get_spec(motor, 'kv', 0)
                kv = float(str(kv_raw).lower().replace('kv',''))
            except:
                cells, kv = 0, 0
            
            if cells > 0 and kv > 0:
                if cells >= 6 and kv > 2150:
                    errors.append(f"CRITICAL: Voltage Mismatch! 6S Battery with {int(kv)}KV Motors will burn out. Target < 2150KV.")
                elif cells <= 4 and kv < 2000:
                    warnings.append(f"Performance Warning: 4S Battery with {int(kv)}KV Motors will be underpowered.")

        # --- CHECK B: ELECTRONIC I/O ---
        fc = parts.get('FC_Stack')
        vtx = parts.get('Camera_VTX_Kit')
        gps = parts.get('GPS_Module')
        
        # Find receiver dynamically (it might be named 'Receiver' or 'ELRS')
        rx = next((p for p in bom if "receiver" in str(p.get('part_type', '')).lower()), None)
        
        if fc:
            spec_str = str(fc.get('engineering_specs', {}))
            
            # Smart UART Counting
            uart_count = 3 # Default assumption
            if "uart_count" in fc.get('engineering_specs', {}):
                try: uart_count = int(fc['engineering_specs']['uart_count'])
                except: pass
            
            used_uarts = 0
            
            # Check VTX
            if vtx:
                vtx_name = str(vtx.get('product_name', '')).lower()
                if any(x in vtx_name for x in ["digital", "o3", "vista", "walksnail"]):
                    used_uarts += 1
            
            # Check RX (FIXED LOGIC)
            if rx:
                rx_name = str(rx.get('product_name', '')).lower()
                if "elrs" in rx_name or "crsf" in rx_name or "crossfire" in rx_name:
                    used_uarts += 1
            
            # Check GPS
            if gps:
                used_uarts += 1
            
            if used_uarts > uart_count:
                errors.append(f"I/O Bottleneck: FC has ~{uart_count} UARTs, but peripherals require {used_uarts}. Upgrade FC.")

        # --- CHECK C: PHYSICAL CLEARANCE ---
        frame = parts.get('Frame_Kit')
        props = parts.get('Propellers')
        
        if frame and props:
            try:
                # Get Frame Max Prop
                frame_max = get_spec(frame, 'max_prop_size_inch')
                if not frame_max:
                    # Guess based on name
                    name = frame['product_name'].lower()
                    if "7 inch" in name or "chimera7" in name: frame_max = 7.5
                    elif "5 inch" in name or "5inch" in name: frame_max = 5.2
                    else: frame_max = 99.0
                
                # Get Prop Size
                prop_size = get_spec(props, 'diameter_inches') or get_spec(props, 'diameter_inch')
                if not prop_size:
                    # Try mm -> inch conversion
                    mm = get_spec(props, 'diameter_mm')
                    if mm: prop_size = float(mm) / 25.4
                
                if frame_max and prop_size:
                    if float(prop_size) > float(frame_max):
                        errors.append(f"Geometry Clash: {prop_size}\" Props are too large for this frame (Max {frame_max}\").")
            except Exception as e:
                pass # If data is too messy, let the AI Master Builder catch it later

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }