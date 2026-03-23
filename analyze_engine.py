#!/usr/bin/env python
"""
Script to add LEFT-TURN SLIP LANES support to simulation_engine/engine.py
"""

# Read the current engine file
with open('simulation_engine/engine.py', 'r') as f:
    content = f.read()

# Find where add_turn_lane is defined and ends
# We'll search for the end of the add_turn_lane function definition
# by finding the line with "def add_slip_lane" or the first add_turn_lane() call

# Check if add_slip_lane already exists
if 'def add_slip_lane' in content:
    print("✓ add_slip_lane function already exists")
else:
    print("✗ add_slip_lane function NOT found - will add it")
    
# Check if slip lanes are being instantiated
if 'add_slip_lane(' in content and 'lane_north_left' in content:
    print("✓ Slip lanes already being instantiated")
else:
    print("✗ Slip lane instantiations NOT found - will add them")

# The strategy:
# 1. Find "def add_turn_lane(" location
# 2. Find the end of the add_turn_lane function (look for the next "        def " at same indent)
# 3. Insert add_slip_lane function there
# 4. Find where right lanes are instantiated
# 5. Add slip lane instantiations after all right lanes

# Let's find the line where we need to insert add_slip_lane
lines = content.split('\n')
print(f"\nTotal lines: {len(lines)}")

# Find add_turn_lane definition
add_turn_line = -1
for i, line in enumerate(lines):
    if 'def add_turn_lane(' in line:
        add_turn_line = i
        print(f"Found 'def add_turn_lane(' at line {i+1}")
        break

# Find where add_turn_lane ends by looking for the closing of its LaneDefinition assignment
if add_turn_line > 0:
    for i in range(add_turn_line + 10, len(lines)):
        # Look for a line that starts the next function or is blank followed by an add_turn_lane call
        if 'def add_slip_lane' in lines[i] or (lines[i].strip().startswith('add_turn_lane(') and '                ' in lines[i]):
            print(f"add_turn_lane likely ends around line {i}")
            break
        if i > add_turn_line + 100:  # Safety limit
            print(f"Reached safety limit, stopping search at line {i}")
            break

# Now let's look for where the right lanes end (the last add_turn_lane(...) call)
add_turn_call_lines = []
for i, line in enumerate(lines):
    if line.strip().startswith('add_turn_lane('):
        add_turn_call_lines.append(i)

print(f"\nFound {len(add_turn_call_lines)} add_turn_lane() calls")
if add_turn_call_lines:
    print(f"First at line {add_turn_call_lines[0]+1}, Last at line {add_turn_call_lines[-1]+1}")
    
    # The last add_turn_lane call might span multiple lines
    # Let's find where it ends
    last_call_start = add_turn_call_lines[-1]
    for i in range(last_call_start, min(last_call_start + 50, len(lines))):
        if lines[i].strip().endswith(')') and 'Point2D' in lines[i-1]:
            print(f"Last add_turn_lane call ends at line {i+1}: {lines[i]}")
            print(f"Next line ({i+2}): {lines[i+1]}")
            break
