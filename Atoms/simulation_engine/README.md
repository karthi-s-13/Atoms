# Simulation Engine

Pure Python simulation logic for the traffic digital twin.

Responsibilities:

- one-direction-at-a-time signal control
- emergency preemption and green extension
- stop-line enforcement at each incoming approach
- analytical straight motion plus shared-lane right turns
- protected in-intersection left-turn arcs
- live metrics and event generation

Run validation:

```powershell
.\.venv\Scripts\python.exe -B -m unittest simulation_engine.test_engine_rules
```
