#!/usr/bin/env python
"""Create the new add_slip_lane function code."""

new_function = '''        def add_slip_lane(approach: Approach) -> None:
            """Create a simple polyline-based free left-turn slip lane."""
            incoming_lane_id = f"lane_{approach.lower()}_straight"
            exit_direction = _left_turn_exit(approach)
            outgoing_approach = _opposite_approach(exit_direction)
            outgoing_lane_id = f"lane_{outgoing_approach.lower()}_straight"
            incoming_lane = lanes[incoming_lane_id]
            outgoing_lane = lanes[outgoing_lane_id]

            # Get entry and exit points from the lanes
            turn_entry = incoming_lane.path.point_at_distance(
                incoming_lane.queue_release_distance
            )
            turn_exit = outgoing_lane.path.point_at_distance(
                outgoing_lane.merge_distance
            )
            if outgoing_lane.merge_distance is None:
                raise ValueError(
                    f"Missing merge point for slip-lane destination {outgoing_lane_id}."
                )

            # Get directions for smooth transitions
            incoming_direction = incoming_lane.path.tangent_at_distance(0.0)
            outgoing_direction = outgoing_lane.path.tangent_at_distance(0.0)

            # Create extended entry and exit points
            entry_start = _offset_point(turn_entry, incoming_direction, -SLIP_TRANSITION_LENGTH)
            exit_end = _offset_point(turn_exit, outgoing_direction, SLIP_TRANSITION_LENGTH)

            # Create simple polyline path with waypoints
            # The path curves gently from entry to exit via intermediate waypoints
            mid_point_x = (turn_entry.x + turn_exit.x) / 2.0
            mid_point_y = (turn_entry.y + turn_exit.y) / 2.0
            
            # Add offset perpendicular to create smooth curve
            offset_x = (turn_exit.y - turn_entry.y) / 2.0
            offset_y = (turn_entry.x - turn_exit.x) / 2.0
            
            mid_point = Point2D(mid_point_x + offset_x * 0.3, mid_point_y + offset_y * 0.3)
            
            # Simple 5-point polyline: entry -> turn_entry -> mid -> turn_exit -> exit
            path_points = (
                entry_start,
                turn_entry,
                mid_point,
                turn_exit,
                exit_end,
            )
            
            path = PolylinePath.from_points(path_points)

            lane_id = f"lane_{approach.lower()}_left_slip"
            lanes[lane_id] = LaneDefinition(
                id=lane_id,
                kind="slip",
                direction=approach,
                lane_index="slip",
                movement="LEFT",
                movement_id=f"{approach[0]}_LEFT",
                path=path,
                stop_line_position=turn_entry,
                stop_distance=_distance(entry_start, turn_entry),
                stop_crosswalk_id=outgoing_lane.stop_crosswalk_id,
                crosswalk_start=turn_entry,
                queue_group=lane_id,
                queue_release_distance=_distance(entry_start, turn_entry) + path.length * 0.3,
                merge_group=outgoing_lane_id,
                merge_distance=path.length,
            )
'''

print(f"New function length: {len(new_function)} chars")
print("First 500 chars:")
print(new_function[:500])
print("\n...")
print("Last 300 chars:")
print(new_function[-300:])

# Write it to a temp file for reference
with open('new_add_slip_lane.txt', 'w') as f:
    f.write(new_function)
print("\nWritten to new_add_slip_lane.txt")
