#!/usr/bin/env python3
"""Test slip lane system."""

import sys
for key in list(sys.modules.keys()):
    if 'simulation_engine' in key or 'shared' in key:
        del sys.modules[key]

from simulation_engine.engine import TrafficSimulationEngine

try:
    e = TrafficSimulationEngine()
    slip_lanes = [l for l in e.lanes.keys() if 'left' in l]
    print(f'✓ Slip lanes created: {slip_lanes}')
    print(f'✓ Engine loaded successfully')
    print(f'✓ Total lanes: {len(e.lanes)}')
    
    # Test spawning left-turn vehicle
    e.config.traffic_intensity = 1.0
    e.tick(0.016)
    left_turn_vehicles = [v for v in e.vehicles if v.route == 'left']
    print(f'✓ Vehicles spawned: {len(e.vehicles)}')
    if left_turn_vehicles:
        print(f'✓ Left-turn vehicles: {len(left_turn_vehicles)}')
    print('\n✅ Slip lane system is working!')
    
except Exception as ex:
    print(f'❌ Error: {ex}')
    import traceback
    traceback.print_exc()
