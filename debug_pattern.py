#!/usr/bin/env python3
"""Debug the pattern search."""

import re

with open('simulation_engine/engine.py', 'r') as f:
    content = f.read()

# Find add_slip_lane definition
idx = content.find('def add_slip_lane(')
if idx == -1:
    print("❌ add_slip_lane not found")
else:
    idx2 = content.find('def add_turn_lane(', idx)
    if idx2 == -1:
        print("❌ add_turn_lane not found after add_slip_lane")
    else:
        print(f"✓ Found both functions")
        print(f"add_slip_lane starts at {idx}")
        print(f"add_turn_lane starts at {idx2}")
        print(f"\nContent between them (last 300 chars before add_turn_lane):")
        print(repr(content[idx2-300:idx2+50]))
