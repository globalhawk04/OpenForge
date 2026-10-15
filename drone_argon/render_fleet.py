# FILE: tools/render_fleet.py
import json
import os
import http.server
import socketserver
import webbrowser

CATALOG_FILE = "drone_catalog.json"
OUTPUT_HTML = "dashboard.html"

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OpenForge Fleet Viewer</title>
    <style>
        body { margin: 0; background: #111; color: #eee; font-family: 'Segoe UI', sans-serif; display: flex; height: 100vh; overflow: hidden; }
        
        #sidebar { 
            width: 320px; 
            background: #1a1a1a; 
            padding: 20px; 
            overflow-y: auto; 
            border-right: 1px solid #333; 
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        #viewer { flex-grow: 1; position: relative; background: radial-gradient(circle at center, #1a1a1a 0%, #000 100%); }
        
        .drone-card { 
            background: #252525; 
            padding: 15px; 
            border-radius: 8px; 
            cursor: pointer; 
            transition: 0.2s; 
            border: 1px solid #333; 
            border-left: 4px solid #444;
        }
        .drone-card:hover { background: #333; border-left-color: #00ff88; transform: translateX(5px); }
        .drone-card.active { background: #333; border-color: #00ff88; border-left-color: #00ff88; }

        .drone-card h3 { margin: 0 0 5px 0; color: #fff; font-size: 14px; line-height: 1.4; }
        .drone-card .class-tag { font-size: 10px; color: #00ff88; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; display: block; }
        
        .metrics { display: flex; gap: 10px; margin-top: 10px; font-size: 11px; color: #ccc; }
        .metric { background: #111; padding: 3px 8px; border-radius: 4px; border: 1px solid #444; }

        h2 { color: #00ff88; margin-top: 0; font-size: 18px; border-bottom: 1px solid #333; padding-bottom: 10px; }
        
        #canvas-container { width: 100%; height: 100%; }
        
        #info-overlay { 
            position: absolute; 
            top: 20px; 
            right: 20px; 
            background: rgba(20, 20, 20, 0.9); 
            padding: 25px; 
            border-radius: 12px; 
            max-width: 350px; 
            backdrop-filter: blur(10px);
            border: 1px solid #444;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            transition: opacity 0.3s;
        }
        
        #overlay-title { font-size: 20px; margin-bottom: 10px; border: none; padding: 0; color: #fff; }
        #overlay-desc { font-size: 13px; line-height: 1.6; color: #bbb; margin-bottom: 15px; }
        
        .bom-list { max-height: 200px; overflow-y: auto; font-size: 12px; border-top: 1px solid #444; padding-top: 10px; }
        .bom-item { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #333; }
        .bom-item span:first-child { color: #888; }
        .bom-item span:last-child { color: #eee; text-align: right; max-width: 180px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    </style>
    <!-- Three.js CDN -->
    <script type="importmap">
      {
        "imports": {
          "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
          "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
        }
      }
    </script>
</head>
<body>

<div id="sidebar">
    <h2>OpenForge Fleet</h2>
    <div id="drone-list"></div>
</div>

<div id="viewer">
    <div id="canvas-container"></div>
    <div id="info-overlay">
        <h2 id="overlay-title">Select a Drone</h2>
        <div id="overlay-desc">Click on a card to load the digital twin.</div>
        <div id="bom-container" class="bom-list"></div>
    </div>
</div>

<script type="module">
    import * as THREE from 'three';
    import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

    // Inject Data safely
    const fleet = __FLEET_DATA__; 

    // --- THREE.JS SETUP ---
    const container = document.getElementById('canvas-container');
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x111111);
    
    // Lighting
    const ambient = new THREE.AmbientLight(0x404040, 2);
    scene.add(ambient);
    
    const sun = new THREE.DirectionalLight(0xffffff, 2);
    sun.position.set(10, 20, 10);
    sun.castShadow = true;
    scene.add(sun);

    const rimLight = new THREE.PointLight(0x00ff88, 5, 50);
    rimLight.position.set(-10, 10, -10);
    scene.add(rimLight);

    // Grid
    const grid = new THREE.GridHelper(2000, 100, 0x333333, 0x111111);
    scene.add(grid);

    const camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 1, 5000);
    camera.position.set(250, 250, 250);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.5;

    // Animation Loop
    const spinners = [];
    function animate() {
        requestAnimationFrame(animate);
        controls.update();
        spinners.forEach(mesh => mesh.rotateY(0.2));
        renderer.render(scene, camera);
    }
    animate();

    // --- DRONE BUILDER ---
    function buildDrone(sceneGraph) {
        // Clear previous
        for (let i = scene.children.length - 1; i >= 0; i--) {
            if (scene.children[i].type === "Group") scene.remove(scene.children[i]);
        }
        spinners.length = 0;

        const group = new THREE.Group();

        if (!sceneGraph || !sceneGraph.components) return;

        sceneGraph.components.forEach(comp => {
            let geometry;
            const dims = comp.dims || { length: 10, width: 10, height: 10, radius: 5 };
            const color = parseInt((comp.visuals?.primary_color_hex || '#888888').replace('#', '0x'));
            
            const material = new THREE.MeshStandardMaterial({ 
                color: color,
                roughness: 0.3,
                metalness: 0.7
            });

            // Geometry Logic matching Python logic
            if (comp.type === "FRAME_CORE") {
                geometry = new THREE.BoxGeometry(dims.length, dims.thickness || 4, dims.width);
            } 
            else if (comp.type === "FRAME_ARM") {
                geometry = new THREE.BoxGeometry(dims.length, dims.thickness || 5, dims.width);
                geometry.translate(dims.length / 2, 0, 0); // Pivot from end
            } 
            else if (comp.type === "MOTOR") {
                geometry = new THREE.CylinderGeometry(dims.radius, dims.radius, dims.height || 15, 32);
                material.color.setHex(0x333333); // Dark motors usually
            } 
            else if (comp.type === "PROPELLER") {
                geometry = new THREE.BoxGeometry(dims.radius * 2, 1, 8);
                material.color.setHex(color);
                material.transparent = true;
                material.opacity = 0.9;
            } 
            else if (comp.type === "BATTERY") {
                geometry = new THREE.BoxGeometry(dims.length, dims.height, dims.width);
                material.color.setHex(0x111111);
                material.roughness = 0.8;
            } 
            else if (comp.type === "PCB_STACK") {
                geometry = new THREE.BoxGeometry(dims.width, dims.height, dims.width); // Square stack
                material.color.setHex(0x2244aa);
            }
            else {
                geometry = new THREE.BoxGeometry(10, 10, 10);
            }

            const mesh = new THREE.Mesh(geometry, material);
            
            // Apply Transforms
            if (comp.pos) mesh.position.set(comp.pos[0], comp.pos[1], comp.pos[2]);
            if (comp.rot) mesh.rotation.set(comp.rot[0], comp.rot[1], comp.rot[2]);

            if (comp.is_dynamic) spinners.push(mesh);
            
            group.add(mesh);
        });

        scene.add(group);
    }

    // --- UI POPULATION ---
    const list = document.getElementById('drone-list');
    
    // Check if fleet exists
    if (!fleet || fleet.length === 0) {
        list.innerHTML = "<p style='color: #ff5555'>No drones found in catalog.</p>";
    } else {
        fleet.forEach((drone, idx) => {
            const card = document.createElement('div');
            card.className = 'drone-card';
            
            // Handle Schema V2 (Design Fleet) vs V1
            const name = drone.anchor_frame || drone.marketing?.model_name || "Unknown Drone";
            const type = drone.class || drone.marketing?.category || "Custom";
            const twr = drone.performance?.twr || drone.performance_metrics?.twr || 0;
            const time = drone.performance?.flight_time || drone.performance_metrics?.flight_time_minutes || 0;

            card.innerHTML = `
                <span class="class-tag">${type}</span>
                <h3>${name}</h3>
                <div class="metrics">
                    <span class="metric">TWR: ${Number(twr).toFixed(1)}</span>
                    <span class="metric">${Number(time).toFixed(1)} min</span>
                </div>
            `;

            card.onclick = () => {
                // Update Overlay
                document.getElementById('overlay-title').innerText = name;
                document.getElementById('overlay-desc').innerText = drone.ai_reasoning || drone.marketing?.tagline || "No description.";
                
                // Update BOM List
                const bomContainer = document.getElementById('bom-container');
                bomContainer.innerHTML = drone.bom.map(p => `
                    <div class="bom-item">
                        <span>${p.part_type || p.category}</span>
                        <span>${p.product_name || p.model_name}</span>
                    </div>
                `).join('');

                // Render 3D
                // Handle nesting of scene_graph
                const sg = drone.technical_data?.scene_graph || drone.technical_data; 
                buildDrone(sg);

                // Highlight active
                document.querySelectorAll('.drone-card').forEach(c => c.classList.remove('active'));
                card.classList.add('active');
            };

            list.appendChild(card);
            
            // Auto-click first one
            if (idx === 0) card.click();
        });
    }

    // Window Resize
    window.addEventListener('resize', () => {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });

</script>
</body>
</html>
"""

def generate_dashboard():
    if not os.path.exists(CATALOG_FILE):
        print("❌ No catalog found. Run design_fleet.py first.")
        return

    with open(CATALOG_FILE, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print("❌ Catalog JSON is corrupt.")
            return

    # Inject JSON data
    json_str = json.dumps(data)
    html_content = TEMPLATE.replace("__FLEET_DATA__", json_str)

    with open(OUTPUT_HTML, "w") as f:
        f.write(html_content)

    print(f"✅ Dashboard generated: {OUTPUT_HTML}")
    
    # Serve
    PORT = 8000
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"🌍 Serving at http://localhost:{PORT}")
        webbrowser.open(f"http://localhost:{PORT}/{OUTPUT_HTML}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped.")

if __name__ == "__main__":
    generate_dashboard()