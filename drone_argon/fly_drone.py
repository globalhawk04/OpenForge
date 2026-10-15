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
    <title>OpenForge Sim v4.0 (Cinematic)</title>
    <style>
        body { margin: 0; overflow: hidden; background: #000; font-family: 'Segoe UI', monospace; user-select: none; }
        
        #hud-overlay {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none;
            display: flex; flex-direction: column; justify-content: space-between; padding: 20px; box-sizing: border-box;
            z-index: 10;
        }
        
        #start-screen {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background: radial-gradient(circle, rgba(10,20,30,0.9) 0%, #000 100%); 
            display: flex; align-items: center; justify-content: center;
            flex-direction: column; z-index: 999; cursor: pointer; backdrop-filter: blur(10px); pointer-events: auto;
        }
        #start-screen h1 { 
            font-size: 80px; color: #fff; letter-spacing: 5px; margin: 0; 
            text-shadow: 0 0 30px rgba(0,255,136,0.5); font-weight: 300;
        }
        .start-btn {
            margin-top: 40px; padding: 15px 60px; border: 1px solid rgba(255,255,255,0.2); 
            color: #fff; background: rgba(0,255,136,0.1);
            font-size: 16px; font-family: inherit; cursor: pointer; transition: 0.3s; letter-spacing: 3px;
        }
        .start-btn:hover { background: #00ff88; color: #000; box-shadow: 0 0 30px rgba(0,255,136,0.4); }

        .panel { 
            background: rgba(0, 0, 0, 0.6); border-left: 2px solid #00ff88;
            padding: 15px; border-radius: 0px; color: #eee; min-width: 280px; backdrop-filter: blur(4px);
        }
        .stat-row { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; color: #888; }
        .stat-val { color: #fff; font-weight: 600; }
        
        .gauge-container { display: flex; gap: 30px; background: rgba(0,0,0,0.5); padding: 15px 40px; border-radius: 4px; backdrop-filter: blur(4px); }
        .gauge-val { font-size: 32px; font-weight: 300; color: #fff; text-align: center; font-variant-numeric: tabular-nums; }
        .gauge-label { font-size: 10px; color: #666; text-align: center; display: block; letter-spacing: 1px; margin-top: 5px; }

        #controls-hint { 
            text-align: right; font-size: 11px; color: #666; padding: 15px; letter-spacing: 1px;
        }
        #top-bar, #bottom-bar { display: flex; justify-content: space-between; align-items: flex-start; }
        #bottom-bar { align-items: flex-end; }
        
        #fpv-overlay {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none;
            display: none;
            background: radial-gradient(circle, transparent 40%, rgba(0,0,0,0.8) 100%);
            box-shadow: inset 0 0 100px rgba(0,0,0,0.9);
        }
        /* Artificial Horizon Line */
        #fpv-horizon {
            position: absolute; top: 50%; left: 0; width: 100%; height: 1px; background: rgba(0,255,136,0.3);
        }
        #fpv-crosshair {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            width: 10px; height: 10px; border: 2px solid rgba(0, 255, 136, 0.8); border-radius: 50%;
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

<div id="start-screen">
    <h1 style="color:white; font-weight:bold;">OPEN<span style="color:#00ff88">FORGE</span></h1>
    <p style="color:#666; margin-top:10px;">CINEMATIC RANCH SIMULATOR v4.0</p>
    <button class="start-btn" onclick="startGame()">INIT_ENGINE</button>
</div>

<div id="fpv-overlay">
    <div id="fpv-horizon"></div>
    <div id="fpv-crosshair"></div>
</div>

<div id="hud-overlay">
    <div id="top-bar">
        <div class="panel">
            <h3 style="margin:0 0 10px 0; color:#fff; font-size:14px; letter-spacing:2px;">TELEMETRY</h3>
            <div id="drone-specs"></div>
        </div>
        <div id="controls-hint">
            SHIFT [THRUST] &nbsp; WASD [VECTOR] &nbsp; Q/E [YAW] &nbsp; V [VIEW]
        </div>
    </div>
    <div id="bottom-bar">
        <div class="panel">
            <div class="stat-row"><span>RENDER</span><span class="stat-val" style="color:#00ff88">HDR + BLOOM</span></div>
            <div class="stat-row"><span>BIOME</span><span class="stat-val">TEXAS_01</span></div>
            <div class="stat-row"><span>CAM</span><span class="stat-val" id="cam-mode-disp" style="color:#fff">CHASE</span></div>
        </div>
        <div class="gauge-container">
            <div><div class="gauge-val" id="hud-alt">0</div><span class="gauge-label">ALT</span></div>
            <div><div class="gauge-val" id="hud-spd">0</div><span class="gauge-label">KPH</span></div>
            <div><div class="gauge-val" id="hud-thr" style="color:#00ff88">0%</div><span class="gauge-label">THR</span></div>
        </div>
    </div>
</div>

<script type="module">
    import * as THREE from 'three';
    import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
    import { Sky } from 'three/addons/objects/Sky.js';
    import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
    import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
    import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
    import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
    import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
    import * as CANNON from 'cannon-es';

    const fleet = __FLEET_DATA__; 

    // --- TEXTURES ---
    function createNoiseTexture(color1, color2, scale=1) {
        const c = document.createElement('canvas');
        c.width = 1024; c.height = 1024; // High Res
        const ctx = c.getContext('2d');
        const grd = ctx.createLinearGradient(0,0,1024,1024);
        grd.addColorStop(0, color1);
        grd.addColorStop(1, color2);
        ctx.fillStyle = grd;
        ctx.fillRect(0,0,1024,1024);
        
        // Detailed Noise
        for(let i=0; i<30000; i++) {
            const v = Math.random();
            ctx.fillStyle = v > 0.5 ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.05)';
            const r = Math.random() * 2 * scale;
            ctx.beginPath();
            ctx.arc(Math.random()*1024, Math.random()*1024, r, 0, 6);
            ctx.fill();
        }
        const tex = new THREE.CanvasTexture(c);
        tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
        return tex;
    }
    
    // More Realistic Palettes
    const TEX_GRASS = createNoiseTexture('#1a2615', '#24381e'); // Darker, more contrast
    const TEX_DIRT = createNoiseTexture('#3e3228', '#2a2119');
    const TEX_BARK = createNoiseTexture('#1b110e', '#0f0907', 2);

    // --- ENGINE ---
    let scene, camera, renderer, composer, world, clock;
    let droneBody, droneMesh, droneProps = [];
    let sunLight;
    let controls;
    let camMode = 'chase'; 
    let input = { thrust: 0, pitch: 0, roll: 0, yaw: 0 };
    let currentDrone = null;
    let isGameActive = false;
    let currentThrottle = 0.0;
    const CEILING_HEIGHT = 200.0;
    const PENDULUM_OFFSET = 0.2; 

    window.startGame = function() {
        document.getElementById('start-screen').style.display = 'none';
        isGameActive = true;
        if(droneBody) {
            droneBody.wakeUp();
            droneBody.position.set(0, 1.0, 0);
            droneBody.velocity.set(0,0,0);
            droneBody.quaternion.set(0,0,0,1);
        }
    };

    function init() {
        scene = new THREE.Scene();
        // Atmospheric Fog
        scene.fog = new THREE.FogExp2(0x8baab5, 0.0015);

        renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance" });
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.toneMapping = THREE.ReinhardToneMapping; // Cinematic Tone Mapping
        document.body.appendChild(renderer.domElement);

        camera = new THREE.PerspectiveCamera(65, window.innerWidth/window.innerHeight, 0.1, 10000);
        
        // --- POST PROCESSING PIPELINE ---
        composer = new EffectComposer(renderer);
        
        const renderPass = new RenderPass(scene, camera);
        composer.addPass(renderPass);

        // BLOOM (Glow effect for Sun/LEDs)
        const bloomPass = new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 1.5, 0.4, 0.85);
        bloomPass.threshold = 0.8; // Only very bright things glow
        bloomPass.strength = 0.4; // Glow intensity
        bloomPass.radius = 0.5;
        composer.addPass(bloomPass);

        const outputPass = new OutputPass();
        composer.addPass(outputPass);

        // --- LIGHTING ---
        // HDRI-like Fill
        const pmrem = new THREE.PMREMGenerator(renderer);
        scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
        
        // Sun
        sunLight = new THREE.DirectionalLight(0xfff5e0, 4.0); // Brighter sun
        sunLight.position.set(100, 300, 100);
        sunLight.castShadow = true;
        sunLight.shadow.mapSize.width = 4096;
        sunLight.shadow.mapSize.height = 4096;
        sunLight.shadow.camera.near = 0.5;
        sunLight.shadow.camera.far = 1000;
        const d = 400;
        sunLight.shadow.camera.left = -d; sunLight.shadow.camera.right = d;
        sunLight.shadow.camera.top = d; sunLight.shadow.camera.bottom = -d;
        sunLight.shadow.bias = -0.0001;
        scene.add(sunLight);

        // Procedural Sky
        const sky = new Sky();
        sky.scale.setScalar(10000);
        const sunPos = new THREE.Vector3().copy(sunLight.position).normalize();
        sky.material.uniforms['sunPosition'].value.copy(sunPos);
        sky.material.uniforms['rayleigh'].value = 1.5;
        sky.material.uniforms['turbidity'].value = 5;
        sky.material.uniforms['mieCoefficient'].value = 0.005;
        scene.add(sky);

        // Physics
        world = new CANNON.World();
        world.gravity.set(0, -9.81, 0);
        world.broadphase = new CANNON.SAPBroadphase(world);
        const defMat = new CANNON.Material();
        world.addContactMaterial(new CANNON.ContactMaterial(defMat, defMat, {friction:0.8, restitution:0}));

        const groundBody = new CANNON.Body({ mass: 0, material: defMat });
        groundBody.addShape(new CANNON.Plane());
        groundBody.quaternion.setFromEuler(-Math.PI/2, 0, 0);
        world.addBody(groundBody);

        buildRanch();
        setupInput();
        if(fleet && fleet.length > 0) loadDrone(fleet[0]);
        clock = new THREE.Clock();
        animate();
    }

    // --- PROCEDURAL GENERATION ---
    function getHeightAt(x, z) {
        // Multi-octave noise approximation
        const base = (Math.sin(x/200) * Math.cos(z/200) * 15);
        const detail = (Math.sin(x/30) * Math.cos(z/50) * 2);
        return base + detail;
    }

    function buildRanch() {
        // High-Poly Terrain
        const geo = new THREE.PlaneGeometry(4000, 4000, 256, 256);
        const pos = geo.attributes.position;
        for (let i = 0; i < pos.count; i++) pos.setZ(i, getHeightAt(pos.getX(i), pos.getY(i)));
        geo.computeVertexNormals();
        
        const mat = new THREE.MeshStandardMaterial({ 
            map: TEX_GRASS, roughness: 0.9, metalness: 0.0,
            color: 0x446633 
        });
        mat.map.repeat.set(128, 128);
        
        const terrain = new THREE.Mesh(geo, mat);
        terrain.rotation.x = -Math.PI/2;
        terrain.receiveShadow = true;
        scene.add(terrain);

        // Trees & Brush
        for (let i = 0; i < 50; i++) createOakTree();
        for (let i = 0; i < 150; i++) createCedarBrush();
        createFenceLine(-200, -200, 400, 'x'); 
        createFenceLine(-200, 200, 400, 'x'); 
        createFenceLine(-200, -200, 400, 'z');

        // Herds
        const herds = [{x:50, z:50}, {x:-150, z:100}, {x:100, z:-150}, {x:-200, z:-50}, {x:0, z:250}];
        herds.forEach(herd => {
            for(let i=0; i<20; i++) createCow(herd.x + (Math.random()-0.5)*70, herd.z + (Math.random()-0.5)*70);
        });
    }

    function createOakTree() {
        const x = (Math.random()-0.5) * 1500;
        const z = (Math.random()-0.5) * 1500;
        if (Math.abs(x) < 40 && Math.abs(z) < 40) return; 
        const y = getHeightAt(x, z);

        const group = new THREE.Group();
        // Detailed Trunk
        const trunkGeo = new THREE.CylinderGeometry(1.2, 1.8, 6, 9);
        const trunkMat = new THREE.MeshStandardMaterial({map: TEX_BARK, roughness: 1, color: 0x5c4033});
        const trunk = new THREE.Mesh(trunkGeo, trunkMat);
        trunk.position.y = 3; trunk.castShadow = true; group.add(trunk);

        // Canopy (Icosahedrons for better low-poly shading)
        const leafMat = new THREE.MeshStandardMaterial({color: 0x224422, roughness: 0.8});
        for(let j=0; j<10; j++) {
            const size = 3 + Math.random()*3;
            const leaf = new THREE.Mesh(new THREE.IcosahedronGeometry(size, 0), leafMat);
            leaf.position.set((Math.random()-0.5)*9, 6 + Math.random()*5, (Math.random()-0.5)*9);
            leaf.castShadow = true; group.add(leaf);
        }
        group.position.set(x, y, z);
        group.scale.setScalar(1.2 + Math.random()*0.6);
        scene.add(group);
        
        const body = new CANNON.Body({ mass: 0 });
        body.addShape(new CANNON.Cylinder(2, 2, 10, 8));
        body.position.set(x, y, z);
        world.addBody(body);
    }

    function createCedarBrush() {
        const x = (Math.random()-0.5) * 1800;
        const z = (Math.random()-0.5) * 1800;
        const y = getHeightAt(x, z);
        const group = new THREE.Group();
        const mat = new THREE.MeshStandardMaterial({color: 0x334433, roughness: 1});
        for(let k=0; k<4; k++) {
            const mesh = new THREE.Mesh(new THREE.ConeGeometry(2, 6, 7), mat);
            mesh.position.set((Math.random()-0.5)*3, 3, (Math.random()-0.5)*3);
            mesh.rotation.set((Math.random()-0.5)*0.4, 0, (Math.random()-0.5)*0.4);
            mesh.castShadow = true; group.add(mesh);
        }
        group.position.set(x,y,z);
        scene.add(group);
    }

    function createFenceLine(startX, startZ, length, axis) {
        const postMat = new THREE.MeshStandardMaterial({color: 0x6d4c41});
        const wireMat = new THREE.MeshStandardMaterial({color: 0xaaaaaa, metalness: 0.5, roughness: 0.2});
        for(let i=0; i<=length; i+=8) { 
            const x = axis === 'x' ? startX + i : startX;
            const z = axis === 'z' ? startZ + i : startZ;
            const y = getHeightAt(x, z);
            const post = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 2.5, 5), postMat);
            post.position.set(x, y+1.25, z); post.castShadow = true; scene.add(post);
            if(i < length) {
                const nX = axis === 'x' ? startX + i + 8 : startX;
                const nZ = axis === 'z' ? startZ + i + 8 : startZ;
                const nY = getHeightAt(nX, nZ);
                for(let h=0; h<3; h++) { // 3 wires
                    const wire = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 1), wireMat);
                    wire.scale.y = 8;
                    wire.position.set((x+nX)/2, ((y+0.8+h*0.5)+(nY+0.8+h*0.5))/2, (z+nZ)/2);
                    wire.rotation.z = axis === 'x' ? Math.PI/2 + Math.atan2(nY-y, 8) : 0;
                    wire.rotation.x = axis === 'z' ? Math.PI/2 + Math.atan2(nY-y, 8) : 0;
                    scene.add(wire);
                }
            }
        }
    }

    function createCow(x, z) {
        const y = getHeightAt(x, z) + 1.2;
        const isAngus = Math.random() > 0.3;
        const color = isAngus ? 0x1a1a1a : 0x8B4513; // Darker Angus
        const mat = new THREE.MeshStandardMaterial({color: color, roughness: 0.6});
        const group = new THREE.Group();
        
        const body = new THREE.Mesh(new THREE.BoxGeometry(1.0, 1.2, 2.2), mat);
        body.castShadow = true; group.add(body);
        
        const head = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.7, 0.9), mat);
        if(Math.random() > 0.6) head.position.set(0, 0.5, 1.4); 
        else { head.position.set(0, -0.4, 1.4); head.rotation.x = 0.5; }
        head.castShadow = true; group.add(head);

        if(!isAngus) {
            const face = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.72, 0.1), new THREE.MeshStandardMaterial({color:0xffffff}));
            face.position.copy(head.position); face.position.z += 0.41; face.rotation.copy(head.rotation);
            group.add(face);
        }
        group.position.set(x, y, z);
        group.rotation.y = Math.random() * Math.PI * 2;
        scene.add(group);

        const pBody = new CANNON.Body({mass: 300});
        pBody.addShape(new CANNON.Box(new CANNON.Vec3(0.5, 0.6, 1.1)));
        pBody.position.set(x, y, z);
        world.addBody(pBody);
    }

    // --- DRONE LOGIC ---
    function loadDrone(data) {
        currentDrone = data;
        const phys = data.technical_data.physics_config;
        document.getElementById('drone-specs').innerHTML = `<div class="stat-row"><span>MASS</span><span class="stat-val">${phys.meta.total_weight_g}g</span></div>`;

        if(droneMesh) scene.remove(droneMesh);
        if(droneBody) world.removeBody(droneBody);
        droneProps = [];

        droneMesh = new THREE.Group();
        const sg = data.technical_data.scene_graph;
        sg.components.forEach(c => {
            const hex = c.visuals?.primary_color_hex || '#888';
            let mat;
            // PBR Materials
            if(c.type === 'PROPELLER') mat = new THREE.MeshPhysicalMaterial({color:hex, transmission:0.95, opacity:1, roughness:0.2});
            else mat = new THREE.MeshStandardMaterial({color:hex, roughness:0.3, metalness:0.4});

            let geo;
            if(c.type === 'PROPELLER') geo = new THREE.BoxGeometry(c.dims.radius*2/1000, 0.005, 0.02);
            else if(c.type === 'MOTOR') geo = new THREE.CylinderGeometry(c.dims.radius/1000, c.dims.radius/1000, c.dims.height/1000, 32);
            else geo = new THREE.BoxGeometry((c.dims.length||20)/1000, (c.dims.thickness||5)/1000, (c.dims.width||20)/1000);
            
            if(c.type === 'FRAME_ARM') geo.translate((c.dims.length/1000)/2, 0, 0);
            const m = new THREE.Mesh(geo, mat);
            m.position.set(c.pos[0]/1000, c.pos[1]/1000, c.pos[2]/1000);
            if(c.rot) m.rotation.set(c.rot[0], c.rot[1], c.rot[2]);
            m.castShadow = true; droneMesh.add(m);
            if(c.type === 'PROPELLER') droneProps.push(m);
        });
        
        // Add Emissive "Status Light" to Drone
        const led = new THREE.PointLight(0x00ff88, 2, 5);
        led.position.set(0, 0.05, -0.05);
        droneMesh.add(led);
        
        scene.add(droneMesh);

        droneBody = new CANNON.Body({
            mass: phys.mass_kg,
            position: new CANNON.Vec3(0, 1.0, 0),
            linearDamping: 0.95, 
            angularDamping: 0.99
        });
        droneBody.angularFactor = new CANNON.Vec3(0, 1, 0);
        const shape = new CANNON.Box(new CANNON.Vec3(phys.collider_size_m[0]/2, 0.05, phys.collider_size_m[2]/2));
        droneBody.addShape(shape, new CANNON.Vec3(0, PENDULUM_OFFSET, 0));
        world.addBody(droneBody);
    }

    function setupInput() {
        window.addEventListener('keydown', (e) => {
            if(!isGameActive) return;
            if(e.code === 'ShiftLeft') input.thrust = 1;
            if(e.code === 'KeyW') input.pitch = 1;
            if(e.code === 'KeyS') input.pitch = -1;
            if(e.code === 'KeyA') input.roll = 1;
            if(e.code === 'KeyD') input.roll = -1;
            if(e.code === 'KeyQ') input.yaw = 1;
            if(e.code === 'KeyE') input.yaw = -1;
            if(e.code === 'KeyV') {
                if(camMode === 'chase') { camMode = 'fpv'; document.getElementById('fpv-overlay').style.display = 'block'; }
                else if(camMode === 'fpv') { camMode = 'orbit'; document.getElementById('fpv-overlay').style.display = 'none'; controls = new OrbitControls(camera, renderer.domElement); }
                else { camMode = 'chase'; if(controls) { controls.dispose(); controls = null; } }
                document.getElementById('cam-mode-disp').innerText = camMode.toUpperCase();
            }
            if(e.code === 'KeyR') {
                droneBody.position.set(0, 1, 0); droneBody.velocity.set(0,0,0); currentThrottle = 0;
            }
        });
        window.addEventListener('keyup', (e) => {
            if(e.code === 'ShiftLeft') input.thrust = 0;
            if(['KeyW','KeyS'].includes(e.code)) input.pitch = 0;
            if(['KeyA','KeyD'].includes(e.code)) input.roll = 0;
            if(['KeyQ','KeyE'].includes(e.code)) input.yaw = 0;
        });
    }

    function animate() {
        requestAnimationFrame(animate);
        const dt = Math.min(clock.getDelta(), 0.1);
        
        if (isGameActive && droneBody) {
            world.step(1/60, dt, 3);
            const phys = currentDrone.technical_data.physics_config;
            
            const targetThrust = input.thrust ? 1.0 : 0.0;
            currentThrottle += (targetThrust - currentThrottle) * 0.05;
            const thrustForce = 9.81 * phys.mass_kg * 1.8 * currentThrottle;

            const moveSpeed = 15.0 * phys.mass_kg; 
            const forward = new CANNON.Vec3(0,0,-1);
            droneBody.quaternion.vmult(forward, forward); forward.y = 0; forward.normalize();
            const right = new CANNON.Vec3(1,0,0);
            droneBody.quaternion.vmult(right, right); right.y = 0; right.normalize();

            const moveForce = new CANNON.Vec3();
            moveForce.x += forward.x * input.pitch * moveSpeed;
            moveForce.z += forward.z * input.pitch * moveSpeed;
            moveForce.x -= right.x * input.roll * moveSpeed;
            moveForce.z -= right.z * input.roll * moveSpeed;

            droneBody.applyForce(droneBody.quaternion.vmult(new CANNON.Vec3(0, thrustForce, 0)), droneBody.position);
            droneBody.applyForce(moveForce, droneBody.position);
            droneBody.torque.y = input.yaw * 3.0;

            if(droneBody.position.y > CEILING_HEIGHT) {
                droneBody.position.y = CEILING_HEIGHT; droneBody.velocity.y = Math.min(0, droneBody.velocity.y);
            }

            droneMesh.position.copy(droneBody.position);
            droneMesh.quaternion.copy(droneBody.quaternion);
            droneMesh.rotateX(input.pitch * -0.2);
            droneMesh.rotateZ(input.roll * 0.2);
            const offset = new THREE.Vector3(0, PENDULUM_OFFSET, 0);
            offset.applyQuaternion(droneBody.quaternion);
            droneMesh.position.add(offset);

            sunLight.position.set(droneMesh.position.x+50, droneMesh.position.y+100, droneMesh.position.z+50);
            sunLight.target.position.copy(droneMesh.position);
            
            droneProps.forEach(p => p.rotation.y += (5 + currentThrottle*50)*dt);

            // CAMERA
            if(camMode === 'chase') {
                const camOff = new THREE.Vector3(0, 2, -6).applyMatrix4(droneMesh.matrixWorld);
                camera.position.lerp(camOff, 0.1);
                camera.lookAt(droneMesh.position);
            } else if (camMode === 'fpv') {
                const fpvPos = new THREE.Vector3(0, 0.2, 0.3).applyMatrix4(droneMesh.matrixWorld);
                camera.position.copy(fpvPos);
                camera.quaternion.copy(droneMesh.quaternion);
            } else if(controls) controls.update();

            document.getElementById('hud-alt').innerText = Math.round(droneBody.position.y);
            document.getElementById('hud-spd').innerText = Math.round(droneBody.velocity.length()*3.6);
            document.getElementById('hud-thr').innerText = Math.round(currentThrottle*100) + "%";
        }
        
        // RENDER VIA COMPOSER
        composer.render();
    }

    init();
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth/window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
        composer.setSize(window.innerWidth, window.innerHeight);
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

    print(f"✅ Ranch Sim v4.0 (Cinematic) generated: {OUTPUT_HTML}")
    
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