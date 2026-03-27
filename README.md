# 🚦 ATOMS: Advanced Traffic Optimization & Monitoring System

[![Vite](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-646CFF?logo=vite)](https://vitejs.dev/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![YOLOv8](https://img.shields.io/badge/AI-YOLOv8%20Detection-FF2D20?logo=yolo)](https://github.com/ultralytics/ultralytics)
[![License](https://img.shields.io/badge/License-Proprietary-CD7F32)](LICENSE)

**ATOMS** is a next-generation traffic intelligence platform engineered to revolutionize urban mobility. By fusing ultra-realistic 3D simulation with real-time AI computer vision and predictive emergency preemption, ATOMS provides city planners and traffic operators with a unified "digital twin" of their urban infrastructure.

---

## ✨ Key Pillars of ATOMS

### 🏙️ 1. High-Fidelity 3D Digital Twin
Experience traffic as it happens. Our **React Three Fiber** engine renders massive junctions with smooth, physics-based vehicle interpolation, allowing operators to monitor congestion in a way traditional 2D maps never could.

### 🧠 2. AI-Driven Computer Vision (Live CV)
Stop relying on manual counts. Our integrated **YOLOv8 pipeline** automatically detects vehicle classes (cars, buses, bikes) and prioritizes emergency vehicles (ambulances) in real-time, feeding live queue metrics directly into the controller.

### 🚑 3. Emergency Preemption & Green Waves
Seconds save lives. ATOMS predicts emergency vehicle paths and automatically coordinates "Green Waves" across multiple junctions, clearing the corridor before the ambulance even arrives.

### 📊 4. Predictive Analytics & ROI Calculator
Make data-driven decisions. The built-in Impact Dashboard translates simulation metrics into real-world cost savings, fuel reduction, and emission targets, making the business case for smart-city rollout effortless.

---

## 🛠️ Technology Stack

| Layer | Technologies |
| --- | --- |
| **Simulation Engine** | Python, Custom Vector Math, Deterministic State Management |
| **Real-time Backend** | FastAPI, WebSockets, Python 3.10+ |
| **Web Operator UI** | React, Vite, Tailwind CSS, Framer Motion |
| **3D Rendering** | React Three Fiber (Three.js), Instanced Mesh Rendering |
| **AI / Machine Learning** | YOLOv8 (Detection), Custom CNN (Ambulance Classification) |
| **Geospatial** | Leaflet, Google Maps Directions Integration |

---

## 🚀 Quick Start (Local Setup)

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1️⃣ Backend Setup
```powershell
# Create environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r realtime_server\requirements.txt
pip install streamlit plotly
```

### 2️⃣ Frontend Setup
```powershell
cd frontend
npm install
cd ..
```

### 3️⃣ Launch the Platform
```powershell
# Start Backend (Sim Server + AI APIs)
uvicorn realtime_server.main:app --reload --port 8000

# Start Frontend Dashboard (separate terminal)
cd frontend
npm run dev
```
Visit `http://localhost:5173` to see the future of traffic.

---

## 📈 Business Value & Scalability

ATOMS is designed for scale. From a single junction to a city-wide grid:
- **Modular Architecture**: Swap simulation engines or AI models without touching the UI.
- **Hardware Integration**: Hooks for physical Arduino/PLC signal controllers.
- **Data Privacy**: Local AI processing ensures video streams never leave your infrastructure.

---

## 🗺️ Roadmap
- [ ] **Adaptive Reinforcement Learning**: Self-optimizing signal timings based on weekly trends.
- [ ] **V2X Integration**: Direct communication with connected vehicles for ultra-safe junctions.
- [ ] **Mobile Operator App**: Native iOS/Android alerts for field responders.

---

© 2026 ATOMS Project Team. Built for the future of urban mobility.
