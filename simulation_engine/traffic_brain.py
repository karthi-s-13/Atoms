"""Predictive but stable traffic intelligence for the intersection controller."""

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

APPROACHES: tuple[Approach, ...] = ("NORTH", "SOUTH", "EAST", "WEST")
EMERGENCY_KINDS: tuple[VehicleKind, ...] = ("ambulance", "firetruck", "police")

QUEUE_SCORE_WEIGHT = 1.25
WAIT_SCORE_WEIGHT = 0.45
TREND_SCORE_WEIGHT = 0.9
FLOW_SCORE_WEIGHT = 0.65
FAIRNESS_SCORE_WEIGHT = 0.12
PEDESTRIAN_QUEUE_SCORE = 1.1
PEDESTRIAN_WAIT_SCORE = 0.16
ACTIVE_STREAM_BONUS = 1.15
EMERGENCY_BASE_BOOST = 5.5
EMERGENCY_ETA_WINDOW = 12.0
FLOW_SMOOTH_EXTENSION_THRESHOLD = 0.55
MEDIUM_CONGESTION_QUEUE = 3.0
HIGH_CONGESTION_QUEUE = 5.0
CONGESTION_WAIT_ALERT = 4.0
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
    """Compute stable traffic intelligence without changing the signal state machine."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.previous_direction_queues: Dict[Approach, float] = {approach: 0.0 for approach in APPROACHES}
        self.previous_phase_queues: Dict[SignalCycleState, float] = {}
        self.smoothed_flow_rates: Dict[Approach, float] = {approach: 0.0 for approach in APPROACHES}

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
    ) -> TrafficBrainView:
        direction_queue_counts: Dict[Approach, float] = {approach: 0.0 for approach in APPROACHES}
        direction_wait_totals: Dict[Approach, float] = {approach: 0.0 for approach in APPROACHES}
        direction_queue_actors: Dict[Approach, int] = {approach: 0 for approach in APPROACHES}
        direction_emergencies: Dict[Approach, int] = {approach: 0 for approach in APPROACHES}

        for vehicle in vehicles:
            if vehicle.queued:
                direction_queue_counts[vehicle.approach] += 1.0
                direction_wait_totals[vehicle.approach] += vehicle.wait_time
                direction_queue_actors[vehicle.approach] += 1
            if vehicle.has_siren or vehicle.kind in EMERGENCY_KINDS:
                direction_emergencies[vehicle.approach] += 1

        direction_metrics: Dict[str, DirectionMetricView] = {}
        congestion_alerts: list[CongestionAlertView] = []
        for approach in APPROACHES:
            previous_queue = self.previous_direction_queues.get(approach, 0.0)
            current_queue = direction_queue_counts[approach]
            queue_delta = 0.0 if dt <= 0.0 else current_queue - previous_queue
            avg_wait_time = (
                direction_wait_totals[approach] / direction_queue_actors[approach]
                if direction_queue_actors[approach]
                else 0.0
            )
            instant_flow = (
                float(processed_by_approach.get(approach, 0)) / max(dt, 1e-6)
                if dt > 0.0
                else 0.0
            )
            flow_rate = (
                instant_flow
                if previous_queue == 0.0 and self.smoothed_flow_rates.get(approach, 0.0) == 0.0
                else _lerp(self.smoothed_flow_rates.get(approach, 0.0), instant_flow, FLOW_SMOOTHING)
            )
            congestion_trend = _clamp(queue_delta * TREND_SCORE_WEIGHT, -2.0, 3.5)
            alert_level = "normal"
            if current_queue >= HIGH_CONGESTION_QUEUE or (queue_delta >= 2.0 and avg_wait_time >= CONGESTION_WAIT_ALERT):
                alert_level = "high"
            elif current_queue >= MEDIUM_CONGESTION_QUEUE or queue_delta >= 1.0 or avg_wait_time >= CONGESTION_WAIT_ALERT:
                alert_level = "medium"
            if alert_level != "normal":
                growth_text = "and rising" if queue_delta > 0.0 else "with persistent delay"
                congestion_alerts.append(
                    CongestionAlertView(
                        approach=approach,
                        level=alert_level,
                        message=f"{approach.title()} approach is congested {growth_text}.",
                        queue_length=round(current_queue, 3),
                        queue_delta=round(queue_delta, 3),
                    )
                )

            direction_metrics[approach] = DirectionMetricView(
                approach=approach,
                queue_length=round(current_queue, 3),
                avg_wait_time=round(avg_wait_time, 3),
                flow_rate=round(flow_rate, 3),
                queue_delta=round(queue_delta, 3),
                congestion_trend=round(congestion_trend, 3),
                emergency_vehicles=direction_emergencies[approach],
                alert_level=alert_level,
            )
            self.previous_direction_queues[approach] = current_queue
            self.smoothed_flow_rates[approach] = flow_rate

        waiting_pedestrians: Dict[RoadDirection, list[PedestrianTelemetryInput]] = {"NS": [], "EW": []}
        for pedestrian in pedestrians:
            if pedestrian.state == "WAITING":
                waiting_pedestrians[pedestrian.crossing].append(pedestrian)

        emergency = self._closest_emergency(vehicles, lane_phase_map, current_phase, controller_phase)
        phase_scores: Dict[str, PhaseScoreView] = {}
        top_phase = current_phase
        top_score = float("-inf")

        for phase in phase_order:
            matching_lane_ids = set(phase_lane_ids.get(phase, ()))
            matching_vehicles = [vehicle for vehicle in vehicles if vehicle.lane_id in matching_lane_ids]
            queued_vehicles = [vehicle for vehicle in matching_vehicles if vehicle.queued]
            queue_length = float(len(queued_vehicles))
            avg_wait_time = (
                sum(vehicle.wait_time for vehicle in queued_vehicles) / len(queued_vehicles)
                if queued_vehicles
                else 0.0
            )
            previous_phase_queue = self.previous_phase_queues.get(phase, queue_length)
            phase_queue_delta = 0.0 if dt <= 0.0 else queue_length - previous_phase_queue
            phase_approaches = {vehicle.approach for vehicle in matching_vehicles}
            flow_rate = float(sum(direction_metrics[approach].flow_rate for approach in phase_approaches))
            pedestrian_crossing = phase_crossings.get(phase)
            waiting_crossers = waiting_pedestrians.get(pedestrian_crossing, []) if pedestrian_crossing else []
            pedestrian_demand = float(len(waiting_crossers))
            pedestrian_wait_average = (
                sum(pedestrian.wait_time for pedestrian in waiting_crossers) / len(waiting_crossers)
                if waiting_crossers
                else 0.0
            )

            queue_component = (queue_length * QUEUE_SCORE_WEIGHT) + (pedestrian_demand * PEDESTRIAN_QUEUE_SCORE)
            wait_component = (avg_wait_time * WAIT_SCORE_WEIGHT) + (pedestrian_wait_average * PEDESTRIAN_WAIT_SCORE)
            congestion_component = _clamp(phase_queue_delta * TREND_SCORE_WEIGHT, -1.5, 3.5)
            flow_component = flow_rate * FLOW_SCORE_WEIGHT
            fairness_boost = min(float(unserved_demand_time.get(phase, 0.0)) * FAIRNESS_SCORE_WEIGHT, 4.0)
            recommended_hold = (
                phase == current_phase
                and controller_phase == "PHASE_GREEN"
                and flow_rate >= FLOW_SMOOTH_EXTENSION_THRESHOLD
                and (queue_length > 0.0 or len(matching_vehicles) > 0)
            )
            if recommended_hold:
                flow_component += ACTIVE_STREAM_BONUS

            emergency_boost = 0.0
            if emergency.detected and emergency.preferred_phase == phase:
                eta_factor = max(0.0, EMERGENCY_ETA_WINDOW - emergency.eta_seconds)
                emergency_boost = EMERGENCY_BASE_BOOST + (eta_factor * 0.45)
                if phase == current_phase and controller_phase == "PHASE_GREEN":
                    flow_component += 0.75

            demand_active = bool(queue_length > 0.0 or len(matching_vehicles) > 0 or pedestrian_demand > 0.0 or emergency_boost > 0.0)
            score = queue_component + wait_component + congestion_component + flow_component + fairness_boost + emergency_boost
            decision_reason = self._decision_reason(
                phase=phase,
                current_phase=current_phase,
                recommended_hold=recommended_hold,
                emergency=emergency,
                queue_length=queue_length,
                avg_wait_time=avg_wait_time,
                flow_rate=flow_rate,
            )

            phase_scores[phase] = PhaseScoreView(
                phase=phase,
                score=round(score, 3),
                queue_component=round(queue_component, 3),
                wait_time_component=round(wait_component, 3),
                congestion_component=round(congestion_component, 3),
                flow_component=round(flow_component, 3),
                fairness_boost=round(fairness_boost, 3),
                emergency_boost=round(emergency_boost, 3),
                queue_length=round(queue_length, 3),
                avg_wait_time=round(avg_wait_time, 3),
                flow_rate=round(flow_rate, 3),
                pedestrian_demand=round(pedestrian_demand, 3),
                demand_active=demand_active,
                recommended_hold=recommended_hold,
                decision_reason=decision_reason,
            )
            self.previous_phase_queues[phase] = queue_length

            if demand_active:
                if score > top_score + 1e-6:
                    top_phase = phase
                    top_score = score
                elif abs(score - top_score) < 1e-6:
                    current_index = phase_order.index(top_phase)
                    candidate_index = phase_order.index(phase)
                    if phase == current_phase or candidate_index < current_index:
                        top_phase = phase
                        top_score = score

        if top_score == float("-inf"):
            top_phase = current_phase
            top_score = float(phase_scores[current_phase].score)

        strategy = self._strategy_text(
            current_phase=current_phase,
            top_phase=top_phase,
            controller_phase=controller_phase,
            emergency=emergency,
            phase_scores=phase_scores,
        )
        return TrafficBrainView(
            active_phase_score=round(float(phase_scores[current_phase].score), 3),
            top_phase=top_phase,
            strategy=strategy,
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
        controller_phase: ControllerPhase,
    ) -> EmergencyPriorityView:
        best_vehicle: VehicleTelemetryInput | None = None
        best_eta = float("inf")
        best_phase: SignalCycleState | None = None
        for vehicle in vehicles:
            if not (vehicle.has_siren or vehicle.kind in EMERGENCY_KINDS):
                continue
            preferred_phase = lane_phase_map.get(vehicle.lane_id)
            if preferred_phase is None:
                continue
            eta = max(vehicle.distance_to_stop, 0.0) / max(vehicle.speed, vehicle.cruise_speed * 0.7, 1.0)
            if eta < best_eta:
                best_eta = eta
                best_vehicle = vehicle
                best_phase = preferred_phase

        if best_vehicle is None or best_phase is None:
            return EmergencyPriorityView()

        if best_phase == current_phase and controller_phase == "PHASE_GREEN":
            state = "serving"
        elif best_eta <= 7.0:
            state = "preparing"
        else:
            state = "tracking"

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
        *,
        phase: SignalCycleState,
        current_phase: SignalCycleState,
        recommended_hold: bool,
        emergency: EmergencyPriorityView,
        queue_length: float,
        avg_wait_time: float,
        flow_rate: float,
    ) -> str:
        if emergency.detected and emergency.preferred_phase == phase:
            return f"Emergency approach tracked with ETA {emergency.eta_seconds:.1f}s."
        if recommended_hold:
            return "Active stream is flowing smoothly, so the brain favors a stable extension."
        if phase == current_phase and flow_rate > 0.0:
            return "Current green is still serving vehicles efficiently."
        if queue_length > 0.0 and avg_wait_time > 0.0:
            return "Queue and accumulated wait time are increasing pressure on this phase."
        if queue_length > 0.0:
            return "Queued vehicles are building up on this phase."
        return "Low immediate demand."

    def _strategy_text(
        self,
        *,
        current_phase: SignalCycleState,
        top_phase: SignalCycleState,
        controller_phase: ControllerPhase,
        emergency: EmergencyPriorityView,
        phase_scores: Mapping[str, PhaseScoreView],
    ) -> str:
        if emergency.detected and emergency.preferred_phase is not None:
            target = emergency.preferred_phase.replace("_", " ")
            return f"Emergency {emergency.state} for {target}; pre-adjust timing without skipping safe transitions."
        if top_phase == current_phase and controller_phase == "PHASE_GREEN" and phase_scores[current_phase].recommended_hold:
            return "Holding the current green because vehicles are clearing smoothly."
        target = top_phase.replace("_", " ")
        return f"Highest score currently favors {target} from queue, wait, trend, flow, and fairness pressure."
