#!/usr/bin/env python
import traceback
import sys

try:
    print("Importing engine...")
    from simulation_engine.engine import TrafficSimulationEngine
    
    print("Creating engine instance...")
    e = TrafficSimulationEngine()
    
    print(f"Engine created!")
    print(f"Total lanes: {len(e.lanes)}")
    print(f"Lane IDs: {sorted(e.lanes.keys())}")
    
except Exception as ex:
    print(f"ERROR: {ex}")
    traceback.print_exc(file=sys.stdout)
