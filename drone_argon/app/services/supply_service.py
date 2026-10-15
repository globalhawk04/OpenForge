# FILE: app/services/supply_service.py
import json
import os
import difflib

ARSENAL_FILE = "drone_arsenal.json"

class SupplyService:
    def __init__(self):
        self.inventory = self._load_inventory()

    def _load_inventory(self):
        if os.path.exists(ARSENAL_FILE):
            try:
                with open(ARSENAL_FILE, "r") as f:
                    data = json.load(f)
                    return data.get("components", [])
            except: 
                pass
        return []

    def find_part(self, category, ideal_model_name):
        """
        Fuzzy searches the Arsenal for a part.
        If verified part exists: Returns it.
        If not: Returns a 'Generic' placeholder (so the code doesn't crash).
        """
        # Filter by category
        candidates = [p for p in self.inventory if p.get('category') == category]
        
        if not candidates:
            return self._get_generic_fallback(category)

        # 1. Exact Match
        for part in candidates:
            if part['model_name'].lower() == ideal_model_name.lower():
                return part

        # 2. Fuzzy Match (Find closest string)
        model_names = [p['model_name'] for p in candidates]
        matches = difflib.get_close_matches(ideal_model_name, model_names, n=1, cutoff=0.4)
        
        if matches:
            return next(p for p in candidates if p['model_name'] == matches[0])

        # 3. Fallback: Return the first verified part in that category
        return candidates[0]

    def _get_generic_fallback(self, category):
        """Generates a dummy part if the Arsenal is empty."""
        return {
            "category": category,
            "model_name": f"Generic {category}",
            "price_est": 0.0,
            "specs": {},
            "visuals": { # Default visual DNA
                "primary_color_hex": "#555555",
                "material_type": "PLASTIC"
            },
            "source": "FALLBACK"
        }