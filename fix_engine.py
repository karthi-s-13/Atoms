#!/usr/bin/env python3
"""Find and fix the add_slip_lane function."""

import re

with open('simulation_engine/engine.py', 'r') as f:
    content = f.read()

# Find add_slip_lane function and replace it
pattern = r'(        def add_slip_lane\(.*?\n(?:.*?\n)*?        def add_turn_lane|        def add_slip_lane\(.*?\n(?:.*?\n)*?        add_turn_lane\()'

# Better pattern: just find the second CircularArc.from_center and delete it + surrounding code
old_code = '''            # Create outer radius entry and exit points
            outer_entry = Point2D(
                slip_entry.x + (lane_width / 2.0) if approach in {"NORTH", "SOUTH"} else slip_entry.x,
                slip_entry.y + (lane_width / 2.0) if approach in {"EAST", "WEST"} else slip_entry.y,
            )
            outer_exit = Point2D(
                slip_exit.x if approach in {"NORTH", "SOUTH"} else slip_exit.x + (lane_width / 2.0),
                slip_exit.y if approach in {"EAST", "WEST"} else slip_exit.y + (lane_width / 2.0),
            )

            arc = CircularArc.from_center(
                arc_center,
                outer_entry,
                outer_exit,
                clockwise=clockwise_arc,
            )

            path = TurnArcPath.from_points(
                entry_start,
                outer_entry,
                arc,
                outer_exit,
                exit_end,
            )

            lanes[lane_id] = LaneDefinition(
                id=lane_id,
                direction=approach,
                lane_index=lane_index,
                movement=movement,
                movement_id=f"{approach[0]}_{movement}",
                path=path,
                stop_line_position=slip_entry,
                stop_distance=_distance(path.points[0], slip_entry),
                stop_crosswalk_id=crosswalk_id,
                crosswalk_start=crosswalk_start,
                queue_group=queue_group,
                queue_release_distance=_distance(path.points[0], slip_entry),
                arc=arc.to_view(),
                turn_entry=outer_entry,
                turn_exit=outer_exit,
            )'''

new_code = '''            path = PolylinePath.from_points(path_points)

            lanes[lane_id] = LaneDefinition(
                id=lane_id,
                direction=approach,
                lane_index=lane_index,
                movement=movement,
                movement_id=f"{approach[0]}_{movement}",
                path=path,
                stop_line_position=slip_entry,
                stop_distance=_distance(path.points[0], slip_entry),
                stop_crosswalk_id=crosswalk_id,
                crosswalk_start=crosswalk_start,
                queue_group=queue_group,
                queue_release_distance=_distance(path.points[0], slip_entry),
            )'''

if old_code in content:
    print("Found old code to replace")
    content = content.replace(old_code, new_code)
    with open('simulation_engine/engine.py', 'w') as f:
        f.write(content)
    print("✓ Replaced old arc code with polyline version")
else:
    print("Old code pattern not found exactly")
    # Try to find what's actually there
    if 'CircularArc.from_center' in content[content.find('add_slip_lane'):]:
        idx = content.find('add_slip_lane')
        idx2 = content.find('CircularArc.from_center', idx)
        print(f"\nFound CircularArc at position {idx2}")
        print("Context:")
        print(content[idx2-200:idx2+400])
