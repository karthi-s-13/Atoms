from __future__ import annotations

import math
import unittest

from simulation_engine.engine import EAST, NORTH, SOUTH, SUB_PATH_OFFSET, TrafficSimulationEngine


class CollisionAwarenessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = TrafficSimulationEngine()
        self.engine.vehicles = []
        self.engine.config.max_vehicles = 0

    def _distance_for_sub_path_position(self, lane, sub_path_side: str, target_distance: float) -> float:
        lower_bound = 0.0
        upper_bound = lane.path.length
        for _ in range(32):
            midpoint = (lower_bound + upper_bound) / 2.0
            midpoint_distance = self.engine._sub_path_distance_at(lane, midpoint, sub_path_side)
            if midpoint_distance < target_distance:
                lower_bound = midpoint
            else:
                upper_bound = midpoint
        return lower_bound

    def _set_green(self, direction: str) -> None:
        self.engine.signal_controller.current_green_direction = direction
        self.engine.current_state = direction

    def _set_vehicle_distance(
        self,
        vehicle,
        distance_along: float,
        *,
        speed: float,
        state: str = "MOVING",
    ) -> None:
        lane = self.engine.lanes[vehicle.lane_id]
        self.engine._apply_vehicle_pose(vehicle, lane, distance_along, speed=speed)
        vehicle.speed = speed
        vehicle.state = state
        vehicle.wait_time = 0.0

    def _expected_sub_path_position(self, vehicle) -> tuple[float, float]:
        lane = self.engine.lanes[vehicle.lane_id]
        center = lane.path.point_at_distance(vehicle.distance_along)
        tangent = lane.path.tangent_at_distance(vehicle.distance_along)
        if vehicle.sub_path_side == "LEFT":
            normal_x, normal_y = -tangent.y, tangent.x
        else:
            normal_x, normal_y = tangent.y, -tangent.x
        magnitude = math.hypot(normal_x, normal_y) or 1.0
        return (
            center.x + ((normal_x / magnitude) * SUB_PATH_OFFSET),
            center.y + ((normal_y / magnitude) * SUB_PATH_OFFSET),
        )

    def test_vehicle_stays_locked_to_requested_lane_side_by_intent(self) -> None:
        left_vehicle = self.engine._make_vehicle("NORTH", "left")
        straight_vehicle = self.engine._make_vehicle("NORTH", "straight")
        right_vehicle = self.engine._make_vehicle("NORTH", "right")
        left_lane = self.engine.lanes[left_vehicle.lane_id]
        straight_lane = self.engine.lanes[straight_vehicle.lane_id]
        right_lane = self.engine.lanes[right_vehicle.lane_id]
        self._set_vehicle_distance(left_vehicle, 18.0, speed=left_vehicle.cruise_speed)
        self._set_vehicle_distance(straight_vehicle, 18.0, speed=straight_vehicle.cruise_speed)
        self._set_vehicle_distance(right_vehicle, 18.0, speed=right_vehicle.cruise_speed)
        self.engine.vehicles = [left_vehicle, straight_vehicle, right_vehicle]
        self._set_green(NORTH)

        for _ in range(12):
            self.engine.update_vehicles(0.2)
            left_expected_x, left_expected_y = self._expected_sub_path_position(left_vehicle)
            straight_expected_x, straight_expected_y = self._expected_sub_path_position(straight_vehicle)
            right_expected_x, right_expected_y = self._expected_sub_path_position(right_vehicle)
            self.assertAlmostEqual(left_vehicle.position.x, left_expected_x, places=6)
            self.assertAlmostEqual(left_vehicle.position.y, left_expected_y, places=6)
            self.assertAlmostEqual(straight_vehicle.position.x, straight_expected_x, places=6)
            self.assertAlmostEqual(straight_vehicle.position.y, straight_expected_y, places=6)
            self.assertAlmostEqual(right_vehicle.position.x, right_expected_x, places=6)
            self.assertAlmostEqual(right_vehicle.position.y, right_expected_y, places=6)
            self.assertGreater(left_vehicle.position.x, left_lane.path.point_at_distance(left_vehicle.distance_along).x)
            self.assertLess(straight_vehicle.position.x, straight_lane.path.point_at_distance(straight_vehicle.distance_along).x)
            self.assertLess(right_vehicle.position.x, right_lane.path.point_at_distance(right_vehicle.distance_along).x)

    def test_same_lane_queue_never_overlaps(self) -> None:
        leader = self.engine._make_vehicle("NORTH", "straight")
        follower = self.engine._make_vehicle("NORTH", "straight")
        lane = self.engine.lanes[leader.lane_id]
        self._set_vehicle_distance(leader, 38.0, speed=0.0, state="STOPPED")
        self._set_vehicle_distance(follower, 27.0, speed=follower.cruise_speed, state="MOVING")
        self.engine.vehicles = [leader, follower]
        self._set_green(NORTH)

        for _ in range(10):
            self.engine.update_vehicles(0.25)
            required_gap = self.engine._minimum_follow_distance(follower, leader)
            self.assertGreaterEqual(
                self.engine._distance_between_vehicles_on_path(lane, leader, follower),
                required_gap - 1e-6,
            )
            self.assertLessEqual(follower.distance_along, lane.path.length)

    def test_turning_queue_keeps_spacing_along_arc_path(self) -> None:
        leader = self.engine._make_vehicle("NORTH", "left")
        follower = self.engine._make_vehicle("NORTH", "left")
        lane = self.engine.lanes[leader.lane_id]
        leader_distance = lane.path.entry_length + (lane.path.arc.length * 0.84)
        required_gap = self.engine._minimum_follow_distance(follower, leader)
        leader_sub_distance = self.engine._sub_path_distance_at(lane, leader_distance, leader.sub_path_side)
        follower_sub_distance = max(0.0, leader_sub_distance - (required_gap + 1.6))
        follower_distance = self._distance_for_sub_path_position(
            lane,
            follower.sub_path_side,
            follower_sub_distance,
        )

        self._set_vehicle_distance(leader, leader_distance, speed=leader.cruise_speed * 0.35, state="MOVING")
        self._set_vehicle_distance(follower, follower_distance, speed=follower.cruise_speed, state="MOVING")
        self.engine.vehicles = [leader, follower]
        self._set_green(NORTH)

        for _ in range(6):
            self.engine.update_vehicles(0.25)
            required_gap = self.engine._minimum_follow_distance(follower, leader)
            self.assertGreaterEqual(
                self.engine._distance_between_vehicles_on_path(lane, leader, follower),
                required_gap - 1e-6,
            )

    def test_opposing_straight_lanes_do_not_false_block_inside_intersection(self) -> None:
        westbound = self.engine._make_vehicle("WEST", "straight")
        eastbound = self.engine._make_vehicle("EAST", "straight")
        west_lane = self.engine.lanes[westbound.lane_id]
        east_lane = self.engine.lanes[eastbound.lane_id]

        self._set_vehicle_distance(
            westbound,
            west_lane.stop_distance + 1.2,
            speed=westbound.cruise_speed,
            state="MOVING",
        )
        self._set_vehicle_distance(
            eastbound,
            east_lane.intersection_entry_distance + 2.0,
            speed=eastbound.cruise_speed * 0.55,
            state="MOVING",
        )
        self.engine.vehicles = [westbound, eastbound]
        self._set_green(EAST)
        start_distance = westbound.distance_along

        self.engine.update_vehicles(0.35)

        self.assertGreater(westbound.distance_along, start_distance)
        self.assertEqual(westbound.state, "MOVING")
        self.assertFalse(self.engine._vehicle_collides_with_any_object(westbound, [eastbound]))

    def test_long_run_flow_despawns_and_respawns_without_breakdown(self) -> None:
        self.engine.reset({
            "paused": False,
            "traffic_intensity": 0.9,
            "spawn_rate_multiplier": 1.6,
            "max_vehicles": 10,

        })

        for _ in range(600):
            self.engine.tick(0.1)
            self.assertLessEqual(len(self.engine.vehicles), self.engine.config.max_vehicles)

            lane_groups = {}
            for vehicle in self.engine.vehicles:
                expected_x, expected_y = self._expected_sub_path_position(vehicle)
                self.assertAlmostEqual(vehicle.position.x, expected_x, places=5)
                self.assertAlmostEqual(vehicle.position.y, expected_y, places=5)
                lane_groups.setdefault(vehicle.lane_id, []).append(vehicle)

            for lane_vehicles in lane_groups.values():
                lane_vehicles.sort(key=lambda item: item.distance_along, reverse=True)
                for leader, follower in zip(lane_vehicles, lane_vehicles[1:]):
                    lane = self.engine.lanes[leader.lane_id]
                    required_gap = self.engine._minimum_follow_distance(follower, leader)
                    self.assertGreaterEqual(
                        self.engine._distance_between_vehicles_on_path(lane, leader, follower),
                        required_gap - 1e-6,
                    )

        self.assertGreater(self.engine.processed_vehicles, 0)


if __name__ == "__main__":
    unittest.main()
