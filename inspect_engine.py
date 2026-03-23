#!/usr/bin/env python3
import re

with open('simulation_engine/engine.py', 'r') as f:
    content = f.read()

# Find the old arc code pattern
pattern = r'# Build circular arc.*?clockwise=clockwise_arc,\s*\)'
matches = re.finditer(pattern, content, re.DOTALL)
count = 0
for match in matches:
    count += 1
    start = match.start()
    end = match.end()
    line_num = content[:start].count('\n') + 1
    print(f"Match {count} at line {line_num}:")
    print(f"Content:\n{match.group()}\n")
    print("---")

if count == 0:
    print("No old arc code found")
else:
    print(f"Found {count} matches")
