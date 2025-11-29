Drone_3 works end to end however the physics video game simulator needs work as drones are difficult to control and graphics could be less blocky.  The program will render 2 drone constructions which is pretty good since we start from scratch with some basic user requriments and end up with enough parts with good specs through the fusion process to create unique drones.  However these drones are not perfectly aligned or matched up perfectly.  This can be fixed by running the seed and refine .py's multiple times to populate the inventory robustly then seed_ecosystem to look sideways and find the parts needed.  this verges on just a really advanced scrape project with some nifty tricks to force a way to create a catalog robust enough to generate a drone by creating its own kit.  it would be interesting to see how this worked on real database but for now it is a good excersize in llm orch as well as viz. 

seed.py
seed_ecosystem.py
refine_arsenal.py
design_fleet.py

# OpenForge: Neuro-Symbolic Manufacturing Engine

<div align="center">

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-red.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Status](https://img.shields.io/badge/Status-V2_Architecture-green.svg)]()

I challenged myself to test the new Gemini 3.0 to see how far its reasoning capabilities could push actual engineering tasks. The result is OpenForge: a Neuro-Symbolic Manufacturing Engine that translates user intent into flight-proven hardware designs and generates a physics-based simulation to test them. An AI system that builds its own inventory, creates virtual products, and simulates mission-critical robotics.

</div>

---

**OpenForge is a research prototype exploring AI-driven design automation. It demonstrates how constraint propagation, multi-modal verification, and
deterministic validation can work together to automate hardware engineering tasks.** 

Traditional AI tools operate on text. OpenForge operates on **Physics and Supply Chains**. It utilizes a multi-agent architecture to scour the global market for components, verify them using Computer Vision, procedurally generate valid engineering assemblies, and simulate them in a browser-based physics engine.

It transforms **Natural Language Intent** (e.g., "I need to inspect fences autonomously") into **Verified Engineering Reality** (BOMs, Blueprints, and Flight Simulations).

## 🚀 Key Capabilities

### 1. The Arsenal (Active Supply Chain)
*   **The Constraint Chain:** We don't just search for "motors." An **Architect Agent** first translates user intent ("Brush Buster") into physics constraints ("Stator Volume > 2306", "Arm Thickness > 5mm").
*   **The Refinery:** A high-agency background worker (`refine_arsenal.py`) that audits the database. If a spec is missing, it spins up a headless browser, **clicks "Specifications" tabs**, reads the DOM, and updates the record.
*   **Visual Forensics:** Uses Vision AI to read PCB silkscreens and technical drawings to verify data that text scrapers miss.

### 2. The Fabricator (Logic-Gated Manufacturing)
*   **The Class Filter:** Instead of random combinations, the engine intelligently buckets parts (e.g., "7-inch Long Range", "Heavy Lift"). It only attempts to build drones with components in the same class.
*   **The Logic Gate:** A deterministic `CompatibilityService` that enforces hard physics rules *before* AI generation:
    *   **Voltage:** Checks `Battery Cells` vs `Motor KV` (Prevents fires).
    *   **Protocol:** Checks `UART Count` vs `Peripherals` (Prevents I/O bottlenecks).
    *   **Geometry:** Checks `Prop Size` vs `Frame Clearance` (Prevents collisions).

### 3. The Virtual Prototyping Lab (Simulation)
*   **Browser-Based Game Engine:** A fully interactive 3D simulator running on **Three.js** and **Cannon.js**.
*   **Real Physics:** Flight characteristics (inertia, drag, thrust) are derived from the actual mass and motor curves of the sourced parts.
*   **Procedural Environment:** The sim generates context-aware environments (Trees, Cows, Buildings) to test the drone's intended use case.

## 🛠️ Architecture

OpenForge separates Data Acquisition, Product Generation, and User Interaction into distinct layers.

<div align="center">

```mermaid
graph TD
    %% --- STYLING ---
    classDef agent fill:#1a202c,stroke:#00ff88,stroke-width:2px,color:#fff,rx:5,ry:5;
    classDef data fill:#2d3748,stroke:#F6E05E,stroke-width:2px,color:#fff,shape:cylinder;
    classDef logic fill:#1a202c,stroke:#FF5555,stroke-width:2px,color:#fff,shape:rhombus;
    classDef output fill:#1a202c,stroke:#3182ce,stroke-width:2px,color:#fff;
    classDef cluster fill:#111,stroke:#444,stroke-width:1px,color:#ccc;

    %% --- LAYER 1 ---
    subgraph L1 [Layer 1: The Active Supply Chain]
        direction TB
        Seed[Seed Agent]:::agent -->|Broad Search| Raw[Raw Inventory]:::data
        Raw -->|Audit Missing Specs| Refinery[Refinery Agent]:::agent
        Refinery -->|Agentic Browsing / Clicks| Arsenal[(Verified Arsenal)]:::data
    end

    %% --- LAYER 2 ---
    subgraph L2 [Layer 2: The Factory]
        direction TB
        Arsenal --> Fabricator[Fabricator Script]:::agent
        Fabricator -->|Classify & Bucket| Gate{Logic Gate}:::logic
        Gate -- Physics Fail --> Discard[Discard]:::output
        Gate -- Pass --> Builder[AI Assembler]:::agent
        Builder -->|Mint SKU| Catalog[(Catalog JSON)]:::data
    end

    %% --- LAYER 3 ---
    subgraph L3 [Layer 3: The Interface]
        direction TB
        User((User)):::output -->|Natural Language| Architect[Architect Agent]:::agent
        Architect <-->|Query Matches| Catalog
        Architect -->|Select Anchor| Twin[Digital Twin Generator]:::output
        
        Twin --> Sim[Three.js Flight Sim]:::output
        Twin --> Docs[Assembly Guide]:::output
    end

    %% --- CONNECTIONS BETWEEN LAYERS ---
    %% (Implicitly handled by node placement, but enforced here for clarity)
    style L1 fill:#0d1117,stroke:#333,stroke-width:2px
    style L2 fill:#0d1117,stroke:#333,stroke-width:2px
    style L3 fill:#0d1117,stroke:#333,stroke-width:2px
```
</div>

## 📦 Installation

#### Prerequisites
*   **Python 3.10+**
*   **Playwright:** Required for the active refinery agent.
*   **Google Gemini API Key:** (Visual Reasoning & Logic)
*   **Google Custom Search API Key:** (Web Recon)

#### Setup
1.  **Clone the repository:**
    ```sh
    git clone https://github.com/your-username/openforge.git
    cd openforge
    ```

2.  **Install dependencies:**
    ```sh
    pip install -r requirements.txt
    playwright install chromium
    ```

3.  **Configuration:**
    Set your API keys in `app/config.py` or environment variables.

## 🖥️ Usage

### 1. Seed & Refine (The Data Loop)
Populate your local database and let the AI "fix" missing data.
```sh
# Step 1: Broad search based on constraints
python tools/seed_arsenal.py

# Step 2: Active investigation (Clicks tabs, reads screenshots)
python tools/refine_arsenal.py

# Step 3: Grade your data quality
python tools/inspect_data_quality.py
```

### 2. Design the Fleet (The Logic Loop)
Ask the AI to select optimal combinations from your refined inventory.
```sh
python tools/design_fleet.py
```

### 3. Fly (The Simulation)
Launch the physics engine.
```sh
python tools/fly_drone.py
```

## 🗺️ Roadmap

| Feature | Status | Description |
| :--- | :--- | :--- |
| **Constraint Solving** | 🟢 **Done** | Translates "intent" to "physics" before sourcing. |
| **Active Refinery** | 🟢 **Done** | Agentic browsing to click UI elements and find hidden specs. |
| **Physics Logic Gate** | 🟢 **Done** | Deterministic code prevents AI from building unflyable drones. |
| **3D Simulator** | 🟢 **Done** | Procedural "Game Engine" based on real component specs. |
| **Feedback Loop** | 🟡 **In Progress** | If a build fails, auto-trigger the Sourcer to find the missing part. |
| **Cost Optimization** | 🔴 **Planned** | Genetic algorithm to find the cheapest valid configuration. |

## 📄 License

This project is licensed under the AGPL v3.
```
