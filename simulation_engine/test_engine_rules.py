"""Regression coverage for the shared straight/right and protected-left intersection model."""

from __future__ import annotations

import math
import unittest

from simulation_engine.engine import (
    ADAPTIVE_MAX_GREEN,
    ADAPTIVE_MIN_GREEN,
    EAST,
    EMERGENCY_ACTIVE_MIN_GREEN,
    EMERGENCY_MAX_CONTINUOUS_GREEN,
    EMERGENCY_PREEMPT_MIN_GREEN,
    EMERGENCY_RELIEF_UNSERVED_TIME,
    GREEN_INTERVAL,
    INTERSECTION_HALF_SIZE,
    LEFT_TURN_RADIUS,
    MIN_LEFT_TURN_RADIUS,
    NORTH,
    PHASE_GREEN,
    RIGHT_TURN_RADIUS,
    SOUTH,
    WEST,
    TrafficSimulationEngine,
)


class TrafficSimulationEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = TrafficSimulationEngine()
        self.engine.vehicles = []
        self.engine.config.max_vehicles = 0
        # Engine configured with no vehicles for this test

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

    def _run_benchmark(self, config: dict[str, object], *, duration: float = 60.0, dt: float = 0.1) -> dict[str, float]:
        engine = TrafficSimulationEngine()
        engine.reset({"paused": False, **config})
        total_wait = 0.0
        total_queue = 0.0
        samples = 0
        for _ in range(int(duration / dt)):
            engine.tick(dt)
            total_wait += float(engine.metrics.avg_wait_time)
            total_queue += float(engine.metrics.queued_vehicles)
            samples += 1
        return {
            "processed": float(engine.processed_vehicles),
            "avg_wait_time": (total_wait / samples) if samples else 0.0,
            "queued_vehicles": (total_queue / samples) if samples else 0.0,
            "throughput": float(engine.processed_vehicles) / max(duration, dt),
        }

    def test_initial_snapshot_has_single_north_green(self) -> None:
        snapshot = self.engine.snapshot().to_dict()

        self.assertEqual(snapshot["current_state"], NORTH)
        self.assertEqual(snapshot["controller_phase"], PHASE_GREEN)
        self.assertEqual(snapshot["signals"], {"NORTH": "GREEN", "EAST": "RED", "SOUTH": "RED", "WEST": "RED"})
        self.assertEqual(snapshot["vehicles"], [])
        self.assertEqual(len(snapshot["crosswalks"]), 4)

    def test_lane_geometry_uses_left_side_driving_consistently(self) -> None:
        north_straight = self.engine.lanes["lane_north_straight"]
        south_straight = self.engine.lanes["lane_south_straight"]
        east_straight = self.engine.lanes["lane_east_straight"]
        west_straight = self.engine.lanes["lane_west_straight"]
        north_left = self.engine.lanes["lane_north_left"]
        south_left = self.engine.lanes["lane_south_left"]
        east_left = self.engine.lanes["lane_east_left"]
        west_left = self.engine.lanes["lane_west_left"]

        self.assertLess(north_straight.path.points[0].x, north_left.path.points[0].x)
        self.assertGreater(south_straight.path.points[0].x, south_left.path.points[0].x)
        self.assertGreater(east_straight.path.points[0].y, east_left.path.points[0].y)
        self.assertLess(west_straight.path.points[0].y, west_left.path.points[0].y)

        self.assertEqual(north_straight.stop_crosswalk_id, "north_crosswalk")
        self.assertEqual(south_straight.stop_crosswalk_id, "south_crosswalk")
        self.assertEqual(east_straight.stop_crosswalk_id, "east_crosswalk")
        self.assertEqual(west_straight.stop_crosswalk_id, "west_crosswalk")
        self.assertTrue(all(lane.kind == "main" for lane in self.engine.lanes.values()))

    def test_no_slip_lanes_exist_and_right_turns_share_the_inner_approach_lane(self) -> None:
        lane_ids = set(self.engine.lanes.keys())
        straight_lane = self.engine.lanes["lane_north_straight"]
        right_lane = self.engine.lanes["lane_north_right"]
        right_vehicle = self.engine._make_vehicle("NORTH", "right")

        self.assertFalse(any("slip" in lane_id for lane_id in lane_ids))
        self.assertIn("lane_north_right", lane_ids)
        self.assertEqual(self.engine._lane_ids_for_route("NORTH", "right"), ["lane_north_right"])
        self.assertEqual(right_lane.lane_index, "inner")
        self.assertEqual(right_lane.shared_lane_id, straight_lane.shared_lane_id)
        self.assertAlmostEqual(right_lane.path.points[0].x, straight_lane.path.points[0].x, places=6)
        self.assertAlmostEqual(right_lane.path.points[0].y, straight_lane.path.points[0].y, places=6)
        self.assertAlmostEqual(right_lane.stop_line_position.x, straight_lane.stop_line_position.x, places=6)
        self.assertAlmostEqual(right_lane.stop_line_position.y, straight_lane.stop_line_position.y, places=6)
        self.assertEqual(right_vehicle.route, "right")
        self.assertEqual(right_vehicle.intent, "RIGHT")
        self.assertEqual(right_vehicle.lane_id, "lane_north_right")
        self.assertEqual(right_vehicle.sub_path_side, "RIGHT")

    def test_lane_assignment_matches_vehicle_intent(self) -> None:
        straight_vehicle = self.engine._make_vehicle("NORTH", "straight")
        right_vehicle = self.engine._make_vehicle("NORTH", "right")
        left_vehicle = self.engine._make_vehicle("NORTH", "left")
        straight_lane = self.engine.lanes[straight_vehicle.lane_id]
        right_lane = self.engine.lanes[right_vehicle.lane_id]
        expected_straight_position = self.engine._sub_path_pose_at_distance(straight_lane, 0.0, "RIGHT")[0]
        expected_right_position = self.engine._sub_path_pose_at_distance(right_lane, 0.0, "RIGHT")[0]
        expected_left_position = self.engine._sub_path_pose_at_distance(
            self.engine.lanes[left_vehicle.lane_id],
            0.0,
            "LEFT",
        )[0]

        self.assertEqual(straight_vehicle.route, "straight")
        self.assertEqual(straight_vehicle.intent, "STRAIGHT")
        self.assertEqual(straight_vehicle.lane_id, "lane_north_straight")
        self.assertEqual(straight_vehicle.sub_path_side, "RIGHT")
        self.assertEqual(self.engine.lanes[straight_vehicle.lane_id].lane_index, "inner")
        self.assertAlmostEqual(straight_vehicle.position.x, expected_straight_position.x, places=5)
        self.assertAlmostEqual(straight_vehicle.position.y, expected_straight_position.y, places=5)

        self.assertEqual(right_vehicle.route, "right")
        self.assertEqual(right_vehicle.intent, "RIGHT")
        self.assertEqual(right_vehicle.lane_id, "lane_north_right")
        self.assertEqual(right_vehicle.sub_path_side, "RIGHT")
        self.assertEqual(self.engine.lanes[right_vehicle.lane_id].lane_index, "inner")
        self.assertAlmostEqual(right_vehicle.position.x, expected_right_position.x, places=5)
        self.assertAlmostEqual(right_vehicle.position.y, expected_right_position.y, places=5)
        self.assertEqual(left_vehicle.route, "left")
        self.assertEqual(left_vehicle.intent, "LEFT")
        self.assertEqual(left_vehicle.lane_id, "lane_north_left")
        self.assertEqual(left_vehicle.sub_path_side, "LEFT")
        self.assertEqual(self.engine.lanes[left_vehicle.lane_id].lane_index, "outer")
        self.assertAlmostEqual(left_vehicle.position.x, expected_left_position.x, places=5)
        self.assertAlmostEqual(left_vehicle.position.y, expected_left_position.y, places=5)

    def test_cycle_order_rotates_through_all_approaches(self) -> None:
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

    def test_left_turn_lane_arcs_are_symmetric_and_inside_intersection(self) -> None:
        for approach in ("NORTH", "EAST", "SOUTH", "WEST"):
            lane = self.engine.lanes[f"lane_{approach.lower()}_left"]
            self.assertEqual(lane.lane_index, "outer")
            self.assertIsNotNone(lane.arc)
            self.assertIsNotNone(lane.turn_entry)
            self.assertIsNotNone(lane.turn_exit)
            self.assertAlmostEqual(lane.arc.radius, LEFT_TURN_RADIUS, places=6)
            self.assertGreaterEqual(abs(lane.arc.center.x), INTERSECTION_HALF_SIZE)
            self.assertGreaterEqual(abs(lane.arc.center.y), INTERSECTION_HALF_SIZE)
            crosswalk_distance = math.hypot(
                lane.crosswalk_start.x - lane.path.points[0].x,
                lane.crosswalk_start.y - lane.path.points[0].y,
            )
            self.assertGreater(lane.path.entry_length, crosswalk_distance)

            for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
                point = lane.path.point_at_distance(lane.path.entry_length + (lane.path.arc.length * fraction))
                radius = math.hypot(point.x - lane.arc.center.x, point.y - lane.arc.center.y)
                self.assertAlmostEqual(radius, lane.arc.radius, places=5)
                self.assertLessEqual(abs(point.x), INTERSECTION_HALF_SIZE + lane.arc.radius + 1e-6)
                self.assertLessEqual(abs(point.y), INTERSECTION_HALF_SIZE + lane.arc.radius + 1e-6)

    def test_right_turn_lane_arcs_share_the_inner_entry_and_stay_inside_intersection(self) -> None:
        for approach in ("NORTH", "EAST", "SOUTH", "WEST"):
            straight_lane = self.engine.lanes[f"lane_{approach.lower()}_straight"]
            right_lane = self.engine.lanes[f"lane_{approach.lower()}_right"]
            self.assertEqual(right_lane.lane_index, "inner")
            self.assertIsNotNone(right_lane.arc)
            self.assertIsNotNone(right_lane.turn_entry)
            self.assertIsNotNone(right_lane.turn_exit)
            self.assertAlmostEqual(right_lane.arc.radius, RIGHT_TURN_RADIUS, places=6)
            self.assertAlmostEqual(right_lane.path.points[0].x, straight_lane.path.points[0].x, places=6)
            self.assertAlmostEqual(right_lane.path.points[0].y, straight_lane.path.points[0].y, places=6)
            self.assertAlmostEqual(right_lane.stop_line_position.x, straight_lane.stop_line_position.x, places=6)
            self.assertAlmostEqual(right_lane.stop_line_position.y, straight_lane.stop_line_position.y, places=6)
            self.assertLess(abs(right_lane.arc.center.x), INTERSECTION_HALF_SIZE)
            self.assertLess(abs(right_lane.arc.center.y), INTERSECTION_HALF_SIZE)

            for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
                point = right_lane.path.point_at_distance(right_lane.path.entry_length + (right_lane.path.arc.length * fraction))
                radius = math.hypot(point.x - right_lane.arc.center.x, point.y - right_lane.arc.center.y)
                self.assertAlmostEqual(radius, right_lane.arc.radius, places=5)

    def test_left_turn_vehicle_pose_matches_arc_equation(self) -> None:
        vehicle = self.engine._make_vehicle("NORTH", "left")
        lane = self.engine.lanes[vehicle.lane_id]
        arc_distance = lane.path.entry_length + (lane.path.arc.length * 0.4)
        self._set_vehicle_distance(vehicle, arc_distance, speed=0.0, state="STOPPED")

        self.assertIsNotNone(vehicle.arc_center)
        self.assertIsNotNone(vehicle.arc_radius)
        expected_position, tangent, expected_heading, expected_angle, expected_radius, _ = self.engine._sub_path_pose_at_distance(
            lane,
            arc_distance,
            vehicle.sub_path_side,
        )
        radius = math.hypot(
            vehicle.position.x - vehicle.arc_center.x,
            vehicle.position.y - vehicle.arc_center.y,
        )

        self.assertAlmostEqual(radius, vehicle.arc_radius, places=5)
        self.assertAlmostEqual(radius, expected_radius, places=5)
        self.assertAlmostEqual(vehicle.position.x, expected_position.x, places=5)
        self.assertAlmostEqual(vehicle.position.y, expected_position.y, places=5)
        self.assertAlmostEqual(vehicle.arc_angle, expected_angle, places=5)
        self.assertAlmostEqual(vehicle.heading, expected_heading, places=5)

    def test_left_turn_vehicle_obeys_signal_before_entering_intersection(self) -> None:
        blocked = self._make_vehicle("WEST", "left", distance_before_stop=5.0, speed=7.0)
        allowed = self._make_vehicle("NORTH", "left", distance_before_stop=1.0, speed=7.0)
        self.engine.vehicles = [blocked, allowed]
        self._set_green(NORTH)

        self.engine.update_vehicles(1.0)

        blocked_lane = self.engine.lanes[blocked.lane_id]
        crosswalk_distance = math.hypot(
            blocked_lane.crosswalk_start.x - blocked_lane.path.points[0].x,
            blocked_lane.crosswalk_start.y - blocked_lane.path.points[0].y,
        )
        self.assertLessEqual(blocked.distance_along, blocked_lane.stop_distance)
        self.assertLess(blocked.distance_along + (blocked.length / 2.0), crosswalk_distance)
        self.assertGreater(allowed.distance_along, blocked.distance_along)

    def test_same_path_queue_maintains_safe_gap(self) -> None:
        leader = self.engine._make_vehicle("NORTH", "straight")
        follower = self.engine._make_vehicle("NORTH", "straight")
        leader_distance = 38.0
        follower_distance = 24.0
        self._set_vehicle_distance(leader, leader_distance, speed=0.0, state="STOPPED")
        self._set_vehicle_distance(follower, follower_distance, speed=follower.cruise_speed)
        self.engine.vehicles = [leader, follower]
        self._set_green(NORTH)

        self.engine.update_vehicles(1.2)

        required_gap = self.engine._safe_follow_distance(follower, leader)
        self.assertGreaterEqual(leader.distance_along - follower.distance_along, required_gap - 1e-6)
        self.assertLessEqual(follower.distance_along, leader.distance_along - required_gap + 1e-6)

    def test_soft_following_reduces_speed_without_freezing_flow(self) -> None:
        leader = self.engine._make_vehicle("NORTH", "straight")
        follower = self.engine._make_vehicle("NORTH", "straight")
        self._set_vehicle_distance(leader, 40.0, speed=leader.cruise_speed * 0.35, state="MOVING")
        self._set_vehicle_distance(follower, 31.0, speed=follower.cruise_speed, state="MOVING")
        self.engine.vehicles = [leader, follower]
        self._set_green(NORTH)

        self.engine.update_vehicles(0.6)

        self.assertGreater(follower.distance_along, 31.0)
        self.assertGreater(follower.speed, 0.0)
        self.assertLess(follower.speed, follower.cruise_speed)
        self.assertGreaterEqual(
            leader.distance_along - follower.distance_along,
            self.engine._minimum_follow_distance(follower, leader) - 1e-6,
        )

    def test_stopped_red_approach_holds_before_stop_line_until_signal_changes(self) -> None:
        vehicle = self._make_vehicle(
            "WEST",
            "straight",
            distance_before_stop=3.4,
            wait_time=12.0,
            speed=0.0,
        )
        lane = self.engine.lanes[vehicle.lane_id]
        start_distance = vehicle.distance_along
        self.engine.vehicles = [vehicle]
        self._set_green(NORTH)

        self.engine.update_vehicles(1.0)

        self.assertGreaterEqual(vehicle.distance_along, start_distance)
        self.assertLess(vehicle.distance_along, lane.stop_distance)
        self.assertLess(vehicle.distance_along, lane.intersection_entry_distance)

    def test_straight_lane_entry_waits_when_intersection_box_is_full(self) -> None:
        leader = self.engine._make_vehicle("NORTH", "straight")
        blocker = self.engine._make_vehicle("NORTH", "straight")
        follower = self.engine._make_vehicle("NORTH", "straight")
        lane = self.engine.lanes[leader.lane_id]

        self._set_vehicle_distance(leader, lane.intersection_entry_distance + 0.9, speed=0.0, state="STOPPED")
        self._set_vehicle_distance(blocker, lane.intersection_exit_distance - 0.9, speed=0.0, state="STOPPED")
        self._set_vehicle_distance(follower, lane.stop_distance + 1.0, speed=follower.cruise_speed)
        self.engine.vehicles = [leader, blocker, follower]
        self._set_green(NORTH)

        self.engine.update_vehicles(1.0)

        self.assertLess(follower.distance_along, lane.intersection_entry_distance)
        self.assertEqual(follower.state, "STOPPED")

    def test_straight_lane_entry_waits_until_exit_path_is_clear(self) -> None:
        leader = self.engine._make_vehicle("NORTH", "straight")
        follower = self.engine._make_vehicle("NORTH", "straight")
        lane = self.engine.lanes[leader.lane_id]

        self._set_vehicle_distance(leader, lane.intersection_exit_distance + 1.2, speed=0.0, state="STOPPED")
        self._set_vehicle_distance(follower, lane.stop_distance + 0.8, speed=follower.cruise_speed)
        self.engine.vehicles = [leader, follower]
        self._set_green(NORTH)

        self.engine.update_vehicles(1.0)

        self.assertLess(follower.distance_along, lane.intersection_entry_distance)
        self.assertEqual(follower.state, "STOPPED")

    def test_shared_inner_lane_uses_front_awareness_without_overlap(self) -> None:
        scenarios = (("right", "straight"), ("straight", "right"))
        for leader_route, follower_route in scenarios:
            with self.subTest(leader_route=leader_route, follower_route=follower_route):
                leader = self.engine._make_vehicle("NORTH", leader_route)
                follower = self.engine._make_vehicle("NORTH", follower_route)
                leader_lane = self.engine.lanes[leader.lane_id]
                follower_lane = self.engine.lanes[follower.lane_id]
                follower_start_distance = max(0.0, follower_lane.stop_distance - 2.0)

                self._set_vehicle_distance(
                    leader,
                    leader_lane.intersection_entry_distance + 0.6,
                    speed=0.0,
                    state="STOPPED",
                )
                self._set_vehicle_distance(
                    follower,
                    follower_start_distance,
                    speed=follower.cruise_speed,
                )
                self.engine.vehicles = [leader, follower]
                self._set_green(NORTH)

                self.engine.update_vehicles(1.0)

                self.assertGreaterEqual(follower.distance_along, follower_start_distance)
                self.assertFalse(self.engine._vehicle_collides_with_any_object(follower, [leader]))

    def test_shared_inner_lane_releases_promptly_after_right_turn_clears_entry(self) -> None:
        leader = self.engine._make_vehicle("NORTH", "right")
        follower = self.engine._make_vehicle("NORTH", "straight")
        leader_lane = self.engine.lanes[leader.lane_id]
        follower_lane = self.engine.lanes[follower.lane_id]
        release_distance = self.engine._shared_lane_release_distance(leader_lane, follower, leader)
        follower_start_distance = follower_lane.stop_distance + 0.7

        self._set_vehicle_distance(
            leader,
            min(leader_lane.path.length, release_distance + 1.1),
            speed=0.0,
            state="STOPPED",
        )
        self._set_vehicle_distance(
            follower,
            follower_start_distance,
            speed=follower.cruise_speed,
            state="MOVING",
        )
        self.engine.vehicles = [leader, follower]
        self._set_green(NORTH)

        self.engine.update_vehicles(0.8)

        self.assertGreater(follower.distance_along, follower_lane.intersection_entry_distance)
        self.assertEqual(follower.state, "MOVING")
        self.assertFalse(self.engine._vehicle_collides_with_any_object(follower, [leader]))

    def test_left_turn_followers_use_front_awareness_without_overlap(self) -> None:
        leader = self.engine._make_vehicle("NORTH", "left")
        follower = self.engine._make_vehicle("NORTH", "left")
        blocker = self.engine._make_vehicle("NORTH", "left")
        lane = self.engine.lanes[leader.lane_id]
        safe_gap = self.engine._safe_follow_distance(follower, leader)
        leader_release_distance = (lane.path.entry_length + lane.path.arc.length + safe_gap) - 0.2
        blocker_gap = self.engine._safe_follow_distance(leader, blocker)

        self._set_vehicle_distance(leader, leader_release_distance, speed=0.0, state="STOPPED")
        self._set_vehicle_distance(blocker, leader_release_distance + blocker_gap - 0.2, speed=0.0, state="STOPPED")
        follower_start_distance = min(lane.path.entry_length - 0.6, lane.stop_distance + 0.2)
        self._set_vehicle_distance(follower, follower_start_distance, speed=follower.cruise_speed)
        self.engine.vehicles = [leader, follower, blocker]
        self._set_green(NORTH)

        self.engine.update_vehicles(1.0)

        self.assertGreaterEqual(follower.distance_along, follower_start_distance)
        self.assertFalse(self.engine._vehicle_collides_with_any_object(follower, [leader, blocker]))

    def test_left_turn_queue_releases_when_exit_space_opens(self) -> None:
        leader = self.engine._make_vehicle("NORTH", "left")
        follower = self.engine._make_vehicle("NORTH", "left")
        lane = self.engine.lanes[leader.lane_id]
        safe_gap = self.engine._safe_follow_distance(follower, leader)
        clear_distance = lane.path.entry_length + lane.path.arc.length + safe_gap + 4.0

        self._set_vehicle_distance(leader, clear_distance, speed=leader.cruise_speed)
        self._set_vehicle_distance(follower, lane.stop_distance + 1.2, speed=follower.cruise_speed)
        self.engine.vehicles = [leader, follower]
        self._set_green(NORTH)

        self.engine.update_vehicles(1.0)

        self.assertGreater(follower.distance_along, lane.path.entry_length)
        self.assertEqual(follower.state, "MOVING")

    def test_turn_smoothness_updates_lane_radius_and_repositions_live_vehicle(self) -> None:
        vehicle = self.engine._make_vehicle("NORTH", "left")
        lane = self.engine.lanes[vehicle.lane_id]
        arc_distance = lane.path.entry_length + (lane.path.arc.length * 0.35)
        self._set_vehicle_distance(vehicle, arc_distance, speed=0.0, state="STOPPED")
        self.engine.vehicles = [vehicle]
        original_radius = lane.arc.radius

        self.engine.update_config({"turn_smoothness": 0.0})

        updated_lane = self.engine.lanes[vehicle.lane_id]
        expected_position, _, _, _, expected_radius, _ = self.engine._sub_path_pose_at_distance(
            updated_lane,
            min(arc_distance, updated_lane.path.length),
            vehicle.sub_path_side,
        )

        self.assertAlmostEqual(updated_lane.arc.radius, MIN_LEFT_TURN_RADIUS, places=5)
        self.assertLess(updated_lane.arc.radius, original_radius)
        self.assertAlmostEqual(vehicle.position.x, expected_position.x, places=5)
        self.assertAlmostEqual(vehicle.position.y, expected_position.y, places=5)
        self.assertAlmostEqual(vehicle.arc_radius, expected_radius, places=5)

    def test_dynamic_spawn_interval_slows_under_heavy_congestion(self) -> None:
        baseline_interval = self.engine._vehicle_spawn_interval()
        for index in range(8):
            vehicle = self.engine._make_vehicle("NORTH" if index % 2 == 0 else "EAST", "straight")
            lane = self.engine.lanes[vehicle.lane_id]
            self._set_vehicle_distance(vehicle, lane.stop_distance + 0.2 + (index * 0.3), speed=0.0, state="STOPPED")
            self.engine.vehicles.append(vehicle)

        congested_interval = self.engine._vehicle_spawn_interval()

        self.assertGreater(congested_interval, baseline_interval)

    def test_reset_reseeds_and_reapplies_config_deterministically(self) -> None:
        deterministic_config = {
            "traffic_intensity": 0.22,
            "spawn_rate_multiplier": 0.6,
            "ambulance_frequency": 0.3,
            "max_emergency_vehicles": 1,
            "max_vehicles": 4,
            "route_distribution": {
                "NORTH->SOUTH": 9,
                "NORTH->EAST": 0,
                "NORTH->WEST": 0,
                "EAST->WEST": 0,
                "EAST->SOUTH": 0,
                "EAST->NORTH": 0,
                "SOUTH->NORTH": 0,
                "SOUTH->WEST": 0,
                "SOUTH->EAST": 0,
                "WEST->EAST": 0,
                "WEST->NORTH": 0,
                "WEST->SOUTH": 0,
            },
        }

        self.engine.reset(deterministic_config)
        self.assertAlmostEqual(self.engine._vehicle_spawn_timer, self.engine._vehicle_spawn_interval(), places=6)
        self.engine._spawn_vehicle()
        self.assertEqual(len(self.engine.vehicles), 1)
        first = self.engine.vehicles[0]
        first_signature = (
            first.id,
            first.kind,
            first.origin_direction,
            first.route,
            first.intent,
            first.sub_path_side,
            first.color,
            first.length,
            first.width,
            first.cruise_speed,
            round(first.position.x, 5),
            round(first.position.y, 5),
        )

        self.engine.reset(deterministic_config)
        self.assertAlmostEqual(self.engine._vehicle_spawn_timer, self.engine._vehicle_spawn_interval(), places=6)
        self.engine._spawn_vehicle()
        self.assertEqual(len(self.engine.vehicles), 1)
        second = self.engine.vehicles[0]
        second_signature = (
            second.id,
            second.kind,
            second.origin_direction,
            second.route,
            second.intent,
            second.sub_path_side,
            second.color,
            second.length,
            second.width,
            second.cruise_speed,
            round(second.position.x, 5),
            round(second.position.y, 5),
        )

        self.assertEqual(first_signature, second_signature)

    def test_route_distribution_can_force_a_single_direction_pair(self) -> None:
        self.engine.vehicles = []
        self.engine.config.max_vehicles = 1
        self.engine.update_config({
            "route_distribution": {
                "NORTH->SOUTH": 0,
                "NORTH->EAST": 9,
                "NORTH->WEST": 0,
                "EAST->WEST": 0,
                "EAST->SOUTH": 0,
                "EAST->NORTH": 0,
                "SOUTH->NORTH": 0,
                "SOUTH->WEST": 0,
                "SOUTH->EAST": 0,
                "WEST->EAST": 0,
                "WEST->NORTH": 0,
                "WEST->SOUTH": 0,
            }
        })

        self.engine._spawn_vehicle()

        self.assertEqual(len(self.engine.vehicles), 1)
        self.assertEqual(self.engine.vehicles[0].origin_direction, "NORTH")
        self.assertEqual(self.engine.vehicles[0].route, "left")

    def test_emergency_vehicle_cap_limits_active_sirens(self) -> None:
        self.engine.vehicles = []
        self.engine.config.max_vehicles = 4
        self.engine.update_config({
            "ambulance_frequency": 1.0,
            "max_emergency_vehicles": 1,
            "route_distribution": {
                "NORTH->SOUTH": 4,
                "NORTH->EAST": 0,
                "NORTH->WEST": 0,
                "EAST->WEST": 4,
                "EAST->SOUTH": 0,
                "EAST->NORTH": 0,
                "SOUTH->NORTH": 4,
                "SOUTH->WEST": 0,
                "SOUTH->EAST": 0,
                "WEST->EAST": 4,
                "WEST->NORTH": 0,
                "WEST->SOUTH": 0,
            },
        })

        self.engine._spawn_vehicle()
        self.engine._spawn_vehicle()

        emergency_count = sum(1 for vehicle in self.engine.vehicles if vehicle.kind != "car")
        self.assertLessEqual(emergency_count, 1)

    def test_phase_demands_raise_fairness_for_long_waiting_vehicles(self) -> None:
        north_waiting = self._make_vehicle("NORTH", "straight", distance_before_stop=1.0, wait_time=14.0, speed=0.0)
        east_waiting = self._make_vehicle("EAST", "straight", distance_before_stop=1.0, wait_time=2.0, speed=0.0)
        self.engine.vehicles = [north_waiting, east_waiting]
        self.engine.signal_controller.unserved_demand_time["NORTH"] = 15.0
        self.engine.signal_controller.unserved_demand_time["EAST"] = 3.0

        self.engine._refresh_phase_demand_cache(0.0)

        self.assertGreater(self.engine.phase_demands["NORTH"]["fairness_boost"], self.engine.phase_demands["EAST"]["fairness_boost"])
        self.assertGreater(self.engine.phase_scores["NORTH"], self.engine.phase_scores["EAST"])

    def test_phase_demands_use_lane_weight_and_emergency_count_priority(self) -> None:
        east_ambulance = self.engine._make_vehicle_for_lane("lane_east_straight", emergency_kind="ambulance", intent="STRAIGHT")
        east_firetruck = self.engine._make_vehicle_for_lane("lane_east_left", emergency_kind="firetruck", intent="LEFT")
        east_car = self.engine._make_vehicle("EAST", "straight")
        north_car = self.engine._make_vehicle("NORTH", "straight")

        self._set_vehicle_distance(east_ambulance, self.engine.lanes[east_ambulance.lane_id].stop_distance - 0.8, speed=0.0, state="STOPPED")
        east_ambulance.wait_time = 5.0
        self._set_vehicle_distance(east_firetruck, self.engine.lanes[east_firetruck.lane_id].stop_distance - 1.1, speed=0.0, state="STOPPED")
        east_firetruck.wait_time = 4.0
        self._set_vehicle_distance(east_car, self.engine.lanes[east_car.lane_id].stop_distance - 1.4, speed=0.0, state="STOPPED")
        east_car.wait_time = 3.0
        self._set_vehicle_distance(north_car, self.engine.lanes[north_car.lane_id].stop_distance - 1.0, speed=0.0, state="STOPPED")
        north_car.wait_time = 3.0
        self.engine.vehicles = [east_ambulance, east_firetruck, east_car, north_car]

        self.engine._refresh_phase_demand_cache(0.0)

        self.assertEqual(self.engine.traffic_brain_state.emergency.preferred_phase, EAST)
        self.assertEqual(self.engine.traffic_brain_state.emergency.vehicle_count, 2)
        self.assertGreater(self.engine.traffic_brain_state.emergency.priority_score, 0.0)
        self.assertGreater(self.engine.phase_scores["EAST"], self.engine.phase_scores["NORTH"])
        self.assertGreater(self.engine.phase_demands["EAST"]["emergency_boost"], self.engine.phase_demands["NORTH"]["emergency_boost"])

    def test_firetruck_waiting_behind_three_vehicles_gets_priority_from_wait_and_lane_weight(self) -> None:
        north_lead = self.engine._make_vehicle("NORTH", "straight")
        north_mid = self.engine._make_vehicle("NORTH", "straight")
        north_tail = self.engine._make_vehicle("NORTH", "straight")
        north_firetruck = self.engine._make_vehicle_for_lane("lane_north_straight", emergency_kind="firetruck", intent="STRAIGHT")
        east_queued = [
            self.engine._make_vehicle("EAST", "straight")
            for _ in range(4)
        ]

        north_lane = self.engine.lanes[north_lead.lane_id]
        self._set_vehicle_distance(north_lead, north_lane.stop_distance - 0.8, speed=0.0, state="STOPPED")
        north_lead.wait_time = 3.0
        self._set_vehicle_distance(north_mid, north_lane.stop_distance - 3.0, speed=0.0, state="STOPPED")
        north_mid.wait_time = 4.0
        self._set_vehicle_distance(north_tail, north_lane.stop_distance - 5.2, speed=0.0, state="STOPPED")
        north_tail.wait_time = 5.0
        self._set_vehicle_distance(north_firetruck, north_lane.stop_distance - 7.4, speed=0.0, state="STOPPED")
        north_firetruck.wait_time = 12.0

        east_lane = self.engine.lanes[east_queued[0].lane_id]
        for index, vehicle in enumerate(east_queued):
            self._set_vehicle_distance(vehicle, east_lane.stop_distance - (1.0 + (index * 1.6)), speed=0.0, state="STOPPED")
            vehicle.wait_time = 4.0 + index

        self.engine.vehicles = [north_lead, north_mid, north_tail, north_firetruck, *east_queued]

        self.engine._refresh_phase_demand_cache(0.0)

        self.assertEqual(self.engine.traffic_brain_state.emergency.preferred_phase, NORTH)
        self.assertGreater(self.engine.traffic_brain_state.emergency.priority_score, 10.0)
        self.assertGreater(self.engine.phase_demands["NORTH"]["emergency_boost"], self.engine.phase_demands["EAST"]["emergency_boost"])
        self.assertGreater(self.engine.phase_scores["NORTH"], self.engine.phase_scores["EAST"])

    def test_ai_signal_switches_to_busiest_queued_direction(self) -> None:
        self.engine.update_config({"ai_mode": "adaptive"})
        east_queued = [
            self._make_vehicle("EAST", "straight", distance_before_stop=1.5 + index, wait_time=2.0 + index, speed=0.0)
            for index in range(4)
        ]
        north_vehicle = self._make_vehicle("NORTH", "straight", distance_before_stop=1.0, wait_time=0.0, speed=0.0)
        self.engine.vehicles = [north_vehicle, *east_queued]
        self._set_green(NORTH, elapsed=ADAPTIVE_MIN_GREEN + 0.6)
        self.engine._refresh_phase_demand_cache(0.0)

        self.engine.update_signals(0.1)

        self.assertEqual(self.engine.current_state, EAST)

    def test_ai_green_duration_scales_with_queue_and_respects_caps(self) -> None:
        controller = self.engine.signal_controller
        controller.phase_duration_memory[NORTH] = ADAPTIVE_MIN_GREEN
        low_demand = {"NORTH": {"queue": 0.0, "wait_time": 0.0, "emergency_boost": 0.0}}
        heavy_demand = {"NORTH": {"queue": 12.0, "wait_time": 16.0, "emergency_boost": 0.0}}
        emergency_demand = {"NORTH": {"queue": 6.0, "wait_time": 8.0, "emergency_boost": 5.6}}

        low_duration = controller._adaptive_duration(NORTH, low_demand)
        heavy_duration = controller._adaptive_duration(NORTH, heavy_demand)
        emergency_duration = controller._adaptive_duration(NORTH, emergency_demand)

        self.assertAlmostEqual(low_duration, ADAPTIVE_MIN_GREEN, places=6)
        self.assertGreater(heavy_duration, low_duration)
        self.assertLessEqual(heavy_duration, ADAPTIVE_MAX_GREEN)
        self.assertGreater(emergency_duration, controller._adaptive_duration(NORTH, {"NORTH": {"queue": 6.0, "wait_time": 8.0, "emergency_boost": 0.0}}))

    def test_ai_priority_score_uses_phase_totals_and_fairness(self) -> None:
        controller = self.engine.signal_controller
        low_priority = controller._priority_score(
            NORTH,
            {"NORTH": {"score": 3.0}, "SOUTH": {"score": 0.0}},
        )
        starved_priority = controller._priority_score(
            EAST,
            {"EAST": {"score": 6.2}, "WEST": {"score": 0.0}},
        )
        queued_priority = controller._priority_score(
            NORTH,
            {"NORTH": {"score": 4.5}, "SOUTH": {"score": 4.0}},
        )

        self.assertGreater(starved_priority, low_priority)
        self.assertGreater(queued_priority, low_priority)

    def test_ai_controller_waits_until_min_green_before_switching(self) -> None:
        self.engine.update_config({"ai_mode": "adaptive"})
        self._set_green(NORTH, elapsed=ADAPTIVE_MIN_GREEN - 0.2)
        self.engine.phase_demands = {
            "NORTH": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 0.0},
            "EAST": {"queue": 5.0, "wait_time": 4.0, "arrival_rate": 1.2, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 12.4},
            "SOUTH": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 0.0},
            "WEST": {"queue": 4.0, "wait_time": 3.0, "arrival_rate": 0.8, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 9.46},
        }
        self.engine.phase_scores = {direction: values["score"] for direction, values in self.engine.phase_demands.items()}
        self.engine.phase_has_demand = {"NORTH": False, "EAST": True, "SOUTH": False, "WEST": True}

        self.engine.update_signals(0.1)

        self.assertEqual(self.engine.current_state, NORTH)

    def test_ai_controller_forces_starved_phase_after_timeout(self) -> None:
        self.engine.update_config({"ai_mode": "adaptive"})
        self._set_green(NORTH, elapsed=ADAPTIVE_MIN_GREEN + 1.0)
        self.engine.signal_controller.unserved_demand_time["EAST"] = 20.0
        self.engine.signal_controller.unserved_demand_time["WEST"] = 20.0
        self.engine.phase_demands = {
            "NORTH": {"queue": 4.0, "wait_time": 2.0, "arrival_rate": 0.8, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 8.2},
            "EAST": {"queue": 1.0, "wait_time": 1.0, "arrival_rate": 0.2, "fairness_boost": 6.0, "emergency_boost": 0.0, "score": 8.7},
            "SOUTH": {"queue": 3.0, "wait_time": 1.5, "arrival_rate": 0.7, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 6.1},
            "WEST": {"queue": 1.0, "wait_time": 1.0, "arrival_rate": 0.3, "fairness_boost": 6.0, "emergency_boost": 0.0, "score": 8.82},
        }
        self.engine.phase_scores = {direction: values["score"] for direction, values in self.engine.phase_demands.items()}
        self.engine.phase_has_demand = {direction: values["score"] > 0.0 for direction, values in self.engine.phase_demands.items()}

        self.engine.update_signals(0.1)

        self.assertEqual(self.engine.current_state, EAST)

    def test_ai_emergency_preempts_before_normal_min_green_when_intersection_is_clear(self) -> None:
        self.engine.update_config({"ai_mode": "adaptive"})
        self._set_green(NORTH, elapsed=EMERGENCY_PREEMPT_MIN_GREEN + 0.4)
        self.engine.phase_demands = {
            "NORTH": {"queue": 5.0, "wait_time": 3.4, "arrival_rate": 1.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 12.1},
            "EAST": {"queue": 1.0, "wait_time": 0.6, "arrival_rate": 0.2, "fairness_boost": 0.0, "emergency_boost": 5.6, "score": 8.4},
            "SOUTH": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 0.0},
            "WEST": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 0.0},
        }
        self.engine.phase_scores = {direction: values["score"] for direction, values in self.engine.phase_demands.items()}
        self.engine.phase_has_demand = {"NORTH": True, "EAST": True, "SOUTH": False, "WEST": False}
        self.engine.traffic_brain_state.emergency.detected = True
        self.engine.traffic_brain_state.emergency.preferred_phase = EAST
        self.engine.traffic_brain_state.emergency.approach = EAST
        self.engine.traffic_brain_state.emergency.vehicle_id = "emer-1"
        self.engine.traffic_brain_state.emergency.eta_seconds = 3.2
        self.engine.traffic_brain_state.emergency.state = "tracking"

        self.engine.update_signals(0.1)

        self.assertEqual(self.engine.current_state, EAST)

    def test_ai_holds_green_for_active_emergency_approach(self) -> None:
        self.engine.update_config({"ai_mode": "adaptive"})
        self._set_green(EAST, elapsed=EMERGENCY_ACTIVE_MIN_GREEN - 0.15)
        self.engine.phase_demands = {
            "NORTH": {"queue": 6.0, "wait_time": 4.0, "arrival_rate": 1.1, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 13.7},
            "EAST": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.3, "fairness_boost": 0.0, "emergency_boost": 5.6, "score": 6.4},
            "SOUTH": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 0.0},
            "WEST": {"queue": 3.0, "wait_time": 1.4, "arrival_rate": 0.7, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 7.0},
        }
        self.engine.phase_scores = {direction: values["score"] for direction, values in self.engine.phase_demands.items()}
        self.engine.phase_has_demand = {"NORTH": True, "EAST": True, "SOUTH": False, "WEST": True}
        self.engine.traffic_brain_state.emergency.detected = True
        self.engine.traffic_brain_state.emergency.preferred_phase = EAST
        self.engine.traffic_brain_state.emergency.approach = EAST
        self.engine.traffic_brain_state.emergency.vehicle_id = "emer-2"
        self.engine.traffic_brain_state.emergency.eta_seconds = 1.8
        self.engine.traffic_brain_state.emergency.state = "serving"

        self.engine.update_signals(0.1)

        self.assertEqual(self.engine.current_state, EAST)

    def test_ai_emergency_relief_switches_after_sustained_noncritical_emergency_service(self) -> None:
        self.engine.update_config({"ai_mode": "adaptive"})
        self._set_green(EAST, elapsed=EMERGENCY_ACTIVE_MIN_GREEN + 0.4)
        self.engine.signal_controller.continuous_green_time = EMERGENCY_MAX_CONTINUOUS_GREEN + 0.5
        self.engine.signal_controller.unserved_demand_time["NORTH"] = EMERGENCY_RELIEF_UNSERVED_TIME + 1.0
        self.engine.phase_demands = {
            "NORTH": {"queue": 5.0, "wait_time": 8.0, "arrival_rate": 0.8, "fairness_boost": 4.5, "emergency_boost": 0.0, "score": 21.6},
            "EAST": {"queue": 4.0, "wait_time": 2.0, "arrival_rate": 0.9, "fairness_boost": 0.0, "emergency_boost": 6.2, "score": 14.3},
            "SOUTH": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 0.0},
            "WEST": {"queue": 1.0, "wait_time": 1.0, "arrival_rate": 0.2, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 2.9},
        }
        self.engine.phase_scores = {direction: values["score"] for direction, values in self.engine.phase_demands.items()}
        self.engine.phase_has_demand = {"NORTH": True, "EAST": True, "SOUTH": False, "WEST": True}
        self.engine.traffic_brain_state.emergency.detected = True
        self.engine.traffic_brain_state.emergency.preferred_phase = EAST
        self.engine.traffic_brain_state.emergency.approach = EAST
        self.engine.traffic_brain_state.emergency.vehicle_id = "emer-fair"
        self.engine.traffic_brain_state.emergency.eta_seconds = 5.2
        self.engine.traffic_brain_state.emergency.vehicle_count = 1
        self.engine.traffic_brain_state.emergency.priority_score = 7.8
        self.engine.traffic_brain_state.emergency.state = "serving"

        self.engine.update_signals(0.1)

        self.assertEqual(self.engine.current_state, NORTH)
        self.assertEqual(self.engine.signal_controller.emergency_relief_lock_direction, NORTH)

    def test_ai_relief_green_resists_noncritical_emergency_repreemption(self) -> None:
        self.engine.update_config({"ai_mode": "adaptive"})
        self._set_green(NORTH, elapsed=EMERGENCY_PREEMPT_MIN_GREEN + 0.6)
        self.engine.signal_controller.emergency_relief_lock_direction = NORTH
        self.engine.signal_controller.continuous_green_time = 2.8
        self.engine.phase_demands = {
            "NORTH": {"queue": 4.0, "wait_time": 5.0, "arrival_rate": 0.7, "fairness_boost": 3.0, "emergency_boost": 0.0, "score": 14.6},
            "EAST": {"queue": 2.0, "wait_time": 1.2, "arrival_rate": 0.4, "fairness_boost": 0.0, "emergency_boost": 6.0, "score": 8.7},
            "SOUTH": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 0.0},
            "WEST": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 0.0},
        }
        self.engine.phase_scores = {direction: values["score"] for direction, values in self.engine.phase_demands.items()}
        self.engine.phase_has_demand = {"NORTH": True, "EAST": True, "SOUTH": False, "WEST": False}
        self.engine.traffic_brain_state.emergency.detected = True
        self.engine.traffic_brain_state.emergency.preferred_phase = EAST
        self.engine.traffic_brain_state.emergency.approach = EAST
        self.engine.traffic_brain_state.emergency.vehicle_id = "emer-lock"
        self.engine.traffic_brain_state.emergency.eta_seconds = 4.5
        self.engine.traffic_brain_state.emergency.vehicle_count = 1
        self.engine.traffic_brain_state.emergency.priority_score = 7.2
        self.engine.traffic_brain_state.emergency.state = "tracking"

        self.engine.update_signals(0.1)

        self.assertEqual(self.engine.current_state, NORTH)

    def test_ai_critical_emergency_can_override_fairness_relief_lock(self) -> None:
        self.engine.update_config({"ai_mode": "adaptive"})
        self._set_green(NORTH, elapsed=EMERGENCY_PREEMPT_MIN_GREEN + 0.6)
        self.engine.signal_controller.emergency_relief_lock_direction = NORTH
        self.engine.signal_controller.continuous_green_time = 2.8
        self.engine.phase_demands = {
            "NORTH": {"queue": 4.0, "wait_time": 5.0, "arrival_rate": 0.7, "fairness_boost": 3.0, "emergency_boost": 0.0, "score": 14.6},
            "EAST": {"queue": 2.0, "wait_time": 1.2, "arrival_rate": 0.4, "fairness_boost": 0.0, "emergency_boost": 7.0, "score": 9.5},
            "SOUTH": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 0.0},
            "WEST": {"queue": 0.0, "wait_time": 0.0, "arrival_rate": 0.0, "fairness_boost": 0.0, "emergency_boost": 0.0, "score": 0.0},
        }
        self.engine.phase_scores = {direction: values["score"] for direction, values in self.engine.phase_demands.items()}
        self.engine.phase_has_demand = {"NORTH": True, "EAST": True, "SOUTH": False, "WEST": False}
        self.engine.traffic_brain_state.emergency.detected = True
        self.engine.traffic_brain_state.emergency.preferred_phase = EAST
        self.engine.traffic_brain_state.emergency.approach = EAST
        self.engine.traffic_brain_state.emergency.vehicle_id = "emer-critical"
        self.engine.traffic_brain_state.emergency.eta_seconds = 1.6
        self.engine.traffic_brain_state.emergency.vehicle_count = 1
        self.engine.traffic_brain_state.emergency.priority_score = 13.4
        self.engine.traffic_brain_state.emergency.state = "tracking"

        self.engine.update_signals(0.1)

        self.assertEqual(self.engine.current_state, EAST)

    def test_ai_signal_outperforms_fixed_cycle_under_skewed_demand(self) -> None:
        benchmark_config = {
            "traffic_intensity": 0.74,
            "spawn_rate_multiplier": 1.12,
            "speed_multiplier": 1.0,
            "safe_gap_multiplier": 0.92,
            "max_emergency_vehicles": 1,
            "max_vehicles": 18,
            "ambulance_frequency": 0.01,
            "route_distribution": {
                "NORTH->SOUTH": 9,
                "NORTH->EAST": 4,
                "NORTH->WEST": 0,
                "EAST->WEST": 0,
                "EAST->SOUTH": 0,
                "EAST->NORTH": 0,
                "SOUTH->NORTH": 0,
                "SOUTH->WEST": 0,
                "SOUTH->EAST": 0,
                "WEST->EAST": 0,
                "WEST->NORTH": 0,
                "WEST->SOUTH": 0,
            },
        }

        fixed_result = self._run_benchmark({"ai_mode": "fixed", **benchmark_config})
        adaptive_result = self._run_benchmark({"ai_mode": "adaptive", **benchmark_config})

        self.assertGreater(adaptive_result["processed"], fixed_result["processed"])
        self.assertLess(adaptive_result["avg_wait_time"], fixed_result["avg_wait_time"])
        self.assertGreaterEqual(adaptive_result["throughput"], fixed_result["throughput"])

    def test_spawned_routes_include_right_turns_when_distribution_requests_them(self) -> None:
        self.engine.vehicles = []
        self.engine.config.max_vehicles = 1
        self.engine.update_config({
            "route_distribution": {
                "NORTH->SOUTH": 0,
                "NORTH->EAST": 0,
                "NORTH->WEST": 9,
                "EAST->WEST": 0,
                "EAST->SOUTH": 0,
                "EAST->NORTH": 0,
                "SOUTH->NORTH": 0,
                "SOUTH->WEST": 0,
                "SOUTH->EAST": 0,
                "WEST->EAST": 0,
                "WEST->NORTH": 0,
                "WEST->SOUTH": 0,
            },
        })

        self.engine._spawn_vehicle()

        self.assertEqual(len(self.engine.vehicles), 1)
        self.assertEqual(self.engine.vehicles[0].origin_direction, "NORTH")
        self.assertEqual(self.engine.vehicles[0].route, "right")
        self.assertEqual(self.engine.vehicles[0].intent, "RIGHT")

    def test_emergency_vehicle_types_have_distinct_safe_profiles(self) -> None:
        baseline = self.engine._make_vehicle("NORTH", "straight")
        ambulance = self.engine._make_vehicle_for_lane("lane_north_straight", emergency_kind="ambulance", intent="STRAIGHT")
        firetruck = self.engine._make_vehicle_for_lane("lane_north_straight", emergency_kind="firetruck", intent="STRAIGHT")
        police = self.engine._make_vehicle_for_lane("lane_north_straight", emergency_kind="police", intent="RIGHT")

        self.assertEqual(ambulance.kind, "ambulance")
        self.assertEqual(ambulance.color, "#f8fafc")
        self.assertTrue(ambulance.has_siren)
        self.assertGreater(ambulance.cruise_speed, baseline.cruise_speed)

        self.assertEqual(firetruck.kind, "firetruck")
        self.assertEqual(firetruck.color, "#dc2626")
        self.assertTrue(firetruck.has_siren)
        self.assertGreaterEqual(firetruck.length, 6.6)

        self.assertEqual(police.kind, "police")
        self.assertEqual(police.color, "#2563eb")
        self.assertEqual(police.intent, "RIGHT")
        self.assertEqual(police.sub_path_side, "RIGHT")
        self.assertTrue(police.has_siren)


if __name__ == "__main__":
    unittest.main()
