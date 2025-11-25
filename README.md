# OpenForge Drone Architect

<div align="center">

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()

An AI-powered generative engineering system that designs, validates, and documents custom FPV drones from natural language requirements.

</div>

![OpenForge Demo GIF](https://user-images.githubusercontent.com/username/repo/assets/openforge_demo.gif)

---

## About The Project

Designing and building custom drones is a complex, iterative process requiring deep domain knowledge in electronics, aerodynamics, and supply chain logistics. A single incompatible component can invalidate an entire design, leading to wasted time and money.

**OpenForge** is a proof-of-concept that reimagines this workflow. It acts as an autonomous engineering partner, leveraging a team of specialized AI agents to translate a high-level mission requirement into a fully validated, buildable, and documented drone design.

The system is designed to be **resilient and intelligent**. It doesn't just follow a static template; it generates a custom design plan, sources real-world components, and validates their conceptual and geometric compatibility. When it encounters a problem—from a sourcing failure to a physical collision in the CAD model—it enters a self-correction loop, diagnoses the issue, and attempts to fix it automatically.

The final output is not just a parts list, but a comprehensive **Digital Twin**: an interactive, 3D dashboard complete with an animated assembly guide, flight performance simulations, and a full procurement manifest.

### Key Features

*   **Natural Language Interface:** Start your design with a simple, high-level prompt (e.g., "a 7-inch long-range drone for autonomous animal detection").
*   **Dynamic System Architecture:** An AI "System Architect" dynamically determines the required component categories for each unique mission, moving beyond static templates.
*   **AI-Powered Validation Loop:** The system validates the design for both **conceptual compatibility** (do the parts make sense together?) and **geometric integrity** (do the parts physically fit?).
*   **Autonomous Self-Correction:** If a design fails validation, an "Optimization Engineer" AI diagnoses the problem and attempts to fix it by sourcing a new, more compatible part.
*   **"Nuke and Rebuild" Strategy:** For fundamentally flawed designs, the system intelligently scraps the entire Bill of Materials and re-architects the build around a new, known-good "anchor" component.
*   **Generative CAD:** Automatically produces 3D-printable STL models for all components using a programmatic CAD backend (OpenSCAD).
*   **Physics Simulation:** Simulates key flight metrics like Thrust-to-Weight Ratio (TWR), estimated flight time, and hover throttle.
*   **Interactive Digital Twin:** Generates a final HTML dashboard with a 3D model viewer, step-by-step animated assembly, parts list, and performance charts.

## How It Works: The AI Agent Workflow

OpenForge operates as a pipeline of specialized AI agents, each with a distinct role.

1.  **User Input & Planning:**
    *   **Chief Architect:** Analyzes the user's natural language prompt to create a high-level engineering plan.
    *   **Human-in-the-Loop:** Asks clarifying questions if critical information is missing.

2.  **Dynamic Design & Sourcing:**
    *   **System Architect:** Reads the engineering plan and dynamically generates a list of all required component categories (e.g., `['Frame_Kit', 'Motors', 'Companion_Computer']`).
    *   **Sourcing Engineer:** Creates specific, high-quality search queries for each component category based on the plan.
    *   **Fusion Service:** Executes the search, scrapes product pages for data, and uses a dynamic vision analysis pipeline to extract engineering specs from product images.
        *   **Vision Prompt Engineer (Meta-AI):** For each component type, this agent writes a custom prompt for the Vision AI.
        *   **Vision AI:** Executes the custom prompt to analyze the image.

3.  **Validation & Correction Loop:**
    *   **Master Builder:** Analyzes the complete Bill of Materials (BOM) for conceptual compatibility. If a part is illogical (e.g., an e-bike kit instead of a frame), it triggers a failure.
    *   **CAD Service:** If the build is conceptually sound, it generates a virtually assembled 3D model based on the AI's blueprint.
    *   **Geometry Simulator:** Performs mathematical checks on the CAD model to detect physical collisions (e.g., propellers striking each other).
    *   **Optimization Engineer:** If any validation step fails, this agent receives the failure report, diagnoses the root cause, and proposes a fix (either a single part replacement or a full "Nuke and Rebuild"). The loop then restarts.

4.  **Finalization:**
    *   Once a design passes all validation checks, the system generates the final physics simulations, cost analysis, wiring diagrams, and the interactive Digital Twin dashboard.

## Technology Stack

*   **Backend:** Python 3.10+, asyncio
*   **AI & Machine Learning:** Google Gemini Pro & Gemini Pro Vision
*   **Data Acquisition:** Playwright (Web Scraping), Google Custom Search API
*   **3D Modeling:** OpenSCAD (Programmatic CAD Generation)
*   **Frontend (Digital Twin):** HTML, TailwindCSS, Three.js (3D Rendering), GSAP (Animation), Chart.js (Data Visualization)

## Getting Started

Follow these steps to set up and run the project locally.

### Prerequisites

*   **Python 3.10+**
*   **OpenSCAD:** The command-line tool must be installed and available in your system's PATH. You can download it from [openscad.org](https://openscad.org/downloads.html).
*   **API Keys:**
    *   Google AI API Key (for Gemini)
    *   Google Custom Search Engine API Key and Search Engine ID

### Installation

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/your-username/openforge-drone-architect.git
    cd openforge-drone-architect
    ```

2.  **Create and activate a virtual environment:**
    ```sh
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the required Python packages:**
    ```sh
    pip install -r requirements.txt
    ```

4.  **Install Playwright browsers:**
    ```sh
    playwright install
    ```

5.  **Configure your environment variables:**
    *   Create a file named `.env` in the root of the project.
    *   Copy the contents of `.env.example` into it and fill in your API keys.

    ```.env
    GOOGLE_API_KEY="your_google_ai_api_key"
    GOOGLE_SEARCH_ENGINE_ID="your_custom_search_engine_id"
    ```

### Usage

1.  Run the main application from the root directory:
    ```sh
    python3 main.py
    ```

2.  The application will start in your terminal. Enter your drone requirements at the prompt.

3.  Follow the on-screen instructions and answer any clarifying questions from the AI.

4.  Upon successful completion, the final Digital Twin dashboard (`output/dashboard.html`) will automatically open in your default web browser. A `master_record.json` file containing a full audit trail of the generation process will also be saved in the `output` directory.

## Project Structure

```
/
├── app/
│   ├── services/
│   │   ├── ai_service.py       # Core AI agent functions and prompts
│   │   ├── cad_service.py      # Generates 3D models with OpenSCAD
│   │   ├── fusion_service.py   # Orchestrates search, scraping, and vision
│   │   ├── vision_service.py   # Dynamic Gemini Vision executor
│   │   ├── recon_service.py    # Playwright-based web scraper
│   │   └── ...                 # Other services (cost, physics, etc.)
│   └── prompts.py              # Contains all master prompts for the AI agents
├── cad/
│   └── library.scad            # Parametric OpenSCAD library for drone parts
├── output/                     # Default location for generated files
├── templates/
│   └── dashboard.html          # Template for the final Digital Twin
├── main.py                     # Main application entry point and orchestrator
├── requirements.txt
└── .env.example
```

## Roadmap

*   [ ] **Advanced CAD Generation:** Implement procedural generation of wiring channels, antenna mounts, and aerodynamically optimized surfaces.
*   [ ] **Enhanced Human-in-the-Loop:** Allow the user to provide natural language feedback to correct a failed design instead of just halting.
*   [ ] **Cost & Performance Optimization:** Add an AI agent that can make intelligent trade-offs between cost and performance to meet a specific budget.
*   [ ] **AI Result Caching:** Implement a caching layer (e.g., using Redis) to store the results of expensive AI calls (like `generate_vision_prompt`) to improve speed and reduce costs on subsequent runs.
*   [ ] **Expanded Component Library:** Teach the "Vision Prompt Engineer" about a wider array of component types (e.g., gimbals, LiDAR sensors, parachutes).

## Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

## License
