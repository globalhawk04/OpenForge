# --- START OF FILE tools/launch_workbench.py ---
import json
import math
import os
import sys
import http.server
import socketserver
import webbrowser

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR) if os.path.basename(CURRENT_DIR) == "tools" else CURRENT_DIR
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.normalizer import resolve_data_path, normalize_bom, normalize_component
from app.services.physics_service import generate_physics_config
from app.services.compatibility_service import CompatibilityService
from app.services.digital_twin_service import generate_scene_graph
from app.services.cost_service import generate_procurement_manifest
from app.services.firmware_service import generate_firmware_configs

CATALOG_FILE = resolve_data_path("drone_catalog.json")
OUTPUT_HTML = os.path.join(PROJECT_ROOT, "dashboard.html")
TEMPLATE_OUT = os.path.join(PROJECT_ROOT, "templates", "workbench.html")


WORKBENCH_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OpenForge MBSE | Autonomous Drone Engineering Workbench</title>
    <style>
        :root {
            --bg-dark: #090d14;
            --bg-panel: rgba(13, 19, 30, 0.94);
            --border: #1e2d42;
            --accent: #00e5a3;
            --accent-blue: #38bdf8;
            --warn: #f59e0b;
            --danger: #ef4444;
            --text-main: #e2e8f0;
            --text-muted: #8b9bb4;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0; overflow: hidden; background: var(--bg-dark); color: var(--text-main);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            display: grid; grid-template-columns: 365px 1fr 415px; height: 100vh; user-select: none;
        }
        .sidebar {
            background: var(--bg-panel); border-right: 1px solid var(--border);
            display: flex; flex-direction: column; height: 100vh; overflow: hidden; z-index: 20;
        }
        .sidebar-right { border-right: none; border-left: 1px solid var(--border); }
        .panel-header {
            padding: 14px 18px; border-bottom: 1px solid var(--border);
            display: flex; justify-content: space-between; align-items: center;
            background: rgba(5, 8, 14, 0.6);
        }
        .panel-header h2 {
            margin: 0; font-size: 13px; letter-spacing: 1.5px; text-transform: uppercase;
            color: var(--accent); font-weight: 700;
        }
        .scroll-area { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 14px; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #090d14; }
        ::-webkit-scrollbar-thumb { background: #24354f; border-radius: 3px; }

        .sku-card {
            background: #111927; border: 1px solid var(--border); border-left: 3px solid #334155;
            border-radius: 6px; padding: 12px; cursor: pointer; transition: 0.15s;
        }
        .sku-card:hover { background: #172235; border-left-color: var(--accent-blue); }
        .sku-card.active { background: #162436; border-color: var(--accent); border-left-color: var(--accent); }
        .sku-top { display: flex; justify-content: space-between; align-items: center; font-size: 10px; color: var(--accent); margin-bottom: 4px; font-weight: 700; }
        .sku-title { font-size: 13px; font-weight: 600; color: #fff; margin: 0 0 8px 0; line-height: 1.3; }
        .sku-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; font-size: 11px; }
        .metric-pill { background: #0b1019; padding: 4px 6px; border-radius: 4px; border: 1px solid #1c283a; text-align: center; }
        .metric-pill span { display: block; font-size: 9px; color: var(--text-muted); }

        .section-box { background: #0f1623; border: 1px solid var(--border); border-radius: 6px; padding: 12px; }
        .section-title {
            font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;
            color: var(--accent-blue); margin: 0 0 10px 0; display: flex; justify-content: space-between;
        }
        .data-row {
            display: flex; justify-content: space-between; align-items: center;
            padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 11.5px;
        }
        .data-row:last-child { border-bottom: none; }
        .data-label { color: var(--text-muted); }
        .data-val { font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #fff; }

        .rule-item {
            padding: 8px; border-radius: 4px; background: #0a0f18; border: 1px solid #182334;
            margin-bottom: 6px; font-size: 11px;
        }
        .rule-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; }
        .badge { padding: 2px 6px; border-radius: 3px; font-size: 9.5px; font-weight: 700; font-family: monospace; }
        .badge-PASS { background: rgba(0, 229, 163, 0.15); color: var(--accent); border: 1px solid rgba(0, 229, 163, 0.4); }
        .badge-WARN { background: rgba(245, 158, 11, 0.15); color: var(--warn); border: 1px solid rgba(245, 158, 11, 0.4); }
        .badge-FAIL { background: rgba(239, 68, 68, 0.18); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.5); }

        #center-stage { position: relative; width: 100%; height: 100vh; overflow: hidden; background: #070a10; }
        #canvas-container { width: 100%; height: 100%; }

        #viewport-toolbar {
            position: absolute; top: 14px; left: 14px; right: 14px;
            display: flex; justify-content: space-between; align-items: center; pointer-events: none; z-index: 15;
        }
        .tool-group {
            display: flex; gap: 6px; background: var(--bg-panel); padding: 6px;
            border-radius: 6px; border: 1px solid var(--border); pointer-events: auto; align-items: center;
        }
        .btn {
            background: #131c2b; border: 1px solid #263854; color: var(--text-main);
            padding: 6px 10px; border-radius: 4px; font-size: 11px; font-weight: 600;
            cursor: pointer; transition: 0.15s;
        }
        .btn:hover { border-color: var(--accent-blue); color: #fff; }
        .btn.active { background: rgba(0, 229, 163, 0.18); border-color: var(--accent); color: var(--accent); }
        .slider-wrap { display: flex; align-items: center; gap: 8px; font-size: 11px; padding: 0 8px; color: var(--text-muted); }
        input[type=range] { accent-color: var(--accent); width: 95px; cursor: pointer; }

        #flight-hud {
            position: absolute; bottom: 16px; left: 16px; right: 16px;
            display: flex; justify-content: space-between; align-items: flex-end; pointer-events: none; z-index: 15;
        }
        .hud-box {
            background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px;
            padding: 10px 16px; pointer-events: auto;
        }
        .telemetry-grid { display: flex; gap: 22px; }
        .tel-item { text-align: center; }
        .tel-val { font-size: 20px; font-weight: 700; font-family: monospace; color: #fff; }
        .tel-lbl { font-size: 9.5px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }

        .motor-bars { display: flex; gap: 8px; align-items: flex-end; height: 55px; }
        .m-col { display: flex; flex-direction: column; align-items: center; gap: 3px; }
        .m-track { width: 14px; height: 42px; background: #0b1019; border: 1px solid #22324a; border-radius: 2px; display: flex; align-items: flex-end; overflow: hidden; }
        .m-fill { width: 100%; background: var(--accent); height: 0%; transition: height 0.05s linear; }
        .m-lbl { font-size: 9px; font-family: monospace; color: var(--text-muted); }

        .modal-backdrop {
            position: fixed; inset: 0; background: rgba(0,0,0,0.82); z-index: 100;
            display: none; align-items: center; justify-content: center; backdrop-filter: blur(4px);
        }
        .modal-card {
            background: #101724; border: 1px solid var(--border); border-radius: 8px;
            width: 720px; max-height: 85vh; display: flex; flex-direction: column; overflow: hidden;
        }
        .modal-body { padding: 18px; overflow-y: auto; }
        pre.fw-code {
            background: #070a10; color: #00e5a3; padding: 14px; border-radius: 6px;
            border: 1px solid #1e2d42; font-size: 11.5px; max-height: 420px; overflow: auto;
            user-select: text; line-height: 1.45;
        }
        a.vendor-link { color: var(--accent-blue); text-decoration: none; }
        a.vendor-link:hover { text-decoration: underline; }
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

<!-- LEFT PANEL: FLEET, 3D PRINTABLE MOUNTS & MASS BREAKDOWN -->
<div class="sidebar">
    <div class="panel-header">
        <h2>OpenForge MBSE Fleet</h2>
        <span style="font-size:10px; color:var(--text-muted);">v5.0 COMPILER</span>
    </div>
    <div class="scroll-area">
        <div id="sku-list" style="display:flex; flex-direction:column; gap:8px;"></div>

        <!-- NEW: 3D-PRINTABLE TPU & CF-PETG MOUNTS PANEL -->
        <div class="section-box">
            <div class="section-title">
                <span>🖨️ Auto-Generated 3D-Printable Mounts</span>
                <span id="mounts-count-badge" style="color:var(--accent);">0 STL</span>
            </div>
            <div id="printable-mounts-list"></div>
        </div>

        <div class="section-box">
            <div class="section-title">
                <span>Audit-Ready Mass Breakdown</span>
                <span id="auw-total-badge" style="color:var(--accent);">0.0g</span>
            </div>
            <div id="mass-breakdown-list"></div>
        </div>

        <div class="section-box">
            <div class="section-title"><span>3D Mass & Inertia Tensor (CoG)</span></div>
            <div id="inertia-list"></div>
        </div>

        <div class="section-box">
            <div class="section-title"><span>Engineering Deliverables & Firmware</span></div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px;">
                <button class="btn" id="btn-fw-modal" style="border-color:var(--accent); color:var(--accent);">⚡ Firmware (BF / ArduPilot)</button>
                <button class="btn" id="btn-cost-modal">💰 Procurement BOM ($)</button>
            </div>
            <div style="display:grid; grid-template-columns:1fr; gap:8px;">
                <button class="btn" id="btn-export-urdf">📦 Export Physics URDF (.urdf)</button>
            </div>
            <div id="ai-notes" style="margin-top:10px; font-size:11px; color:var(--text-muted); line-height:1.45;"></div>
        </div>
    </div>
</div>

<!-- CENTER VIEWPORT: 3D CAD & 6-DOF FLIGHT SANDBOX -->
<div id="center-stage">
    <div id="viewport-toolbar">
        <div class="tool-group">
            <button class="btn active" id="mode-cad">📐 CAD Inspector</button>
            <button class="btn" id="mode-flight">🎮 6-DOF Flight Sim</button>
            <div class="slider-wrap" id="explode-wrap">
                <span>Explode CAD:</span>
                <input type="range" id="explode-slider" min="0" max="100" value="0">
            </div>
        </div>

        <div class="tool-group">
            <button class="btn active" id="toggle-cog">⊕ CoG Triad</button>
            <button class="btn active" id="toggle-clearance">◎ Prop Clearance</button>
            <button class="btn active" id="toggle-vectors">↑ Thrust Vectors</button>
            <button class="btn" id="btn-flight-mode">FC: ANGLE + ALT HOLD</button>
            <button class="btn" id="btn-cam-mode">Cam: ORBIT</button>
            <button class="btn" id="btn-reset-sim">Reset (R)</button>
        </div>
    </div>

    <div id="canvas-container"></div>

    <div id="flight-hud">
        <div class="hud-box">
            <div style="font-size:10px; color:var(--text-muted); margin-bottom:6px; letter-spacing:1px;">
                QUAD-X PID MOTOR MIXER (FL / FR / RL / RR)
            </div>
            <div style="display:flex; align-items:center; gap:18px;">
                <div class="motor-bars">
                    <div class="m-col"><div class="m-track"><div class="m-fill" id="mbar-0"></div></div><span class="m-lbl">M1</span></div>
                    <div class="m-col"><div class="m-track"><div class="m-fill" id="mbar-1"></div></div><span class="m-lbl">M2</span></div>
                    <div class="m-col"><div class="m-track"><div class="m-fill" id="mbar-2"></div></div><span class="m-lbl">M3</span></div>
                    <div class="m-col"><div class="m-track"><div class="m-fill" id="mbar-3"></div></div><span class="m-lbl">M4</span></div>
                </div>
                <div style="font-size:11px; color:var(--text-muted); line-height:1.5;">
                    <div><b>SHIFT / SPACE</b>: Climb / Descend</div>
                    <div><b>W/S</b>: Pitch &bull; <b>A/D</b>: Roll &bull; <b>Q/E</b>: Yaw</div>
                </div>
            </div>
        </div>

        <div class="hud-box telemetry-grid">
            <div class="tel-item"><div class="tel-val" id="tel-alt">0.0m</div><div class="tel-lbl">Altitude</div></div>
            <div class="tel-item"><div class="tel-val" id="tel-spd">0</div><div class="tel-lbl">Speed (km/h)</div></div>
            <div class="tel-item"><div class="tel-val" id="tel-att">0° / 0°</div><div class="tel-lbl">Roll / Pitch</div></div>
            <div class="tel-item"><div class="tel-val" id="tel-thr" style="color:var(--accent);">0%</div><div class="tel-lbl">Throttle</div></div>
            <div class="tel-item"><div class="tel-val" id="tel-amps" style="color:var(--accent-blue);">0.0A</div><div class="tel-lbl">Current</div></div>
            <div class="tel-item"><div class="tel-val" id="tel-watts">0W</div><div class="tel-lbl">Power</div></div>
        </div>
    </div>
</div>

<!-- RIGHT PANEL: DRC/ERC MATRIX & PROPULSION CURVES -->
<div class="sidebar sidebar-right">
    <div class="panel-header">
        <h2>Verification & Propulsion</h2>
        <span id="drc-overall-badge" class="badge badge-PASS">VERIFIED</span>
    </div>
    <div class="scroll-area">
        <div class="section-box">
            <div class="section-title"><span>First-Principles Aero & Electrical</span></div>
            <div id="aero-elec-summary"></div>
        </div>

        <div class="section-box">
            <div class="section-title">
                <span>Propulsion Curve (Thrust & Current vs. Throttle)</span>
            </div>
            <canvas id="propulsion-chart" width="350" height="175" style="width:100%; background:#080c14; border-radius:4px; border:1px solid #182334;"></canvas>
        </div>

        <div class="section-box">
            <div class="section-title"><span>Mechanical Design Rule Checks (DRC)</span></div>
            <div id="drc-list"></div>
        </div>

        <div class="section-box">
            <div class="section-title"><span>Electrical Rule Checks (ERC)</span></div>
            <div id="erc-list"></div>
        </div>
    </div>
</div>

<!-- COST & PROCUREMENT MODAL -->
<div class="modal-backdrop" id="cost-modal">
    <div class="modal-card">
        <div class="panel-header">
            <h2>Consolidated Procurement Manifest</h2>
            <button class="btn" id="close-cost-modal">✕ Close</button>
        </div>
        <div class="modal-body" id="cost-modal-body"></div>
    </div>
</div>

<!-- NEW: FIRMWARE COMPILER MODAL (BETAFLIGHT CLI & ARDUPILOT .PARAM) -->
<div class="modal-backdrop" id="fw-modal">
    <div class="modal-card">
        <div class="panel-header">
            <h2>⚡ Inertia-Scaled Firmware Config Generator</h2>
            <button class="btn" id="close-fw-modal">✕ Close</button>
        </div>
        <div class="modal-body">
            <div id="fw-uart-summary" style="margin-bottom:12px;"></div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <div style="display:flex; gap:8px;">
                    <button class="btn active" id="tab-bf">Betaflight 4.5 CLI (.txt)</button>
                    <button class="btn" id="tab-ap">ArduPilot ArduCopter (.param)</button>
                </div>
                <div style="display:flex; gap:8px;">
                    <button class="btn" id="btn-copy-fw">📋 Copy</button>
                    <button class="btn" id="btn-dl-fw" style="border-color:var(--accent); color:var(--accent);">⬇ Download File</button>
                </div>
            </div>
            <pre class="fw-code" id="fw-code-view"></pre>
        </div>
    </div>
</div>

<script type="module">
    import * as THREE from 'three';
    import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
    import * as CANNON from 'cannon-es';

    const FLEET = __FLEET_DATA__;

    // Global helper to download ASCII STL or Firmware files directly in browser
    window.downloadTextFile = function(filename, content, mime='application/sla') {
        const blob = new Blob([content], { type: mime });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
    };

    class AxisPID {
        constructor(kp, ki, kd, iLimit = 0.4) {
            this.kp = kp; this.ki = ki; this.kd = kd; this.iLimit = iLimit;
            this.integral = 0; this.prevErr = 0;
        }
        update(err, dt) {
            this.integral = Math.max(-this.iLimit, Math.min(this.iLimit, this.integral + err * dt));
            const deriv = dt > 0 ? (err - this.prevErr) / dt : 0;
            this.prevErr = err;
            return (this.kp * err) + (this.ki * this.integral) + (this.kd * deriv);
        }
        reset() { this.integral = 0; this.prevErr = 0; }
    }

    class SixDOFFlightController {
        constructor() {
            this.rollPID = new AxisPID(0.42, 0.05, 0.14);
            this.pitchPID = new AxisPID(0.42, 0.05, 0.14);
            this.yawRatePID = new AxisPID(0.35, 0.02, 0.02);
            this.mode = 'ANGLE_ALTHOLD';
            this.targetAlt = 1.5;
            this.motorState = [0, 0, 0, 0];
        }
        reset(currentAlt = 1.2) {
            this.rollPID.reset(); this.pitchPID.reset(); this.yawRatePID.reset();
            this.targetAlt = currentAlt;
            this.motorState = [0, 0, 0, 0];
        }
        compute(body, input, hoverThrottle, dt) {
            const q = new THREE.Quaternion(body.quaternion.x, body.quaternion.y, body.quaternion.z, body.quaternion.w);
            const euler = new THREE.Euler().setFromQuaternion(q, 'YXZ');
            const currPitch = euler.x, currRoll = euler.z;

            const invQ = q.clone().invert();
            const angVelLocal = new THREE.Vector3(body.angularVelocity.x, body.angularVelocity.y, body.angularVelocity.z).applyQuaternion(invQ);

            let baseThr = hoverThrottle;
            if (this.mode === 'ANGLE_ALTHOLD') {
                this.targetAlt = Math.max(0.2, Math.min(150.0, this.targetAlt + (input.climb - input.descend) * 4.5 * dt));
                const altErr = this.targetAlt - body.position.y;
                const vz = body.velocity.y;
                baseThr = hoverThrottle + (0.28 * altErr) - (0.18 * vz);
                const tiltFactor = Math.max(0.55, Math.cos(currRoll) * Math.cos(currPitch));
                baseThr = baseThr / tiltFactor;
            } else {
                baseThr = Math.max(0.05, hoverThrottle * 0.6 + input.climb * 0.75 - input.descend * 0.5);
            }
            baseThr = Math.max(0.05, Math.min(0.92, baseThr));

            const maxAngleRad = 0.48;
            let uRoll = 0, uPitch = 0, uYaw = 0;
            if (this.mode === 'ANGLE_ALTHOLD') {
                uPitch = this.pitchPID.update((input.pitch * maxAngleRad) - currPitch, dt);
                uRoll = this.rollPID.update((-input.roll * maxAngleRad) - currRoll, dt);
            } else {
                uPitch = 0.16 * ((input.pitch * 3.5) - angVelLocal.x);
                uRoll = 0.16 * ((-input.roll * 3.5) - angVelLocal.z);
            }
            uYaw = this.yawRatePID.update((input.yaw * 2.6) - angVelLocal.y, dt);

            const rawM = [
                baseThr - uPitch - uRoll - uYaw,
                baseThr - uPitch + uRoll + uYaw,
                baseThr + uPitch - uRoll + uYaw,
                baseThr + uPitch + uRoll - uYaw
            ];

            const alpha = Math.min(1.0, dt / 0.028);
            for (let i = 0; i < 4; i++) {
                const clamped = Math.max(0.0, Math.min(1.0, rawM[i]));
                this.motorState[i] += (clamped - this.motorState[i]) * alpha;
            }
            return this.motorState;
        }
    }

    const container = document.getElementById('canvas-container');
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x070a10);
    scene.fog = new THREE.FogExp2(0x070a10, 0.008);

    const camera = new THREE.PerspectiveCamera(50, container.clientWidth / container.clientHeight, 0.02, 1000);
    camera.position.set(0.45, 0.35, 0.55);

    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0, 0.05, 0);

    scene.add(new THREE.AmbientLight(0x6b7c96, 1.8));
    const dirLight = new THREE.DirectionalLight(0xffffff, 2.6);
    dirLight.position.set(5, 12, 8);
    dirLight.castShadow = true;
    scene.add(dirLight);
    scene.add(new THREE.GridHelper(100, 200, 0x00e5a3, 0x162234));

    const world = new CANNON.World();
    world.gravity.set(0, -9.80665, 0);
    const groundBody = new CANNON.Body({ mass: 0 });
    groundBody.addShape(new CANNON.Plane());
    groundBody.quaternion.setFromEuler(-Math.PI / 2, 0, 0);
    world.addBody(groundBody);

    let activeDrone = null;
    let droneGroup = new THREE.Group();
    scene.add(droneGroup);
    let cogHelperGroup = new THREE.Group();
    scene.add(cogHelperGroup);

    let partMeshes = [], propMeshes = [], clearanceRings = [], thrustCones = [], motorLocalCoordsM = [];
    let droneBody = null;
    const fc = new SixDOFFlightController();
    let workbenchMode = 'CAD', camMode = 'ORBIT';
    let showCoG = true, showClearance = true, showVectors = true;
    let activeFwTab = 'BF';
    const keys = { climb: 0, descend: 0, pitch: 0, roll: 0, yaw: 0 };

    function buildDigitalTwin(sku) {
        activeDrone = sku;
        const sg = sku.technical_data.scene_graph;
        const phys = sku.technical_data.physics_config;
        const drcReport = sku.technical_data.drc_erc_report || { drc_matrix: [], erc_matrix: [] };
        const mounts = sku.technical_data.printable_mounts || [];

        while (droneGroup.children.length) droneGroup.remove(droneGroup.children[0]);
        while (cogHelperGroup.children.length) cogHelperGroup.remove(cogHelperGroup.children[0]);
        partMeshes = []; propMeshes = []; clearanceRings = []; thrustCones = []; motorLocalCoordsM = [];

        const propRule = (drcReport.drc_matrix || []).find(r => r.code === 'DRC-MECH-01');
        const ringColor = propRule?.status === 'FAIL' ? 0xef4444 : (propRule?.status === 'WARN' ? 0xf59e0b : 0x00e5a3);

        sg.components.forEach(comp => {
            const dims = comp.dims || {};
            const hexStr = comp.visuals?.primary_color_hex || '#64748b';
            const color = new THREE.Color(hexStr);

            let geo, mat;
            if (comp.type === 'FRAME_CORE') {
                geo = new THREE.BoxGeometry((dims.length || 120) / 1000, (dims.thickness || 4) / 1000, (dims.width || 45) / 1000);
                mat = new THREE.MeshStandardMaterial({ color: 0x1e242b, roughness: 0.35, metalness: 0.4 });
            } else if (comp.type === 'FRAME_ARM') {
                const lenM = (dims.length || 110) / 1000;
                geo = new THREE.BoxGeometry(lenM, (dims.thickness || 5) / 1000, (dims.width || 12) / 1000);
                geo.translate(lenM / 2, 0, 0);
                mat = new THREE.MeshStandardMaterial({ color: 0x222930, roughness: 0.35, metalness: 0.4 });
            } else if (comp.type === 'MOTOR') {
                const rM = (dims.radius || 14) / 1000, hM = (dims.height || 16) / 1000;
                geo = new THREE.CylinderGeometry(rM, rM, hM, 28);
                mat = new THREE.MeshStandardMaterial({ color, roughness: 0.2, metalness: 0.85 });
                motorLocalCoordsM.push(new THREE.Vector3(comp.pos[0] / 1000, comp.pos[1] / 1000, comp.pos[2] / 1000));

                const coneGeo = new THREE.ConeGeometry(rM * 0.65, 0.08, 16);
                coneGeo.translate(0, 0.04, 0);
                const coneMat = new THREE.MeshBasicMaterial({ color: 0x00e5a3, transparent: true, opacity: 0.65 });
                const cone = new THREE.Mesh(coneGeo, coneMat);
                cone.position.set(comp.pos[0] / 1000, (comp.pos[1] + (dims.height || 16)) / 1000, comp.pos[2] / 1000);
                cone.visible = showVectors;
                droneGroup.add(cone);
                thrustCones.push(cone);
            } else if (comp.type === 'PROPELLER') {
                const rM = (dims.radius || 63.5) / 1000;
                geo = new THREE.BoxGeometry(rM * 2, 0.0025, 0.014);
                mat = new THREE.MeshPhysicalMaterial({ color, transparent: true, opacity: 0.85, roughness: 0.2 });

                const ringGeo = new THREE.RingGeometry(rM * 0.96, rM, 48);
                ringGeo.rotateX(-Math.PI / 2);
                const ringMat = new THREE.MeshBasicMaterial({ color: ringColor, side: THREE.DoubleSide, transparent: true, opacity: 0.55 });
                const ring = new THREE.Mesh(ringGeo, ringMat);
                ring.position.set(comp.pos[0] / 1000, comp.pos[1] / 1000, comp.pos[2] / 1000);
                ring.visible = showClearance;
                droneGroup.add(ring);
                clearanceRings.push(ring);
            } else if (comp.type === 'PCB_STACK') {
                geo = new THREE.BoxGeometry((dims.width || 30.5) / 1000, (dims.height || 15) / 1000, (dims.length || 30.5) / 1000);
                mat = new THREE.MeshStandardMaterial({ color: 0x0f52ba, roughness: 0.4, metalness: 0.5 });
            } else if (comp.type === 'BATTERY') {
                geo = new THREE.BoxGeometry((dims.width || 38) / 1000, (dims.height || 34) / 1000, (dims.length || 78) / 1000);
                mat = new THREE.MeshStandardMaterial({ color: 0x18181b, roughness: 0.6 });
            } else {
                geo = new THREE.BoxGeometry(0.02, 0.02, 0.02);
                mat = new THREE.MeshStandardMaterial({ color: 0xeab308 });
            }

            const mesh = new THREE.Mesh(geo, mat);
            const basePos = new THREE.Vector3(comp.pos[0] / 1000, comp.pos[1] / 1000, comp.pos[2] / 1000);
            mesh.position.copy(basePos);
            if (comp.rot) mesh.rotation.set(comp.rot[0], comp.rot[1], comp.rot[2]);
            mesh.castShadow = true;

            let explodeOffset = new THREE.Vector3(0, 0, 0);
            if (comp.type === 'BATTERY') explodeOffset.set(0, 0.12, 0);
            else if (comp.type === 'PCB_STACK') explodeOffset.set(0, 0.05, 0);
            else if (comp.type === 'PROPELLER') explodeOffset.set(basePos.x * 0.25, 0.09, basePos.z * 0.25);
            else if (comp.type === 'MOTOR') explodeOffset.set(basePos.x * 0.25, 0.03, basePos.z * 0.25);
            else if (comp.type === 'CAMERA') explodeOffset.set(0, 0, 0.06);

            mesh.userData = { basePos: basePos.clone(), explodeOffset };
            droneGroup.add(mesh);
            partMeshes.push(mesh);
            if (comp.type === 'PROPELLER') propMeshes.push(mesh);
        });

        // Render Auto-Generated 3D-Printed TPU & CF-PETG Mounts on the Digital Twin
        mounts.forEach(mnt => {
            const pMm = mnt.pos_mm || [0, 15, -75];
            const basePos = new THREE.Vector3(pMm[0] / 1000, pMm[1] / 1000, pMm[2] / 1000);
            let mGeo, explodeVec;
            if (mnt.type === 'GPS_ANTENNA_TPU_POD') {
                mGeo = new THREE.BoxGeometry(0.028, 0.022, 0.036);
                explodeVec = new THREE.Vector3(0, 0.06, -0.07);
            } else if (mnt.type === 'STACK_ADAPTER_PLATE') {
                mGeo = new THREE.BoxGeometry(0.038, 0.003, 0.038);
                explodeVec = new THREE.Vector3(0, 0.025, 0);
            } else {
                mGeo = new THREE.BoxGeometry(0.024, 0.016, 0.016);
                explodeVec = new THREE.Vector3(0, 0.02, 0.08);
            }
            const mMat = new THREE.MeshStandardMaterial({
                color: new THREE.Color(mnt.color_hex || '#00e5a3'),
                roughness: 0.45, metalness: 0.1, transparent: true, opacity: 0.90
            });
            const mMesh = new THREE.Mesh(mGeo, mMat);
            mMesh.position.copy(basePos);
            mMesh.userData = { basePos: basePos.clone(), explodeOffset: explodeVec };
            droneGroup.add(mMesh);
            partMeshes.push(mMesh);
        });

        // 3D Center of Gravity (CoG) Marker
        const cogM = sg.mass_properties?.cog_m || [0, 0.015, 0];
        const cogSphere = new THREE.Mesh(
            new THREE.SphereGeometry(0.012, 20, 20),
            new THREE.MeshBasicMaterial({ color: 0xff0055 })
        );
        cogSphere.add(new THREE.AxesHelper(0.075));
        cogSphere.position.set(cogM[0], cogM[1], cogM[2]);
        cogHelperGroup.add(cogSphere);
        cogHelperGroup.visible = showCoG;

        if (droneBody) world.removeBody(droneBody);
        const massKg = phys.mass_kg || 0.55;
        const inertia = sg.mass_properties?.inertia_webgl_kg_m2 || { ixx: 0.004, iyy: 0.007, izz: 0.004 };
        const halfExt = new CANNON.Vec3(
            (phys.collider_size_m?.[0] || 0.22) / 2,
            0.035,
            (phys.collider_size_m?.[2] || 0.22) / 2
        );

        droneBody = new CANNON.Body({
            mass: massKg,
            shape: new CANNON.Box(halfExt),
            linearDamping: 0.15,
            angularDamping: 0.12
        });
        droneBody.inertia.set(inertia.ixx, inertia.iyy, inertia.izz);
        droneBody.updateMassProperties();
        world.addBody(droneBody);

        resetSimulation();
        updateAllPanels(sku);
    }

    function applyExplodeSlider(pct) {
        const t = pct / 100.0;
        partMeshes.forEach(m => {
            m.position.copy(m.userData.basePos).addScaledVector(m.userData.explodeOffset, t);
        });
    }

    function resetSimulation() {
        if (!droneBody) return;
        const startY = workbenchMode === 'FLIGHT' ? 1.2 : 0.04;
        droneBody.position.set(0, startY, 0);
        droneBody.velocity.set(0, 0, 0);
        droneBody.angularVelocity.set(0, 0, 0);
        droneBody.quaternion.set(0, 0, 0, 1);
        fc.reset(startY);
        droneGroup.position.copy(droneBody.position);
        droneGroup.quaternion.copy(droneBody.quaternion);
        cogHelperGroup.position.copy(droneBody.position);
        cogHelperGroup.quaternion.copy(droneBody.quaternion);
    }

    function updateAllPanels(sku) {
        const phys = sku.technical_data.physics_config;
        const sg = sku.technical_data.scene_graph;
        const drcReport = sku.technical_data.drc_erc_report || { valid: true, drc_matrix: [], erc_matrix: [] };
        const mounts = sku.technical_data.printable_mounts || [];

        // 1. Auto-Generated 3D-Printable Mounts List
        document.getElementById('mounts-count-badge').innerText = `${mounts.length} STL FILES`;
        const mountsContainer = document.getElementById('printable-mounts-list');
        mountsContainer.innerHTML = mounts.map((m, idx) => `
            <div class="rule-item">
                <div class="rule-head">
                    <span style="font-weight:600; color:#fff;">${m.name}</span>
                    <button class="btn" style="padding:2px 7px; font-size:10px; border-color:var(--accent); color:var(--accent);" onclick="window.dlMount(${idx})">⬇ .STL</button>
                </div>
                <div style="color:var(--text-muted); font-size:10px;">
                    <b>${m.material}</b> &bull; ${m.weight_g}g &bull; ${m.dims_mm}<br>
                    <i>Slicer: ${m.slicer_settings}</i>
                </div>
            </div>
        `).join('');

        window.dlMount = (idx) => {
            const m = mounts[idx];
            if (m && m.stl_ascii) window.downloadTextFile(m.stl_filename, m.stl_ascii, 'model/stl');
        };

        // 2. Mass Breakdown
        document.getElementById('auw-total-badge').innerText = `${phys.meta.total_weight_g}g`;
        document.getElementById('mass-breakdown-list').innerHTML = (phys.mass_breakdown || []).map(item => `
            <div class="data-row">
                <span class="data-label" title="${item.model_name}">
                    ${item.category} (x${item.quantity}) ${item.empirical ? '' : '<span style="color:var(--warn)">[EST]</span>'}
                </span>
                <span class="data-val">${item.total_weight_g}g</span>
            </div>
        `).join('');

        // 3. Inertia & CoG
        const mp = sg.mass_properties || {};
        const inTensor = mp.inertia_urdf_kg_m2 || { ixx: 0, iyy: 0, izz: 0 };
        const cogMm = mp.cog_mm || [0, 0, 0];
        document.getElementById('inertia-list').innerHTML = `
            <div class="data-row"><span class="data-label">CoG Offset (X, Y, Z)</span><span class="data-val">[${cogMm[0]}, ${cogMm[1]}, ${cogMm[2]}] mm</span></div>
            <div class="data-row"><span class="data-label">Roll Inertia (Ixx)</span><span class="data-val">${inTensor.ixx.toFixed(5)} kg·m²</span></div>
            <div class="data-row"><span class="data-label">Pitch Inertia (Iyy)</span><span class="data-val">${inTensor.iyy.toFixed(5)} kg·m²</span></div>
            <div class="data-row"><span class="data-label">Yaw Inertia (Izz)</span><span class="data-val">${inTensor.izz.toFixed(5)} kg·m²</span></div>
        `;

        // 4. Aero & Electrical Summary
        const aero = phys.aerodynamics || {}, elec = phys.electrical || {};
        document.getElementById('aero-elec-summary').innerHTML = `
            <div class="data-row"><span class="data-label">Thrust-to-Weight (TWR)</span><span class="data-val" style="color:var(--accent)">${phys.dynamics.twr}:1</span></div>
            <div class="data-row"><span class="data-label">Hover Throttle / Current</span><span class="data-val">${phys.dynamics.hover_throttle_pct}% (${elec.hover_current_total_a}A)</span></div>
            <div class="data-row"><span class="data-label">Induced / Total Hover Power</span><span class="data-val">${aero.induced_hover_power_w}W / ${aero.total_hover_power_w}W</span></div>
            <div class="data-row"><span class="data-label">Peak Burst Current / Power</span><span class="data-val">${elec.peak_current_total_a}A (${elec.peak_power_total_w}W)</span></div>
            <div class="data-row"><span class="data-label">Disk Loading</span><span class="data-val">${aero.disk_loading_g_dm2} g/dm²</span></div>
            <div class="data-row"><span class="data-label">Pitch / Top Speed</span><span class="data-val">${aero.pitch_speed_kmh} / ${aero.top_speed_kmh} km/h</span></div>
            <div class="data-row"><span class="data-label">Peukert Hover / Mixed Time</span><span class="data-val">${phys.meta.est_flight_time_min}m / ${phys.meta.mixed_flight_time_min}m</span></div>
        `;

        // 5. DRC & ERC Lists
        const overallBadge = document.getElementById('drc-overall-badge');
        overallBadge.className = `badge badge-${drcReport.valid ? 'PASS' : 'FAIL'}`;
        overallBadge.innerText = drcReport.valid ? 'DRC/ERC PASS' : 'DRC VIOLATION';

        const renderRules = (rules) => (rules || []).map(r => `
            <div class="rule-item">
                <div class="rule-head">
                    <span style="font-weight:600; color:#fff;">${r.code}: ${r.rule}</span>
                    <span class="badge badge-${r.status}">${r.status} &bull; ${r.value}</span>
                </div>
                <div style="color:var(--text-muted); font-size:10.5px;">${r.detail}</div>
            </div>
        `).join('');

        document.getElementById('drc-list').innerHTML = renderRules(drcReport.drc_matrix);
        document.getElementById('erc-list').innerHTML = renderRules(drcReport.erc_matrix);
        document.getElementById('ai-notes').innerText = sku.ai_reasoning || '';

        drawPropulsionChart(phys.throttle_curve || [], phys.meta.total_weight_g);
    }


    function drawPropulsionChart(curve, auwG) {
        const canvas = document.getElementById('propulsion-chart');
        const ctx = canvas.getContext('2d');
        const W = canvas.width, H = canvas.height;
        ctx.clearRect(0, 0, W, H);
        if (!curve.length) return;

        const padL = 38, padR = 36, padT = 16, padB = 24;
        const plotW = W - padL - padR, plotH = H - padT - padB;
        const maxThrust = Math.max(...curve.map(c => c.total_thrust_g), auwG * 1.2, 1000);
        const maxAmps = Math.max(...curve.map(c => c.total_current_a), 20);

        ctx.strokeStyle = '#182436'; ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const y = padT + (plotH * i / 4);
            ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
        }

        const auwY = padT + plotH * (1 - (auwG / maxThrust));
        if (auwY >= padT && auwY <= H - padB) {
            ctx.strokeStyle = 'rgba(245, 158, 11, 0.5)';
            ctx.setLineDash([4, 4]);
            ctx.beginPath(); ctx.moveTo(padL, auwY); ctx.lineTo(W - padR, auwY); ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = '#f59e0b'; ctx.font = '9px monospace';
            ctx.fillText(`AUW ${auwG}g`, padL + 4, auwY - 4);
        }

        ctx.strokeStyle = '#00e5a3'; ctx.lineWidth = 2;
        ctx.beginPath();
        curve.forEach((pt, idx) => {
            const x = padL + (idx / (curve.length - 1)) * plotW;
            const y = padT + plotH * (1 - (pt.total_thrust_g / maxThrust));
            if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();

        ctx.strokeStyle = '#38bdf8'; ctx.lineWidth = 2;
        ctx.beginPath();
        curve.forEach((pt, idx) => {
            const x = padL + (idx / (curve.length - 1)) * plotW;
            const y = padT + plotH * (1 - (pt.total_current_a / maxAmps));
            if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();

        ctx.fillStyle = '#00e5a3'; ctx.font = '9.5px monospace';
        ctx.fillText(`${(maxThrust/1000).toFixed(1)}kg`, 2, padT + 8);
        ctx.fillStyle = '#38bdf8';
        ctx.fillText(`${maxAmps.toFixed(0)}A`, W - padR + 4, padT + 8);
        ctx.fillStyle = '#8b9bb4';
        ctx.fillText('10%', padL, H - 6);
        ctx.fillText('50%', padL + plotW * 0.45, H - 6);
        ctx.fillText('100% Thr', W - padR - 42, H - 6);
    }

    const clock = new THREE.Clock();

    function animate() {
        requestAnimationFrame(animate);
        const dt = Math.min(clock.getDelta(), 0.05);

        if (activeDrone && droneBody) {
            const phys = activeDrone.technical_data.physics_config;
            const hoverThr = phys.dynamics.hover_throttle || 0.28;
            const maxMotorForceN = phys.motor_max_force_n || 15.0;

            let motors = [0, 0, 0, 0];

            if (workbenchMode === 'FLIGHT') {
                motors = fc.compute(droneBody, keys, hoverThr, dt);
                const spinDirs = [-1, 1, 1, -1];
                for (let i = 0; i < 4; i++) {
                    const mCoord = motorLocalCoordsM[i] || new THREE.Vector3(0, 0, 0);
                    const thrustN = maxMotorForceN * Math.pow(motors[i], 1.85);
                    droneBody.applyLocalForce(
                        new CANNON.Vec3(0, thrustN, 0),
                        new CANNON.Vec3(mCoord.x, mCoord.y, mCoord.z)
                    );
                    const yawTorque = thrustN * 0.018 * spinDirs[i];
                    const worldTorque = droneBody.quaternion.vmult(new CANNON.Vec3(0, yawTorque, 0));
                    droneBody.torque.vadd(worldTorque, droneBody.torque);
                }

                const v = droneBody.velocity;
                const speed = v.length();
                if (speed > 0.01) {
                    const dragMag = 0.22 * speed * speed;
                    droneBody.applyForce(
                        new CANNON.Vec3(-v.x / speed * dragMag, -v.y / speed * dragMag * 1.8, -v.z / speed * dragMag),
                        droneBody.position
                    );
                }

                world.step(1 / 120, dt, 4);
                droneGroup.position.copy(droneBody.position);
                droneGroup.quaternion.copy(droneBody.quaternion);
                cogHelperGroup.position.copy(droneBody.position);
                cogHelperGroup.quaternion.copy(droneBody.quaternion);
            } else {
                motors = [hoverThr, hoverThr, hoverThr, hoverThr];
            }

            const avgThr = (motors[0] + motors[1] + motors[2] + motors[3]) / 4.0;
            propMeshes.forEach((p, idx) => {
                const dir = (idx === 0 || idx === 3) ? -1 : 1;
                p.rotation.y += dir * (8 + motors[idx] * 65) * dt;
            });
            thrustCones.forEach((cone, idx) => {
                const scaleY = Math.max(0.15, motors[idx] * 2.4);
                cone.scale.set(1, scaleY, 1);
                cone.material.color.setHex(motors[idx] > 0.80 ? 0xef4444 : (motors[idx] > 0.50 ? 0xf59e0b : 0x00e5a3));
            });

            for (let i = 0; i < 4; i++) {
                const pct = Math.round(motors[i] * 100);
                const bar = document.getElementById(`mbar-${i}`);
                if (bar) {
                    bar.style.height = `${pct}%`;
                    bar.style.background = pct > 85 ? 'var(--danger)' : (pct > 60 ? 'var(--warn)' : 'var(--accent)');
                }
            }

            const q = new THREE.Quaternion(droneBody.quaternion.x, droneBody.quaternion.y, droneBody.quaternion.z, droneBody.quaternion.w);
            const euler = new THREE.Euler().setFromQuaternion(q, 'YXZ');
            const rollDeg = Math.round(THREE.MathUtils.radToDeg(euler.z));
            const pitchDeg = Math.round(THREE.MathUtils.radToDeg(euler.x));

            const peakAmps = phys.electrical?.peak_current_total_a || 90;
            const sysVolt = phys.electrical?.system_voltage_v || 22.2;
            const liveAmps = peakAmps * Math.pow(avgThr, 2.1);
            const liveWatts = Math.round(liveAmps * sysVolt);

            document.getElementById('tel-alt').innerText = `${Math.max(0, droneBody.position.y).toFixed(1)}m`;
            document.getElementById('tel-spd').innerText = `${Math.round(droneBody.velocity.length() * 3.6)}`;
            document.getElementById('tel-att').innerText = `${rollDeg}° / ${pitchDeg}°`;
            document.getElementById('tel-thr').innerText = `${Math.round(avgThr * 100)}%`;
            document.getElementById('tel-amps').innerText = `${liveAmps.toFixed(1)}A`;
            document.getElementById('tel-watts').innerText = `${liveWatts}W`;

            if (workbenchMode === 'FLIGHT' && camMode === 'CHASE') {
                const offset = new THREE.Vector3(0, 0.45, -1.15).applyQuaternion(droneGroup.quaternion);
                camera.position.lerp(droneGroup.position.clone().add(offset), 0.14);
                camera.lookAt(droneGroup.position.clone().add(new THREE.Vector3(0, 0.08, 0)));
            } else if (workbenchMode === 'FLIGHT' && camMode === 'FPV') {
                const fpvOffset = new THREE.Vector3(0, 0.04, 0.12).applyQuaternion(droneGroup.quaternion);
                camera.position.copy(droneGroup.position).add(fpvOffset);
                const lookTarget = droneGroup.position.clone().add(new THREE.Vector3(0, 0.02, 2.0).applyQuaternion(droneGroup.quaternion));
                camera.lookAt(lookTarget);
            } else {
                controls.target.lerp(droneGroup.position, 0.15);
                controls.update();
            }
        } else {
            controls.update();
        }

        renderer.render(scene, camera);
    }

    function renderFirmwareModal() {
        const fw = activeDrone?.technical_data?.firmware_configs;
        if (!fw) return;
        const uarts = fw.uart_map || [];
        document.getElementById('fw-uart-summary').innerHTML = `
            <div class="section-box">
                <div class="section-title"><span>Deterministic UART Bus Allocation</span></div>
                ${uarts.map(u => `<div class="data-row">
                    <span class="data-label"><b>${u.port}</b> (${u.ap_serial}) &rarr; ${u.function}</span>
                    <span class="data-val">${u.protocol} @ ${u.baud}</span>
                </div>`).join('')}
            </div>
        `;
        const codeEl = document.getElementById('fw-code-view');
        codeEl.textContent = activeFwTab === 'BF' ? fw.betaflight_cli_text : fw.ardupilot_param_text;
    }

    function initWorkbench() {
        const skuList = document.getElementById('sku-list');
        FLEET.forEach((sku, idx) => {
            const card = document.createElement('div');
            card.className = 'sku-card';
            const drcValid = sku.technical_data.drc_erc_report?.valid !== false;
            card.innerHTML = `
                <div class="sku-top">
                    <span>${sku.sku_id} &bull; ${sku.class}</span>
                    <span class="badge badge-${drcValid ? 'PASS' : 'FAIL'}">${drcValid ? 'DRC PASS' : 'DRC WARN'}</span>
                </div>
                <div class="sku-title">${sku.anchor_frame}</div>
                <div class="sku-metrics">
                    <div class="metric-pill"><b>${sku.performance.twr}:1</b><span>TWR</span></div>
                    <div class="metric-pill"><b>${sku.performance.total_weight}g</b><span>AUW</span></div>
                    <div class="metric-pill"><b>${sku.performance.flight_time}m</b><span>Hover</span></div>
                </div>
            `;
            card.onclick = () => {
                document.querySelectorAll('.sku-card').forEach(c => c.classList.remove('active'));
                card.classList.add('active');
                document.getElementById('explode-slider').value = 0;
                buildDigitalTwin(sku);
            };
            skuList.appendChild(card);
            if (idx === 0) card.click();
        });

        document.getElementById('mode-cad').onclick = () => {
            workbenchMode = 'CAD';
            document.getElementById('mode-cad').classList.add('active');
            document.getElementById('mode-flight').classList.remove('active');
            document.getElementById('explode-wrap').style.display = 'flex';
            camMode = 'ORBIT';
            document.getElementById('btn-cam-mode').innerText = 'Cam: ORBIT';
            resetSimulation();
            camera.position.set(0.45, 0.35, 0.55);
        };
        document.getElementById('mode-flight').onclick = () => {
            workbenchMode = 'FLIGHT';
            document.getElementById('mode-flight').classList.add('active');
            document.getElementById('mode-cad').classList.remove('active');
            document.getElementById('explode-wrap').style.display = 'none';
            document.getElementById('explode-slider').value = 0;
            applyExplodeSlider(0);
            camMode = 'CHASE';
            document.getElementById('btn-cam-mode').innerText = 'Cam: CHASE';
            resetSimulation();
        };

        document.getElementById('explode-slider').oninput = (e) => applyExplodeSlider(Number(e.target.value));
        document.getElementById('toggle-cog').onclick = (e) => {
            showCoG = !showCoG; cogHelperGroup.visible = showCoG; e.target.classList.toggle('active', showCoG);
        };
        document.getElementById('toggle-clearance').onclick = (e) => {
            showClearance = !showClearance; clearanceRings.forEach(r => r.visible = showClearance); e.target.classList.toggle('active', showClearance);
        };
        document.getElementById('toggle-vectors').onclick = (e) => {
            showVectors = !showVectors; thrustCones.forEach(c => c.visible = showVectors); e.target.classList.toggle('active', showVectors);
        };
        document.getElementById('btn-flight-mode').onclick = (e) => {
            fc.mode = fc.mode === 'ANGLE_ALTHOLD' ? 'ACRO' : 'ANGLE_ALTHOLD';
            e.target.innerText = `FC: ${fc.mode === 'ANGLE_ALTHOLD' ? 'ANGLE + ALT HOLD' : 'ACRO RATE'}`;
        };
        document.getElementById('btn-cam-mode').onclick = (e) => {
            const modes = ['ORBIT', 'CHASE', 'FPV'];
            camMode = modes[(modes.indexOf(camMode) + 1) % modes.length];
            e.target.innerText = `Cam: ${camMode}`;
        };
        document.getElementById('btn-reset-sim').onclick = () => resetSimulation();

        // Firmware Modal Controls
        document.getElementById('btn-fw-modal').onclick = () => {
            renderFirmwareModal();
            document.getElementById('fw-modal').style.display = 'flex';
        };
        document.getElementById('close-fw-modal').onclick = () => {
            document.getElementById('fw-modal').style.display = 'none';
        };
        document.getElementById('tab-bf').onclick = (e) => {
            activeFwTab = 'BF';
            e.target.classList.add('active');
            document.getElementById('tab-ap').classList.remove('active');
            renderFirmwareModal();
        };
        document.getElementById('tab-ap').onclick = (e) => {
            activeFwTab = 'AP';
            e.target.classList.add('active');
            document.getElementById('tab-bf').classList.remove('active');
            renderFirmwareModal();
        };
        document.getElementById('btn-copy-fw').onclick = (e) => {
            const txt = document.getElementById('fw-code-view').textContent;
            navigator.clipboard.writeText(txt);
            e.target.innerText = '✅ Copied!';
            setTimeout(() => { e.target.innerText = '📋 Copy'; }, 1500);
        };
        document.getElementById('btn-dl-fw').onclick = () => {
            const fw = activeDrone?.technical_data?.firmware_configs;
            if (!fw) return;
            if (activeFwTab === 'BF') {
                window.downloadTextFile(fw.betaflight_cli_filename, fw.betaflight_cli_text, 'text/plain');
            } else {
                window.downloadTextFile(fw.ardupilot_param_filename, fw.ardupilot_param_text, 'text/plain');
            }
        };

        // Cost Modal Controls
        document.getElementById('btn-cost-modal').onclick = () => {
            const manifest = activeDrone?.technical_data?.cost_manifest;
            const body = document.getElementById('cost-modal-body');
            if (manifest) {
                let html = `<div style="display:flex; justify-content:space-between; margin-bottom:14px; font-size:14px;">
                    <span>Subtotal: <b>$${manifest.subtotal}</b> | Est. Tax/Ship: <b>$${(manifest.estimated_shipping + manifest.estimated_tax).toFixed(2)}</b></span>
                    <span style="color:var(--accent); font-size:18px; font-weight:700;">Total: $${manifest.total_estimated_cost}</span>
                </div>`;
                for (const [vendor, items] of Object.entries(manifest.vendors || {})) {
                    html += `<div class="section-box" style="margin-bottom:10px;">
                        <div class="section-title"><span>${vendor}</span><span>${items.length} parts</span></div>
                        ${items.map(i => `<div class="data-row">
                            <a class="vendor-link" href="${i.link}" target="_blank">${i.part}: ${i.name}</a>
                            <span class="data-val">$${Number(i.price).toFixed(2)}</span>
                        </div>`).join('')}
                    </div>`;
                }
                body.innerHTML = html;
            }
            document.getElementById('cost-modal').style.display = 'flex';
        };
        document.getElementById('close-cost-modal').onclick = () => {
            document.getElementById('cost-modal').style.display = 'none';
        };

        document.getElementById('btn-export-urdf').onclick = () => {
            if (!activeDrone) return;
            const mp = activeDrone.technical_data.scene_graph.mass_properties;
            const inU = mp.inertia_urdf_kg_m2;
            const urdfXml = `<?xml version="1.0"?>\n<robot name="${activeDrone.sku_id}">\n  <link name="base_link">\n    <inertial>\n      <origin xyz="${mp.cog_m.join(' ')}" rpy="0 0 0"/>\n      <mass value="${mp.total_mass_kg}"/>\n      <inertia ixx="${inU.ixx}" ixy="0" ixz="0" iyy="${inU.iyy}" iyz="0" izz="${inU.izz}"/>\n    </inertial>\n  </link>\n</robot>`;
            window.downloadTextFile(`${activeDrone.sku_id}.urdf`, urdfXml, 'application/xml');
        };

        window.addEventListener('keydown', (e) => {
            if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') keys.climb = 1;
            if (e.code === 'Space') keys.descend = 1;
            if (e.code === 'KeyW') keys.pitch = 1;
            if (e.code === 'KeyS') keys.pitch = -1;
            if (e.code === 'KeyA') keys.roll = -1;
            if (e.code === 'KeyD') keys.roll = 1;
            if (e.code === 'KeyQ') keys.yaw = 1;
            if (e.code === 'KeyE') keys.yaw = -1;
            if (e.code === 'KeyR') resetSimulation();
        });
        window.addEventListener('keyup', (e) => {
            if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') keys.climb = 0;
            if (e.code === 'Space') keys.descend = 0;
            if (['KeyW', 'KeyS'].includes(e.code)) keys.pitch = 0;
            if (['KeyA', 'KeyD'].includes(e.code)) keys.roll = 0;
            if (['KeyQ', 'KeyE'].includes(e.code)) keys.yaw = 0;
        });
        window.addEventListener('resize', () => {
            camera.aspect = container.clientWidth / container.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(container.clientWidth, container.clientHeight);
        });

        animate();
    }

    initWorkbench();
</script>
</body>
</html>
"""


def sanitize_floats(obj):
    if isinstance(obj, float):
        return 0.0 if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_floats(v) for v in obj]
    return obj


def upgrade_catalog_in_place(catalog: list[dict]) -> list[dict]:
    """
    Upgrades every SKU in drone_catalog.json with:
      - Normalized BOM & First-Principles Physics
      - Auto-Generated 3D-Printable TPU & CF-PETG Mounts (.STL)
      - Inertia-Scaled Betaflight 4.5 CLI (.txt) & ArduPilot (.param) Firmware
    """
    compat = CompatibilityService()
    upgraded = []

    for sku in catalog:
        sku_id = sku.get("sku_id", "OF-AI-1000")
        bom = normalize_bom(sku.get("bom", []))
        scene_graph = generate_scene_graph({"mission_name": sku.get("class", "Industrial")}, bom)
        physics = generate_physics_config(bom)
        physics["center_of_mass_offset"] = scene_graph["mass_properties"]["cog_m"]

        drc_erc = compat.validate_build(bom, scene_graph=scene_graph, physics_config=physics, sku_id=sku_id)
        existing_cats = {b["category"] for b in bom}
        for extra in drc_erc.get("required_accessories", []):
            if extra["category"] not in existing_cats:
                bom.append(normalize_component(extra))

        # Add 3D-printed mounts mass into mass breakdown
        mounts = drc_erc.get("printable_mounts", [])
        mounts_mass_g = round(sum(m.get("weight_g", 0.0) for m in mounts), 1)
        if mounts_mass_g > 0:
            physics["mass_breakdown"].append({
                "category": "3D_Printed_Mounts",
                "model_name": f"{len(mounts)}x Custom TPU/CF-PETG Mounts",
                "unit_weight_g": mounts_mass_g,
                "quantity": 1,
                "total_weight_g": mounts_mass_g,
                "empirical": True,
            })
            physics["meta"]["total_weight_g"] = round(physics["meta"]["total_weight_g"] + mounts_mass_g, 1)
            physics["mass_kg"] = round(physics["meta"]["total_weight_g"] / 1000.0, 3)

        firmware_configs = generate_firmware_configs(sku_id, bom, physics, scene_graph)
        cost_manifest = generate_procurement_manifest(bom)

        sku["bom"] = bom
        sku["performance"] = {
            "twr": physics["dynamics"]["twr"],
            "hover_throttle_pct": physics["dynamics"]["hover_throttle_pct"],
            "flight_time": physics["meta"]["est_flight_time_min"],
            "mixed_flight_time": physics["meta"]["mixed_flight_time_min"],
            "total_weight": physics["meta"]["total_weight_g"],
            "top_speed_kmh": physics["aerodynamics"]["top_speed_kmh"],
            "disk_loading_g_dm2": physics["aerodynamics"]["disk_loading_g_dm2"],
        }
        tech = sku.setdefault("technical_data", {})
        tech["physics_config"] = physics
        tech["scene_graph"] = scene_graph
        tech["drc_erc_report"] = drc_erc
        tech["printable_mounts"] = mounts
        tech["firmware_configs"] = firmware_configs
        tech["cost_manifest"] = cost_manifest
        upgraded.append(sku)

    return upgraded


def launch_workbench():
    if not os.path.exists(CATALOG_FILE):
        print(f"❌ No catalog found at {CATALOG_FILE}. Run tools/design_fleet.py first.")
        return

    with open(CATALOG_FILE, "r") as f:
        raw_catalog = json.load(f)

    print("🔧 Compiling 3D-Printable Mounts (.STL), Betaflight/ArduPilot Firmware & Physics...")
    upgraded_catalog = sanitize_floats(upgrade_catalog_in_place(raw_catalog))

    with open(CATALOG_FILE, "w") as f:
        json.dump(upgraded_catalog, f, indent=2)

    os.makedirs(os.path.dirname(TEMPLATE_OUT), exist_ok=True)
    with open(TEMPLATE_OUT, "w") as f:
        f.write(WORKBENCH_HTML_TEMPLATE)

    html_out = WORKBENCH_HTML_TEMPLATE.replace("__FLEET_DATA__", json.dumps(upgraded_catalog))
    with open(OUTPUT_HTML, "w") as f:
        f.write(html_out)

    print(f"✅ Engineering Workbench v5.0 compiled: {OUTPUT_HTML}")
    socketserver.TCPServer.allow_reuse_address = True
    PORT = 8000
    Handler = http.server.SimpleHTTPRequestHandler

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}/dashboard.html"
        print(f"🌍 OpenForge MBSE Workbench active at: {url}")
        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Workbench server stopped.")


if __name__ == "__main__":
    launch_workbench()
# --- END OF FILE tools/launch_workbench.py ---