# FILE: app/services/library_service.py
import re
from typing import Optional

# Mapping Stator Size -> Bolt Circle Diameter (mm)
STANDARD_MOTOR_PATTERNS = {
    # --- Tiny Whoop / Micro (3-Hole) ---
    "0603": 6.6,
    "0702": 6.6,
    "0703": 6.6,
    "0802": 6.6,  # Standard Whoop
    "0803": 9.0,  # Larger Whoop
    "1002": 9.0,
    "1102": 9.0,  # Toothpick standard
    "1103": 9.0,
    
    # --- Ultralight / Cine (4-Hole 9mm or 12mm) ---
    "1202": 9.0,
    "1204": 9.0,
    "1404": 9.0,  # 4-inch LR standard
    "1507": 12.0, # 3-inch Cinewhoop
    "2004": 12.0, # Ultralight 5-inch
    
    # --- Freestyle (4-Hole 16mm) ---
    "2205": 16.0,
    "2207": 16.0, # The 5-inch Standard
    "2306": 16.0, # The other 5-inch Standard
    "2208": 16.0,
    
    # --- Long Range / Heavy (4-Hole 19mm) ---
    "2806": 19.0, # 7-inch
    "2807": 19.0,
    "2810": 19.0
}

def infer_motor_mounting(product_title: str) -> Optional[float]:
    """
    If Vision fails, guess mounting based on motor stator size in title.
    Returns: Bolt circle diameter (mm) or None.
    """
    if not product_title:
        return None

    # Extract 4-digit stator size (e.g., 0802, 2207)
    # \b ensures we don't match inside other numbers
    match = re.search(r"\b(\d{4})\b", product_title)
    if match:
        size = match.group(1)
        return STANDARD_MOTOR_PATTERNS.get(size, None)
    
    return None

def extract_prop_diameter(product_title: str) -> Optional[float]:
    """
    Extracts prop size (31mm, 40mm, 5 inch) from title.
    Returns: Diameter in mm.
    """
    if not product_title:
        return None
        
    lower_title = product_title.lower()

    # 1. Try millimeter match first (Common for Whoops: 31mm, 40mm, 65mm, 75mm)
    # We look for 2 digits followed specifically by 'mm'
    mm_match = re.search(r"\b(\d{2})\s*mm", lower_title)
    if mm_match:
        return float(mm_match.group(1))
    
    # 2. Try inch match (Common for Freestyle: 5", 5 inch, 5.1 inch)
    # Matches: "5 inch", "5inch", "5.1 inch", "7 inch"
    inch_match = re.search(r"\b(\d(?:\.\d)?)\s*(?:inch|\"|in)\b", lower_title)
    if inch_match:
        return float(inch_match.group(1)) * 25.4
    
    # 3. Try "Prop Size Notation" (e.g., 5143 = 5.1 inch, 3040 = 3.0 inch)
    # Look for 4 digits where the first digit is 3-7 (likely a prop size code, not a year or kv)
    code_match = re.search(r"\b([3-7])\d{3}\b", lower_title)
    if code_match:
        # e.g. 5143 -> 5.1 inch
        # This is aggressive, might false positive on dates, but useful for props
        first_digit = float(code_match.group(1))
        return first_digit * 25.4

    return None