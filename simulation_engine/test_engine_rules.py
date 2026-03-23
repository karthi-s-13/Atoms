"""Regression coverage for stable lane discipline and one-green control."""

from __future__ import annotations

import math
import unittest

from simulation_engine.engine import (
    EAST,
    GREEN_INTERVAL,
    INNER_LANE_OFFSET,
    INTERSECTION_HALF_SIZE,
    NORTH,
    PHASE_GREEN,
    SOUTH,
    WEST,
    TrafficSimulationEngine,
)


class TrafficSimulationEngineTest(unittest.TestCase):
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
        vehicle.distance_along = max(0.0, lane.stop_distance - distance_before_stop)
        vehicle.position = lane.path.point_at_distance(vehicle.distance_along)
        vehicle.progress = vehicle.distance_along / lane.path.length
        vehicle.wait_time = wait_time
        vehicle.speed = vehicle.cruise_speed if speed is None else speed
        vehicle.state = "STOPPED" if wait_time > 0 else "MOVING"
        return vehicle

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

        self.assertEqual(straight_vehicle.route, "straight")
        self.assertEqual(straight_vehicle.lane_id, "lane_north_straight")
        self.assertEqual(self.engine.lanes[straight_vehicle.lane_id].lane_index, "outer")

        self.assertEqual(right_vehicle.route, "right")
        self.assertEqual(right_vehicle.lane_id, "lane_north_right")
        self.assertEqual(self.engine.lanes[right_vehicle.lane_id].lane_index, "inner")

        self.assertEqual(self.engine._lane_ids_for_route("NORTH", "left"), [])

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

    def test_only_straight_and_right_routes_exist(self) -> None:
        routes = set()
        for route in ("straight", "right"):
            vehicle = self.engine._make_vehicle("EAST", route)
            routes.add(vehicle.route)
        self.assertEqual(routes, {"straight", "right"})
        self.assertEqual(self.engine._lane_ids_for_route("NORTH", "straight"), ["lane_north_straight"])
        self.assertEqual(self.engine._lane_ids_for_route("NORTH", "right"), ["lane_north_right"])
        self.assertEqual(self.engine._lane_ids_for_route("NORTH", "left"), [])

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
