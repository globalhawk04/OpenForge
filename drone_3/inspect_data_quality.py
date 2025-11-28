# FILE: tools/inspect_data_quality.py
import json
import os
import sys

ARSENAL_FILE = "drone_arsenal.json"

def get_spec_value(specs, keys):
    """Helper to check multiple possible key variations."""
    for k in keys:
        val = specs.get(k)
        if val and str(val).lower() not in ["n/a", "null", "none", ""]:
            return val
    return None

def inspect_arsenal():
    if not os.path.exists(ARSENAL_FILE):
        print("❌ No arsenal file found.")
        return

    with open(ARSENAL_FILE, "r") as f:
        data = json.load(f)
        components = data.get("components", [])

    print(f"📊 INSPECTING {len(components)} COMPONENTS (Strict Mode)...\n")

    stats = {
        "total": len(components),
        "missing_mounting": 0,
        "missing_voltage": 0,
        "missing_protocol": 0,
        "vision_verified": 0
    }

    for comp in components:
        specs = comp.get("specs", {}) or comp.get("engineering_specs", {})
        cat = comp.get("category", "")
        name = comp.get("model_name", "Unknown")

        # Check Vision Source
        if specs.get("source") in ["vision", "multimodal_fusion", "active_refinery"]:
            stats["vision_verified"] += 1

        # --- 1. MOUNTING CHECKS (Category Aware) ---
        if cat == "Frame_Kit":
            # Frames need to know where to put the FC AND the Motors
            fc_mount = get_spec_value(specs, ["stack_mount_mm", "fc_mount_pattern_mm", "electronics_mount_mm", "stack_mounting_mm", "mounting_pattern_mm"])
            motor_mount = get_spec_value(specs, ["motor_mount_mm", "motor_mounting_pattern_mm", "motor_mount_pattern"])
            
            if not fc_mount:
                print(f"   ⚠️  Frame missing FC Mount: {name}")
                stats["missing_mounting"] += 1
            elif not motor_mount:
                print(f"   ⚠️  Frame missing Motor Mount: {name}")
                stats["missing_mounting"] += 1

        elif cat == "Motors":
            mount = get_spec_value(specs, ["mounting_pattern_mm", "mounting_bolt_pattern_mm", "mounting_mm", "bolt_pattern"])
            if not mount:
                print(f"   ⚠️  Motor missing Bolt Pattern: {name}")
                stats["missing_mounting"] += 1

        elif cat == "FC_Stack":
            mount = get_spec_value(specs, ["mounting_pattern_mm", "mounting_mm", "stack_size"])
            if not mount:
                print(f"   ⚠️  FC missing Mounting Holes: {name}")
                stats["missing_mounting"] += 1

        # --- 2. VOLTAGE / PROP CHECKS ---
        if cat == "Motors":
            kv = get_spec_value(specs, ["kv", "kv_rating"])
            if not kv or float(str(kv).replace(",","")) < 10:
                print(f"   ⚠️  Motor missing KV: {name}")
                stats["missing_specs"] += 1
        
        if cat == "Battery":
            cells = get_spec_value(specs, ["cell_count_s", "s_rating", "cells"])
            if not cells: 
                print(f"   ⚠️  Battery missing Cell Count: {name}")
                stats["missing_voltage"] += 1

        # --- 3. ELECTRONIC CHECKS ---
        if cat == "FC_Stack":
            uart = get_spec_value(specs, ["uart_count", "uart_port_count", "uarts"])
            if not uart:
                print(f"   ⚠️  FC missing UART Count: {name}")
                stats["missing_protocol"] += 1

    # --- REPORT CARD ---
    print("\n" + "="*40)
    print("📈 DATA QUALITY REPORT CARD")
    print("="*40)
    
    # Simple weighted score
    issues = stats["missing_mounting"] + stats["missing_voltage"] + stats["missing_protocol"]
    # Be lenient: partial credit if mostly complete
    completeness = 100 - (issues * 2) 
    if completeness < 0: completeness = 0

    grade = "F"
    if completeness >= 95: grade = "A+"
    elif completeness >= 90: grade = "A"
    elif completeness >= 80: grade = "B"
    elif completeness >= 70: grade = "C"
    elif completeness >= 60: grade = "D"

    print(f"   Total Components: {stats['total']}")
    print(f"   Vision/Multimodal Verified: {stats['vision_verified']}")
    print("-" * 20)
    print(f"   Mounting Gaps: {stats['missing_mounting']}")
    print(f"   Voltage/Spec Gaps: {stats['missing_voltage']}")
    print(f"   Protocol/IO Gaps: {stats['missing_protocol']}")
    print("-" * 20)
    print(f"   🏆 ENGINEERING GRADE: {grade} ({int(completeness)}%)")

if __name__ == "__main__":
    inspect_arsenal()