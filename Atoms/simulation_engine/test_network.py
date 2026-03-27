"""Compatibility coverage for the simplified TrafficNetwork wrapper."""

from __future__ import annotations

import unittest

from simulation_engine import TrafficNetwork


class TrafficNetworkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.network = TrafficNetwork()
        self.network.update_config({"max_vehicles": 0})

    def test_tick_delegates_to_single_intersection_snapshot(self) -> None:
        snapshot = self.network.tick()

        self.assertEqual(snapshot["current_state"], "NORTH")
        self.assertEqual(snapshot["signals"], {"NORTH": "GREEN", "EAST": "RED", "SOUTH": "RED", "WEST": "RED"})
        self.assertEqual(snapshot["vehicles"], [])
        self.assertTrue(snapshot["config"]["paused"])
        self.assertEqual(snapshot["timestamp"], 0.0)

    def test_reset_clears_engine_state(self) -> None:
        self.network.engine.vehicles = [self.network.engine._make_vehicle("NORTH", "straight")]
        self.network.reset()

        snapshot = self.network.snapshot().to_dict()
        self.assertEqual(snapshot["vehicles"], [])
        self.assertEqual(snapshot["current_state"], "NORTH")

    def test_reset_accepts_config_and_applies_it(self) -> None:
        self.network.reset({"traffic_intensity": 0.18, "paused": False, "max_vehicles": 12})

        snapshot = self.network.snapshot().to_dict()

        self.assertAlmostEqual(snapshot["config"]["traffic_intensity"], 0.18)
        self.assertFalse(snapshot["config"]["paused"])
        self.assertEqual(snapshot["config"]["max_vehicles"], 12)


if __name__ == "__main__":
    unittest.main()
