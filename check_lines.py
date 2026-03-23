#!/usr/bin/env python
# Read file and show specific lines
with open('simulation_engine/engine.py') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
print(f"\nLine 876: {lines[875]}")
print(f"Line 875: {lines[874]}")
print(f"Line 877: {lines[876]}")

# Find first occurrence of "add_turn_lane"
for i, line in enumerate(lines):
    if 'def add_turn_lane' in line:
        print(f"\nadd_turn_lane defined at line {i+1}")
        # Print next 5 lines
        for j in range(i, min(i+10, len(lines))):
            print(f"  {j+1}: {lines[j].rstrip()}")
        break

# Find where add_turn_lane ends (look for next "def " or significant outdent)
found_add_turn = False
for i, line in enumerate(lines):
    if 'def add_turn_lane' in line:
        found_add_turn = True
        print(f"\nLooking for end of add_turn_lane starting at line {i+1}...")
        for j in range(i+1, min(i+100, len(lines))):
            if (line.startswith('        ') and not lines[j].startswith('        ')) or (line.startswith('        def ') and lines[j].startswith('        def ')):
                print(f"add_turn_lane appears to end around line {j}")
                print(f"Line {j}: {lines[j-1].rstrip()}")
                print(f"Line {j+1}: {lines[j].rstrip()}")
                break
        break
