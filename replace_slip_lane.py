#!/usr/bin/env python3
"""Replace add_slip_lane with clean polyline ver sion."""

import re

with open('simulation_engine/engine.py', 'r') as f:
    content = f.read()

# Find the add_slip_lane function and replace it entirely
pattern = r'        def add_slip_lane\([\s\S]*?\n        def add_turn_lane\('

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
            """Build a free left-turn slip lane using polyline geometry."""
            # Determine path based on approach
            if approach == "NORTH":
                path_points = (
                    entry_start,
                    Point2D(OUTER_LANE_OFFSET, STOP_OFFSET),
                    Point2D(INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5, INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5),
                    Point2D(INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5, -INNER_LANE_OFFSET),
                    exit_end,
                )
            elif approach == "SOUTH":
                path_points = (
                    entry_start,
                    Point2D(-OUTER_LANE_OFFSET, -STOP_OFFSET),
                    Point2D(-(INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5), -(INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5)),
                    Point2D(-(INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5), INNER_LANE_OFFSET),
                    exit_end,
                )
            elif approach == "EAST":
                path_points = (
                    entry_start,
                    Point2D(STOP_OFFSET, -OUTER_LANE_OFFSET),
                    Point2D(INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5, -(INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5)),
                    Point2D(INNER_LANE_OFFSET, -(INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5)),
                    exit_end,
                )
            else:  # WEST
                path_points =  (
                    entry_start,
                    Point2D(-STOP_OFFSET, OUTER_LANE_OFFSET),
                    Point2D(-(INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5), INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5),
                    Point2D(-INNER_LANE_OFFSET, INTERSECTION_HALF_SIZE + LANE_WIDTH + 1.5),
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

        def add_turn_lane('''

match = re.search(pattern, content, re.DOTALL)
if match:
    content = content[:match.start()] + new_func + content[match.end()-20:]
    with open('simulation_engine/engine.py', 'w') as f:
        f.write(content)
    print("✓ Replaced add_slip_lane function successfully")
else:
    print("❌ Could not find add_slip_lane + add_turn_lane pattern")
