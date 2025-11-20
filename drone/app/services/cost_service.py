# FILE: app/services/cost_service.py
import re
from urllib.parse import urlparse

def generate_procurement_manifest(bom: list) -> dict:
    """
    Calculates total cost and groups items by vendor.
    """
    subtotal = 0.0
    vendor_list = {}
    
    for item in bom:
        price_str = str(item.get("price", ""))
        url = item.get("source_url", "")
        
        # 1. Extract Price
        price_val = 0.0
        # Look for digits like 24.99 or 1,200.00
        match = re.search(r"(\d+[\.,]\d{2})", price_str)
        if match:
            try:
                clean_price = match.group(1).replace(",", "")
                price_val = float(clean_price)
            except ValueError: pass
            
        # 2. Extract Vendor
        domain = "Unknown"
        if url:
            try:
                domain = urlparse(url).netloc.replace("www.", "")
            except: pass
            
        # 3. Aggregate
        subtotal += price_val
        
        if domain not in vendor_list:
            vendor_list[domain] = []
            
        vendor_list[domain].append({
            "part": item.get("part_type"),
            "name": item.get("product_name"),
            "price": price_val,
            "link": url
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