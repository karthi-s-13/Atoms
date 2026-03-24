# Traffic Digital Twin

This repository now runs on a clean three-part architecture:

- `simulation_engine/`
  Pure Python traffic logic. This package owns vehicles, signal phases, emergency preemption, lane geometry, turning paths, and metrics.
- `realtime_server/`
  FastAPI + WebSocket bridge. This package owns the authoritative 60 FPS clock and streams buffered snapshots to clients.
- `frontend/`
  React + Vite operator interface with React Three Fiber, persistent camera state, buffered interpolation, live controls, analytics, and impact views.
- `shared/`
  Shared Python and TypeScript contracts so the server and frontend stay aligned.

## Folder Structure

```text
simulation_engine/
  __init__.py
  engine.py
  test_engine_rules.py
realtime_server/
  __init__.py
  app.py
  main.py
  requirements.txt
frontend/
  src/
    components/
    hooks/
    pages/
    App.jsx
    main.jsx
    index.css
  package.json
  vite.config.js
  tailwind.config.js
shared/
  contracts.py
  contracts.ts
```

## What The System Does

- Runs continuously without returning `None`
- Allows only one vehicle approach green at a time: `NORTH`, `SOUTH`, `EAST`, or `WEST`
- Stops vehicles cleanly at the approach stop lines
- Gives siren vehicles directional priority and green extension
- Moves vehicles on lane paths with smooth straight, right-turn, and left-turn arcs
- Streams timestamps, positions, velocities, and signal state over WebSocket
- Renders the 3D scene with buffered interpolation so motion stays smooth and the camera does not reset

## Pages

- `/`
  Home overview with system summary and feature sections
- `/simulation`
  Live 3D operator scene, controls, signal panel, and realtime stats
- `/dashboard`
  KPI cards, timeline charts, distribution view, and event log
- `/impact`
  Deployment impact calculator with live simulation inputs

## Run

### 1. Install Backend Dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r realtime_server\requirements.txt
```

### 2. Start The Realtime Server

```powershell
.\.venv\Scripts\python.exe -m uvicorn realtime_server.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Start The Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### Optional: Start The Streamlit Debug Monitor

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

This runner keeps a single engine instance in `st.session_state`, advances the simulation across reruns, and falls back to the last valid snapshot if a frame fails.

## Validation

The current clean build has been verified with:

```powershell
.\.venv\Scripts\python.exe -B -m unittest simulation_engine.test_engine_rules
.\.venv\Scripts\python.exe -B -m py_compile simulation_engine\engine.py realtime_server\app.py realtime_server\main.py shared\contracts.py
cd frontend
npm run build
```

## Realtime Protocol

WebSocket endpoint:

- `ws://localhost:8000/ws`

Messages accepted:

- `set_config`
- `play`
- `pause`
- `reset`
- `ping`

## Notes

- The old legacy backend stack is no longer part of the active architecture.
- If your IDE still shows files from `traffic/...` or `backend/...`, those are stale tabs from the previous structure.
