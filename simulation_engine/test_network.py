"""Compatibility coverage for the simplified TrafficNetwork wrapper."""

from __future__ import annotations

import unittest

from simulation_engine import TrafficNetwork


class TrafficNetworkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.network = TrafficNetwork()
        self.network.update_config({"max_vehicles": 0, "max_pedestrians": 0})

    def test_tick_delegates_to_single_intersection_snapshot(self) -> None:
        snapshot = self.network.tick()

        self.assertEqual(snapshot["current_state"], "NORTH")
        self.assertEqual(snapshot["signals"], {"NORTH": "GREEN", "EAST": "RED", "SOUTH": "RED", "WEST": "RED"})
        self.assertEqual(snapshot["pedestrians"], [])

    def test_reset_clears_engine_state(self) -> None:
        self.network.engine.vehicles = [self.network.engine._make_vehicle("NORTH", "straight")]
        self.network.reset()

        snapshot = self.network.snapshot().to_dict()
        self.assertEqual(snapshot["vehicles"], [])
        self.assertEqual(snapshot["current_state"], "NORTH")


if __name__ == "__main__":
    unittest.main()
