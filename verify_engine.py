#!/usr/bin/env python
from simulation_engine.engine import TrafficSimulationEngine

print("Loading engine...")
e = TrafficSimulationEngine()

print(f"\nEngine loaded successfully!")
print(f"Total lanes: {len(e.lanes)}")

slip_lanes = [k for k in e.lanes.keys() if "left" in k]
print(f"Slip lanes found: {slip_lanes}")

regular_lanes = [k for k in e.lanes.keys() if "left" not in k]
print(f"Regular lanes found: {len(regular_lanes)}")
print(f"All lanes summary:")
print(f"  - straight: {len([k for k in e.lanes.keys() if 'straight' in k])}")
print(f"  - right: {len([k for k in e.lanes.keys() if 'right' in k])}")
print(f"  - left: {len(slip_lanes)}")

# Test that signal controller bypasses signals for left turns
print(f"\nTesting signal bypass for left turns:")
print(f"  can_vehicle_move(NORTH, 'straight'): {e.signal_controller.can_vehicle_move('NORTH', 'straight')}")
print(f"  can_vehicle_move(NORTH, 'left'): {e.signal_controller.can_vehicle_move('NORTH', 'left')}")

print("\n✅ Engine loads successfully with all slip lanes!")
