#!/usr/bin/env python
"""Extract and analyze the actual add_slip_lane function."""

import re

with open('simulation_engine/engine.py', 'r') as f:
    content = f.read()

# Find the add_slip_lane function definition
pattern = r'(        def add_slip_lane\(approach: Approach\) -> None:.*?)(\n        for approach in SIGNAL_ORDER:)'

match = re.search(pattern, content, re.DOTALL)
if match:
    old_function = match.group(1)
    print(f"Found add_slip_lane function. Length: {len(old_function)} chars")
    print(f"\nFirst 1000 chars:\n{'='*60}")
    print(old_function[:1000])
    print(f"\n{'='*60}\nLast 1000 chars:\n{'='*60}")
    print(old_function[-1000:])
else:
    print("Could not find add_slip_lane function")
    print("\nSearching for 'add_slip_lane'...")
    if 'add_slip_lane' in content:
        idx = content.find('add_slip_lane')
        print(f"Found 'add_slip_lane' at position {idx}")
        print(f"Context: ...{content[max(0, idx-100):idx+200]}...")
