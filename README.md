
**The First Open Source Autonomous Supply Chain Agent.**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Gemini Powered](https://img.shields.io/badge/AI-Gemini_Pro_Vision-orange)](https://deepmind.google/technologies/gemini/)
[![Status](https://img.shields.io/badge/Status-Public_Beta-green)]()

> **"Don't just generate code. Generate physical objects."**

---

## 📜 The Manifesto
Hardware engineering is gatekept by expensive consultants and proprietary supply chains. **OpenForge** is an attempt to democratize physical creation.

This is not a chatbot. It is an **Agentic Framework** that acts as a Chief Engineer, Sourcing Manager, and Physics Simulator in one. It takes a prompt, validates the physics, finds the real parts in stock, and generates the files to build it.

**We are building the "Linux of Manufacturing."**

---

## 🧠 How It Works
Unlike standard LLMs which hallucinate physical specifications, OpenForge uses a **"Hardware-Aware" architecture**. It grounds its creativity in reality by using Computer Vision to read datasheets, Python simulations to validate flight physics, and OpenSCAD to generate physical geometry.

### The "Self-Healing" Loop
The core differentiator is the **Optimization Agent**. If the sourced parts fail the physics simulation (e.g., TWR < 1.5), the system doesn't error out. It *reasons* about the failure, swaps components (e.g., "Upgrade motors from 2207 to 2306"), and re-simulates until it passes.

```mermaid
graph TD
    User[User Prompt] --> Intake(Intake Agent)
    Intake --> Specs(Spec Generator)
    Specs --> Fusion{Fusion Sourcing}
    Fusion -->|Search| Google[Google Shopping]
    Fusion -->|Scrape| Recon[Playwright Scraper]
    Fusion -->|Verify| Vision[Gemini Vision AI]
    Vision --> BOM[Verified BOM]
    BOM --> Physics{Physics Validator}
    Physics -->|Pass| Architect(CAD Engine)
    Physics -->|Fail: Low TWR| Optimization(Optimization Agent)
    Optimization -->|Revise Specs| Fusion
    Architect --> STL[STL Files]
    BOM --> Schematics(Wiring Diagram)
    BOM --> Costing(Procurement)
    STL & Schematics & Costing --> Dashboard[Interactive HTML Dashboard]
```

---

## ✨ Key Features

*   **⚛️ Data Fusion Sourcing:** Orchestrates parallel searches across multiple vendors (Amazon, GetFPV, Pyrodrone). It merges the best *pricing* data with the best *technical* data to create a "Composite Component."
*   **👁️ Multimodal Vision Verification:** Uses **Gemini Pro Vision** to "look" at product images and extract critical engineering constraints (e.g., measuring bolt patterns from a JPEG) that are missing from text descriptions.
*   **🚀 Physics Sandbox:** Runs a Dockerized physics engine to calculate Thrust-to-Weight Ratios (TWR), Disk Loading, and estimated flight times *before* you buy a single part.
*   **📐 Generative CAD:** Dynamically generates `.scad` and `.stl` files for the frame, tailored to the exact dimensions of the sourced components.
*   **⚡ Automated Electrical Schematics:** Generates a visual wiring diagram (PNG) showing exactly how to connect the specific peripherals (GPS, Receiver, VTX) to the selected Flight Controller.

---

## 🛠️ Tech Stack

*   **Core:** Python 3.10+, FastAPI
*   **Orchestration:** Celery, Redis (Task Queue)
*   **Intelligence:** Google Gemini Pro (Logic) + Gemini Pro Vision (Visual Extraction)
*   **Reconnaissance:** Playwright (Headless Browser), Serper/Google Search API
*   **Engineering:** OpenSCAD (Parametric CAD), Graphviz (Schematics), NumPy (Physics)

---

## 🚀 Getting Started

### Prerequisites
*   **Python 3.10+**
*   **Google Gemini API Key** (Free tier available)
*   **Google Custom Search / Serper Key**

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/OpenForge.git
cd OpenForge
```

### 2. Environment Setup
Create a `.env` file (see `.env.example`):
```bash
GOOGLE_API_KEY="your_gemini_key"
SERPER_API_KEY="your_serper_key"
DATABASE_URL="postgresql+asyncpg://user:password@db/drone_db"
```

### 3. Install Dependencies
```bash
# Install System Tools (Debian/Ubuntu)
sudo apt-get update && sudo apt-get install openscad graphviz

# Install Python Deps
pip install -r requirements.txt
playwright install chromium
```

### 4. Run the Master Pipeline
Witness the entire lifecycle from prompt to dashboard:

```bash
python -m scripts.test_all_systems
```

---

## 🤝 Contributing & Roadmap

**This project is community-driven.** We are looking for contributors to help expand beyond drones into other hardware verticals (Robotics, IoT, PCBs).

*   [ ] **Add New Scrapers:** Help us support DigiKey, Mouser, and AliExpress.
*   [ ] **Improve Physics:** Add drag coefficient calculations for different frame geometries.
*   [ ] **Frontend:** Port the dashboard to React/Next.js.

**Found a bug?** Open an issue.
**Have a feature idea?** Join the discussion on [Discord](Link_To_Discord) or submit a PR.

---

## ⚠️ Disclaimer

*   **Safety:** Lithium Polymer (LiPo) batteries and high-speed propellers are dangerous. This tool generates *theoretical* designs. Always verify wiring diagrams and physics calculations manually.
*   **Scraping:** The reconnaissance module uses a headless browser to scrape public e-commerce data. Respect `robots.txt` and rate limits.

---

## 📜 License

**AGPL v3 License.**

*   **Free for Open Source:** You are free to use, modify, and distribute this software for open projects.
*   **Paid for Closed Source:** If you use this code in a proprietary service, you *must* open-source your changes or contact us for a commercial license.

---

### 💡 Why the changes?

1.  **The Name Change:** "OpenForge" sounds like a platform. "Drone Architect" sounds like a single-use script.
2.  **The Manifesto:** This addresses the "VC ghosting" issue by framing the project as a movement for democratization. It gives people a reason to star the repo beyond just the code.
3.  **The "AGPL" Badge:** This is a signal to the VCs. It effectively says "You can't steal this now."
4.  **Vision Verification Emphasis:** This is your strongest technical "moat." It is highlighted earlier in the text.
5.  **Call for Contributors:** Explicitly mentioning DigiKey/Mouser signals the ambition to go beyond hobby drones into professional engineering.
