"""Regression coverage for stable lane discipline and one-green control."""

from __future__ import annotations

import math
import unittest

from simulation_engine.engine import (
    CROSSWALK_OUTER_OFFSET,
    EAST,
    GREEN_INTERVAL,
    INNER_LANE_OFFSET,
    INTERSECTION_HALF_SIZE,
    LANE_WIDTH,
    NORTH,
    PHASE_GREEN,
    SLIP_TRANSITION_LENGTH,
    SLIP_TURN_RADIUS,
    SOUTH,
    WEST,
    TrafficSimulationEngine,
)


class TrafficSimulationEngineTest(unittest.TestCase):
    @staticmethod
    def _left_normal(x: float, y: float) -> tuple[float, float]:
        return (-y, x)

    @staticmethod
    def _offset(x: float, y: float, direction_x: float, direction_y: float, distance: float) -> tuple[float, float]:
        return (x + (direction_x * distance), y + (direction_y * distance))

    @staticmethod
    def _line_intersection(
        origin_a: tuple[float, float],
        direction_a: tuple[float, float],
        origin_b: tuple[float, float],
        direction_b: tuple[float, float],
    ) -> tuple[float, float]:
        determinant = (direction_a[0] * direction_b[1]) - (direction_a[1] * direction_b[0])
        delta_x = origin_b[0] - origin_a[0]
        delta_y = origin_b[1] - origin_a[1]
        t = ((delta_x * direction_b[1]) - (delta_y * direction_b[0])) / determinant
        return (
            origin_a[0] + (direction_a[0] * t),
            origin_a[1] + (direction_a[1] * t),
        )

    def setUp(self) -> None:
        self.engine = TrafficSimulationEngine()
        self.engine.vehicles = []
        self.engine.config.max_vehicles = 0
        self.engine.config.max_pedestrians = 0

    def _set_green(self, direction: str, *, elapsed: float = 0.0) -> None:
        self.engine.signal_controller.current_green_direction = direction
        self.engine.signal_controller.elapsed = elapsed
        self.engine.current_state = direction

    def _make_vehicle(
        self,
        approach: str,
        route: str,
        *,
        distance_before_stop: float = 2.0,
        wait_time: float = 0.0,
        speed: float | None = None,
    ):
        vehicle = self.engine._make_vehicle(approach, route)
        lane = self.engine.lanes[vehicle.lane_id]
        distance_along = max(0.0, lane.stop_distance - distance_before_stop)
        resolved_speed = vehicle.cruise_speed if speed is None else speed
        self.engine._apply_vehicle_pose(vehicle, lane, distance_along, speed=resolved_speed)
        vehicle.wait_time = wait_time
        vehicle.speed = resolved_speed
        vehicle.state = "STOPPED" if wait_time > 0 else "MOVING"
        return vehicle

    def _set_vehicle_distance(
        self,
        vehicle,
        distance_along: float,
        *,
        speed: float | None = None,
        state: str | None = None,
    ) -> None:
        lane = self.engine.lanes[vehicle.lane_id]
        resolved_speed = vehicle.cruise_speed if speed is None else speed
        clamped_distance = max(0.0, min(distance_along, lane.path.length))
        self.engine._apply_vehicle_pose(vehicle, lane, clamped_distance, speed=resolved_speed)
        vehicle.speed = resolved_speed
        vehicle.state = state or ("MOVING" if resolved_speed > 0 else "STOPPED")
        vehicle.wait_time = 0.0

    def test_initial_snapshot_has_one_green_and_no_pedestrians(self) -> None:
        snapshot = self.engine.snapshot().to_dict()

        self.assertEqual(snapshot["current_state"], NORTH)
        self.assertEqual(snapshot["controller_phase"], PHASE_GREEN)
        self.assertEqual(snapshot["signals"], {"NORTH": "GREEN", "EAST": "RED", "SOUTH": "RED", "WEST": "RED"})
        self.assertEqual(snapshot["pedestrians"], [])
        self.assertEqual(len(snapshot["crosswalks"]), 4)

    def test_lane_geometry_uses_left_side_driving_consistently(self) -> None:
        north_straight = self.engine.lanes["lane_north_straight"]
        south_straight = self.engine.lanes["lane_south_straight"]
        east_straight = self.engine.lanes["lane_east_straight"]
        west_straight = self.engine.lanes["lane_west_straight"]
        north_right = self.engine.lanes["lane_north_right"]
        south_right = self.engine.lanes["lane_south_right"]
        east_right = self.engine.lanes["lane_east_right"]
        west_right = self.engine.lanes["lane_west_right"]

        self.assertGreater(north_straight.path.points[0].x, 0.0)
        self.assertLess(south_straight.path.points[0].x, 0.0)
        self.assertLess(east_straight.path.points[0].y, 0.0)
        self.assertGreater(west_straight.path.points[0].y, 0.0)

        self.assertGreater(north_straight.path.points[0].x, north_right.path.points[0].x)
        self.assertLess(south_straight.path.points[0].x, south_right.path.points[0].x)
        self.assertLess(east_straight.path.points[0].y, east_right.path.points[0].y)
        self.assertGreater(west_straight.path.points[0].y, west_right.path.points[0].y)

        self.assertLess(north_right.path.points[-1].y, 0.0)
        self.assertGreater(south_right.path.points[-1].y, 0.0)
        self.assertLess(east_right.path.points[-1].x, 0.0)
        self.assertGreater(west_right.path.points[-1].x, 0.0)

        self.assertEqual(north_straight.stop_crosswalk_id, "north_crosswalk")
        self.assertEqual(south_straight.stop_crosswalk_id, "south_crosswalk")
        self.assertEqual(east_straight.stop_crosswalk_id, "east_crosswalk")
        self.assertEqual(west_straight.stop_crosswalk_id, "west_crosswalk")

    def test_lane_assignment_matches_vehicle_intent(self) -> None:
        straight_vehicle = self.engine._make_vehicle("NORTH", "straight")
        right_vehicle = self.engine._make_vehicle("NORTH", "right")
        left_vehicle = self.engine._make_vehicle("NORTH", "left")

        self.assertEqual(straight_vehicle.route, "straight")
        self.assertEqual(straight_vehicle.lane_id, "lane_north_straight")
        self.assertEqual(self.engine.lanes[straight_vehicle.lane_id].lane_index, "outer")

        self.assertEqual(right_vehicle.route, "right")
        self.assertEqual(right_vehicle.lane_id, "lane_north_right")
        self.assertEqual(self.engine.lanes[right_vehicle.lane_id].lane_index, "inner")

        self.assertEqual(left_vehicle.route, "left")
        self.assertEqual(left_vehicle.lane_id, "lane_north_left_slip")
        self.assertEqual(self.engine.lanes[left_vehicle.lane_id].kind, "slip")

    def test_cycle_order_is_north_east_south_west(self) -> None:
        self._set_green(NORTH, elapsed=GREEN_INTERVAL)
        self.engine.update_signals(0.01)
        self.assertEqual(self.engine.current_state, EAST)

        self._set_green(EAST, elapsed=GREEN_INTERVAL)
        self.engine.update_signals(0.01)
        self.assertEqual(self.engine.current_state, SOUTH)

        self._set_green(SOUTH, elapsed=GREEN_INTERVAL)
        self.engine.update_signals(0.01)
        self.assertEqual(self.engine.current_state, WEST)

        self._set_green(WEST, elapsed=GREEN_INTERVAL)
        self.engine.update_signals(0.01)
        self.assertEqual(self.engine.current_state, NORTH)

    def test_switch_waits_until_intersection_clears(self) -> None:
        moving = self._make_vehicle("NORTH", "straight", distance_before_stop=0.0, speed=8.0)
        moving.position.x = 0.0
        moving.position.y = 0.0
        self.engine.vehicles = [moving]
        self._set_green(NORTH, elapsed=GREEN_INTERVAL)

        self.engine.update_signals(0.05)

        self.assertEqual(self.engine.current_state, NORTH)

    def test_vehicle_from_red_direction_stops_before_stop_line(self) -> None:
        blocked = self._make_vehicle("WEST", "straight", distance_before_stop=6.0, speed=8.0)
        allowed = self._make_vehicle("NORTH", "straight", distance_before_stop=1.0, speed=8.0)
        self.engine.vehicles = [blocked, allowed]
        self._set_green(NORTH)

        self.engine.update_vehicles(1.2)

        blocked_lane = self.engine.lanes[blocked.lane_id]
        crosswalk_distance = math.hypot(
            blocked_lane.crosswalk_start.x - blocked_lane.path.points[0].x,
            blocked_lane.crosswalk_start.y - blocked_lane.path.points[0].y,
        )
        self.assertLessEqual(blocked.distance_along, blocked_lane.stop_distance)
        self.assertLess(blocked.distance_along + (blocked.length / 2.0), crosswalk_distance)
        self.assertGreater(allowed.distance_along, self.engine.lanes[allowed.lane_id].stop_distance - 1.0)

    def test_right_turn_lane_is_smooth_and_starts_from_inner_lane(self) -> None:
        lane = self.engine.lanes["lane_north_right"]
        self.assertEqual(lane.lane_index, "inner")
        self.assertEqual(len(lane.path.points), 4)
        self.assertIsNotNone(lane.arc)
        self.assertIsNotNone(lane.turn_entry)
        self.assertIsNotNone(lane.turn_exit)

        expected_radius = INTERSECTION_HALF_SIZE + INNER_LANE_OFFSET
        self.assertAlmostEqual(lane.arc.radius, expected_radius, places=6)
        self.assertTrue(lane.arc.clockwise)
        self.assertAlmostEqual(lane.arc.center.x, -INTERSECTION_HALF_SIZE, places=6)
        self.assertAlmostEqual(lane.arc.center.y, INTERSECTION_HALF_SIZE, places=6)

        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            point = lane.path.point_at_distance(lane.path.entry_length + (lane.path.arc.length * fraction))
            radius = math.hypot(point.x - lane.arc.center.x, point.y - lane.arc.center.y)
            self.assertAlmostEqual(radius, lane.arc.radius, places=5)

        vehicle = self._make_vehicle("NORTH", "right", distance_before_stop=1.0, speed=6.0)
        self.engine.vehicles = [vehicle]
        self._set_green(NORTH)
        start_x = vehicle.position.x
        start_y = vehicle.position.y

        for _ in range(8):
            self.engine.update_vehicles(0.25)

        self.assertLess(vehicle.position.x, start_x)
        self.assertLess(vehicle.position.y, start_y)

    def test_left_slip_lanes_are_lane_connected_and_symmetric(self) -> None:
        outgoing_lane_ids = {
            "NORTH": "lane_west_straight",
            "EAST": "lane_north_straight",
            "SOUTH": "lane_east_straight",
            "WEST": "lane_south_straight",
        }

        for approach, outgoing_lane_id in outgoing_lane_ids.items():
            lane = self.engine.lanes[f"lane_{approach.lower()}_left_slip"]
            incoming_lane = self.engine.lanes[f"lane_{approach.lower()}_straight"]
            outgoing_lane = self.engine.lanes[outgoing_lane_id]

            incoming_direction = incoming_lane.path.tangent_at_distance(0.0)
            outgoing_direction = outgoing_lane.path.tangent_at_distance(0.0)
            incoming_normal = self._left_normal(incoming_direction.x, incoming_direction.y)
            outgoing_normal = self._left_normal(outgoing_direction.x, outgoing_direction.y)
            expected_entry = (
                incoming_lane.path.point_at_distance(incoming_lane.queue_release_distance).x,
                incoming_lane.path.point_at_distance(incoming_lane.queue_release_distance).y,
            )
            expected_exit = (
                outgoing_lane.path.point_at_distance(outgoing_lane.merge_distance).x,
                outgoing_lane.path.point_at_distance(outgoing_lane.merge_distance).y,
            )
            expected_center = self._line_intersection(
                expected_entry,
                incoming_normal,
                expected_exit,
                outgoing_normal,
            )

            self.assertEqual(lane.kind, "slip")
            self.assertEqual(lane.movement, "LEFT")
            self.assertEqual(len(lane.path.points), 4)
            self.assertIsNotNone(lane.arc)
            self.assertIsNotNone(lane.turn_entry)
            self.assertIsNotNone(lane.turn_exit)
            self.assertFalse(lane.arc.clockwise)
            self.assertEqual(lane.turn_entry, lane.path.points[1])
            self.assertEqual(lane.turn_exit, lane.path.points[2])
            self.assertEqual(lane.stop_crosswalk_id, outgoing_lane.stop_crosswalk_id)
            self.assertEqual(lane.merge_group, outgoing_lane.id)

            self.assertAlmostEqual(lane.arc.center.x, expected_center[0], places=6)
            self.assertAlmostEqual(lane.arc.center.y, expected_center[1], places=6)
            self.assertAlmostEqual(lane.turn_entry.x, expected_entry[0], places=6)
            self.assertAlmostEqual(lane.turn_entry.y, expected_entry[1], places=6)
            self.assertAlmostEqual(lane.turn_exit.x, expected_exit[0], places=6)
            self.assertAlmostEqual(lane.turn_exit.y, expected_exit[1], places=6)
            self.assertAlmostEqual(lane.arc.radius, SLIP_TURN_RADIUS, places=6)
            self.assertAlmostEqual(lane.arc.inner_radius, SLIP_TURN_RADIUS - (LANE_WIDTH / 2.0), places=6)
            self.assertAlmostEqual(lane.arc.outer_radius, SLIP_TURN_RADIUS + (LANE_WIDTH / 2.0), places=6)
            self.assertAlmostEqual(lane.arc.outer_radius - lane.arc.inner_radius, LANE_WIDTH, places=6)
            self.assertAlmostEqual(lane.path.entry_length, SLIP_TRANSITION_LENGTH, places=6)
            self.assertAlmostEqual(lane.path.exit_length, SLIP_TRANSITION_LENGTH, places=6)
            expected_length = (SLIP_TRANSITION_LENGTH * 2.0) + (lane.arc.radius * (math.pi / 2.0))
            self.assertAlmostEqual(lane.path.length, expected_length, places=6)

            start_tangent = lane.path.tangent_at_distance(0.0)
            arc_start_tangent = lane.path.tangent_at_distance(lane.path.entry_length)
            arc_end_tangent = lane.path.tangent_at_distance(lane.path.entry_length + lane.path.arc.length)
            end_tangent = lane.path.tangent_at_distance(lane.path.length)
            self.assertAlmostEqual(start_tangent.x, incoming_direction.x, places=5)
            self.assertAlmostEqual(start_tangent.y, incoming_direction.y, places=5)
            self.assertAlmostEqual(arc_start_tangent.x, incoming_direction.x, places=5)
            self.assertAlmostEqual(arc_start_tangent.y, incoming_direction.y, places=5)
            self.assertAlmostEqual(arc_end_tangent.x, outgoing_direction.x, places=5)
            self.assertAlmostEqual(arc_end_tangent.y, outgoing_direction.y, places=5)
            self.assertAlmostEqual(end_tangent.x, outgoing_direction.x, places=5)
            self.assertAlmostEqual(end_tangent.y, outgoing_direction.y, places=5)

            entry_margin = (
                ((lane.turn_entry.x - incoming_lane.crosswalk_start.x) * -incoming_direction.x)
                + ((lane.turn_entry.y - incoming_lane.crosswalk_start.y) * -incoming_direction.y)
            )
            self.assertGreater(entry_margin, 0.0)
            self.assertGreater(entry_margin, CROSSWALK_OUTER_OFFSET - INTERSECTION_HALF_SIZE)

            self.assertLess(
                abs(
                    ((lane.turn_entry.x - incoming_lane.path.points[0].x) * incoming_normal[0])
                    + ((lane.turn_entry.y - incoming_lane.path.points[0].y) * incoming_normal[1])
                ),
                1e-6,
            )
            self.assertLess(
                abs(
                    ((lane.turn_exit.x - outgoing_lane.path.points[0].x) * outgoing_normal[0])
                    + ((lane.turn_exit.y - outgoing_lane.path.points[0].y) * outgoing_normal[1])
                ),
                1e-6,
            )

            for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
                arc_distance = lane.path.arc.length * fraction
                point = lane.path.point_at_distance(lane.path.entry_length + arc_distance)
                radius = math.hypot(point.x - lane.arc.center.x, point.y - lane.arc.center.y)
                self.assertAlmostEqual(radius, lane.arc.radius, places=5)
                angle = lane.path.arc.angle_at_distance(arc_distance)
                inner_edge = (
                    lane.arc.center.x + (lane.arc.inner_radius * math.cos(angle)),
                    lane.arc.center.y + (lane.arc.inner_radius * math.sin(angle)),
                )
                self.assertTrue(
                    abs(inner_edge[0]) >= INTERSECTION_HALF_SIZE - 1e-6
                    or abs(inner_edge[1]) >= INTERSECTION_HALF_SIZE - 1e-6,
                )

    def test_left_slip_lane_ignores_signal_and_bypasses_stop_line(self) -> None:
        vehicle = self.engine._make_vehicle("NORTH", "left")
        lane = self.engine.lanes[vehicle.lane_id]
        start_distance = lane.path.entry_length * 0.5
        self._set_vehicle_distance(vehicle, start_distance, speed=vehicle.cruise_speed)
        self.engine.vehicles = [vehicle]
        self._set_green(SOUTH)

        for _ in range(6):
            self.engine.update_vehicles(0.25)

        self.assertGreater(vehicle.distance_along, start_distance + 4.0)
        self.assertGreaterEqual(vehicle.position.x, INTERSECTION_HALF_SIZE - 1e-6)
        self.assertLess(vehicle.position.y, lane.path.points[0].y)

    def test_left_slip_lane_vehicle_pose_matches_arc_equation(self) -> None:
        vehicle = self.engine._make_vehicle("NORTH", "left")
        lane = self.engine.lanes[vehicle.lane_id]
        self._set_vehicle_distance(
            vehicle,
            lane.path.entry_length + (lane.path.arc.length * 0.35),
            speed=vehicle.cruise_speed,
        )
        self.engine.vehicles = [vehicle]
        self._set_green(WEST)

        self.engine.update_vehicles(0.2)

        self.assertIsNotNone(vehicle.arc_angle)
        self.assertIsNotNone(vehicle.arc_radius)
        self.assertIsNotNone(vehicle.arc_center)
        self.assertAlmostEqual(vehicle.arc_radius, lane.arc.radius, places=6)
        self.assertAlmostEqual(vehicle.arc_center.x, lane.arc.center.x, places=6)
        self.assertAlmostEqual(vehicle.arc_center.y, lane.arc.center.y, places=6)

        expected_x = vehicle.arc_center.x + (vehicle.arc_radius * math.cos(vehicle.arc_angle))
        expected_y = vehicle.arc_center.y + (vehicle.arc_radius * math.sin(vehicle.arc_angle))
        self.assertAlmostEqual(vehicle.position.x, expected_x, places=5)
        self.assertAlmostEqual(vehicle.position.y, expected_y, places=5)
        arc_distance = vehicle.distance_along - lane.path.entry_length
        self.assertAlmostEqual(vehicle.heading, lane.path.arc.heading_at_distance(arc_distance), places=5)
        self.assertGreaterEqual(vehicle.position.x, lane.turn_entry.x)
        self.assertGreaterEqual(vehicle.position.y, lane.turn_exit.y)

    def test_straight_lane_stays_in_outer_lane_under_active_green(self) -> None:
        lane = self.engine.lanes["lane_north_straight"]
        self.assertEqual(lane.lane_index, "outer")

        vehicle = self._make_vehicle("NORTH", "straight", distance_before_stop=1.0, speed=8.0)
        self.engine.vehicles = [vehicle]
        self._set_green(NORTH)
        start_x = vehicle.position.x
        start_y = vehicle.position.y

        for _ in range(8):
            self.engine.update_vehicles(0.25)

        self.assertAlmostEqual(vehicle.position.x, start_x, places=2)
        self.assertLess(vehicle.position.y, start_y)

    def test_all_supported_vehicle_routes_exist(self) -> None:
        routes = set()
        for route in ("straight", "right", "left"):
            vehicle = self.engine._make_vehicle("EAST", route)
            routes.add(vehicle.route)
        self.assertEqual(routes, {"straight", "right", "left"})
        self.assertEqual(self.engine._lane_ids_for_route("NORTH", "straight"), ["lane_north_straight"])
        self.assertEqual(self.engine._lane_ids_for_route("NORTH", "right"), ["lane_north_right"])
        self.assertEqual(self.engine._lane_ids_for_route("NORTH", "left"), ["lane_north_left_slip"])

    def test_following_vehicle_does_not_overlap_leader(self) -> None:
        leader = self._make_vehicle("NORTH", "straight", distance_before_stop=0.5, speed=0.0)
        follower = self._make_vehicle("NORTH", "straight", distance_before_stop=4.5, speed=0.0)
        self.engine.vehicles = [leader, follower]
        self._set_green(NORTH)

        self.engine.update_vehicles(0.3)

        self.assertLess(follower.distance_along, leader.distance_along)

    def test_same_lane_queue_keeps_spacing(self) -> None:
        leader = self._make_vehicle("NORTH", "straight", distance_before_stop=0.5, speed=0.0)
        follower = self._make_vehicle("NORTH", "straight", distance_before_stop=5.5, speed=0.0)
        self.engine.vehicles = [leader, follower]
        self._set_green(NORTH)

        self.engine.update_vehicles(0.4)

        self.assertEqual(leader.lane_id, follower.lane_id)
        self.assertLess(follower.distance_along, leader.distance_along)
        spacing = math.hypot(leader.position.x - follower.position.x, leader.position.y - follower.position.y)
        self.assertGreaterEqual(spacing, (leader.length + follower.length) / 2.0)

    def test_left_slip_lane_waits_for_merge_gap_then_proceeds(self) -> None:
        slip_vehicle = self.engine._make_vehicle("NORTH", "left")
        slip_lane = self.engine.lanes[slip_vehicle.lane_id]
        self.assertIsNotNone(slip_lane.merge_distance)
        self._set_vehicle_distance(slip_vehicle, slip_lane.merge_distance - 1.4, speed=slip_vehicle.cruise_speed)

        blocker = self.engine._make_vehicle("WEST", "straight")
        blocker_lane = self.engine.lanes[blocker.lane_id]
        self.assertIsNotNone(blocker_lane.merge_distance)
        blocker_speed = blocker.cruise_speed
        blocker.cruise_speed = 0.0
        self._set_vehicle_distance(blocker, blocker_lane.merge_distance + 2.0, speed=0.0, state="STOPPED")

        self.engine.vehicles = [slip_vehicle, blocker]
        self._set_green(SOUTH)

        self.engine.update_vehicles(0.6)
        self.assertLess(slip_vehicle.distance_along, slip_lane.merge_distance)

        blocker.cruise_speed = blocker_speed
        self._set_vehicle_distance(blocker, blocker_lane.merge_distance + 18.0, speed=blocker_speed)

        self.engine.update_vehicles(0.8)
        self.assertGreaterEqual(slip_vehicle.distance_along, slip_lane.merge_distance)

    def test_pedestrian_waits_until_allowed_and_then_completes_crossing(self) -> None:
        self.engine.config.max_pedestrians = 1
        pedestrian = self.engine._make_pedestrian("north_crosswalk", start_from_start=True)
        self.engine.pedestrians = [pedestrian]
        self._set_green(EAST)

        self.engine.update_pedestrians(0.5)
        self.assertEqual(self.engine.pedestrians[0].state, "WAITING")

        self._set_green(NORTH)
        self.engine.update_pedestrians(0.5)
        self.assertIn(self.engine.pedestrians[0].state, {"CROSSING", "EXITING"})

        for _ in range(50):
            self.engine.update_pedestrians(0.4)
            if not self.engine.pedestrians:
                break

        self.assertEqual(self.engine.pedestrians, [])

    def test_vehicle_stops_for_active_pedestrian_crosswalk(self) -> None:
        vehicle = self._make_vehicle("NORTH", "straight", distance_before_stop=3.0, speed=8.0)
        pedestrian = self.engine._make_pedestrian("north_crosswalk", start_from_start=True)
        pedestrian.state = "CROSSING"
        pedestrian.distance_along = pedestrian.crosswalk_entry_distance + 0.8
        pedestrian.position = pedestrian.path.point_at_distance(pedestrian.distance_along)
        tangent = pedestrian.path.tangent_at_distance(pedestrian.distance_along)
        pedestrian.velocity_x = tangent.x * pedestrian.speed
        pedestrian.velocity_y = tangent.y * pedestrian.speed
        pedestrian.look_angle = math.atan2(tangent.x, tangent.y)
        self.engine.vehicles = [vehicle]
        self.engine.pedestrians = [pedestrian]
        self._set_green(NORTH)

        self.engine.update_vehicles(0.8)

        lane = self.engine.lanes[vehicle.lane_id]
        crosswalk_distance = math.hypot(
            lane.crosswalk_start.x - lane.path.points[0].x,
            lane.crosswalk_start.y - lane.path.points[0].y,
        )
        self.assertLess(vehicle.distance_along + (vehicle.length / 2.0), crosswalk_distance)
        self.assertLessEqual(vehicle.distance_along, lane.stop_distance)

    def test_pedestrian_spawns_from_sidewalk_with_variation(self) -> None:
        pedestrian = self.engine._make_pedestrian("north_crosswalk", start_from_start=True)
        crosswalk = self.engine.crosswalks["north_crosswalk"]

        self.assertLess(pedestrian.position.x, crosswalk.start.x)
        self.assertIn(pedestrian.shirt_color, {"#ef4444", "#3b82f6", "#22c55e", "#facc15"})
        self.assertIn(pedestrian.pants_color, {"#334155", "#1f2937", "#475569", "#0f172a"})
        self.assertGreaterEqual(pedestrian.body_scale, 0.9)
        self.assertLessEqual(pedestrian.body_scale, 1.08)

    def test_traffic_brain_reports_direction_scores(self) -> None:
        north_vehicle = self._make_vehicle("NORTH", "straight", wait_time=3.0, speed=0.0)
        east_vehicle = self._make_vehicle("EAST", "right", wait_time=1.0, speed=0.0)
        self.engine.vehicles = [north_vehicle, east_vehicle]
        self.engine._refresh_phase_demand_cache(0.1)

        snapshot = self.engine.snapshot().to_dict()
        scores = snapshot["traffic_brain"]["phase_scores"]

        self.assertEqual(set(scores.keys()), {NORTH, EAST, SOUTH, WEST})
        self.assertGreater(scores[NORTH]["score"], scores[WEST]["score"])


if __name__ == "__main__":
    unittest.main()
