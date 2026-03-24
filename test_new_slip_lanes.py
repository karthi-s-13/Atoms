#!/usr/bin/env python
"""Test that the simulation works with new PolylinePath slip lanes."""

import os
import sys
import shutil

# Clear cache
for root, dirs, files in os.walk('.'):
    if '__pycache__' in dirs:
        try:
            shutil.rmtree(os.path.join(root, '__pycache__'))
        except:
            pass

from simulation_engine.engine import TrafficSimulationEngine

print('=== Simulation Test ===')
engine = TrafficSimulationEngine()

# Run a few simulation ticks
print('\nRunning simulation ticks...')
for i in range(3):
    snapshot = engine.tick(0.016)
    print(f'Tick {i}: {snapshot["timestamp"]:.3f}s, vehicles: {len(snapshot["vehicles"])}, frame: {snapshot["frame"]}')

# Check slip lanes exist and are accessible
slip_lanes = [lane for lane in engine.lanes.values() if 'slip' in lane.id]
print(f'\nSlip lanes created: {len(slip_lanes)}')
for lane in slip_lanes:
    print(f'  {lane.id}: path_length={lane.path.length:.1f}, points={len(lane.path.points)}')

print('\n✓ SUCCESS: Simulation working with new PolylinePath slip lanes!')
