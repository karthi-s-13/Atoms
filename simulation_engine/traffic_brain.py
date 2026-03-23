"""Small deterministic telemetry layer for the simplified single-green controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Sequence

from shared.contracts import (
    Approach,
    CongestionAlertView,
    ControllerPhase,
    DirectionMetricView,
    EmergencyPriorityView,
    PhaseScoreView,
    RoadDirection,
    SignalCycleState,
    TrafficBrainView,
    VehicleKind,
)

APPROACH_ORDER: tuple[Approach, ...] = ("NORTH", "EAST", "SOUTH", "WEST")
EMERGENCY_KINDS: tuple[VehicleKind, ...] = ("ambulance", "firetruck", "police")

QUEUE_SCORE_WEIGHT = 1.35
WAIT_SCORE_WEIGHT = 0.42
TREND_SCORE_WEIGHT = 0.8
FLOW_SCORE_WEIGHT = 0.3
FAIRNESS_SCORE_WEIGHT = 0.08
EMERGENCY_BASE_BOOST = 4.5
CONGESTION_QUEUE_MEDIUM = 3.0
CONGESTION_QUEUE_HIGH = 5.0
CONGESTION_WAIT_HIGH = 4.0
FLOW_SMOOTHING = 0.35


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _lerp(a: float, b: float, t: float) -> float:
    return a + ((b - a) * t)


@dataclass(frozen=True)
class VehicleTelemetryInput:
    id: str
    lane_id: str
    approach: Approach
    wait_time: float
    speed: float
    cruise_speed: float
    state: str
    distance_to_stop: float
    queued: bool
    kind: VehicleKind
    has_siren: bool


@dataclass(frozen=True)
class PedestrianTelemetryInput:
    crossing: RoadDirection
    wait_time: float
    state: str


class TrafficBrain:
    """Compute simple queue and flow telemetry without controlling the signals."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.previous_direction_queues: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        self.smoothed_flow_rates: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}

    def evaluate(
        self,
        *,
        dt: float,
        current_phase: SignalCycleState,
        controller_phase: ControllerPhase,
        vehicles: Sequence[VehicleTelemetryInput],
        pedestrians: Sequence[PedestrianTelemetryInput],
        lane_phase_map: Mapping[str, SignalCycleState],
        phase_lane_ids: Mapping[SignalCycleState, tuple[str, ...]],
        phase_crossings: Mapping[SignalCycleState, RoadDirection | None],
        phase_order: Sequence[SignalCycleState],
        unserved_demand_time: Mapping[SignalCycleState, float],
        processed_by_approach: Mapping[Approach, int],
        network_context: Mapping[str, object] | None = None,
    ) -> TrafficBrainView:
        del pedestrians, phase_crossings, network_context

        queue_counts: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        wait_totals: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        queue_actors: Dict[Approach, int] = {approach: 0 for approach in APPROACH_ORDER}
        emergency_counts: Dict[Approach, int] = {approach: 0 for approach in APPROACH_ORDER}
        direction_metrics: Dict[str, DirectionMetricView] = {}
        phase_scores: Dict[str, PhaseScoreView] = {}
        congestion_alerts: list[CongestionAlertView] = []

        for vehicle in vehicles:
            if vehicle.queued:
                queue_counts[vehicle.approach] += 1.0
                wait_totals[vehicle.approach] += vehicle.wait_time
                queue_actors[vehicle.approach] += 1
            if vehicle.has_siren or vehicle.kind in EMERGENCY_KINDS:
                emergency_counts[vehicle.approach] += 1

        emergency = self._closest_emergency(vehicles, lane_phase_map, current_phase)
        top_phase = current_phase
        top_score = float("-inf")

        for approach in APPROACH_ORDER:
            current_queue = queue_counts[approach]
            previous_queue = self.previous_direction_queues.get(approach, current_queue)
            queue_delta = 0.0 if dt <= 0.0 else current_queue - previous_queue
            avg_wait = wait_totals[approach] / queue_actors[approach] if queue_actors[approach] else 0.0
            instant_flow = float(processed_by_approach.get(approach, 0)) / max(dt, 1e-6) if dt > 0.0 else 0.0
            flow_rate = (
                instant_flow
                if self.smoothed_flow_rates[approach] == 0.0 and instant_flow == 0.0
                else _lerp(self.smoothed_flow_rates[approach], instant_flow, FLOW_SMOOTHING)
            )
            trend = _clamp(queue_delta * TREND_SCORE_WEIGHT, -1.5, 3.0)
            queue_component = current_queue * QUEUE_SCORE_WEIGHT
            wait_component = avg_wait * WAIT_SCORE_WEIGHT
            flow_component = flow_rate * FLOW_SCORE_WEIGHT
            fairness_boost = min(float(unserved_demand_time.get(approach, 0.0)) * FAIRNESS_SCORE_WEIGHT, 2.5)
            emergency_boost = EMERGENCY_BASE_BOOST if emergency.detected and emergency.preferred_phase == approach else 0.0
            score = queue_component + wait_component + trend + flow_component + fairness_boost + emergency_boost
            demand_active = bool(current_queue > 0.0 or emergency_boost > 0.0 or any(vehicle.approach == approach for vehicle in vehicles))

            alert_level = "normal"
            if current_queue >= CONGESTION_QUEUE_HIGH or avg_wait >= CONGESTION_WAIT_HIGH:
                alert_level = "high"
            elif current_queue >= CONGESTION_QUEUE_MEDIUM or queue_delta >= 1.0:
                alert_level = "medium"
            if alert_level != "normal":
                congestion_alerts.append(
                    CongestionAlertView(
                        approach=approach,
                        level=alert_level,
                        message=f"{approach.title()} queue is building up under the fixed-direction cycle.",
                        queue_length=round(current_queue, 3),
                        queue_delta=round(queue_delta, 3),
                    )
                )

            direction_metrics[approach] = DirectionMetricView(
                approach=approach,
                queue_length=round(current_queue, 3),
                avg_wait_time=round(avg_wait, 3),
                flow_rate=round(flow_rate, 3),
                queue_delta=round(queue_delta, 3),
                congestion_trend=round(trend, 3),
                emergency_vehicles=emergency_counts[approach],
                alert_level=alert_level,
            )
            phase_scores[approach] = PhaseScoreView(
                phase=approach,
                score=round(score, 3),
                queue_component=round(queue_component, 3),
                wait_time_component=round(wait_component, 3),
                congestion_component=round(trend, 3),
                flow_component=round(flow_component, 3),
                fairness_boost=round(fairness_boost, 3),
                emergency_boost=round(emergency_boost, 3),
                queue_length=round(current_queue, 3),
                avg_wait_time=round(avg_wait, 3),
                flow_rate=round(flow_rate, 3),
                pedestrian_demand=0.0,
                demand_active=demand_active,
                recommended_hold=approach == current_phase,
                decision_reason=self._decision_reason(approach, current_phase, emergency, current_queue, avg_wait),
            )

            self.previous_direction_queues[approach] = current_queue
            self.smoothed_flow_rates[approach] = flow_rate

            if demand_active and score > top_score + 1e-6:
                top_phase = approach
                top_score = score

        if top_score == float("-inf"):
            top_phase = current_phase

        return TrafficBrainView(
            active_phase_score=round(float(phase_scores[current_phase].score), 3),
            top_phase=top_phase,
            strategy=self._strategy_text(current_phase, controller_phase),
            direction_metrics=direction_metrics,
            phase_scores=phase_scores,
            congestion_alerts=congestion_alerts,
            emergency=emergency,
        )

    def _closest_emergency(
        self,
        vehicles: Sequence[VehicleTelemetryInput],
        lane_phase_map: Mapping[str, SignalCycleState],
        current_phase: SignalCycleState,
    ) -> EmergencyPriorityView:
        best_vehicle: VehicleTelemetryInput | None = None
        best_eta = float("inf")
        best_phase: SignalCycleState | None = None
        for vehicle in vehicles:
            if not (vehicle.has_siren or vehicle.kind in EMERGENCY_KINDS):
                continue
            preferred_phase = lane_phase_map.get(vehicle.lane_id, vehicle.approach)
            eta = max(vehicle.distance_to_stop, 0.0) / max(vehicle.speed, vehicle.cruise_speed * 0.6, 1.0)
            if eta < best_eta:
                best_vehicle = vehicle
                best_eta = eta
                best_phase = preferred_phase

        if best_vehicle is None or best_phase is None:
            return EmergencyPriorityView()

        state = "serving" if best_phase == current_phase else "tracking"
        return EmergencyPriorityView(
            detected=True,
            preferred_phase=best_phase,
            approach=best_vehicle.approach,
            vehicle_id=best_vehicle.id,
            eta_seconds=round(best_eta, 3),
            state=state,
        )

    def _decision_reason(
        self,
        phase: SignalCycleState,
        current_phase: SignalCycleState,
        emergency: EmergencyPriorityView,
        queue_length: float,
        avg_wait_time: float,
    ) -> str:
        if emergency.detected and emergency.preferred_phase == phase:
            return f"Emergency vehicle is approaching from {phase.lower()}."
        if phase == current_phase:
            return "This is the only allowed green direction right now."
        if queue_length > 0.0 and avg_wait_time > 0.0:
            return "Queued vehicles are accumulating while this direction waits its turn."
        if queue_length > 0.0:
            return "Vehicles are queued on this approach."
        return "Low demand."

    def _strategy_text(self, current_phase: SignalCycleState, controller_phase: ControllerPhase) -> str:
        if controller_phase != "PHASE_GREEN":
            return "The simplified controller only exposes a single active green direction."
        return f"Fixed one-direction cycle is currently serving {current_phase.lower()} traffic."
