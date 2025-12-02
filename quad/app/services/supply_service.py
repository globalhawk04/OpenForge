# FILE: app/services/supply_service.py
from app.services.db_service import ArsenalDB
import difflib

class SupplyService:
    def __init__(self):
        self.db = ArsenalDB()

    def find_part(self, part_type, ideal_model_name):
        """
        Smart Inventory Lookup:
        1. Checks DB for exact match.
        2. Checks DB for fuzzy match.
        3. Returns a 'Generic Fallback' if the scraping failed.
        """
        # 1. Exact/SQL Search
        candidate = self.db.find_component(part_type, ideal_model_name)
        if candidate:
            return candidate

        # 2. Broad Category Search (for fuzzy matching)
        all_category_parts = self._get_all_by_type(part_type)
        
        if all_category_parts:
            # Fuzzy Match
            model_names = [p['product_name'] for p in all_category_parts]
            matches = difflib.get_close_matches(ideal_model_name, model_names, n=1, cutoff=0.4)
            
            if matches:
                return next(p for p in all_category_parts if p['product_name'] == matches[0])
            
            # If no fuzzy match but we have *something*, return the best verify part
            return all_category_parts[0]

        # 3. Fallback (The "Dummy Part")
        return self._get_generic_fallback(part_type, ideal_model_name)

    def save_part(self, part_data):
        return self.db.add_component(part_data)

    def _get_all_by_type(self, part_type):
        inventory = self.db.get_all_inventory()
        return [p for p in inventory if p['part_type'] == part_type]

    def _get_generic_fallback(self, part_type, name):
        """Generates a dummy part based on library knowledge."""
        from app.services.library_service import infer_actuator_specs
        
        inferred_specs = {}
        
        # FIX: Ensure Actuators always have torque, even if inference fails
        if "actuator" in part_type.lower():
            inferred_specs = infer_actuator_specs(name)
            if "est_torque_kgcm" not in inferred_specs:
                # Default to a "Standard" servo torque so physics doesn't divide by zero
                inferred_specs["est_torque_kgcm"] = 20.0 
                inferred_specs["protocol"] = "PWM"

        return {
            "part_type": part_type,
            "product_name": f"Generic {name}",
            "price": 10.0, # Give it a price so cost calculation works
            "engineering_specs": inferred_specs,
            "visuals": {
                "primary_color_hex": "#888888",
                "material_type": "PLASTIC"
            },
            "source": "FALLBACK_GENERATOR"
        }