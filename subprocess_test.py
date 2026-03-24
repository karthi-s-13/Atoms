#!/usr/bin/env python
"""Test slip lanes with fresh Python subprocess."""

import subprocess
import sys
import os

# First pass: delete .pycfiles
delete_script = r"""
import shutil
import os
for root, dirs, files in os.walk('.'):
    if '__pycache__' in dirs:
        try:
            shutil.rmtree(os.path.join(root, '__pycache__'))
            print(f'Deleted: {root}/__pycache__')
        except Exception as e:
            print(f'Failed to delete {root}/__pycache__: {e}')
"""

print("=== PHASE 1: Deleting bytecode ===")
result = subprocess.run([sys.executable, '-c', delete_script], capture_output=True, text=True, cwd='.')
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

# Second pass: run test in fresh interpreter
test_script = r"""
import os
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

from simulation_engine.engine import TrafficSimulationEngine

engine = TrafficSimulationEngine()
lane = engine.lanes.get('lane_north_left_slip')
if lane:
    path_type = type(lane.path).__name__
    has_arc = hasattr(lane.path, 'arc') and lane.path.arc is not None
    num_points = len(lane.path.points) if hasattr(lane.path, 'points') else 0
    print(f'lane_north_left_slip: {path_type}, has_arc={has_arc}, points={num_points}')
"""

print("\n=== PHASE 2: Running test in fresh subprocess ===")
env = os.environ.copy()
env['PYTHONDONTWRITEBYTECODE'] = '1'
result = subprocess.run([sys.executable, '-c', test_script], capture_output=True, text=True, cwd='.', env=env)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
if result.returncode != 0:
    print(f"Return code: {result.returncode}")
