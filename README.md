
```
## Version Notes - v2.0 (November 2025)
**Major Architectural Overhaul:**
*   **CAD Engine:** Migrated from OpenSCAD to **CadQuery**. The system now understands object-oriented geometry (Mass, Inertia, Center of Gravity) rather than just string manipulation.
*   **Physics Engine:** Migrated from static math scripts (`calc_twr.py`) to **PyBullet**. The system now exports URDF files and performs dynamic flight simulation (Hover, Barrel Rolls, Loops) with a virtual PID controller.
*   **Evolutionary Loop:** Implemented `auto_engineer.py`. The system now iteratively designs, builds, flies, crashes, analyzes telemetry, and rebuilds the hardware automatically until performance criteria are met.

# OpenForge
**A Hardware-Aware Agentic Framework for Autonomous Engineering.**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Engine: CadQuery](https://img.shields.io/badge/CAD-CadQuery-red)](https://cadquery.readthedocs.io/)
[![Sim: PyBullet](https://img.shields.io/badge/Physics-PyBullet-yellow)](https://pybullet.org/)
[![Status](https://img.shields.io/badge/Status-Active_Development-green)]()

> **"Neuro-Symbolic Architecture for Physical Systems: AI for Reasoning, Code for Physics."**

---

## 📜 Overview

OpenForge is an experiment in **Evolutionary Manufacturing**. It demonstrates how Large Language Models (LLMs) can be grounded in physical reality by chaining them with deterministic engineering simulation tools.

Unlike standard chatbots that hallucinate physical specifications, OpenForge uses a **Closed-Loop Engineering System**:
1.  **The Architect (AI):** Defines the high-level topology (e.g., "5-inch Freestyle Drone").
2.  **The Forge (CadQuery):** Procedurally generates the mechanical assembly and calculates the Inertia Tensor.
3.  **The Proving Ground (PyBullet):** Spawns the Digital Twin in a physics sandbox and attempts autonomous flight maneuvers.
4.  **The Optimizer (Heuristic/AI):** Analyzes crash telemetry (e.g., "Rollover at T=2.4s") and mutates the hardware specs to fix the flaw.

---

## 🧠 Architecture: The Evolutionary Loop

The core differentiator of OpenForge is the **Self-Healing Loop**. It does not just generate a design; it *proves* it works.

If a design fails the flight test (e.g., crashes during a loop-de-loop), the system catches the failure event. The Optimization Agent reasons about the physics (e.g., *"The drone was too heavy to recover from the dive; increasing propeller surface area"*), modifies the blueprint, and re-runs the simulation.

```mermaid
graph TD
    User[User Prompt] --> Architect(Architect Agent)
    Architect --> Specs[Parametric Specs]
    Specs --> CAD{CAD Engine}
    CAD -->|Generate| STL[STL Meshes]
    CAD -->|Calculate| URDF[Physics Definition]
    URDF --> Sim{PyBullet Sim}
    Sim -->|Run Scenario| FlightController(Virtual Pilot)
    FlightController -->|Telemetry| Report[Flight Report]
    Report -->|Success| Master[Master Record (DNA)]
    Report -->|Crash/Fail| Optimizer(Optimization Agent)
    Optimizer -->|Mutate Specs| Specs
```

---

## ✨ Key Capabilities

*   **🏭 High-Fidelity CAD Generation:** Uses **CadQuery** to generate constraint-based assemblies. The system models specific components (Motors, Stacks, Batteries) and "mates" them to a procedurally generated frame, ensuring exact fitment and accurate center-of-mass calculations.
*   **🧪 Dynamic Physics Simulation:** Instead of simple math checks, OpenForge exports a **URDF (Unified Robot Description Format)** file. It simulates Aerodynamic Drag, Motor Thrust curves, and PID Control loops in **PyBullet**.
*   **🎥 Automated Forensic Logging:** Every simulation run is recorded. The system generates `.mp4` video files of the flight tests (hovering, acrobatic stunts) alongside JSON telemetry logs, creating an audit trail of *why* a design succeeded or failed.
*   **🧬 Evolutionary Optimization:** The system runs in generations. It can start with a flawed design (e.g., tiny props on a heavy frame), watch it fail, and iteratively evolve the hardware geometry until it achieves stable flight.

---

## 🛠️ Tech Stack

*   **Core Logic:** Python 3.10+
*   **CAD Engine:** CadQuery (Parametric Geometry & STEP Export)
*   **Physics Engine:** PyBullet (Rigid Body Dynamics & Collision)
*   **Math:** NumPy (Vector math for PID controllers)
*   **Visualization:** Graphviz (Schematics) & Browser-based Video/GLTF

---

## 🚀 Getting Started

### Prerequisites
*   **Python 3.10+**
*   **FFmpeg** (Required for video recording in PyBullet)

### 1. Installation
```bash
git clone https://github.com/yourusername/OpenForge.git
cd OpenForge
pip install -r requirements.txt
# Ensure you have cadquery, pybullet, numpy, and scipy installed
```

### 2. Run the Autonomous Engineer
To witness the full Evolution Cycle (Design -> Build -> Fly -> Fix):

```bash
python auto_engineer.py
```

### 3. Analyze the Results
The system creates a `static/evolution` directory. Inside, you will find folders for each generation (`gen_1`, `gen_2`...):
*   `flight.mp4`: A video recording of the simulation test.
*   `drone.urdf`: The physics description file.
*   `master_dna.json`: The specs and performance metrics.
*   `base.stl` / `prop.stl`: The 3D printable files.

---

## 🤝 Contributing

This project is a framework for **Hardware-Aware AI**. We are looking for contributors to help expand the "Vertical Slice":

*   **Aerodynamics:** Implement more complex drag models (CFD approximation).
*   **Sourcing:** Re-integrate the Live Sourcing/Price Check module with the new CAD pipeline.
*   **Frontend:** Build a React/Three.js dashboard to visualize the evolution history in real-time.

---

## 📜 License

**AGPL v3 License.**

*   **Open Source:** Free to use and modify for open projects.
*   **Commercial:** Proprietary use requires a commercial license.
```
