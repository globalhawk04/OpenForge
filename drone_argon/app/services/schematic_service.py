# FILE: app/services/schematic_service.py
import os
try:
    import graphviz
except ImportError:
    graphviz = None

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "static", "generated")

def generate_wiring_diagram(project_id: str, bom: list) -> str:
    """
    Generates a wiring schematic PNG based on the specific components sourced.
    Returns the path to the generated image.
    """
    if not graphviz:
        print("⚠️ Graphviz not installed. Skipping schematic.")
        return None

    # 1. Initialize Diagram
    dot = graphviz.Digraph(comment='Drone Wiring Diagram')
    dot.attr(rankdir='LR', bgcolor='#1a202c', fontcolor='white')
    
    # --- STYLE DEFINITIONS ---
    # Base Node Style
    node_attr = {
        'shape': 'box', 
        'style': 'filled', 
        'color': '#4a5568', 
        'fontcolor': 'white', 
        'fontname': 'Helvetica'
    }
    
    # Specific Styles to prevent Argument Collision
    bat_attr = node_attr.copy()
    bat_attr.update({'fillcolor': '#d69e2e', 'fontcolor': 'black'})
    
    motor_attr = node_attr.copy()
    motor_attr.update({'shape': 'circle', 'width': '1', 'fixedsize': 'true'})

    # Edge Styles
    edge_attr = {
        'color': '#cbd5e0', 
        'fontcolor': '#a0aec0', 
        'fontsize': '10'
    }
    
    pwr_edge_attr = edge_attr.copy()
    pwr_edge_attr.update({'color': '#ecc94b', 'penwidth': '2'})

    ribbon_edge_attr = edge_attr.copy()
    ribbon_edge_attr.update({'penwidth': '2'})

    rx_edge_attr = edge_attr.copy()
    rx_edge_attr.update({'color': '#68d391'}) # Green

    vtx_edge_attr = edge_attr.copy()
    vtx_edge_attr.update({'color': '#fc8181'}) # Red

    # 2. Central Core (Always present)
    dot.node('FC', 'Flight Controller\n(UARTs / 5V / GND)', **node_attr, fillcolor='#2b6cb0') # Blue
    dot.node('ESC', 'ESC / Power Board\n(Battery Input)', **node_attr, fillcolor='#2b6cb0')
    dot.node('BAT', 'Battery\n(XT60)', **bat_attr) 
    
    # Core Power Links
    dot.edge('BAT', 'ESC', label='V_BAT (12-25V)', **pwr_edge_attr)
    dot.edge('ESC', 'FC', label='Ribbon Cable\n(V_BAT + Current + M1-M4)', **ribbon_edge_attr)

    # 3. Scan BOM for Peripherals
    bom_text = str(bom).lower()
    
    # --- Receiver (ELRS/Crossfire) ---
    if 'receiver' in bom_text or 'elrs' in bom_text:
        dot.node('RX', 'Receiver\n(ELRS/Crossfire)', **node_attr)
        dot.edge('RX', 'FC', label='5V / GND', **edge_attr)
        dot.edge('RX', 'FC', label='TX -> RX1', **rx_edge_attr)
        dot.edge('RX', 'FC', label='RX -> TX1', **rx_edge_attr)

    # --- Video System (Analog vs Digital) ---
    if 'dji' in bom_text or 'o3' in bom_text or 'vista' in bom_text:
        dot.node('VTX', 'Digital VTX\n(DJI O3 / Vista)', **node_attr, fillcolor='#e53e3e') # Red
        dot.edge('VTX', 'FC', label='9V / GND', **vtx_edge_attr)
        dot.edge('VTX', 'FC', label='RX -> TX2 (MSP)', **edge_attr)
        dot.edge('VTX', 'FC', label='TX -> RX2 (MSP)', **edge_attr)
    elif 'analog' in bom_text:
        dot.node('CAM', 'Analog Camera', **node_attr)
        dot.node('VTX', 'Analog VTX', **node_attr)
        dot.edge('CAM', 'FC', label='Video In', **edge_attr)
        dot.edge('FC', 'VTX', label='Video Out (OSD)', **edge_attr)
        dot.edge('VTX', 'FC', label='SmartAudio (TX3)', **edge_attr)

    # --- GPS ---
    if 'gps' in bom_text:
        dot.node('GPS', 'GPS Module\n(M10)', **node_attr)
        dot.edge('GPS', 'FC', label='5V / GND', **edge_attr)
        dot.edge('GPS', 'FC', label='TX -> RX4', **edge_attr)
        dot.edge('GPS', 'FC', label='RX -> TX4', **edge_attr)

    # --- Motors ---
    # Using the specific motor_attr to avoid 'shape' collision
    dot.node('M1', 'Motor 1', **motor_attr)
    dot.node('M2', 'Motor 2', **motor_attr)
    dot.node('M3', 'Motor 3', **motor_attr)
    dot.node('M4', 'Motor 4', **motor_attr)
    
    dot.edge('ESC', 'M1', **edge_attr)
    dot.edge('ESC', 'M2', **edge_attr)
    dot.edge('ESC', 'M3', **edge_attr)
    dot.edge('ESC', 'M4', **edge_attr)

    # 4. Render
    output_path_base = os.path.join(OUTPUT_DIR, f"{project_id}_schematic")
    try:
        # Renders to .png
        final_path = dot.render(filename=output_path_base, format='png', cleanup=True)
        print(f"⚡ Schematic Generated: {final_path}")
        return final_path
    except Exception as e:
        print(f"❌ Graphviz Error: {e}")
        return None