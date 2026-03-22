"""Validation for the production traffic engine."""

from __future__ import annotations

import unittest

from shared.contracts import Point2D
from simulation_engine.engine import MIN_GREEN, PEDESTRIAN_MAX, PedestrianStateModel, TrafficSimulationEngine


class TrafficSimulationEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = TrafficSimulationEngine()

    def test_only_one_direction_green(self) -> None:
        snapshot = self.engine.snapshot().to_dict()
        green_count = sum(1 for direction in ("NORTH", "SOUTH", "EAST", "WEST") if snapshot["signals"][direction] == "GREEN")
        self.assertEqual(green_count, 1)

    def test_emergency_override_prefers_siren_direction(self) -> None:
        north = self.engine._make_vehicle("NORTH")
        north.kind = "ambulance"
        north.has_siren = True
        north.priority = 100
        self.engine.vehicles = [north]
        self.engine.active_direction = "SOUTH"
        self.engine.phase_state = "GREEN"
        self.engine.phase_elapsed = 0.2

        self.engine.update_signals(0.016)
        self.assertEqual(self.engine.phase_state, "GREEN")
        self.assertEqual(self.engine.active_direction, "NORTH")

    def test_vehicle_stops_before_zebra_on_red(self) -> None:
        vehicle = self.engine._make_vehicle("EAST")
        vehicle.position = Point2D(21.0, 0.0)
        vehicle.approach_distance = self.engine._approach_distance(vehicle)
        self.engine._update_vehicle_progress(vehicle)
        vehicle.speed = vehicle.cruise_speed
        self.engine.vehicles = [vehicle]
        self.engine.active_direction = "NORTH"
        self.engine.phase_state = "GREEN"

        for _ in range(90):
            self.engine.update_vehicles(0.016)

        self.assertGreaterEqual(vehicle.position.x, 17.0)
        self.assertEqual(vehicle.speed, 0.0)

    def test_vehicle_stays_on_lane_during_approach(self) -> None:
        vehicle = self.engine._make_vehicle("NORTH")
        self.engine.vehicles = [vehicle]
        self.engine.active_direction = "NORTH"
        self.engine.phase_state = "GREEN"

        for _ in range(80):
            self.engine.update_vehicles(0.016)
            if vehicle.segment != "APPROACH":
                break
            self.assertAlmostEqual(vehicle.position.x, 0.0, places=4)

    def test_vehicle_moves_when_lane_is_green(self) -> None:
        vehicle = self.engine._make_vehicle("WEST")
        self.engine.vehicles = [vehicle]
        self.engine.active_direction = "WEST"
        self.engine.phase_state = "GREEN"
        before = self.engine._approach_distance(vehicle)

        for _ in range(20):
            self.engine.update_vehicles(0.016)

        self.assertGreater(self.engine._approach_distance(vehicle), before)
        self.assertGreater(vehicle.speed, 0.0)

    def test_pedestrian_crosswalks_are_perpendicular(self) -> None:
        north_crosswalk = self.engine.crosswalks["north_crosswalk"]
        east_crosswalk = self.engine.crosswalks["east_crosswalk"]
        self.assertEqual((north_crosswalk.movement.x, north_crosswalk.movement.y), (1.0, 0.0))
        self.assertEqual((east_crosswalk.movement.x, east_crosswalk.movement.y), (0.0, 1.0))

    def test_pedestrian_phase_forces_all_red(self) -> None:
        self.engine.pedestrians = [
            PedestrianStateModel(
                id="ped-test",
                crosswalk_id="north_crosswalk",
                road_direction="NS",
                progress=0.0,
                speed=2.5,
                wait_time=0.0,
            )
        ]
        self.engine.phase_elapsed = MIN_GREEN + 0.1
        self.engine.update_signals(0.016)
        self.engine.update_signals(2.0)
        snapshot = self.engine.snapshot().to_dict()
        self.assertTrue(snapshot["pedestrian_phase_active"])
        for direction in ("NORTH", "SOUTH", "EAST", "WEST"):
            self.assertEqual(snapshot["signals"][direction], "RED")

    def test_tick_recovers_missing_active_direction(self) -> None:
        self.engine.active_direction = None
        self.engine.pedestrian_phase_active = False

        snapshot = self.engine.tick(0.016)

        self.assertIn(snapshot["active_direction"], ("NORTH", "SOUTH", "EAST", "WEST"))

    def test_pedestrian_phase_has_timeout(self) -> None:
        self.engine.pedestrian_phase_active = True
        self.engine.active_direction = None
        self.engine.phase_elapsed = PEDESTRIAN_MAX + 0.1
        self.engine.pedestrians = [
            PedestrianStateModel(
                id="ped-stuck",
                crosswalk_id="east_crosswalk",
                road_direction="EW",
                progress=0.4,
                speed=0.0,
                wait_time=0.0,
                state="CROSSING",
            )
        ]

        self.engine.update_signals(0.016)

        self.assertFalse(self.engine.pedestrian_phase_active)
        self.assertIn(self.engine.active_direction, ("NORTH", "SOUTH", "EAST", "WEST"))


if __name__ == "__main__":
    unittest.main()
