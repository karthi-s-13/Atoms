"""Small deterministic telemetry layer for the single-green controller."""

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
    SignalCycleState,
    TrafficBrainView,
    VehicleKind,
)

APPROACH_ORDER: tuple[Approach, ...] = ("NORTH", "EAST", "SOUTH", "WEST")
EMERGENCY_KINDS: tuple[VehicleKind, ...] = ("ambulance", "firetruck", "police")

QUEUE_SCORE_WEIGHT = 1.0
WAIT_SCORE_WEIGHT = 1.5
ARRIVAL_SCORE_WEIGHT = 1.2
FAIRNESS_BOOST_WEIGHT = 1.5
QUEUE_SCORE_WEIGHT = 1.0
PREDICTIVE_LOAD_WEIGHT = 0.85
PREDICTION_HORIZON = 10.0
EMERGENCY_BOOST_WEIGHT = 3.5
EMERGENCY_PRIORITY_WEIGHTS: Dict[VehicleKind, float] = {
    "ambulance": 3.4,
    "firetruck": 3.0,
    "police": 2.5,
}

EMERGENCY_BASE_BOOST = 1.8
EMERGENCY_COUNT_SCORE_WEIGHT = 1.2
EMERGENCY_PRIORITY_SCORE_WEIGHT = 1.45
EMERGENCY_PROXIMITY_SCORE_WEIGHT = 3.4
EMERGENCY_PROXIMITY_HORIZON = 12.0
EMERGENCY_WAIT_SCORE_WEIGHT = 0.72
EMERGENCY_WAIT_SCORE_CAP = 8.0
EMERGENCY_BLOCKING_SCORE_WEIGHT = 1.15
EMERGENCY_BLOCKING_SCORE_CAP = 5.0

# Starvation Prevention (Production Specs)
STARVATION_THRESHOLD = 18.0
STARVATION_BOOST_THRESHOLD = 8.0
STARVATION_BOOST_PER_SECOND = 0.6
STARVATION_BOOST_CAP = 12.0

# Adaptive Green Time
MIN_GREEN = 5.0
MAX_GREEN = 25.0
BASE_GREEN = 5.0
QUEUE_GROWTH_FACTOR = 1.7
DURATION_SMOOTHING = 0.6
CONGESTION_QUEUE_MEDIUM = 3.0
CONGESTION_QUEUE_HIGH = 5.0
CONGESTION_WAIT_HIGH = 4.0
QUEUE_SMOOTHING = 0.34
WAIT_SMOOTHING = 0.28
ARRIVAL_SMOOTHING = 0.38
SERVICE_SMOOTHING = 0.35
EMERGENCY_KIND_PRIORITY: Dict[VehicleKind, float] = {
    "ambulance": 3.4,
    "firetruck": 2.9,
    "police": 2.4,
    "car": 0.0,
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _lerp(a: float, b: float, t: float) -> float:
    return a + ((b - a) * t)


def _phase_anchor(phase: SignalCycleState) -> SignalCycleState:
    return phase


def _phase_approaches(phase: SignalCycleState) -> tuple[Approach, ...]:
    return (phase,)


def _phase_serves_approach(phase: SignalCycleState, approach: Approach) -> bool:
    return approach in _phase_approaches(phase)


def _phase_label(phase: SignalCycleState) -> str:
    return phase.lower()


def _emergency_wait_pressure(wait_time: float) -> float:
    return min(max(0.0, wait_time) * EMERGENCY_WAIT_SCORE_WEIGHT, EMERGENCY_WAIT_SCORE_CAP)


def _emergency_blocking_pressure(queued_ahead: int) -> float:
    return min(max(0, queued_ahead) * EMERGENCY_BLOCKING_SCORE_WEIGHT, EMERGENCY_BLOCKING_SCORE_CAP)


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
    priority: int


class TrafficBrain:
    """Compute simple queue and flow telemetry without controlling the signals."""

    def __init__(self) -> None:
        self.previous_direction_queues: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        self.smoothed_queue_lengths: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        self.smoothed_wait_times: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        self.smoothed_arrival_rates: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        self.smoothed_flow_rates: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        self.emergency_suppression_time: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        self.last_emergency_active: bool = False

    def reset(self) -> None:
        self.__init__()

    def evaluate(
        self,
        *,
        dt: float,
        ai_mode: str,
        current_phase: SignalCycleState,
        controller_phase: ControllerPhase,
        vehicles: Sequence[VehicleTelemetryInput],
        lane_phase_map: Mapping[str, SignalCycleState],
        phase_lane_ids: Mapping[SignalCycleState, tuple[str, ...]],
        unserved_demand_time: Mapping[SignalCycleState, float],
        processed_by_approach: Mapping[Approach, int],
        arrivals_by_approach: Mapping[Approach, int],
        network_context: Mapping[str, object] | None = None,
    ) -> TrafficBrainView:
        del network_context

        queue_counts: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        wait_totals: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        queue_actors: Dict[Approach, int] = {approach: 0 for approach in APPROACH_ORDER}
        max_wait_times: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        emergency_counts: Dict[Approach, int] = {approach: 0 for approach in APPROACH_ORDER}
        emergency_priority_totals: Dict[Approach, float] = {approach: 0.0 for approach in APPROACH_ORDER}
        nearest_emergency_eta: Dict[Approach, float] = {approach: float("inf") for approach in APPROACH_ORDER}
        lane_queue_counts: Dict[str, float] = {}
        lane_vehicle_counts: Dict[str, float] = {}
        direction_metrics: Dict[str, DirectionMetricView] = {}
        phase_scores: Dict[str, PhaseScoreView] = {}
        congestion_alerts: list[CongestionAlertView] = []

        for vehicle in vehicles:
            lane_vehicle_counts[vehicle.lane_id] = lane_vehicle_counts.get(vehicle.lane_id, 0.0) + 1.0
            if vehicle.queued:
                queue_counts[vehicle.approach] += 1.0
                wait_totals[vehicle.approach] += vehicle.wait_time
                queue_actors[vehicle.approach] += 1
                max_wait_times[vehicle.approach] = max(max_wait_times[vehicle.approach], vehicle.wait_time)
                lane_queue_counts[vehicle.lane_id] = lane_queue_counts.get(vehicle.lane_id, 0.0) + 1.0
            if vehicle.has_siren or vehicle.kind in EMERGENCY_KINDS:
                emergency_counts[vehicle.approach] += 1
                eta = max(vehicle.distance_to_stop, 0.0) / max(vehicle.speed, vehicle.cruise_speed * 0.6, 1.0)
                nearest_emergency_eta[vehicle.approach] = min(nearest_emergency_eta[vehicle.approach], eta)

        for vehicle in vehicles:
            if not (vehicle.has_siren or vehicle.kind in EMERGENCY_KINDS):
                continue
            queued_ahead = sum(
                1
                for other in vehicles
                if (
                    other.approach == vehicle.approach
                    and other.queued
                    and other.distance_to_stop < vehicle.distance_to_stop - 0.2
                )
            )
            emergency_priority_totals[vehicle.approach] += (
                EMERGENCY_KIND_PRIORITY.get(vehicle.kind, 0.0)
                + max(0.0, float(vehicle.priority) * 0.35)
                + _emergency_wait_pressure(vehicle.wait_time)
                + _emergency_blocking_pressure(queued_ahead)
            )

        emergency = self._closest_emergency(vehicles, lane_phase_map, current_phase)
        phase_priority: Dict[SignalCycleState, float] = {direction: 0.0 for direction in APPROACH_ORDER}

        # Update suppression times for other lanes if an emergency is active somewhere else
        any_emergency = any(emergency_counts.values())
        if any_emergency:
            for apr in APPROACH_ORDER:
                if emergency_counts[apr] == 0:
                    self.emergency_suppression_time[apr] += dt

        for approach in APPROACH_ORDER:
            current_queue = queue_counts[approach]
            previous_queue = self.previous_direction_queues.get(approach, current_queue)
            queue_delta = 0.0 if dt <= 0.0 else current_queue - previous_queue
            avg_wait = wait_totals[approach] / queue_actors[approach] if queue_actors[approach] else 0.0
            smoothed_queue = (
                current_queue
                if self.smoothed_queue_lengths[approach] == 0.0 and current_queue == 0.0
                else _lerp(self.smoothed_queue_lengths[approach], current_queue, QUEUE_SMOOTHING)
            )
            smoothed_wait = (
                avg_wait
                if self.smoothed_wait_times[approach] == 0.0 and avg_wait == 0.0
                else _lerp(self.smoothed_wait_times[approach], avg_wait, WAIT_SMOOTHING)
            )
            instant_arrival = float(arrivals_by_approach.get(approach, 0)) / max(dt, 1e-6) if dt > 0.0 else 0.0
            arrival_rate = (
                instant_arrival
                if self.smoothed_arrival_rates[approach] == 0.0 and instant_arrival == 0.0
                else _lerp(self.smoothed_arrival_rates[approach], instant_arrival, ARRIVAL_SMOOTHING)
            )
            instant_flow = float(processed_by_approach.get(approach, 0)) / max(dt, 1e-6) if dt > 0.0 else 0.0
            flow_rate = (
                instant_flow
                if self.smoothed_flow_rates[approach] == 0.0 and instant_flow == 0.0
                else _lerp(self.smoothed_flow_rates[approach], instant_flow, SERVICE_SMOOTHING)
            )
            lane_ids = phase_lane_ids.get(approach, ())
            starvation_time = max(0.0, float(unserved_demand_time.get(approach, 0.0)) - STARVATION_BOOST_THRESHOLD)
            demand_active = bool(
                current_queue > 0.0
                or arrival_rate > 0.05
                or emergency_counts[approach] > 0
                or any(vehicle.approach == approach for vehicle in vehicles)
            )
            starvation_boost = min(starvation_time * STARVATION_BOOST_PER_SECOND, STARVATION_BOOST_CAP) if demand_active else 0.0
            
            # Implementation of FairnessBoost
            fairness_boost = starvation_boost * FAIRNESS_BOOST_WEIGHT
            
            # Enhancement: Post-Emergency Fairness Compensation
            if emergency_counts[approach] > 0:
                self.emergency_suppression_time = {k: 0.0 for k in APPROACH_ORDER}
                self.last_emergency_active = True
            elif self.last_emergency_active and any(emergency_counts.values()) == 0:
                # Emergency just passed
                self.last_emergency_active = False

            # Fairness Boost (Enhanced with Starvation + Emergency Compensation)
            emergency_compensation = self.emergency_suppression_time[approach] * 0.45
            fairness_boost = (starvation_boost + emergency_compensation) * FAIRNESS_BOOST_WEIGHT
            
            # Implementation of Enhanced EmergencyBoost
            # EmergencyBoost = weight * (1 / max(ETA, 0.1)) * proximity_factor
            emergency_boost = 0.0
            if emergency_counts[approach] > 0 and nearest_emergency_eta[approach] < float("inf"):
                vehicle_kind = "ambulance" # Default as backup
                for v in vehicles:
                    if v.approach == approach and v.kind in EMERGENCY_PRIORITY_WEIGHTS:
                        vehicle_kind = v.kind
                        break
                
                weight = EMERGENCY_PRIORITY_WEIGHTS.get(vehicle_kind, 2.5)
                eta = max(nearest_emergency_eta[approach], 0.1)
                proximity_factor = max(1.0, 1.25 * (EMERGENCY_PROXIMITY_HORIZON / (eta + 1.0)))
                
                emergency_boost = weight * (1.0 / eta) * proximity_factor
            
            # Decision Scoring Loop
            # Score = (Queue * 1.0) + (WaitTime * 1.5) + (ArrivalRate * 1.2) + (PredictiveLoad * 0.85) + (FairnessBoost * 1.5) + (EmergencyBoost * 3.5)
            # PredictiveLoad = queue + (arrival_rate * 10)
            
            predictive_load = smoothed_queue + (arrival_rate * PREDICTION_HORIZON)
            
            score = (
                (smoothed_queue * QUEUE_SCORE_WEIGHT)
                + (smoothed_wait * WAIT_SCORE_WEIGHT)
                + (arrival_rate * ARRIVAL_SCORE_WEIGHT)
                + (predictive_load * PREDICTIVE_LOAD_WEIGHT)
                + fairness_boost
                + (emergency_boost * EMERGENCY_BOOST_WEIGHT)
            )

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
                        message=(
                            f"{approach.title()} queue is building up under the AI-controlled cycle."
                            if ai_mode == "adaptive"
                            else f"{approach.title()} queue is building up under the fixed single-green cycle."
                        ),
                        queue_length=float(current_queue),
                        queue_delta=float(queue_delta),
                    )
                )

            direction_metrics[approach] = DirectionMetricView(
                approach=approach,
                queue_length=float(current_queue),
                avg_wait_time=float(avg_wait),
                flow_rate=float(flow_rate),
                queue_delta=float(queue_delta),
                congestion_trend=0.0,
                emergency_vehicles=emergency_counts[approach],
                alert_level=alert_level,
                arrival_rate=float(arrival_rate),
            )
            phase_scores[approach] = PhaseScoreView(
                phase=approach,
                score=float(score),
                queue_component=float(smoothed_queue * QUEUE_SCORE_WEIGHT),
                wait_time_component=float(smoothed_wait * WAIT_SCORE_WEIGHT),
                congestion_component=float(predictive_load * PREDICTIVE_LOAD_WEIGHT),
                flow_component=float(arrival_rate * ARRIVAL_SCORE_WEIGHT),
                lane_weight_component=0.0,
                fairness_boost=float(fairness_boost),
                emergency_boost=float(emergency_boost * EMERGENCY_BOOST_WEIGHT),
                queue_length=float(smoothed_queue),
                avg_wait_time=float(smoothed_wait),
                flow_rate=float(flow_rate),
                demand_active=demand_active,
                recommended_hold=_phase_serves_approach(current_phase, approach),
                decision_reason=self._decision_reason(
                    approach,
                    current_phase,
                    emergency,
                    current_queue,
                    avg_wait,
                    arrival_rate,
                    fairness_boost,
                ),
                arrival_rate=round(float(arrival_rate), 3),
                queue=round(float(self.smoothed_queue_lengths[approach]), 3),
                wait_time=round(float(self.smoothed_wait_times[approach]), 3),
                arrival_rate_smoothed=round(float(self.smoothed_arrival_rates[approach]), 3),
                flow_rate_smoothed=round(float(self.smoothed_flow_rates[approach]), 3),
                congestion_component_raw=round(float(predictive_load * PREDICTIVE_LOAD_WEIGHT), 3), # Assuming congestion_trend was predictive_load * PREDICTIVE_LOAD_WEIGHT
                fairness_boost_raw=round(float(fairness_boost), 3),
                emergency_boost_raw=round(float(emergency_boost), 3),
                score_raw=round(float(score), 3),
                demand_active_raw=bool(demand_active),
            )

            self.previous_direction_queues[approach] = current_queue
            self.smoothed_queue_lengths[approach] = smoothed_queue
            self.smoothed_wait_times[approach] = smoothed_wait
            self.smoothed_arrival_rates[approach] = arrival_rate
            self.smoothed_flow_rates[approach] = flow_rate

            phase_priority[approach] += score

        top_phase = max(
            phase_priority,
            key=lambda phase: (phase_priority[phase], 1 if phase == current_phase else 0),
        )
        active_phase_score = phase_priority[current_phase]
        return TrafficBrainView(
            active_phase_score=round(float(active_phase_score), 3),
            top_phase=top_phase,
            strategy=self._strategy_text(current_phase, controller_phase, ai_mode),
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
        phase_counts: Dict[SignalCycleState, int] = {direction: 0 for direction in APPROACH_ORDER}
        phase_priority_scores: Dict[SignalCycleState, float] = {direction: 0.0 for direction in APPROACH_ORDER}
        phase_closest_eta: Dict[SignalCycleState, float] = {direction: float("inf") for direction in APPROACH_ORDER}
        for vehicle in vehicles:
            if not (vehicle.has_siren or vehicle.kind in EMERGENCY_KINDS):
                continue
            preferred_phase = lane_phase_map.get(vehicle.lane_id, vehicle.approach)
            eta = max(vehicle.distance_to_stop, 0.0) / max(vehicle.speed, vehicle.cruise_speed * 0.6, 1.0)
            queued_ahead = sum(
                1
                for other in vehicles
                if (
                    other.approach == vehicle.approach
                    and other.queued
                    and other.distance_to_stop < vehicle.distance_to_stop - 0.2
                )
            )
            severity = (
                EMERGENCY_KIND_PRIORITY.get(vehicle.kind, 0.0)
                + max(0.0, float(vehicle.priority) * 0.35)
                + _emergency_wait_pressure(vehicle.wait_time)
                + _emergency_blocking_pressure(queued_ahead)
            )
            phase_counts[preferred_phase] += 1
            phase_priority_scores[preferred_phase] += severity
            phase_closest_eta[preferred_phase] = min(phase_closest_eta[preferred_phase], eta)
            if eta < best_eta:
                best_vehicle = vehicle
                best_eta = eta

        candidate_phases = [phase for phase, count in phase_counts.items() if count > 0]
        if candidate_phases:
            best_phase = max(
                candidate_phases,
                key=lambda phase: (
                    phase_priority_scores[phase] + (phase_counts[phase] * 1.35) + max(0.0, EMERGENCY_PROXIMITY_HORIZON - phase_closest_eta[phase]),
                    1 if phase == current_phase else 0,
                ),
            )
            best_eta = phase_closest_eta[best_phase]
            emergency_vehicles = [
                vehicle
                for vehicle in vehicles
                if (vehicle.has_siren or vehicle.kind in EMERGENCY_KINDS)
                and lane_phase_map.get(vehicle.lane_id, vehicle.approach) == best_phase
            ]
            if emergency_vehicles:
                best_vehicle = min(
                    emergency_vehicles,
                    key=lambda vehicle: max(vehicle.distance_to_stop, 0.0) / max(vehicle.speed, vehicle.cruise_speed * 0.6, 1.0),
                )

        if best_vehicle is None or best_phase is None:
            return EmergencyPriorityView()

        assert best_vehicle is not None
        assert best_phase is not None
        state = "serving" if current_phase == best_phase else "tracking"
        return EmergencyPriorityView(
            detected=True,
            preferred_phase=best_phase,
            approach=best_vehicle.approach,
            vehicle_id=best_vehicle.id,
            eta_seconds=float(best_eta),
            vehicle_count=int(phase_counts[best_phase]),
            priority_score=float(phase_priority_scores[best_phase]),
            state=state,
        )

    def _decision_reason(
        self,
        phase: SignalCycleState,
        current_phase: SignalCycleState,
        emergency: EmergencyPriorityView,
        queue_length: float,
        avg_wait_time: float,
        arrival_rate: float,
        fairness_boost: float,
    ) -> str:
        if emergency.detected and emergency.preferred_phase == phase:
            return (
                f"Emergency priority active on {phase.lower()}: {emergency.vehicle_count} vehicle(s), "
                f"severity {emergency.priority_score:.1f}, ETA {emergency.eta_seconds:.1f}s."
            )
        if fairness_boost > 0.0:
            return "Fairness protection is lifting this approach because vehicles have been waiting too long."
        if avg_wait_time > 6.0:
            return "Average wait time on this approach has exceeded the stability target."
        if queue_length >= 4.0:
            return "Queue length is high enough to justify additional green time."
        if arrival_rate >= 0.75:
            return "Arrival rate is high enough to justify keeping this approach responsive."
        if current_phase == phase:
            return "This approach is currently being served under the single-green controller."
        if queue_length > 0.0 and avg_wait_time > 0.0:
            return "Queued vehicles are building up while this approach waits for service."
        if queue_length > 0.0:
            return "Vehicles are queued on this approach."
        return "Low demand."

    def _strategy_text(self, current_phase: SignalCycleState, controller_phase: ControllerPhase, ai_mode: str) -> str:
        if controller_phase != "PHASE_GREEN":
            return "The simplified controller only exposes one active non-conflicting approach."
        if ai_mode == "adaptive":
            return f"AI signal is serving the {_phase_label(current_phase)} approach using wait fairness, lane weight, arrivals, and emergency severity."
        return f"Fixed single-green cycle is currently serving the {_phase_label(current_phase)} approach."
