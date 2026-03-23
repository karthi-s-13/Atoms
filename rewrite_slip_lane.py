#!/usr/bin/env python3
"""Completely rewrite add_slip_lane function."""

with open('simulation_engine/engine.py', 'r') as f:
    content = f.read()

# Find the start of add_slip_lane
start_idx = content.find('        def add_slip_lane(')
if start_idx == -1:
    print("❌ add_slip_lane not found")
else:
    # Find where the function ends (the next top-level function def or main code)
    # Look for the next "        add_turn_lane(" call which comes right after the function
    end_idx = content.find('        add_turn_lane(\n', start_idx)
    if end_idx == -1:
        print("❌ Could not find end marker")
    else:
        # Replace just the function body
        new_func = '''        def add_slip_lane(
            lane_id: str,
            approach: Approach,
            lane_index: str,
            movement: LaneMovement,
            entry_start: Point2D,
            slip_entry: Point2D,
            inner_radius: float,
            lane_width: float,
            exit_direction: str,
            exit_end: Point2D,
            crosswalk_id: str,
            crosswalk_start: Point2D,
            queue_group: str,
        ) -> None:
            """Build free left-turn slip lane using polylines."""
            # Determine path based on approach direction
            if approach == "NORTH":
                # North incoming -> East outgoing
                path_points = (
                    entry_start,
                    Point2D(OUTER_LANE_OFFSET, STOP_OFFSET),
                    Point2D(INTERSECTION_HALF_SIZE + 4.0, INTERSECTION_HALF_SIZE + 4.0),
                    Point2D(INTERSECTION_HALF_SIZE + 4.0, -INNER_LANE_OFFSET),
                    exit_end,
                )
            elif approach == "SOUTH":
                # South incoming -> West outgoing
                path_points = (
                    entry_start,
                    Point2D(-OUTER_LANE_OFFSET, -STOP_OFFSET),
                    Point2D(-(INTERSECTION_HALF_SIZE + 4.0), -(INTERSECTION_HALF_SIZE + 4.0)),
                    Point2D(-(INTERSECTION_HALF_SIZE + 4.0), INNER_LANE_OFFSET),
                    exit_end,
                )
            elif approach == "EAST":
                # East incoming -> North outgoing
                path_points = (
                    entry_start,
                    Point2D(STOP_OFFSET, -OUTER_LANE_OFFSET),
                    Point2D(INTERSECTION_HALF_SIZE + 4.0, -(INTERSECTION_HALF_SIZE + 4.0)),
                    Point2D(INNER_LANE_OFFSET, -(INTERSECTION_HALF_SIZE + 4.0)),
                    exit_end,
                )
            else:  # WEST
                # West incoming -> South outgoing
                path_points = (
                    entry_start,
                    Point2D(-STOP_OFFSET, OUTER_LANE_OFFSET),
                    Point2D(-(INTERSECTION_HALF_SIZE + 4.0), INTERSECTION_HALF_SIZE + 4.0),
                    Point2D(-INNER_LANE_OFFSET, INTERSECTION_HALF_SIZE + 4.0),
                    exit_end,
                )

            path = PolylinePath.from_points(path_points)
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
            )

        '''
        
        # Replace from start to the marker
        new_content = content[:start_idx] + new_func + content[end_idx:]
        
        with open('simulation_engine/engine.py', 'w') as f:
            f.write(new_content)
        
        print("✓ Successfully rewrote add_slip_lane function")
        print(f"  Replaced {end_idx - start_idx} characters")
