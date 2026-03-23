"""Validation for the adaptive protected multi-phase intersection simulation."""

from __future__ import annotations

import unittest

from simulation_engine.engine import (
    ALL_RED_TIME,
    CROSSWALK_CENTER_OFFSET,
    EW_LEFT,
    EW_STRAIGHT,
    LEFT_MIN_GREEN,
    NS_LEFT,
    NS_STRAIGHT,
    PEDESTRIAN_SPEED,
    PHASE_ALL_RED,
    PHASE_GREEN,
    PHASE_YELLOW,
    STARVATION_LIMIT,
    STRAIGHT_MAX_GREEN,
    STRAIGHT_MIN_GREEN,
    TrafficSimulationEngine,
    YELLOW_TIME,
)


class TrafficSimulationEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = TrafficSimulationEngine()
        self.engine.vehicles = []
        self.engine.pedestrians = []
        self.engine.config.max_vehicles = 0
        self.engine.config.max_pedestrians = 0

    def _set_phase(self, phase: str, *, stage: str = PHASE_GREEN, elapsed: float = 0.0) -> None:
        self.engine.signal_controller.current_phase_name = phase
        self.engine.signal_controller.next_phase_name = phase
        self.engine.signal_controller.stage = stage
        self.engine.signal_controller.stage_elapsed = elapsed
        self.engine.signal_controller.all_red_release_time = ALL_RED_TIME
        self.engine.signal_controller.unserved_demand_time = {
            key: 0.0 for key in self.engine.signal_controller.unserved_demand_time
        }
        self.engine.current_state = self.engine.signal_controller.state

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

    def _make_pedestrian(
        self,
        crosswalk_id: str,
        *,
        wait_time: float = 0.0,
        reverse: bool = False,
    ):
        pedestrian = self.engine._make_pedestrian(crosswalk_id, reverse=reverse)
        pedestrian.speed = PEDESTRIAN_SPEED
        pedestrian.wait_time = wait_time
        pedestrian.state = "WAITING"
        return pedestrian

    def test_initial_snapshot_starts_in_ns_green(self) -> None:
        snapshot = self.engine.snapshot().to_dict()

        self.assertEqual(snapshot["current_state"], NS_STRAIGHT)
        self.assertEqual(snapshot["controller_phase"], PHASE_GREEN)
        self.assertEqual(set(snapshot["signals"].keys()), {"NORTH", "SOUTH", "EAST", "WEST"})
        self.assertEqual(snapshot["signals"]["NORTH"], "GREEN")
        self.assertEqual(snapshot["signals"]["SOUTH"], "GREEN")
        self.assertEqual(snapshot["signals"]["EAST"], "RED")
        self.assertEqual(snapshot["signals"]["WEST"], "RED")
        self.assertIn("traffic_brain", snapshot)

    def test_demand_calculation_uses_queue_wait_and_safe_pedestrian_pressure(self) -> None:
        ns_straight_a = self._make_vehicle("NORTH", "straight", wait_time=3.0, speed=0.0)
        ns_straight_b = self._make_vehicle("SOUTH", "straight", wait_time=1.0, speed=0.0)
        ew_left = self._make_vehicle("EAST", "left", wait_time=4.0, speed=0.0)
        pedestrian = self._make_pedestrian("north_crosswalk", wait_time=5.0)
        self.engine.vehicles = [ns_straight_a, ns_straight_b, ew_left]
        self.engine.pedestrians = [pedestrian]

        phase_demands, phase_scores, phase_has_demand = self.engine.calculate_phase_demands()

        self.assertEqual(phase_demands[NS_STRAIGHT]["queue"], 2.0)
        self.assertAlmostEqual(phase_demands[NS_STRAIGHT]["wait_time"], 2.0, places=3)
        self.assertEqual(phase_demands[NS_STRAIGHT]["pedestrian_demand"], 1.0)
        self.assertIn("flow_rate", phase_demands[NS_STRAIGHT])
        self.assertIn("congestion_trend", phase_demands[NS_STRAIGHT])
        self.assertIn("fairness_boost", phase_demands[NS_STRAIGHT])
        self.assertGreater(phase_scores[NS_STRAIGHT], phase_scores[EW_LEFT])
        self.assertEqual(phase_demands[EW_LEFT]["queue"], 1.0)
        self.assertEqual(phase_demands[EW_LEFT]["pedestrian_demand"], 0.0)
        self.assertTrue(phase_has_demand[EW_LEFT])
        self.assertFalse(phase_has_demand[EW_STRAIGHT])

    def test_snapshot_exposes_traffic_brain_hooks(self) -> None:
        self.engine.vehicles = [self._make_vehicle("WEST", "straight", wait_time=2.5, speed=0.0)]
        self.engine._refresh_phase_demand_cache(0.1)

        snapshot = self.engine.snapshot().to_dict()
        traffic_brain = snapshot["traffic_brain"]

        self.assertEqual(set(traffic_brain["direction_metrics"].keys()), {"NORTH", "SOUTH", "EAST", "WEST"})
        self.assertEqual(set(traffic_brain["phase_scores"].keys()), {NS_STRAIGHT, NS_LEFT, EW_STRAIGHT, EW_LEFT})
        self.assertIn("strategy", traffic_brain)
        self.assertIn("active_phase_score", traffic_brain)
        self.assertFalse(traffic_brain["emergency"]["detected"])

    def test_min_green_prevents_early_switch(self) -> None:
        self._set_phase(NS_STRAIGHT, elapsed=STRAIGHT_MIN_GREEN - 0.05)
        self.engine.vehicles = [self._make_vehicle("EAST", "left", wait_time=8.0, speed=0.0)]

        self.engine.update_signals(0.01)

        self.assertEqual(self.engine.current_state, NS_STRAIGHT)
        self.assertEqual(self.engine.signal_controller.controller_phase(), PHASE_GREEN)

    def test_phase_switch_passes_through_yellow_then_all_red_then_next_green(self) -> None:
        self._set_phase(NS_STRAIGHT, elapsed=STRAIGHT_MIN_GREEN + 0.1)
        self.engine.vehicles = [self._make_vehicle("EAST", "left", wait_time=8.0, speed=0.0)]

        self.engine.update_signals(0.05)
        self.assertEqual(self.engine.signal_controller.controller_phase(), PHASE_YELLOW)
        self.assertEqual(self.engine.signal_controller.next_phase_name, EW_LEFT)
        self.assertEqual(self.engine._signal_snapshot()["NORTH"], "YELLOW")
        self.assertEqual(self.engine._signal_snapshot()["EAST"], "RED")

        self.engine.update_signals(YELLOW_TIME + 0.01)
        self.assertEqual(self.engine.signal_controller.controller_phase(), PHASE_ALL_RED)
        self.assertEqual(self.engine._signal_snapshot(), {
            "NORTH": "RED",
            "SOUTH": "RED",
            "EAST": "RED",
            "WEST": "RED",
        })

        self.engine.update_signals(ALL_RED_TIME + 0.01)
        self.assertEqual(self.engine.current_state, EW_LEFT)
        self.assertEqual(self.engine.signal_controller.controller_phase(), PHASE_GREEN)
        self.assertEqual(self.engine._signal_snapshot()["EAST"], "GREEN_LEFT")

    def test_max_green_forces_rotation_when_other_demand_exists(self) -> None:
        self._set_phase(NS_STRAIGHT, elapsed=STRAIGHT_MAX_GREEN + 0.05)
        self.engine.vehicles = [
            self._make_vehicle("NORTH", "straight", wait_time=0.0),
            self._make_vehicle("SOUTH", "straight", wait_time=0.0),
            self._make_vehicle("WEST", "left", wait_time=0.5, speed=0.0),
        ]

        self.engine.update_signals(0.01)

        self.assertEqual(self.engine.signal_controller.controller_phase(), PHASE_YELLOW)
        self.assertEqual(self.engine.signal_controller.next_phase_name, EW_LEFT)

    def test_starvation_guard_promotes_waiting_phase(self) -> None:
        self._set_phase(NS_STRAIGHT, elapsed=STRAIGHT_MIN_GREEN + 0.1)
        self.engine.vehicles = [
            self._make_vehicle("NORTH", "straight", wait_time=0.0),
            self._make_vehicle("SOUTH", "straight", wait_time=0.0),
            self._make_vehicle("WEST", "left", wait_time=0.0),
        ]
        self.engine.signal_controller.unserved_demand_time[EW_LEFT] = STARVATION_LIMIT + 1.0

        self.engine.update_signals(0.05)

        self.assertEqual(self.engine.signal_controller.next_phase_name, EW_LEFT)
        self.assertEqual(self.engine.signal_controller.controller_phase(), PHASE_YELLOW)

    def test_emergency_vehicle_prepares_phase_change_without_skipping_transitions(self) -> None:
        emergency_vehicle = self._make_vehicle("EAST", "straight", wait_time=6.0, speed=0.0)
        emergency_vehicle.kind = "ambulance"
        emergency_vehicle.has_siren = True
        emergency_vehicle.priority = 2
        self._set_phase(NS_STRAIGHT, elapsed=STRAIGHT_MIN_GREEN + 0.1)
        self.engine.vehicles = [emergency_vehicle]

        self.engine.update_signals(0.05)

        self.assertEqual(self.engine.traffic_brain_state.emergency.preferred_phase, EW_STRAIGHT)
        self.assertEqual(self.engine.signal_controller.next_phase_name, EW_STRAIGHT)
        self.assertEqual(self.engine.signal_controller.controller_phase(), PHASE_YELLOW)

    def test_active_flow_bonus_avoids_cutting_current_stream(self) -> None:
        self._set_phase(NS_STRAIGHT, elapsed=STRAIGHT_MIN_GREEN + 0.1)
        flowing_vehicle = self._make_vehicle("NORTH", "straight", distance_before_stop=6.0, wait_time=0.0, speed=8.0)
        competing_vehicle = self._make_vehicle("WEST", "left", wait_time=0.2, speed=0.0)
        self.engine.vehicles = [flowing_vehicle, competing_vehicle]
        self.engine._vehicles_processed_by_approach_last_tick["NORTH"] = 2

        self.engine.update_signals(0.05)

        self.assertEqual(self.engine.signal_controller.controller_phase(), PHASE_GREEN)
        self.assertEqual(self.engine.current_state, NS_STRAIGHT)
        self.assertGreater(
            self.engine.traffic_brain_state.phase_scores[NS_STRAIGHT].flow_component,
            self.engine.traffic_brain_state.phase_scores[EW_LEFT].flow_component,
        )

    def test_vehicle_permission_matches_active_phase_and_intent(self) -> None:
        straight_vehicle = self._make_vehicle("NORTH", "straight", distance_before_stop=1.0, wait_time=2.0, speed=0.0)
        left_vehicle = self._make_vehicle("NORTH", "left", distance_before_stop=1.0, wait_time=2.0, speed=0.0)
        self.engine.vehicles = [straight_vehicle, left_vehicle]
        self._set_phase(NS_LEFT)

        self.engine.update_vehicles(0.4)

        self.assertEqual(straight_vehicle.state, "STOPPED")
        self.assertGreater(left_vehicle.distance_along, self.engine.lanes[left_vehicle.lane_id].stop_distance - 1.0)

    def test_yellow_allows_close_vehicle_to_clear_but_far_vehicle_stops(self) -> None:
        close_vehicle = self._make_vehicle("NORTH", "straight", distance_before_stop=1.0, speed=8.0)
        far_vehicle = self._make_vehicle("SOUTH", "straight", distance_before_stop=8.0, speed=8.0)
        self.engine.vehicles = [close_vehicle, far_vehicle]
        self._set_phase(NS_STRAIGHT, stage=PHASE_YELLOW, elapsed=0.4)

        for _ in range(4):
            self.engine.update_signals(0.3)
            self.engine.update_vehicles(0.3)

        self.assertGreater(close_vehicle.distance_along, self.engine.lanes[close_vehicle.lane_id].stop_distance)
        self.assertLessEqual(far_vehicle.distance_along, self.engine.lanes[far_vehicle.lane_id].stop_distance)
        self.assertEqual(far_vehicle.state, "STOPPED")

    def test_all_red_prevents_vehicle_entry(self) -> None:
        vehicle = self._make_vehicle("NORTH", "straight", distance_before_stop=1.5, speed=8.0)
        self.engine.vehicles = [vehicle]
        self._set_phase(NS_STRAIGHT, stage=PHASE_ALL_RED, elapsed=0.5)

        self.engine.update_vehicles(0.3)
        self.engine.update_vehicles(0.3)

        self.assertLessEqual(vehicle.distance_along, self.engine.lanes[vehicle.lane_id].stop_distance)
        self.assertEqual(vehicle.state, "STOPPED")

    def test_all_red_extends_until_intersection_clears(self) -> None:
        vehicle = self._make_vehicle("NORTH", "straight", distance_before_stop=0.0, speed=4.0)
        vehicle.position.x = 0.0
        vehicle.position.y = 0.0
        self.engine.vehicles = [vehicle]
        self._set_phase(NS_STRAIGHT, stage=PHASE_ALL_RED, elapsed=ALL_RED_TIME + 0.1)
        self.engine.signal_controller.next_phase_name = EW_LEFT

        self.engine.update_signals(0.1)

        self.assertEqual(self.engine.signal_controller.controller_phase(), PHASE_ALL_RED)
        self.assertGreater(self.engine.signal_controller.stage_duration(), ALL_RED_TIME)

        self.engine.vehicles = []
        self.engine.update_signals(0.31)

        self.assertEqual(self.engine.current_state, EW_LEFT)
        self.assertEqual(self.engine.signal_controller.controller_phase(), PHASE_GREEN)

    def test_pedestrians_do_not_start_on_yellow_or_all_red_but_continue_if_already_crossing(self) -> None:
        waiting = self._make_pedestrian("north_crosswalk", wait_time=2.0)
        self.engine.pedestrians = [waiting]

        self._set_phase(NS_STRAIGHT, stage=PHASE_YELLOW, elapsed=0.4)
        self.engine.update_pedestrians(0.5)
        self.assertEqual(waiting.state, "WAITING")

        self._set_phase(NS_STRAIGHT, stage=PHASE_ALL_RED, elapsed=0.4)
        self.engine.update_pedestrians(0.5)
        self.assertEqual(waiting.state, "WAITING")

        crossing = self._make_pedestrian("north_crosswalk", wait_time=1.0)
        self.engine.pedestrians = [crossing]
        self._set_phase(NS_STRAIGHT)
        self.engine.update_pedestrians(0.5)
        self.assertEqual(crossing.state, "CROSSING")
        crossing_x = crossing.position.x

        self._set_phase(NS_STRAIGHT, stage=PHASE_YELLOW, elapsed=0.5)
        self.engine.update_pedestrians(0.5)
        self.assertEqual(crossing.state, "CROSSING")
        self.assertGreater(crossing.position.x, crossing_x)

        self._set_phase(NS_STRAIGHT, stage=PHASE_ALL_RED, elapsed=0.5)
        self.engine.update_pedestrians(0.5)
        self.assertEqual(crossing.state, "CROSSING")
        self.assertAlmostEqual(crossing.position.y, CROSSWALK_CENTER_OFFSET, places=4)

    def test_reset_clears_actors_and_restores_adaptive_phase(self) -> None:
        self.engine.vehicles = [self._make_vehicle("SOUTH", "left", wait_time=3.0, speed=0.0)]
        self.engine.pedestrians = [self._make_pedestrian("west_crosswalk", wait_time=2.0)]
        self._set_phase(EW_LEFT, stage=PHASE_ALL_RED, elapsed=0.4)

        self.engine.reset()
        snapshot = self.engine.snapshot().to_dict()

        self.assertEqual(snapshot["vehicles"], [])
        self.assertEqual(snapshot["pedestrians"], [])
        self.assertEqual(snapshot["current_state"], NS_STRAIGHT)
        self.assertEqual(snapshot["controller_phase"], PHASE_GREEN)
        self.assertEqual(snapshot["config"]["ai_mode"], "adaptive")


if __name__ == "__main__":
    unittest.main()
