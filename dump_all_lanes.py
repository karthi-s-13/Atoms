#!/usr/bin/env python3
"""Dump all lane IDs in the system."""

from simulation_engine.engine import TrafficSimulationEngine

engine = TrafficSimulationEngine()

print("ALL LANES IN SYSTEM:")
print("=" * 50)

for lane_id in sorted(engine.lanes.keys()):
    lane = engine.lanes[lane_id]
    print(f"{lane_id}: direction={lane.direction}, movement={lane.movement}")

print("\n" + "=" * 50)
print(f"Total: {len(engine.lanes)} lanes")
