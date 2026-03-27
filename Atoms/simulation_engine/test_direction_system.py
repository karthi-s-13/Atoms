"""Validation coverage for the fixed global direction system."""

from __future__ import annotations

import unittest

from simulation_engine.engine import LANE_SLOT_INDEX, TrafficSimulationEngine
from shared.contracts import WORLD_DIRECTION_AXES


class DirectionSystemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = TrafficSimulationEngine()
        self.engine.update_config({"max_vehicles": 0})

    def test_snapshot_exposes_fixed_world_direction_axes(self) -> None:
        snapshot = self.engine.snapshot().to_dict()

        self.assertEqual(snapshot["direction_axes"]["NORTH"], {"x": 0.0, "z": -1.0})
        self.assertEqual(snapshot["direction_axes"]["SOUTH"], {"x": 0.0, "z": 1.0})
        self.assertEqual(snapshot["direction_axes"]["EAST"], {"x": 1.0, "z": 0.0})
        self.assertEqual(snapshot["direction_axes"]["WEST"], {"x": -1.0, "z": 0.0})
        self.assertIn("NORTH->SOUTH", snapshot["config"]["route_distribution"])
        self.assertAlmostEqual(snapshot["config"]["traffic_intensity"], 0.48)
        self.assertAlmostEqual(snapshot["config"]["spawn_rate_multiplier"], 0.92)
        self.assertEqual(snapshot["config"]["max_emergency_vehicles"], 3)
        self.assertEqual(snapshot["config"]["safe_gap_multiplier"], 1.0)
        self.assertEqual(snapshot["config"]["turn_smoothness"], 1.0)
        self.assertTrue(snapshot["config"]["paused"])
        self.assertEqual(WORLD_DIRECTION_AXES["NORTH"].z, -1.0)

    def test_lane_view_exposes_direction_type_and_numeric_index(self) -> None:
        lanes = {lane.id: lane for lane in self.engine.snapshot().lanes}
        north_straight = lanes["lane_north_straight"]
        north_right = lanes["lane_north_right"]
        north_left = lanes["lane_north_left"]

        self.assertEqual(north_straight.direction, "NORTH")
        self.assertEqual(north_straight.lane_type, "INCOMING")
        self.assertEqual(north_straight.lane_index, 1)
        self.assertEqual(north_straight.lane_slot, "inner")
        self.assertEqual(north_straight.kind, "main")
        self.assertTrue(north_straight.left_sub_path)
        self.assertTrue(north_straight.right_sub_path)
        self.assertGreater(north_straight.left_sub_path[0].x, north_straight.start.x)
        self.assertLess(north_straight.right_sub_path[0].x, north_straight.start.x)
        self.assertAlmostEqual(north_straight.right_sub_path[0].y, north_straight.start.y, places=6)
        self.assertAlmostEqual(north_straight.left_sub_path[0].y, north_straight.start.y, places=6)

        self.assertEqual(north_left.direction, "NORTH")
        self.assertEqual(north_left.lane_type, "INCOMING")
        self.assertEqual(north_left.lane_index, 0)
        self.assertEqual(north_left.lane_slot, "outer")
        self.assertEqual(north_left.kind, "main")
        self.assertGreater(north_left.left_sub_path[0].x, north_left.start.x)
        self.assertLess(north_left.right_sub_path[0].x, north_left.start.x)
        self.assertEqual(north_right.direction, "NORTH")
        self.assertEqual(north_right.lane_type, "INCOMING")
        self.assertEqual(north_right.lane_index, 1)
        self.assertEqual(north_right.lane_slot, "inner")
        self.assertEqual(north_right.movement, "RIGHT")
        self.assertAlmostEqual(north_right.start.x, north_straight.start.x, places=6)
        self.assertAlmostEqual(north_right.start.y, north_straight.start.y, places=6)
        self.assertEqual(LANE_SLOT_INDEX["outer"], 0)
        self.assertFalse(any("slip" in lane_id for lane_id in lanes))

        east_straight = lanes["lane_east_straight"]
        self.assertLess(east_straight.left_sub_path[0].y, east_straight.start.y)
        self.assertGreater(east_straight.right_sub_path[0].y, east_straight.start.y)

    def test_vehicle_view_keeps_origin_direction_and_current_lane(self) -> None:
        vehicle = self.engine._make_vehicle("NORTH", "straight")
        vehicle_view = self.engine._vehicle_view(vehicle)

        self.assertEqual(vehicle_view.origin_direction, "NORTH")
        self.assertEqual(vehicle_view.current_lane_id, vehicle.lane_id)
        self.assertEqual(vehicle_view.approach, "NORTH")
        self.assertEqual(vehicle_view.intent, "STRAIGHT")
        self.assertEqual(vehicle_view.sub_path_side, "RIGHT")


if __name__ == "__main__":
    unittest.main()
