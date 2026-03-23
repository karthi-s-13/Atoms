#!/usr/bin/env python
# Read the actual file and search for add_slip_lane
with open('simulation_engine/engine.py', 'r') as f:
    lines = f.readlines()

total_lines = len(lines)
print(f"Total lines in file: {total_lines}")

# Search for add_slip_lane
found_add_slip_lane = False
for i, line in enumerate(lines, 1):
    if 'add_slip_lane' in line:
        print(f"Line {i}: {line.rstrip()}")
        found_add_slip_lane = True

if not found_add_slip_lane:
    print("add_slip_lane NOT found in the file")

# Search for lane_north_left
found_left_lane = False  
for i, line in enumerate(lines, 1):
    if 'lane_north_left' in line or 'lane_south_left' in line:
        print(f"Line {i}: {line.rstrip()}")
        found_left_lane = True

if not found_left_lane:
    print("No left lane instantiations found in file")

# Let me print specific lines around line 1010
print("\n\n=== Content from line 1005-1080 ===")
for i in range(1004, min(1080, total_lines)):
    print(f"{i+1:4d}: {lines[i].rstrip()}")
