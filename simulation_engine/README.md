# Simulation Engine

Pure Python simulation logic for the traffic digital twin.

Responsibilities:

- one-direction-at-a-time signal control
- emergency preemption and green extension
- stop-line enforcement before zebra crossings
- protected pedestrian all-red phase
- analytical quarter-circle turning motion
- free-slip left-turn lanes with merge control
- live metrics and event generation

Run validation:

```powershell
.\.venv\Scripts\python.exe -B -m unittest simulation_engine.test_engine_rules
```
