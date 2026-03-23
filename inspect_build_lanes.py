#!/usr/bin/env python
import inspect
from simulation_engine.engine import TrafficSimulationEngine

# Create engine
e = TrafficSimulationEngine()

# Check _build_lanes function source
source = inspect.getsource(e._build_lanes)
print("=== _build_lanes source (first 100 lines) ===")
lines = source.split('\n')
for i, line in enumerate(lines[:100], 1):
    print(f"{i:3d}: {line}")

print("\n\n=== Searching for add_slip_lane in source ===")
if 'add_slip_lane' in source:
    print("✓ add_slip_lane found in _build_lanes source")
    # Find the lines with add_slip_lane
    for i, line in enumerate(lines):
        if 'add_slip_lane(' in line:
            print(f"Line {i+1}: {line}")
else:
    print("✗ add_slip_lane NOT found in _build_lanes source")

print(f"\n\nTotal lanes created: {len(e.lanes)}")
print(f"Lane IDs: {sorted(e.lanes.keys())}")
