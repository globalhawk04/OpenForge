# FILE: app/services/cost_service.py
import re
from urllib.parse import urlparse

def generate_procurement_manifest(bom: list) -> dict:
    """
    Calculates total cost and groups items by vendor with robust price handling.
    """
    subtotal = 0.0
    vendor_list = {}
    
    for item in bom:
        price_data = item.get("price") # Can be float, int, string, or None
        url = item.get("source_url", "")
        quantity = item.get("quantity", 1) # Assume quantity is 1 unless specified
        
        # --- ROBUST PRICE EXTRACTION LOGIC ---
        price_val = 0.0
        if isinstance(price_data, (int, float)):
            # The best case: price is already a number.
            price_val = float(price_data)
        elif isinstance(price_data, str):
            # Fallback for strings like "$24.99" or "Check Site"
            match = re.search(r'(\d+[\.,]\d{2})', price_data)
            if match:
                try:
                    clean_price = match.group(1).replace(",", "")
                    price_val = float(clean_price)
                except ValueError:
                    price_val = 0.0 # Failed to parse the string
        # If price_data is None or unhandled, price_val remains 0.0

        # Account for parts that come in multiples (e.g., Motors often sold as a set of 4)
        # We will assume the listed price is for the set, but a more advanced version
        # could parse the title for "4PCS" and divide the price. For now, we'll handle
        # quantity if it's explicitly in the BOM.
        item_total_price = price_val * quantity

        # 2. Extract Vendor
        domain = "Unknown"
        if url:
            try:
                domain = urlparse(url).netloc.replace("www.", "")
            except: pass
            
        # 3. Aggregate
        subtotal += item_total_price
        
        if domain not in vendor_list:
            vendor_list[domain] = []
            
        vendor_list[domain].append({
            "part": item.get("part_type"),
            "name": item.get("product_name"),
            "price": item_total_price, # Use the calculated total price
            "link": url,
            "quantity": quantity
        })
        
    # 4. Totals
    shipping_est = subtotal * 0.05 # 5% buffer
    tax_est = subtotal * 0.08 # 8% buffer
    total_est = subtotal + shipping_est + tax_est
    
    return {
        "currency": "USD",
        "subtotal": round(subtotal, 2),
        "estimated_shipping": round(shipping_est, 2),
        "estimated_tax": round(tax_est, 2),
        "total_estimated_cost": round(total_est, 2),
        "vendors": vendor_list
    }