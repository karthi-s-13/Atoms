#!/usr/bin/env python
"""Direct test of slip lanes."""

import os
import sys
import shutil
import importlib

# Delete all .pyc files
for root, dirs, files in os.walk('.'):
    if '__pycache__' in dirs:
        try:
            shutil.rmtree(os.path.join(root, '__pycache__'))
        except:
            pass

# Don't write bytecode
sys.dont_write_bytecode = True

# Invalidate caches
importlib.invalidate_caches()

print("Importing TrafficSimulationEngine...")
from simulation_engine.engine import TrafficSimulationEngine, PolylinePath, TurnArcPath

print("Creating engine...")
engine = TrafficSimulationEngine()

print("\nSlip lane analysis:")
for lane_id in ['lane_north_left_slip', 'lane_south_left_slip', 'lane_east_left_slip', 'lane_west_left_slip']:
    if lane_id in engine.lanes:
        lane = engine.lanes[lane_id]
        path = lane.path
        path_class = type(path).__name__
        is_polyline = isinstance(path, PolylinePath)
        is_arc = isinstance(path, TurnArcPath)
        print(f"\n{lane_id}:")
        print(f"  Class: {path_class}")
        print(f"  isinstance(PolylinePath): {is_polyline}")
        print(f"  isinstance(TurnArcPath): {is_arc}")
        if hasattr(path, 'points'):
            print(f"  Points: {len(path.points)} waypoints")
        if hasattr(path, 'arc'):
            print(f"  Has arc attr: {path.arc is not None}")
    else:
        print(f"{lane_id}: NOT FOUND")
