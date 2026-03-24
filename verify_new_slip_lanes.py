#!/usr/bin/env python3
"""Direct test of new slip lane path types."""

from simulation_engine.engine import TrafficSimulationEngine, PolylinePath, TurnArcPath

print("Creating engine with new slip lane design...")
engine = TrafficSimulationEngine()

slip_lanes = [k for k in engine.lanes if 'slip' in k]
print(f"Slip lanes found: {len(slip_lanes)}\n")

for lane_id in sorted(slip_lanes):
    lane = engine.lanes[lane_id]
    path = lane.path
    print(f"{lane_id}:")
    print(f"  Path class: {path.__class__.__name__}")
    print(f"  Is PolylinePath: {isinstance(path, PolylinePath)}")
    print(f"  Is TurnArcPath: {isinstance(path, TurnArcPath)}")
    print(f"  has 'arc' attr: {hasattr(lane, 'arc')}")
    print(f"  Path length: {path.length:.1f}")
    print()

print("✓ Verification complete")
