# FILE: tools/fly_drone.py
import json
import os
import http.server
import socketserver
import webbrowser
import math

CATALOG_FILE = "drone_catalog.json"
OUTPUT_HTML = "dashboard.html"

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OpenForge Ranch Sim</title>
    <style>
        body { margin: 0; overflow: hidden; background: #000; font-family: 'Segoe UI', monospace; user-select: none; }
        
        #hud-overlay {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none;
            display: flex; flex-direction: column; justify-content: space-between; padding: 20px; box-sizing: border-box;
        }
        
        /* START SCREEN */
        #start-screen {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center;
            flex-direction: column; z-index: 999; cursor: pointer; backdrop-filter: blur(8px); pointer-events: auto;
        }
        #start-screen h1 { font-size: 60px; color: #00ffcc; text-transform: uppercase; letter-spacing: 5px; margin-bottom: 10px; text-shadow: 0 0 20px #00ffcc; }
        #start-screen p { color: #fff; font-size: 20px; animation: pulse 1.5s infinite; }
        
        @keyframes pulse { 0% { opacity: 0.5; } 50% { opacity: 1; } 100% { opacity: 0.5; } }

        /* HUD PANELS */
        .panel { 
            background: rgba(10, 15, 20, 0.85); 
            border: 1px solid #334455; 
            padding: 15px; 
            border-radius: 8px; 
            color: #eee;
            min-width: 280px;
            pointer-events: auto;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
        }

        .stat-row { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px; color: #aaa; border-bottom: 1px solid #223344; padding-bottom: 2px;}
        .stat-val { color: #fff; font-weight: bold; font-family: 'Consolas', monospace; }

        #drone-select { 
            background: #111; color: #00ffcc; border: 1px solid #334455; padding: 8px; width: 100%; margin-bottom: 15px; outline: none; font-family: monospace; font-size: 14px;
        }

        #controls-hint { text-align: right; font-size: 12px; color: #fff; text-shadow: 1px 1px 2px black; line-height: 1.8; font-weight: bold; background: rgba(0,0,0,0.5); padding: 10px; border-radius: 8px;}
        
        #top-bar { display: flex; justify-content: space-between; align-items: flex-start; }
        #bottom-bar { display: flex; justify-content: space-between; align-items: flex-end; }
        
        .gauge-container { display: flex; gap: 30px; background: rgba(0,0,0,0.6); padding: 15px 40px; border-radius: 30px; border: 1px solid #444; backdrop-filter: blur(5px); }
        .gauge { text-align: center; }
        .gauge-val { font-size: 28px; font-weight: bold; color: #fff; text-shadow: 0 0 10px rgba(0, 255, 200, 0.5); font-family: 'Consolas', monospace; }
        .gauge-label { font-size: 10px; color: #00ffcc; text-transform: uppercase; margin-top: 2px; letter-spacing: 1px; }

        #crosshair {
            position: absolute; top: 50%; left: 50%; width: 40px; height: 40px;
            border: 2px dashed rgba(255,255,255,0.4); border-radius: 50%;
            transform: translate(-50%, -50%); pointer-events: none;
        }
        
        #crosshair::after {
            content: ''; position: absolute; top: 50%; left: 50%; width: 4px; height: 4px; background: #00ffcc; transform: translate(-50%, -50%); border-radius: 50%;
        }
        
        #error-msg {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            color: #ff5555; font-size: 24px; background: rgba(0,0,0,0.9); padding: 40px; display: none; z-index: 1000; border: 2px solid red;
        }
    </style>

    <script type="importmap">
      {
        "imports": {
          "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
          "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/",
          "cannon-es": "https://unpkg.com/cannon-es@0.20.0/dist/cannon-es.js"
        }
      }
    </script>
</head>
<body>

<div id="error-msg"></div>

<div id="start-screen" onclick="startGame()">
    <h1>OpenForge Sim</h1>
    <p>[ CLICK TO INITIALIZE FLIGHT SYSTEMS ]</p>
</div>

<div id="hud-overlay">
    <div id="top-bar">
        <div class="panel">
            <h3 style="margin:0 0 10px 0; color:#00ffcc; border-bottom: 2px solid #00ffcc; padding-bottom: 5px;">FLIGHT COMPUTER</h3>
            <select id="drone-select"></select>
            <div id="drone-specs"></div>
        </div>
        <div id="controls-hint">
            HOLD <b>SHIFT</b> TO FLY UP<br>
            <b>W / S</b> - PITCH FWD/BACK<br>
            <b>A / D</b> - ROLL LEFT/RIGHT<br>
            <b>Q / E</b> - YAW ROTATION<br>
            <b>V</b> - TOGGLE CAMERA<br>
            <b>R</b> - RESPAWN
        </div>
    </div>

    <div id="crosshair"></div>

    <div id="bottom-bar">
        <div class="panel">
            <div class="stat-row"><span>LOCATION:</span><span class="stat-val" style="color:#87CEEB">TEXAS RANCH</span></div>
            <div class="stat-row"><span>PHYSICS:</span><span class="stat-val" style="color:#0f0">ACTIVE (CANNON.JS)</span></div>
        </div>
        
        <div class="gauge-container">
            <div class="gauge">
                <div class="gauge-val" id="hud-alt">0.0</div>
                <div class="gauge-label">Alt (m)</div>
            </div>
            <div class="gauge">
                <div class="gauge-val" id="hud-spd">0</div>
                <div class="gauge-label">km/h</div>
            </div>
            <div class="gauge">
                <div class="gauge-val" id="hud-thr" style="color: #ffaa00;">0%</div>
                <div class="gauge-label">Throttle</div>
            </div>
        </div>
    </div>
</div>

<script type="module">
    import * as THREE from 'three';
    import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
    import * as CANNON from 'cannon-es';

    const fleet = __FLEET_DATA__; 

    // --- 1. PROCEDURAL ASSETS ---
    
    function createCarbonMat() {
        const c = document.createElement('canvas');
        c.width = c.height = 512;
        const ctx = c.getContext('2d');
        
        // Base
        ctx.fillStyle = '#151515'; 
        ctx.fillRect(0,0,512,512);
        
        // Weave
        ctx.fillStyle = '#2a2a2a';
        for(let i=0; i<512; i+=16) {
            ((i/16)%2===0) ? ctx.fillRect(i,0,16,512) : ctx.fillRect(0,i,512,16);
        }
        
        const tex = new THREE.CanvasTexture(c);
        tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
        tex.repeat.set(2,2);
        
        return new THREE.MeshStandardMaterial({
            map: tex, 
            color: 0xffffff, 
            roughness: 0.3, 
            metalness: 0.4
        });
    }
    const MAT_CARBON = createCarbonMat();

    function getMaterial(visuals, type) {
        const c = parseInt((visuals?.primary_color_hex || '#888').replace('#','0x'));
        
        if (type === 'PROPELLER') {
            return new THREE.MeshPhysicalMaterial({
                color: c, transmission: 0.6, opacity: 0.8, transparent: true,
                roughness: 0.2, metalness: 0.1, side: THREE.DoubleSide
            });
        }
        if (visuals?.material_type === 'CARBON_FIBER' || type.includes('FRAME')) {
            return MAT_CARBON;
        }
        if (type === 'MOTOR') {
            return new THREE.MeshStandardMaterial({
                color: 0x222222, roughness: 0.2, metalness: 0.8
            });
        }
        // Battery
        if (type === 'BATTERY') {
             return new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.8 });
        }
        return new THREE.MeshStandardMaterial({ color: c, roughness: 0.5 });
    }

    // --- 2. ENVIRONMENT GENERATION ---
    function createCow(x, z, scene, world) {
        const cowGroup = new THREE.Group();
        
        const bodyMat = new THREE.MeshStandardMaterial({color: 0xffffff}); 
        const spotMat = new THREE.MeshStandardMaterial({color: 0x222222}); 
        
        // Main Body
        const body = new THREE.Mesh(new THREE.BoxGeometry(1.5, 1, 2.5), bodyMat);
        body.position.y = 1.2;
        cowGroup.add(body);
        
        // Random Spots
        const spot = new THREE.Mesh(new THREE.BoxGeometry(1.55, 0.5, 1), spotMat);
        spot.position.set(0, 1.2, 0.2);
        cowGroup.add(spot);

        // Head
        const head = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.8, 1), bodyMat);
        head.position.set(0, 2.0, 1.5);
        cowGroup.add(head);
        
        // Legs
        const legGeo = new THREE.BoxGeometry(0.3, 1.2, 0.3);
        const positions = [[-0.5, 0.6, 1], [0.5, 0.6, 1], [-0.5, 0.6, -1], [0.5, 0.6, -1]];
        positions.forEach(pos => {
            const leg = new THREE.Mesh(legGeo, spotMat);
            leg.position.set(...pos);
            cowGroup.add(leg);
        });

        cowGroup.position.set(x, 0, z);
        cowGroup.rotation.y = Math.random() * Math.PI * 2;
        cowGroup.castShadow = true;
        scene.add(cowGroup);

        // Physics
        const shape = new CANNON.Box(new CANNON.Vec3(0.75, 1, 1.25));
        const bodyP = new CANNON.Body({ mass: 0 }); // Static obstacle (Cow is immovable object)
        bodyP.addShape(shape);
        bodyP.position.set(x, 1.0, z);
        world.addBody(bodyP);
    }

    // --- 3. MAIN ENGINE ---
    let scene, camera, renderer, world, clock;
    let droneBody, droneMesh, droneProps = [];
    let controls;
    let camMode = 'chase'; 
    let input = { thrust: 0, pitch: 0, roll: 0, yaw: 0 };
    let currentDrone = null;
    let isGameActive = false;

    window.startGame = function() {
        document.getElementById('start-screen').style.display = 'none';
        isGameActive = true;
        if(droneBody) {
            droneBody.wakeUp();
            droneBody.position.set(0, 2, 0);
            droneBody.velocity.set(0,0,0);
            droneBody.quaternion.set(0,0,0,1);
        }
    };

    function init() {
        try {
            // Graphics
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x87CEEB); 
            scene.fog = new THREE.FogExp2(0x87CEEB, 0.006);

            camera = new THREE.PerspectiveCamera(60, window.innerWidth/window.innerHeight, 0.1, 5000);
            camera.position.set(0, 2, 5);

            renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.shadowMap.enabled = true;
            renderer.shadowMap.type = THREE.PCFSoftShadowMap;
            document.body.appendChild(renderer.domElement);

            // Lighting
            const hemi = new THREE.HemisphereLight(0xffffff, 0x444444, 0.7);
            scene.add(hemi);
            
            const sun = new THREE.DirectionalLight(0xffffff, 1.5);
            sun.position.set(50, 100, 50);
            sun.castShadow = true;
            sun.shadow.mapSize.width = 2048;
            sun.shadow.mapSize.height = 2048;
            scene.add(sun);

            // Physics
            world = new CANNON.World();
            world.gravity.set(0, -9.81, 0);
            
            const groundMat = new CANNON.Material();
            const droneMat = new CANNON.Material();
            const contactMat = new CANNON.ContactMaterial(groundMat, droneMat, { friction: 0.6, restitution: 0.2 });
            world.addContactMaterial(contactMat);

            // Ground Body
            const groundBody = new CANNON.Body({ mass: 0, material: groundMat });
            groundBody.addShape(new CANNON.Plane());
            groundBody.quaternion.setFromEuler(-Math.PI / 2, 0, 0);
            world.addBody(groundBody);

            buildEnvironment();
            setupUI();
            setupInput();
            clock = new THREE.Clock();
            animate();
        } catch (e) {
            document.getElementById('error-msg').style.display = 'block';
            document.getElementById('error-msg').innerText = "INIT ERROR: " + e.message;
            console.error(e);
        }
    }

    function buildEnvironment() {
        // Ground Visual
        const planeGeo = new THREE.PlaneGeometry(2000, 2000);
        const planeMat = new THREE.MeshStandardMaterial({ color: 0x2d4c1e, roughness: 1.0 });
        const plane = new THREE.Mesh(planeGeo, planeMat);
        plane.rotation.x = -Math.PI/2;
        plane.receiveShadow = true;
        scene.add(plane);

        // Cows
        for(let i=0; i<15; i++) {
            const x = (Math.random()-0.5) * 150;
            const z = (Math.random()-0.5) * 150;
            if(Math.abs(x) > 10 && Math.abs(z) > 10) createCow(x, z, scene, world);
        }

        // Trees
        for(let i=0; i<50; i++) {
            const x = (Math.random()-0.5) * 400;
            const z = (Math.random()-0.5) * 400;
            if(Math.abs(x) < 10 && Math.abs(z) < 10) continue; // Clear spawn

            const h = 8 + Math.random()*12;
            const geo = new THREE.ConeGeometry(3, h, 8);
            const mat = new THREE.MeshStandardMaterial({color: 0x113311});
            const tree = new THREE.Mesh(geo, mat);
            tree.position.set(x, h/2, z);
            tree.castShadow = true;
            scene.add(tree);

            const body = new CANNON.Body({ mass: 0 });
            body.addShape(new CANNON.Cylinder(1, 1, h, 8));
            body.position.set(x, h/2, z);
            world.addBody(body);
        }
    }

    function loadDrone(data) {
        currentDrone = data;
        const phys = data.technical_data.physics_config;
        
        document.getElementById('drone-specs').innerHTML = `
            <div class="stat-row"><span>MASS:</span><span>${phys.meta.total_weight_g}g</span></div>
            <div class="stat-row"><span>TWR:</span><span style="color:#0f0">${phys.dynamics.twr}</span></div>
        `;

        if(droneMesh) scene.remove(droneMesh);
        if(droneBody) world.removeBody(droneBody);
        droneProps = [];

        // Build Visuals
        droneMesh = new THREE.Group();
        const sg = data.technical_data.scene_graph;
        
        sg.components.forEach(c => {
            const mat = getMaterial(c.visuals, c.type);
            let geo;

            if(c.type === 'PROPELLER') {
                geo = new THREE.BoxGeometry(c.dims.radius*2/1000, 0.005, 0.02);
                const m = new THREE.Mesh(geo, mat);
                m.position.set(c.pos[0]/1000, c.pos[1]/1000, c.pos[2]/1000);
                droneProps.push(m);
                droneMesh.add(m);
                return;
            }
            else if(c.type === 'MOTOR') geo = new THREE.CylinderGeometry(c.dims.radius/1000, c.dims.radius/1000, c.dims.height/1000, 16);
            else geo = new THREE.BoxGeometry(
                (c.dims.length||20)/1000, 
                (c.dims.thickness||c.dims.height||5)/1000, 
                (c.dims.width||20)/1000
            );

            if(c.type === 'FRAME_ARM') geo.translate((c.dims.length/1000)/2, 0, 0);

            const m = new THREE.Mesh(geo, mat);
            m.position.set(c.pos[0]/1000, c.pos[1]/1000, c.pos[2]/1000);
            if(c.rot) m.rotation.set(c.rot[0], c.rot[1], c.rot[2]);
            m.castShadow = true;
            droneMesh.add(m);
        });
        scene.add(droneMesh);

        // Physics Body
        const size = phys.collider_size_m;
        const shape = new CANNON.Box(new CANNON.Vec3(size[0]/2, size[1]/2, size[2]/2));
        
        droneBody = new CANNON.Body({
            mass: phys.mass_kg,
            position: new CANNON.Vec3(0, 1, 0),
            linearDamping: 0.4,
            angularDamping: 0.6
        });
        droneBody.addShape(shape);
        world.addBody(droneBody);
    }

    function setupUI() {
        const sel = document.getElementById('drone-select');
        if(!fleet || fleet.length === 0) return;
        fleet.forEach((d, i) => {
            const opt = document.createElement('option');
            opt.value = i;
            opt.innerText = d.anchor_frame || `Drone ${i+1}`;
            sel.appendChild(opt);
        });
        sel.onchange = (e) => loadDrone(fleet[e.target.value]);
        loadDrone(fleet[0]);
    }

    function setupInput() {
        window.addEventListener('keydown', (e) => {
            if(!isGameActive) return;
            // Shift for Thrust
            if(e.code === 'ShiftLeft' || e.code === 'ShiftRight') input.thrust = 1;
            
            // WASD
            if(e.code === 'KeyW') input.pitch = 1;
            if(e.code === 'KeyS') input.pitch = -1;
            if(e.code === 'KeyA') input.roll = 1;
            if(e.code === 'KeyD') input.roll = -1;
            if(e.code === 'KeyQ') input.yaw = 1;
            if(e.code === 'KeyE') input.yaw = -1;
            
            // Arrows (Duplicate WASD)
            if(e.code === 'ArrowUp') input.pitch = 1;
            if(e.code === 'ArrowDown') input.pitch = -1;
            if(e.code === 'ArrowLeft') input.roll = 1;
            if(e.code === 'ArrowRight') input.roll = -1;

            if(e.code === 'KeyR') {
                droneBody.position.set(0, 5, 0);
                droneBody.velocity.set(0,0,0);
                droneBody.quaternion.set(0,0,0,1);
            }
            if(e.code === 'KeyV') {
                camMode = camMode === 'chase' ? 'orbit' : 'chase';
                if(camMode === 'orbit') {
                    controls = new OrbitControls(camera, renderer.domElement);
                } else {
                    if(controls) { controls.dispose(); controls = null; }
                }
            }
        });
        window.addEventListener('keyup', (e) => {
            if(e.code.includes('Shift')) input.thrust = 0;
            if(['KeyW','KeyS','ArrowUp','ArrowDown'].includes(e.code)) input.pitch = 0;
            if(['KeyA','KeyD','ArrowLeft','ArrowRight'].includes(e.code)) input.roll = 0;
            if(['KeyQ','KeyE'].includes(e.code)) input.yaw = 0;
        });
    }

    function animate() {
        requestAnimationFrame(animate);
        const dt = Math.min(clock.getDelta(), 0.1);
        world.step(1/60, dt, 3);

        if(droneBody && droneMesh) {
            // Physics
            const phys = currentDrone.technical_data.physics_config;
            const gravityComp = 9.81 * phys.mass_kg;
            
            let thrustForce = 0;
            if(input.thrust) {
                thrustForce = gravityComp * 2.0; 
            } else {
                thrustForce = gravityComp * 0.95; 
            }

            const localUp = new CANNON.Vec3(0, thrustForce, 0);
            const worldForce = droneBody.quaternion.vmult(localUp);
            droneBody.applyForce(worldForce, droneBody.position);

            // Torque
            const torqueStr = 2.0; 
            const torque = new CANNON.Vec3(input.pitch * torqueStr, input.yaw * torqueStr, -input.roll * torqueStr);
            const worldTorque = droneBody.quaternion.vmult(torque);
            droneBody.torque.vadd(worldTorque, droneBody.torque);

            // Sync
            droneMesh.position.copy(droneBody.position);
            droneMesh.quaternion.copy(droneBody.quaternion);

            // Props
            droneProps.forEach(p => p.rotation.y += (input.thrust ? 25 : 5) * dt);

            // Camera
            if(camMode === 'chase') {
                const off = new THREE.Vector3(0, 2, -6).applyQuaternion(droneMesh.quaternion);
                const target = droneMesh.position.clone().add(off);
                camera.position.lerp(target, 0.1);
                camera.lookAt(droneMesh.position);
            } else if(controls) controls.update();

            // HUD
            document.getElementById('hud-alt').innerText = Math.max(0, droneBody.position.y).toFixed(1);
            document.getElementById('hud-spd').innerText = (droneBody.velocity.length()*3.6).toFixed(0);
            document.getElementById('hud-thr').innerText = input.thrust ? "100%" : "0%";
        }
        renderer.render(scene, camera);
    }

    init();
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth/window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });
</script>
</body>
</html>
"""

def replace_nan(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj): return 0.0
        return obj
    elif isinstance(obj, dict):
        return {k: replace_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_nan(i) for i in obj]
    return obj

def generate_flight_sim():
    if not os.path.exists(CATALOG_FILE):
        print("❌ No catalog found.")
        return

    with open(CATALOG_FILE, "r") as f:
        try: 
            raw_data = json.load(f)
            data = replace_nan(raw_data)
        except Exception as e:
            print(f"❌ JSON Load Error: {e}")
            return

    json_str = json.dumps(data)
    html_content = TEMPLATE.replace("__FLEET_DATA__", json_str)

    with open(OUTPUT_HTML, "w") as f:
        f.write(html_content)

    print(f"✅ Simulator generated: {OUTPUT_HTML}")
    
    socketserver.TCPServer.allow_reuse_address = True
    PORT = 8000
    Handler = http.server.SimpleHTTPRequestHandler
    
    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            print(f"🎮 Simulator Active: http://localhost:{PORT}/{OUTPUT_HTML}")
            webbrowser.open(f"http://localhost:{PORT}/{OUTPUT_HTML}")
            httpd.serve_forever()
    except OSError:
        print(f"❌ Port {PORT} busy. Run: fuser -k {PORT}/tcp")

if __name__ == "__main__":
    generate_flight_sim()