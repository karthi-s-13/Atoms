# ATOMS

ATOMS is a traffic intelligence and emergency-response demo platform built as one repository. It combines:

- a Python traffic simulation engine
- a FastAPI realtime backend
- a React + Vite operator dashboard
- Live CV traffic analysis with YOLO-based detection
- a Leaflet map view for junction monitoring and emergency corridor planning
- shared Python and TypeScript contracts
- local ML model files and training datasets

The repository is organized for local development on Windows, but the code is standard Python and Node.js code and can be adapted to other environments.

## What This Project Does

ATOMS is not just a single simulation screen. The codebase currently supports six major product surfaces:

1. A realtime traffic simulation with play, pause, reset, speed control, traffic presets, custom route weights, and fixed vs adaptive signal modes.
2. A 3D operator view that renders the junction with React Three Fiber and keeps motion smooth through buffered interpolation instead of snapping every websocket frame.
3. A dashboard for wait time, throughput, queue pressure, event logs, and vehicle mix.
4. An impact calculator that turns live simulation metrics into multi-city rollout estimates.
5. A Live CV workflow that accepts browser camera input or uploaded image/video, runs vehicle and ambulance detection, estimates queue and density, and recommends which approach should receive green.
6. A map-based emergency simulation workspace that streams junction state, predicts congestion, visualizes route-wide signal coordination, and can enrich the ambulance route with Google Directions data.

## Architecture

### 1. `simulation_engine/`

This is the core traffic logic layer.

Responsibilities in this package include:

- traffic state progression and frame stepping
- lane/path geometry for vehicles
- route intent handling such as straight, left, and right movements
- signal phase management
- queue, wait-time, throughput, and emergency metrics
- compatibility wrappers for a simplified network and per-intersection abstraction
- regression tests for geometry, spacing, direction handling, and engine rules

Important files:

- `simulation_engine/engine.py`: main traffic engine implementation
- `simulation_engine/traffic_brain.py`: telemetry and scoring logic for direction-level demand and emergency priority
- `simulation_engine/network.py`: wrapper that exposes the engine through a `TrafficNetwork` interface
- `simulation_engine/intersection.py`: local intersection wrapper with summary helpers
- `simulation_engine/test_*.py`: regression coverage for engine behavior

### 2. `realtime_server/`

This package exposes the engine and the intelligence services to the UI.

Responsibilities in this package include:

- owning the authoritative simulation clock
- broadcasting snapshots over websocket
- receiving runtime control messages such as config updates, play, pause, and reset
- serving Live CV detection endpoints
- serving map, junction, and emergency-routing APIs
- managing city/junction state, signal coordination, green-wave timing, and delta streaming
- optionally calling Google Directions through a backend-only API key

Important files:

- `realtime_server/app.py`: main FastAPI app, websocket handlers, CV pipeline, map APIs, emergency APIs
- `realtime_server/main.py`: ASGI entrypoint
- `realtime_server/traffic_platform.py`: junction registry, city-state simulation, coordination, and delta streaming
- `realtime_server/emergency_routing.py`: Google Directions integration and route decoding
- `realtime_server/junction_registry.json`: Chennai demo junction registry
- `realtime_server/train_ambulance_yolo_classifier.py`: dataset preparation and classifier training script
- `realtime_server/requirements.txt`: backend dependency list

### 3. `frontend/`

This is the operator-facing web application built with React, Vite, Tailwind, React Router, React Three Fiber, and Leaflet.

Responsibilities in this package include:

- websocket consumption and local snapshot buffering
- 3D simulation rendering
- operator control panels
- charts, metrics, and event logs
- Live CV camera/upload workflow
- map-based emergency simulation UI
- route and signal visualization

Important files:

- `frontend/src/App.jsx`: app routing
- `frontend/src/hooks/useRealtimeSimulation.js`: websocket client, buffering, local control actions
- `frontend/src/components/SimulationCanvas.jsx`: 3D scene rendering
- `frontend/src/pages/HomePage.jsx`
- `frontend/src/pages/SimulationPage.jsx`
- `frontend/src/pages/DashboardPage.jsx`
- `frontend/src/pages/ImpactPage.jsx`
- `frontend/src/pages/LiveCvPage.jsx`
- `frontend/src/pages/MapPage.jsx`
- `frontend/vite.config.js`: frontend dev server config and `/api` proxy

### 4. `shared/`

This folder keeps backend and frontend data models aligned.

- `shared/contracts.py`: Python dataclasses and literal types for snapshots, vehicles, metrics, network state, and config
- `shared/contracts.ts`: TypeScript equivalents used by the frontend

### 5. Root-level helpers and assets

- `streamlit_app.py`: optional debug monitor for the simulation engine
- `.env.example`: current environment variable template
- `yolov8n.pt`: base YOLO detector used by the CV pipeline
- `models/ambulance_yolo_cls.pt`: ambulance-vs-nonambulance classifier

## Repository Layout

```text
Atoms/
  .env.example
  .gitignore
  README.md
  streamlit_app.py
  yolov8n.pt
  frontend/
    package.json
    vite.config.js
    tailwind.config.js
    src/
      App.jsx
      components/
      hooks/
      lib/
      pages/
  realtime_server/
    app.py
    main.py
    emergency_routing.py
    traffic_platform.py
    junction_registry.json
    train_ambulance_yolo_classifier.py
    requirements.txt
  simulation_engine/
    engine.py
    traffic_brain.py
    network.py
    intersection.py
    test_network.py
    test_direction_system.py
    test_collision_awareness.py
    test_engine_rules.py
  shared/
    contracts.py
    contracts.ts
  models/
    ambulance_yolo_cls.pt
  ambulance_dataset/
  datasets/
  vehicle_dataset/
```

## Frontend Pages

The React app currently exposes the following routes:

- `/`
  Home/overview page for system summary and key live metrics.
- `/simulation`
  Main 3D operator screen with control panel, traffic mode presets, speed control, signal mode switching, and optional custom route distribution editing.
- `/dashboard`
  KPI cards, throughput timeline, queue chart, vehicle distribution donut chart, and event log.
- `/impact`
  Rollout calculator that combines live metrics with simple deployment multipliers.
- `/live-cv`
  Browser-camera and upload-based traffic detection workflow for single-camera and 4-way junction analysis.
- `/map`
  City/junction monitoring map with emergency route simulation, route junction signals, ETA impact, and Google Directions enrichment.

## Backend API Surface

### Realtime simulation

- `GET /health`
  Returns backend health, runtime state, frame interval, connection count, and latest snapshot.
- `WS /ws`
  Main realtime simulation socket used by the simulation/dashboard/impact pages.

Accepted websocket message types:

- `set_config`
- `play`
- `pause`
- `reset`
- `ping`

Common websocket response types:

- `hello`
- `snapshot`
- `ack`
- `pong`
- `error`

### Live CV

- `POST /api/live-cv/detect`
  Accepts uploaded image or video and returns detections, tracking metrics, queue estimates, emergency hints, and accident flags.
- `POST /api/live-cv/junction/priority`
  Accepts per-approach statistics and returns a recommended green direction plus a cycle plan and rationale.

### Map and junction monitoring

- `GET /api/map/junctions`
- `GET /api/map/predictions`
- `GET /api/map/status`
- `GET /api/map/junction-registry`
- `GET /api/map/signal-coordination`
- `PUT /api/map/junctions/{junction_id}`
- `DELETE /api/map/junctions/{junction_id}`
- `POST /api/map/junctions/{junction_id}/heartbeat`
- `POST /api/map/emergency-route`
- `POST /api/map/emergency-route/clear`
- `WS /ws/map-stream`

`/ws/map-stream` sends full snapshots first and then delta updates when junction or coordination state changes materially.

### Emergency routing

- `GET /api/emergency/config`
- `GET /api/emergency/status`
- `POST /api/emergency/start`
- `POST /api/emergency/clear`
- `POST /api/emergency/speed`

These endpoints power the `/map` page's emergency simulation workflow.

## Data, Models, and Demo Assets

This repository includes large local assets, not just code.

- `vehicle_dataset/`
  Local vehicle-image dataset used for traffic-related experimentation. The current checkout contains 15,000+ image files.
- `ambulance_dataset/`
  Source images for ambulance vs non-ambulance classification. The current checkout contains roughly 4,700 image files.
- `datasets/ambulance_cls/`
  Prepared train/validation dataset tree generated for YOLO classification training.
- `yolov8n.pt`
  Base detector used by the Live CV pipeline.
- `models/ambulance_yolo_cls.pt`
  Trained ambulance classifier used to refine emergency detection.
- `realtime_server/junction_registry.json`
  Demo junction metadata with Chennai-based junction IDs, coordinates, cameras, neighbors, and seeded traffic metrics.

Because these assets are already committed locally, the repository is much heavier than a source-only web app.

## Environment Variables

Create a `.env` file in the project root by copying `.env.example`.

| Variable | Required | Used By | Purpose |
| --- | --- | --- | --- |
| `GOOGLE_MAPS_API_KEY` | Optional for most of the app, required for Google-route enrichment | `realtime_server/emergency_routing.py` | Enables backend-only Google Directions lookups for the map emergency workflow. |

If the key is missing:

- the main simulation UI can still run
- the Live CV pages can still run
- the map view can still show local/demo coordination state
- Google-route-based ETA, polyline, and turn-by-turn details may be unavailable

## Local Development Setup

### Prerequisites

- Python 3.10+ recommended
- Node.js 18+ recommended
- npm
- PowerShell on Windows if you want to follow the commands below exactly

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2. Install backend dependencies

```powershell
python -m pip install -r realtime_server\requirements.txt
```

### 3. Install optional Streamlit monitor dependencies

`streamlit_app.py` imports `streamlit` and `plotly`, which are not listed in `realtime_server/requirements.txt`.

```powershell
python -m pip install streamlit plotly
```

### 4. Install frontend dependencies

```powershell
Set-Location frontend
npm install
Set-Location ..
```

### 5. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and add `GOOGLE_MAPS_API_KEY` if you want Google Directions-backed emergency routing.

## Running The Project

### Realtime backend

```powershell
.\.venv\Scripts\python.exe -m uvicorn realtime_server.main:app --reload --host 0.0.0.0 --port 8000
```

This starts:

- the simulation websocket server on `ws://localhost:8000/ws`
- the Live CV APIs
- the map and emergency APIs
- the map delta stream on `ws://localhost:8000/ws/map-stream`

### Frontend

```powershell
Set-Location frontend
npm run dev
```

Open `http://localhost:5173`.

Development notes:

- Vite proxies `/api/*` requests to `http://localhost:8000`
- the simulation websocket still connects directly to `ws://<host>:8000/ws`
- the map stream connects directly to `ws://<host>:8000/ws/map-stream`

### Optional Streamlit monitor

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

The Streamlit app provides a lightweight simulation monitor with:

- play/pause/reset buttons
- traffic intensity and max-vehicle sliders
- a top-level metrics strip
- a scatter visualization of vehicle positions
- signal and event panels

## Ambulance Classifier Training

To retrain the ambulance classifier:

```powershell
.\.venv\Scripts\python.exe realtime_server\train_ambulance_yolo_classifier.py
```

The training script will:

1. read source images from `ambulance_dataset/ambulance` and `ambulance_dataset/noambulance`
2. rebuild `datasets/ambulance_cls/train` and `datasets/ambulance_cls/val`
3. train a YOLO classification model
4. copy the best checkpoint into `models/ambulance_yolo_cls.pt`

## Validation Commands

The repository includes simulation regression tests and a frontend production build path. Common local checks are:

```powershell
.\.venv\Scripts\python.exe -m unittest simulation_engine.test_network
.\.venv\Scripts\python.exe -m unittest simulation_engine.test_direction_system
.\.venv\Scripts\python.exe -m unittest simulation_engine.test_collision_awareness
.\.venv\Scripts\python.exe -m unittest simulation_engine.test_engine_rules
Set-Location frontend
npm run build
```

## Development Notes

- `frontend/dist/` and `frontend/node_modules/` are generated artifacts, not primary source.
- `models/ambulance_yolo_cls_run/` is gitignored as a training output directory.
- The backend loads `.env` from the project root, not from `realtime_server/`.
- The map workflow uses seeded Chennai demo data for junctions, start points, and hospitals.
- The frontend and backend intentionally share contract definitions through `shared/` to reduce schema drift.

## Sub-READMEs

There are also narrower package-level docs in:

- `frontend/README.md`
- `realtime_server/README.md`
- `simulation_engine/README.md`

The root README is the project-level guide. The package READMEs are useful when you only want to work on one layer.
