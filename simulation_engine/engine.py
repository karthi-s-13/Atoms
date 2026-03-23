"""Protected multi-phase 4-way intersection simulation."""

from __future__ import annotations

import math
import random
import copy
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List

from simulation_engine.traffic_brain import (
    PedestrianTelemetryInput,
    TrafficBrain,
    VehicleTelemetryInput,
)
from shared.contracts import (
    Approach,
    ControllerPhase,
    CrosswalkView,
    EventView,
    LaneMovement,
    LaneView,
    MetricsView,
    PedestrianView,
    Point2D,
    RoadDirection,
    RouteType,
    SignalCycleState,
    SignalState,
    SimulationConfig,
    SnapshotView,
    VehicleKind,
    VehicleView,
)

FRAME_DT = 0.016

GREEN = "GREEN"
GREEN_LEFT = "GREEN_LEFT"
YELLOW = "YELLOW"
RED = "RED"

PHASE_GREEN: ControllerPhase = "PHASE_GREEN"
PHASE_YELLOW: ControllerPhase = "PHASE_YELLOW"
PHASE_ALL_RED: ControllerPhase = "PHASE_ALL_RED"

NS_STRAIGHT: SignalCycleState = "NS_STRAIGHT"
EW_STRAIGHT: SignalCycleState = "EW_STRAIGHT"
NS_LEFT: SignalCycleState = "NS_LEFT"
EW_LEFT: SignalCycleState = "EW_LEFT"

STRAIGHT_MIN_GREEN = 4.5
STRAIGHT_MAX_GREEN = 11.5
LEFT_MIN_GREEN = 3.0
LEFT_MAX_GREEN = 7.5
YELLOW_TIME = 2.0
ALL_RED_TIME = 1.0
ALL_RED_EXTENSION_STEP = 0.5
ALL_RED_EXTENSION_LIMIT = 2.0

QUEUE_WEIGHT = 1.0
WAIT_TIME_BOOST_FACTOR = 0.35
PEDESTRIAN_WEIGHT = 1.2
PEDESTRIAN_WAIT_BOOST_FACTOR = 0.3
SWITCH_SCORE_MARGIN = 0.75
STARVATION_LIMIT = 18.0

LEFT_TURN_PROBABILITY = 0.28
EMERGENCY_ROUTE_PREFERENCE = 0.85
EMERGENCY_SPEED_MULTIPLIER = 1.12

SIGNAL_DIRECTIONS: tuple[Approach, ...] = ("NORTH", "SOUTH", "EAST", "WEST")

ROAD_EXTENT = 72.0
LANE_WIDTH = 3.5
LANES_PER_DIRECTION = 2
INNER_LANE_OFFSET = LANE_WIDTH / 2.0
OUTER_LANE_OFFSET = INNER_LANE_OFFSET + LANE_WIDTH
SHOULDER = 0.75
ROAD_HALF_WIDTH = LANE_WIDTH * LANES_PER_DIRECTION
ROAD_SURFACE_HALF_WIDTH = ROAD_HALF_WIDTH + SHOULDER
INTERSECTION_SIZE = 14.0
INTERSECTION_HALF_SIZE = INTERSECTION_SIZE / 2.0
STOP_OFFSET = INTERSECTION_HALF_SIZE + 3.0
CROSSWALK_INNER_OFFSET = INTERSECTION_HALF_SIZE + 0.4
CROSSWALK_OUTER_OFFSET = STOP_OFFSET - 0.9
CROSSWALK_CENTER_OFFSET = (CROSSWALK_INNER_OFFSET + CROSSWALK_OUTER_OFFSET) / 2.0
CROSSWALK_DEPTH = CROSSWALK_OUTER_OFFSET - CROSSWALK_INNER_OFFSET
PATH_ENTRY_OFFSET = ROAD_EXTENT
PATH_EXIT_OFFSET = ROAD_EXTENT

VEHICLE_MIN_LENGTH = 4.2
VEHICLE_MAX_LENGTH = 4.8
VEHICLE_MIN_WIDTH = 1.85
VEHICLE_MAX_WIDTH = 2.1
STRAIGHT_SPEED_MIN = 9.0
STRAIGHT_SPEED_MAX = 11.0
LEFT_SPEED_MIN = 7.2
LEFT_SPEED_MAX = 8.4
ACCELERATION = 8.0
BRAKE_RATE = 16.0
FOLLOW_GAP = 2.2
FOLLOW_RESPONSE_DISTANCE = 16.0
STOP_LINE_BUFFER = 0.25
MIN_MOVEMENT_STEP = 1e-3
YELLOW_REACTION_BUFFER = 0.9
YELLOW_MIN_COMMIT_SPEED = 1.25
YELLOW_COMMIT_WINDOW = 0.85

PEDESTRIAN_SPEED = 2.0
PEDESTRIAN_SNAP_DISTANCE = 0.05

VEHICLE_COLOR_POOL = ("#3b82f6", "#ef4444", "#facc15", "#22c55e", "#f8fafc")
VEHICLE_APPROACHES: tuple[Approach, ...] = ("SOUTH", "WEST", "NORTH", "EAST")
PEDESTRIAN_SPAWN_PLAN: tuple[tuple[str, bool], ...] = (
    ("north_crosswalk", False),
    ("north_crosswalk", True),
    ("east_crosswalk", False),
    ("east_crosswalk", True),
    ("south_crosswalk", False),
    ("south_crosswalk", True),
    ("west_crosswalk", False),
    ("west_crosswalk", True),
)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _lerp(a: float, b: float, t: float) -> float:
    return a + ((b - a) * t)


def _distance(a: Point2D, b: Point2D) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def _normalize(dx: float, dy: float) -> Point2D:
    magnitude = math.hypot(dx, dy) or 1.0
    return Point2D(dx / magnitude, dy / magnitude)


def _move_toward(current: float, target: float, max_delta: float) -> float:
    if current < target:
        return min(current + max_delta, target)
    return max(current - max_delta, target)


def _direction_group(approach: Approach) -> RoadDirection:
    return "NS" if approach in {"NORTH", "SOUTH"} else "EW"


def _sample_quadratic_bezier(
    start: Point2D,
    control: Point2D,
    end: Point2D,
    *,
    steps: int = 24,
) -> List[Point2D]:
    samples: List[Point2D] = []
    for index in range(steps + 1):
        t = index / steps
        one_minus = 1.0 - t
        samples.append(
            Point2D(
                x=((one_minus**2) * start.x) + (2.0 * one_minus * t * control.x) + ((t**2) * end.x),
                y=((one_minus**2) * start.y) + (2.0 * one_minus * t * control.y) + ((t**2) * end.y),
            )
        )
    return samples


@dataclass(frozen=True)
class PolylinePath:
    points: tuple[Point2D, ...]
    cumulative_lengths: tuple[float, ...]
    length: float

    @classmethod
    def from_points(cls, points: Iterable[Point2D]) -> "PolylinePath":
        filtered: List[Point2D] = []
        for point in points:
            if not filtered or _distance(filtered[-1], point) > 1e-6:
                filtered.append(point)
        if len(filtered) < 2:
            raise ValueError("A path requires at least two distinct points.")
        cumulative = [0.0]
        travelled = 0.0
        for start, end in zip(filtered, filtered[1:]):
            travelled += _distance(start, end)
            cumulative.append(travelled)
        return cls(points=tuple(filtered), cumulative_lengths=tuple(cumulative), length=max(travelled, 1e-6))

    def point_at_distance(self, distance_along: float) -> Point2D:
        target = _clamp(distance_along, 0.0, self.length)
        for index in range(len(self.points) - 1):
            segment_start = self.cumulative_lengths[index]
            segment_end = self.cumulative_lengths[index + 1]
            if target <= segment_end or index == len(self.points) - 2:
                span = max(segment_end - segment_start, 1e-6)
                ratio = (target - segment_start) / span
                start = self.points[index]
                end = self.points[index + 1]
                return Point2D(x=_lerp(start.x, end.x, ratio), y=_lerp(start.y, end.y, ratio))
        return self.points[-1]

    def point_at(self, t: float) -> Point2D:
        return self.point_at_distance(self.length * _clamp(t, 0.0, 1.0))

    def tangent_at_distance(self, distance_along: float) -> Point2D:
        target = _clamp(distance_along, 0.0, self.length)
        for index in range(len(self.points) - 1):
            segment_end = self.cumulative_lengths[index + 1]
            if target <= segment_end or index == len(self.points) - 2:
                start = self.points[index]
                end = self.points[index + 1]
                return _normalize(end.x - start.x, end.y - start.y)
        start = self.points[-2]
        end = self.points[-1]
        return _normalize(end.x - start.x, end.y - start.y)

    def tangent_at(self, t: float) -> Point2D:
        return self.tangent_at_distance(self.length * _clamp(t, 0.0, 1.0))


@dataclass(frozen=True)
class CrosswalkDefinition:
    id: str
    road_direction: RoadDirection
    start: Point2D
    end: Point2D
    movement: Point2D

    @property
    def movement_direction(self) -> RoadDirection:
        return "EW" if abs(self.movement.x) > abs(self.movement.y) else "NS"

    def to_view(self) -> CrosswalkView:
        return CrosswalkView(
            id=self.id,
            road_direction=self.road_direction,
            start=self.start,
            end=self.end,
            movement=self.movement,
        )


@dataclass(frozen=True)
class LaneDefinition:
    id: str
    direction: Approach
    lane_index: str
    movement: LaneMovement
    movement_id: str
    direction_group: RoadDirection
    path: PolylinePath
    stop_line_position: Point2D
    stop_distance: float
    stop_crosswalk_id: str
    crosswalk_start: Point2D

    def to_view(self) -> LaneView:
        return LaneView(
            id=self.id,
            kind="main",
            approach=self.direction,
            direction=self.direction,
            movement=self.movement,
            start=self.path.points[0],
            end=self.path.points[-1],
            path=list(self.path.points),
            crosswalk_id=self.stop_crosswalk_id,
            stop_line_position=self.stop_line_position,
            crosswalk_start=self.crosswalk_start,
        )


@dataclass
class VehicleStateModel:
    id: str
    lane_id: str
    route: RouteType
    progress: float
    speed: float
    state: str
    position: Point2D
    heading: float
    velocity_x: float
    velocity_y: float
    wait_time: float
    cruise_speed: float
    color: str
    distance_along: float
    kind: VehicleKind = "car"
    has_siren: bool = False
    priority: int = 0
    length: float = VEHICLE_MIN_LENGTH
    width: float = VEHICLE_MIN_WIDTH


@dataclass
class PedestrianStateModel:
    id: str
    crossing: RoadDirection
    crosswalk_id: str
    road_direction: RoadDirection
    start_position: Point2D
    target_position: Point2D
    position: Point2D
    progress: float
    speed: float
    state: str = "WAITING"
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    wait_time: float = 0.0
    target_crosswalk: str = ""
    is_elderly: bool = False
    is_impatient: bool = False
    risky_crossing: bool = False
    look_angle: float = 0.0


@dataclass(frozen=True)
class PhaseDefinition:
    name: SignalCycleState
    min_green: float
    max_green: float
    direction_group: RoadDirection | None
    movement_ids: tuple[str, ...]
    pedestrian_crossing: RoadDirection | None = None


PHASE_ORDER: tuple[SignalCycleState, ...] = (
    NS_STRAIGHT,
    NS_LEFT,
    EW_STRAIGHT,
    EW_LEFT,
)

PHASE_DEFINITIONS: Dict[SignalCycleState, PhaseDefinition] = {
    NS_STRAIGHT: PhaseDefinition(NS_STRAIGHT, STRAIGHT_MIN_GREEN, STRAIGHT_MAX_GREEN, "NS", ("N_STRAIGHT", "S_STRAIGHT"), pedestrian_crossing="EW"),
    NS_LEFT: PhaseDefinition(NS_LEFT, LEFT_MIN_GREEN, LEFT_MAX_GREEN, "NS", ("N_LEFT", "S_LEFT")),
    EW_STRAIGHT: PhaseDefinition(EW_STRAIGHT, STRAIGHT_MIN_GREEN, STRAIGHT_MAX_GREEN, "EW", ("E_STRAIGHT", "W_STRAIGHT"), pedestrian_crossing="NS"),
    EW_LEFT: PhaseDefinition(EW_LEFT, LEFT_MIN_GREEN, LEFT_MAX_GREEN, "EW", ("E_LEFT", "W_LEFT")),
}


class SignalController:
    """Adaptive protected multi-phase controller with hysteresis and starvation guards."""

    def __init__(self) -> None:
        self.current_phase_name: SignalCycleState = NS_STRAIGHT
        self.next_phase_name: SignalCycleState = NS_STRAIGHT
        self.stage: ControllerPhase = PHASE_GREEN
        self.stage_elapsed = 0.0
        self.all_red_release_time = ALL_RED_TIME
        self.unserved_demand_time: Dict[SignalCycleState, float] = {phase: 0.0 for phase in PHASE_ORDER}

    @property
    def current_phase(self) -> PhaseDefinition:
        return PHASE_DEFINITIONS[self.current_phase_name]

    @property
    def state(self) -> SignalCycleState:
        return self.current_phase_name

    def stage_duration(self) -> float:
        if self.stage == PHASE_GREEN:
            return self.current_phase.max_green
        if self.stage == PHASE_YELLOW:
            return YELLOW_TIME
        return self.all_red_release_time

    def phase_timer(self) -> float:
        return self.stage_elapsed

    def phase_time_remaining(self) -> float:
        return max(0.0, self.stage_duration() - self.stage_elapsed)

    def min_green_remaining(self) -> float:
        if self.stage != PHASE_GREEN:
            return 0.0
        return max(0.0, self.current_phase.min_green - self.stage_elapsed)

    def _update_unserved_demand(self, dt: float, phase_has_demand: Dict[SignalCycleState, bool]) -> None:
        for phase in PHASE_ORDER:
            if phase == self.current_phase_name and self.stage == PHASE_GREEN:
                self.unserved_demand_time[phase] = 0.0
            elif phase_has_demand.get(phase, False):
                self.unserved_demand_time[phase] += dt
            else:
                self.unserved_demand_time[phase] = 0.0

    def _highest_scoring_phase(
        self,
        phase_scores: Dict[SignalCycleState, float],
        phase_has_demand: Dict[SignalCycleState, bool],
        *,
        exclude_current: bool = False,
    ) -> SignalCycleState:
        candidates = [
            phase
            for phase in PHASE_ORDER
            if phase_has_demand.get(phase, False) and not (exclude_current and phase == self.current_phase_name)
        ]
        if not candidates:
            return self.current_phase_name

        highest_score = max(phase_scores.get(phase, 0.0) for phase in candidates)
        top = [phase for phase in candidates if abs(phase_scores.get(phase, 0.0) - highest_score) < 1e-6]
        if not exclude_current and self.current_phase_name in top:
            return self.current_phase_name
        return min(top, key=PHASE_ORDER.index)

    def _starved_phase(
        self,
        phase_scores: Dict[SignalCycleState, float],
        phase_has_demand: Dict[SignalCycleState, bool],
    ) -> SignalCycleState | None:
        starved = [
            phase
            for phase in PHASE_ORDER
            if phase_has_demand.get(phase, False) and self.unserved_demand_time.get(phase, 0.0) >= STARVATION_LIMIT
        ]
        if not starved:
            return None
        return max(starved, key=lambda phase: (self.unserved_demand_time[phase], phase_scores.get(phase, 0.0)))

    def _should_switch_phase(
        self,
        phase_scores: Dict[SignalCycleState, float],
        phase_has_demand: Dict[SignalCycleState, bool],
    ) -> SignalCycleState | None:
        if self.stage_elapsed < self.current_phase.min_green:
            return None

        current_score = phase_scores.get(self.current_phase_name, 0.0)
        current_has_demand = phase_has_demand.get(self.current_phase_name, False)
        competing_demand = any(phase_has_demand.get(phase, False) for phase in PHASE_ORDER if phase != self.current_phase_name)

        starved = self._starved_phase(phase_scores, phase_has_demand)
        if starved is not None and starved != self.current_phase_name:
            return starved

        if self.stage_elapsed >= self.current_phase.max_green and competing_demand:
            return self._highest_scoring_phase(phase_scores, phase_has_demand, exclude_current=True)

        if not current_has_demand:
            candidate = self._highest_scoring_phase(phase_scores, phase_has_demand, exclude_current=True)
            return candidate if candidate != self.current_phase_name else None

        candidate = self._highest_scoring_phase(phase_scores, phase_has_demand)
        candidate_score = phase_scores.get(candidate, 0.0)
        if candidate != self.current_phase_name and candidate_score > current_score + SWITCH_SCORE_MARGIN:
            return candidate

        return None

    def update(
        self,
        dt: float,
        phase_scores: Dict[SignalCycleState, float],
        phase_has_demand: Dict[SignalCycleState, bool],
        *,
        intersection_clear: bool,
    ) -> list[tuple[SignalCycleState, ControllerPhase]]:
        transitions: list[tuple[SignalCycleState, ControllerPhase]] = []
        self._update_unserved_demand(dt, phase_has_demand)
        self.stage_elapsed += dt

        while True:
            # Every change must clear through green -> yellow -> all-red before the next phase goes green.
            if self.stage == PHASE_GREEN:
                next_phase = self._should_switch_phase(phase_scores, phase_has_demand)
                if next_phase is None:
                    break
                self.next_phase_name = next_phase
                self.stage = PHASE_YELLOW
                self.stage_elapsed = 0.0
                transitions.append((self.current_phase_name, self.stage))
                break

            if self.stage == PHASE_YELLOW:
                if self.stage_elapsed < YELLOW_TIME:
                    break

                self.stage = PHASE_ALL_RED
                self.stage_elapsed = 0.0
                self.all_red_release_time = ALL_RED_TIME
                transitions.append((self.current_phase_name, self.stage))
                continue

            if self.stage == PHASE_ALL_RED:
                if self.stage_elapsed < ALL_RED_TIME:
                    break

                if not intersection_clear and self.all_red_release_time < ALL_RED_TIME + ALL_RED_EXTENSION_LIMIT:
                    self.all_red_release_time = min(
                        self.all_red_release_time + ALL_RED_EXTENSION_STEP,
                        ALL_RED_TIME + ALL_RED_EXTENSION_LIMIT,
                    )
                    break

                if self.stage_elapsed < self.all_red_release_time:
                    break

                self.current_phase_name = self.next_phase_name
                self.stage = PHASE_GREEN
                self.stage_elapsed = 0.0
                self.all_red_release_time = ALL_RED_TIME
                transitions.append((self.current_phase_name, self.stage))
                continue

            break
        return transitions

    def controller_phase(self) -> ControllerPhase:
        return self.stage

    def active_direction(self) -> RoadDirection | None:
        if self.stage == PHASE_ALL_RED:
            return None
        return self.current_phase.direction_group

    def signal_state_for_approach(self, approach: Approach) -> SignalState:
        phase = self.current_phase
        if phase.direction_group != _direction_group(approach):
            return RED
        if self.stage == PHASE_ALL_RED:
            return RED
        if self.stage == PHASE_YELLOW:
            return YELLOW
        if phase.name in {NS_LEFT, EW_LEFT}:
            return GREEN_LEFT
        return GREEN

    def can_vehicle_move(self, approach: Approach, route: RouteType) -> bool:
        signal_state = self.signal_state_for_approach(approach)
        if route == "straight":
            return signal_state == GREEN
        if route == "left":
            return signal_state == GREEN_LEFT
        return False

    def pedestrians_can_cross(self, crossing: RoadDirection) -> bool:
        return self.stage == PHASE_GREEN and self.current_phase.pedestrian_crossing == crossing


class TrafficSimulationEngine:
    """Protected multi-phase intersection with straight and left intents."""

    def __init__(self) -> None:
        self.crosswalks = self._build_crosswalks()
        self.lanes = self._build_lanes()
        self.phase_lane_ids = {
            phase: tuple(
                lane_id for lane_id, lane in self.lanes.items() if lane.movement_id in definition.movement_ids
            )
            for phase, definition in PHASE_DEFINITIONS.items()
        }
        self.lane_phase_map = {
            lane_id: phase
            for phase, lane_ids in self.phase_lane_ids.items()
            for lane_id in lane_ids
        }
        self.vehicle_lane_order = list(self.lanes.keys())
        self._rng = random.Random(13)
        self.events: Deque[EventView] = deque(maxlen=40)
        self.traffic_brain = TrafficBrain()
        self.reset()
        self._log("INFO", "Multi-phase intersection initialized with grouped signals, protected straight phases, and safe left turns.")

    def reset(self) -> None:
        self.config = SimulationConfig(ai_mode="adaptive", max_vehicles=36, max_pedestrians=12)
        self.signal_controller = SignalController()
        self.current_state: SignalCycleState = self.signal_controller.state
        self.frame = 0
        self.time = 0.0
        self.processed_vehicles = 0
        self.smoothed_throughput = 0.0
        self.vehicles: List[VehicleStateModel] = []
        self.pedestrians: List[PedestrianStateModel] = []
        self.metrics = MetricsView(0.0, 0.0, 0, 0.0, 0, 0, 0, 0, 12, 0, 12.0)
        self._vehicle_index = 0
        self._pedestrian_index = 0
        self._vehicle_spawn_cursor = 0
        self._pedestrian_spawn_cursor = 0
        self._vehicle_spawn_timer = self._vehicle_spawn_interval()
        self._pedestrian_spawn_timer = self._pedestrian_spawn_interval()
        self._color_cursor = 0
        self._vehicles_processed_last_tick = 0
        self._vehicles_processed_by_approach_last_tick: Dict[Approach, int] = {
            approach: 0 for approach in SIGNAL_DIRECTIONS
        }
        self.traffic_brain.reset()
        self.phase_scores: Dict[SignalCycleState, float] = {phase: 0.0 for phase in PHASE_ORDER}
        self.phase_has_demand: Dict[SignalCycleState, bool] = {phase: False for phase in PHASE_ORDER}
        self.phase_demands: Dict[SignalCycleState, Dict[str, float]] = {
            phase: {
                "queue": 0.0,
                "wait_time": 0.0,
                "pedestrian_demand": 0.0,
                "flow_rate": 0.0,
                "congestion_trend": 0.0,
                "fairness_boost": 0.0,
                "emergency_boost": 0.0,
                "score": 0.0,
            }
            for phase in PHASE_ORDER
        }
        self.events.clear()
        self._refresh_phase_demand_cache(0.0)

    def update_config(self, values: Dict[str, object]) -> SimulationConfig:
        if "traffic_intensity" in values:
            self.config.traffic_intensity = _clamp(float(values["traffic_intensity"]), 0.0, 1.0)
        if "ambulance_frequency" in values:
            self.config.ambulance_frequency = _clamp(float(values["ambulance_frequency"]), 0.0, 1.0)
        if "speed_multiplier" in values:
            self.config.speed_multiplier = _clamp(float(values["speed_multiplier"]), 0.25, 4.0)
        if "paused" in values:
            self.config.paused = bool(values["paused"])
        if "max_vehicles" in values:
            self.config.max_vehicles = max(0, min(80, int(values["max_vehicles"])))
        if "max_pedestrians" in values:
            self.config.max_pedestrians = max(0, min(40, int(values["max_pedestrians"])))
        if "ai_mode" in values:
            self.config.ai_mode = "adaptive"
        return self.config

    def tick(self, dt: float = FRAME_DT) -> Dict[str, object]:
        sim_dt = max(0.0, float(dt))
        if self.config.paused:
            sim_dt = 0.0
        else:
            sim_dt *= self.config.speed_multiplier

        self.frame += 1
        self._vehicles_processed_last_tick = 0
        self._vehicles_processed_by_approach_last_tick = {
            approach: 0 for approach in SIGNAL_DIRECTIONS
        }
        if sim_dt > 0.0:
            self.time += sim_dt
            self.update_signals(sim_dt)
            self.update_vehicles(sim_dt)
            self.update_pedestrians(sim_dt)
        self._refresh_phase_demand_cache(sim_dt)
        self.compute_metrics(sim_dt)
        return self.snapshot().to_dict()

    def get_state(self) -> Dict[str, object]:
        return self.snapshot().to_dict()

    def snapshot(self) -> SnapshotView:
        return SnapshotView(
            frame=self.frame,
            timestamp=round(self.time, 3),
            current_state=self.current_state,
            active_direction=self.signal_controller.active_direction(),
            controller_phase=self.signal_controller.controller_phase(),
            phase_timer=round(self.signal_controller.phase_timer(), 3),
            phase_duration=round(self.signal_controller.stage_duration(), 3),
            min_green_remaining=round(self.signal_controller.min_green_remaining(), 3),
            vehicles=[self._vehicle_view(vehicle) for vehicle in self.vehicles],
            pedestrians=[self._pedestrian_view(pedestrian) for pedestrian in self.pedestrians],
            lanes=[lane.to_view() for lane in self.lanes.values()],
            crosswalks=[crosswalk.to_view() for crosswalk in self.crosswalks.values()],
            signals=self._signal_snapshot(),
            pedestrian_phase_active=self.signal_controller.current_phase.pedestrian_crossing is not None and self.signal_controller.controller_phase() == PHASE_GREEN,
            metrics=self.metrics,
            traffic_brain=self.traffic_brain_state,
            events=list(self.events),
            config=self.config,
        )

    def _build_crosswalks(self) -> Dict[str, CrosswalkDefinition]:
        return {
            "north_crosswalk": CrosswalkDefinition(
                id="north_crosswalk",
                road_direction="NS",
                start=Point2D(-ROAD_SURFACE_HALF_WIDTH, CROSSWALK_CENTER_OFFSET),
                end=Point2D(ROAD_SURFACE_HALF_WIDTH, CROSSWALK_CENTER_OFFSET),
                movement=Point2D(1.0, 0.0),
            ),
            "south_crosswalk": CrosswalkDefinition(
                id="south_crosswalk",
                road_direction="NS",
                start=Point2D(-ROAD_SURFACE_HALF_WIDTH, -CROSSWALK_CENTER_OFFSET),
                end=Point2D(ROAD_SURFACE_HALF_WIDTH, -CROSSWALK_CENTER_OFFSET),
                movement=Point2D(1.0, 0.0),
            ),
            "east_crosswalk": CrosswalkDefinition(
                id="east_crosswalk",
                road_direction="EW",
                start=Point2D(CROSSWALK_CENTER_OFFSET, -ROAD_SURFACE_HALF_WIDTH),
                end=Point2D(CROSSWALK_CENTER_OFFSET, ROAD_SURFACE_HALF_WIDTH),
                movement=Point2D(0.0, 1.0),
            ),
            "west_crosswalk": CrosswalkDefinition(
                id="west_crosswalk",
                road_direction="EW",
                start=Point2D(-CROSSWALK_CENTER_OFFSET, -ROAD_SURFACE_HALF_WIDTH),
                end=Point2D(-CROSSWALK_CENTER_OFFSET, ROAD_SURFACE_HALF_WIDTH),
                movement=Point2D(0.0, 1.0),
            ),
        }

    def _build_lanes(self) -> Dict[str, LaneDefinition]:
        lanes: Dict[str, LaneDefinition] = {}

        def add_lane(
            lane_id: str,
            approach: Approach,
            lane_index: str,
            movement: LaneMovement,
            movement_id: str,
            points: Iterable[Point2D],
            stop_line_position: Point2D,
            crosswalk_start: Point2D,
            crosswalk_id: str,
        ) -> None:
            path = PolylinePath.from_points(points)
            lanes[lane_id] = LaneDefinition(
                id=lane_id,
                direction=approach,
                lane_index=lane_index,
                movement=movement,
                movement_id=movement_id,
                direction_group=_direction_group(approach),
                path=path,
                stop_line_position=stop_line_position,
                stop_distance=_distance(path.points[0], stop_line_position),
                stop_crosswalk_id=crosswalk_id,
                crosswalk_start=crosswalk_start,
            )

        def add_straight_lane(
            lane_id: str,
            approach: Approach,
            lane_position: float,
            *,
            vertical: bool,
            start_sign: float,
            crosswalk_id: str,
        ) -> None:
            if vertical:
                start = Point2D(lane_position, start_sign * PATH_ENTRY_OFFSET)
                end = Point2D(lane_position, -start_sign * PATH_EXIT_OFFSET)
                stop = Point2D(lane_position, start_sign * STOP_OFFSET)
                crosswalk_start = Point2D(lane_position, start_sign * CROSSWALK_OUTER_OFFSET)
            else:
                start = Point2D(start_sign * PATH_ENTRY_OFFSET, lane_position)
                end = Point2D(-start_sign * PATH_EXIT_OFFSET, lane_position)
                stop = Point2D(start_sign * STOP_OFFSET, lane_position)
                crosswalk_start = Point2D(start_sign * CROSSWALK_OUTER_OFFSET, lane_position)
            add_lane(
                lane_id=lane_id,
                approach=approach,
                lane_index="outer",
                movement="STRAIGHT",
                movement_id=f"{approach[0]}_STRAIGHT",
                points=(start, end),
                stop_line_position=stop,
                crosswalk_start=crosswalk_start,
                crosswalk_id=crosswalk_id,
            )

        def add_left_lane(
            lane_id: str,
            approach: Approach,
            entry_start: Point2D,
            stop_line_position: Point2D,
            entry_box: Point2D,
            control: Point2D,
            exit_box: Point2D,
            exit_end: Point2D,
            crosswalk_start: Point2D,
            crosswalk_id: str,
        ) -> None:
            curve = _sample_quadratic_bezier(entry_box, control, exit_box)
            add_lane(
                lane_id=lane_id,
                approach=approach,
                lane_index="inner",
                movement="LEFT",
                movement_id=f"{approach[0]}_LEFT",
                points=(entry_start, stop_line_position, *curve[1:], exit_end),
                stop_line_position=stop_line_position,
                crosswalk_start=crosswalk_start,
                crosswalk_id=crosswalk_id,
            )

        add_straight_lane("lane_south_outer_straight", "SOUTH", OUTER_LANE_OFFSET, vertical=True, start_sign=-1.0, crosswalk_id="south_crosswalk")
        add_straight_lane("lane_north_outer_straight", "NORTH", -OUTER_LANE_OFFSET, vertical=True, start_sign=1.0, crosswalk_id="north_crosswalk")
        add_straight_lane("lane_west_outer_straight", "WEST", OUTER_LANE_OFFSET, vertical=False, start_sign=-1.0, crosswalk_id="west_crosswalk")
        add_straight_lane("lane_east_outer_straight", "EAST", -OUTER_LANE_OFFSET, vertical=False, start_sign=1.0, crosswalk_id="east_crosswalk")

        add_left_lane(
            lane_id="lane_south_inner_left",
            approach="SOUTH",
            entry_start=Point2D(INNER_LANE_OFFSET, -PATH_ENTRY_OFFSET),
            stop_line_position=Point2D(INNER_LANE_OFFSET, -STOP_OFFSET),
            entry_box=Point2D(INNER_LANE_OFFSET, -INTERSECTION_HALF_SIZE),
            control=Point2D(INNER_LANE_OFFSET, -INNER_LANE_OFFSET),
            exit_box=Point2D(-INTERSECTION_HALF_SIZE, -INNER_LANE_OFFSET),
            exit_end=Point2D(-PATH_EXIT_OFFSET, -INNER_LANE_OFFSET),
            crosswalk_start=Point2D(INNER_LANE_OFFSET, -CROSSWALK_OUTER_OFFSET),
            crosswalk_id="south_crosswalk",
        )
        add_left_lane(
            lane_id="lane_north_inner_left",
            approach="NORTH",
            entry_start=Point2D(-INNER_LANE_OFFSET, PATH_ENTRY_OFFSET),
            stop_line_position=Point2D(-INNER_LANE_OFFSET, STOP_OFFSET),
            entry_box=Point2D(-INNER_LANE_OFFSET, INTERSECTION_HALF_SIZE),
            control=Point2D(-INNER_LANE_OFFSET, INNER_LANE_OFFSET),
            exit_box=Point2D(INTERSECTION_HALF_SIZE, INNER_LANE_OFFSET),
            exit_end=Point2D(PATH_EXIT_OFFSET, INNER_LANE_OFFSET),
            crosswalk_start=Point2D(-INNER_LANE_OFFSET, CROSSWALK_OUTER_OFFSET),
            crosswalk_id="north_crosswalk",
        )
        add_left_lane(
            lane_id="lane_west_inner_left",
            approach="WEST",
            entry_start=Point2D(-PATH_ENTRY_OFFSET, INNER_LANE_OFFSET),
            stop_line_position=Point2D(-STOP_OFFSET, INNER_LANE_OFFSET),
            entry_box=Point2D(-INTERSECTION_HALF_SIZE, INNER_LANE_OFFSET),
            control=Point2D(INNER_LANE_OFFSET, INNER_LANE_OFFSET),
            exit_box=Point2D(INNER_LANE_OFFSET, INTERSECTION_HALF_SIZE),
            exit_end=Point2D(INNER_LANE_OFFSET, PATH_EXIT_OFFSET),
            crosswalk_start=Point2D(-CROSSWALK_OUTER_OFFSET, INNER_LANE_OFFSET),
            crosswalk_id="west_crosswalk",
        )
        add_left_lane(
            lane_id="lane_east_inner_left",
            approach="EAST",
            entry_start=Point2D(PATH_ENTRY_OFFSET, -INNER_LANE_OFFSET),
            stop_line_position=Point2D(STOP_OFFSET, -INNER_LANE_OFFSET),
            entry_box=Point2D(INTERSECTION_HALF_SIZE, -INNER_LANE_OFFSET),
            control=Point2D(-INNER_LANE_OFFSET, -INNER_LANE_OFFSET),
            exit_box=Point2D(-INNER_LANE_OFFSET, -INTERSECTION_HALF_SIZE),
            exit_end=Point2D(-INNER_LANE_OFFSET, -PATH_EXIT_OFFSET),
            crosswalk_start=Point2D(CROSSWALK_OUTER_OFFSET, -INNER_LANE_OFFSET),
            crosswalk_id="east_crosswalk",
        )
        return lanes

    def _vehicle_spawn_interval(self) -> float:
        intensity = _clamp(self.config.traffic_intensity, 0.0, 1.0)
        return 3.0 - (2.0 * intensity)

    def _pedestrian_spawn_interval(self) -> float:
        intensity = _clamp(self.config.traffic_intensity, 0.0, 1.0)
        return 6.0 - (2.8 * intensity)

    def _lane_ids_for_route(self, approach: Approach, route: RouteType) -> List[str]:
        movement = {"straight": "STRAIGHT", "left": "LEFT"}.get(route)
        if movement is None:
            return []
        lane_ids = [
            lane_id
            for lane_id, lane in self.lanes.items()
            if lane.direction == approach and lane.movement == movement
        ]
        return sorted(lane_ids)

    def _spawn_vehicle(self) -> None:
        if len(self.vehicles) >= self.config.max_vehicles:
            return

        approach_count = len(VEHICLE_APPROACHES)
        for offset in range(approach_count):
            index = (self._vehicle_spawn_cursor + offset) % approach_count
            approach = VEHICLE_APPROACHES[index]
            emergency_spawn = self._rng.random() < self.config.ambulance_frequency
            route: RouteType = "left" if self._rng.random() < LEFT_TURN_PROBABILITY else "straight"
            if emergency_spawn and self._rng.random() < EMERGENCY_ROUTE_PREFERENCE:
                route = "straight"
            lane_ids = self._lane_ids_for_route(approach, route)
            if not lane_ids:
                continue

            lane_id = lane_ids[0]
            if self._lane_has_spawn_room(lane_id):
                vehicle = self._make_vehicle_for_lane(lane_id, emergency=emergency_spawn)
                self.vehicles.append(vehicle)
                self._vehicle_spawn_cursor = (index + 1) % approach_count
                self._vehicle_spawn_timer = self._vehicle_spawn_interval()
                descriptor = f"{vehicle.kind} {vehicle.route}" if vehicle.kind != "car" else f"{vehicle.route} vehicle"
                self._log("INFO", f"Spawned {descriptor} on {self.lanes[lane_id].direction.lower()} approach.")
                return
        self._vehicle_spawn_timer = 0.35

    def _lane_has_spawn_room(self, lane_id: str) -> bool:
        return not any(
            other.lane_id == lane_id and other.distance_along < (other.length + FOLLOW_GAP + 2.0)
            for other in self.vehicles
        )

    def _spawn_pedestrian(self) -> None:
        if len(self.pedestrians) >= self.config.max_pedestrians:
            return

        crosswalk_id, reverse = PEDESTRIAN_SPAWN_PLAN[self._pedestrian_spawn_cursor % len(PEDESTRIAN_SPAWN_PLAN)]
        self._pedestrian_spawn_cursor += 1
        candidate = self._make_pedestrian(crosswalk_id, reverse=reverse)
        blocked = any(
            pedestrian.crosswalk_id == candidate.crosswalk_id
            and pedestrian.state == "WAITING"
            and _distance(pedestrian.start_position, candidate.start_position) < 0.1
            and _distance(pedestrian.position, candidate.position) < 1.2
            for pedestrian in self.pedestrians
        )
        if blocked:
            self._pedestrian_spawn_timer = 0.6
            return
        self.pedestrians.append(candidate)
        self._pedestrian_spawn_timer = self._pedestrian_spawn_interval()

    def _make_vehicle(self, approach: Approach, route: RouteType) -> VehicleStateModel:
        lane_ids = self._lane_ids_for_route(approach, route)
        if not lane_ids:
            raise ValueError(f"No lane path defined for {approach.lower()} {route}.")
        return self._make_vehicle_for_lane(lane_ids[0])

    def _make_vehicle_for_lane(self, lane_id: str, *, emergency: bool = False) -> VehicleStateModel:
        lane = self.lanes[lane_id]
        start_position = lane.path.point_at(0.0)
        tangent = lane.path.tangent_at(0.0)
        self._vehicle_index += 1
        color = VEHICLE_COLOR_POOL[self._color_cursor % len(VEHICLE_COLOR_POOL)]
        self._color_cursor += 1
        length = round(_lerp(VEHICLE_MIN_LENGTH, VEHICLE_MAX_LENGTH, self._rng.random()), 3)
        width = round(_lerp(VEHICLE_MIN_WIDTH, VEHICLE_MAX_WIDTH, self._rng.random()), 3)
        if lane.movement == "STRAIGHT":
            cruise_speed = round(_lerp(STRAIGHT_SPEED_MIN, STRAIGHT_SPEED_MAX, self._rng.random()), 3)
            route: RouteType = "straight"
        else:
            cruise_speed = round(_lerp(LEFT_SPEED_MIN, LEFT_SPEED_MAX, self._rng.random()), 3)
            route = "left"
        kind: VehicleKind = "car"
        has_siren = False
        priority = 0
        if emergency:
            kind = "ambulance"
            has_siren = True
            priority = 2
            color = "#f8fafc"
            cruise_speed = round(cruise_speed * EMERGENCY_SPEED_MULTIPLIER, 3)
            length = round(max(length, 5.1), 3)
            width = round(max(width, 2.05), 3)
        return VehicleStateModel(
            id=f"veh-{self._vehicle_index}",
            lane_id=lane_id,
            route=route,
            progress=0.0,
            speed=0.0,
            state="MOVING",
            position=start_position,
            heading=math.atan2(tangent.x, tangent.y),
            velocity_x=0.0,
            velocity_y=0.0,
            wait_time=0.0,
            cruise_speed=cruise_speed,
            color=color,
            distance_along=0.0,
            kind=kind,
            has_siren=has_siren,
            priority=priority,
            length=length,
            width=width,
        )

    def _make_pedestrian(self, crosswalk_id: str, *, reverse: bool = False) -> PedestrianStateModel:
        crosswalk = self.crosswalks[crosswalk_id]
        start = crosswalk.end if reverse else crosswalk.start
        target = crosswalk.start if reverse else crosswalk.end
        self._pedestrian_index += 1
        direction = _normalize(target.x - start.x, target.y - start.y)
        return PedestrianStateModel(
            id=f"ped-{self._pedestrian_index}",
            crossing=crosswalk.movement_direction,
            crosswalk_id=crosswalk_id,
            road_direction=crosswalk.road_direction,
            start_position=start,
            target_position=target,
            position=Point2D(start.x, start.y),
            progress=0.0,
            speed=PEDESTRIAN_SPEED,
            target_crosswalk=crosswalk_id,
            look_angle=math.atan2(direction.x, direction.y),
        )

    def _vehicle_view(self, vehicle: VehicleStateModel) -> VehicleView:
        lane = self.lanes[vehicle.lane_id]
        return VehicleView(
            id=vehicle.id,
            lane_id=vehicle.lane_id,
            approach=lane.direction,
            route=vehicle.route,
            progress=round(vehicle.progress, 4),
            speed=round(vehicle.speed, 4),
            velocity_x=round(vehicle.velocity_x, 4),
            velocity_y=round(vehicle.velocity_y, 4),
            heading=round(vehicle.heading, 4),
            x=round(vehicle.position.x, 4),
            y=round(vehicle.position.y, 4),
            kind=vehicle.kind,
            has_siren=vehicle.has_siren,
            priority=vehicle.priority,
            state=vehicle.state,
            wait_time=round(vehicle.wait_time, 3),
            color=vehicle.color,
            length=vehicle.length,
            width=vehicle.width,
        )

    def _pedestrian_view(self, pedestrian: PedestrianStateModel) -> PedestrianView:
        return PedestrianView(
            id=pedestrian.id,
            crossing=pedestrian.crossing,
            target_crosswalk=pedestrian.target_crosswalk or pedestrian.crosswalk_id,
            crosswalk_id=pedestrian.crosswalk_id,
            road_direction=pedestrian.road_direction,
            progress=round(pedestrian.progress, 4),
            speed=round(pedestrian.speed, 4),
            velocity_x=round(pedestrian.velocity_x, 4),
            velocity_y=round(pedestrian.velocity_y, 4),
            x=round(pedestrian.position.x, 4),
            y=round(pedestrian.position.y, 4),
            state=pedestrian.state,
            wait_time=round(pedestrian.wait_time, 3),
            is_elderly=pedestrian.is_elderly,
            is_impatient=pedestrian.is_impatient,
            risky_crossing=pedestrian.risky_crossing,
            look_angle=round(pedestrian.look_angle, 4),
        )

    def _is_vehicle_queued(self, vehicle: VehicleStateModel) -> bool:
        lane = self.lanes[vehicle.lane_id]
        return (
            vehicle.distance_along <= lane.stop_distance + 0.5
            and (vehicle.state == "STOPPED" or vehicle.wait_time > 0.0 or vehicle.speed <= MIN_MOVEMENT_STEP)
        )

    def _traffic_brain_vehicle_inputs(self) -> List[VehicleTelemetryInput]:
        telemetry: List[VehicleTelemetryInput] = []
        for vehicle in self.vehicles:
            lane = self.lanes[vehicle.lane_id]
            telemetry.append(
                VehicleTelemetryInput(
                    id=vehicle.id,
                    lane_id=vehicle.lane_id,
                    approach=lane.direction,
                    wait_time=vehicle.wait_time,
                    speed=vehicle.speed,
                    cruise_speed=vehicle.cruise_speed,
                    state=vehicle.state,
                    distance_to_stop=lane.stop_distance - vehicle.distance_along,
                    queued=self._is_vehicle_queued(vehicle),
                    kind=vehicle.kind,
                    has_siren=vehicle.has_siren,
                )
            )
        return telemetry

    def _traffic_brain_pedestrian_inputs(self) -> List[PedestrianTelemetryInput]:
        return [
            PedestrianTelemetryInput(
                crossing=pedestrian.crossing,
                wait_time=pedestrian.wait_time,
                state=pedestrian.state,
            )
            for pedestrian in self.pedestrians
        ]

    def _build_traffic_brain_state(self, dt: float, *, brain: TrafficBrain | None = None):
        active_brain = brain or self.traffic_brain
        return active_brain.evaluate(
            dt=dt,
            current_phase=self.signal_controller.state,
            controller_phase=self.signal_controller.controller_phase(),
            vehicles=self._traffic_brain_vehicle_inputs(),
            pedestrians=self._traffic_brain_pedestrian_inputs(),
            lane_phase_map=self.lane_phase_map,
            phase_lane_ids=self.phase_lane_ids,
            phase_crossings={phase: definition.pedestrian_crossing for phase, definition in PHASE_DEFINITIONS.items()},
            phase_order=PHASE_ORDER,
            unserved_demand_time=self.signal_controller.unserved_demand_time,
            processed_by_approach=self._vehicles_processed_by_approach_last_tick,
        )

    def _phase_maps_from_brain(self, brain_state) -> tuple[Dict[SignalCycleState, Dict[str, float]], Dict[SignalCycleState, float], Dict[SignalCycleState, bool]]:
        phase_demands: Dict[SignalCycleState, Dict[str, float]] = {}
        phase_scores: Dict[SignalCycleState, float] = {}
        phase_has_demand: Dict[SignalCycleState, bool] = {}

        for phase in PHASE_ORDER:
            score_view = brain_state.phase_scores[phase]
            phase_demands[phase] = {
                "queue": round(score_view.queue_length, 3),
                "wait_time": round(score_view.avg_wait_time, 3),
                "pedestrian_demand": round(score_view.pedestrian_demand, 3),
                "flow_rate": round(score_view.flow_rate, 3),
                "congestion_trend": round(score_view.congestion_component, 3),
                "fairness_boost": round(score_view.fairness_boost, 3),
                "emergency_boost": round(score_view.emergency_boost, 3),
                "score": round(score_view.score, 3),
            }
            phase_scores[phase] = round(score_view.score, 3)
            phase_has_demand[phase] = bool(score_view.demand_active)

        return phase_demands, phase_scores, phase_has_demand

    def _lane_queue_stats(self, lane_id: str) -> tuple[float, float]:
        queued_vehicles = [
            vehicle
            for vehicle in self.vehicles
            if vehicle.lane_id == lane_id and self._is_vehicle_queued(vehicle)
        ]
        queue_length = float(len(queued_vehicles))
        wait_time = float(sum(vehicle.wait_time for vehicle in queued_vehicles))
        return queue_length, wait_time

    def calculate_phase_demands(
        self,
    ) -> tuple[Dict[SignalCycleState, Dict[str, float]], Dict[SignalCycleState, float], Dict[SignalCycleState, bool]]:
        preview_brain = TrafficBrain()
        preview_brain.reset()
        brain_state = self._build_traffic_brain_state(0.0, brain=preview_brain)
        return self._phase_maps_from_brain(brain_state)

    def _refresh_phase_demand_cache(self, dt: float) -> None:
        self.traffic_brain_state = self._build_traffic_brain_state(dt)
        phase_demands, phase_scores, phase_has_demand = self._phase_maps_from_brain(self.traffic_brain_state)
        self.phase_demands = phase_demands
        self.phase_scores = phase_scores
        self.phase_has_demand = phase_has_demand

    def _reset_signals(self) -> Dict[str, SignalState]:
        return {approach: RED for approach in SIGNAL_DIRECTIONS}

    def _set_signal_state(self, signals: Dict[str, SignalState], approach: Approach, state: SignalState) -> None:
        signals[approach] = state

    def _apply_phase(self, signals: Dict[str, SignalState], phase: SignalCycleState, stage: ControllerPhase) -> None:
        if stage == PHASE_YELLOW:
            phase_state: SignalState = YELLOW
        elif phase in {NS_LEFT, EW_LEFT}:
            phase_state = GREEN_LEFT
        else:
            phase_state = GREEN

        if phase in {NS_STRAIGHT, NS_LEFT}:
            active_directions: tuple[Approach, ...] = ("NORTH", "SOUTH")
        else:
            active_directions = ("EAST", "WEST")

        for approach in active_directions:
            self._set_signal_state(signals, approach, phase_state)

    def _signal_snapshot(self) -> Dict[str, SignalState]:
        signals = self._reset_signals()
        if self.signal_controller.controller_phase() != PHASE_ALL_RED:
            self._apply_phase(signals, self.signal_controller.state, self.signal_controller.controller_phase())
        return signals

    def _vehicles_clear_of_intersection(self) -> bool:
        for vehicle in self.vehicles:
            clearance_margin = max(vehicle.length, vehicle.width) / 2.0
            if (
                abs(vehicle.position.x) <= INTERSECTION_HALF_SIZE + clearance_margin
                and abs(vehicle.position.y) <= INTERSECTION_HALF_SIZE + clearance_margin
            ):
                return False
        return True

    def _vehicle_can_commit_on_yellow(self, vehicle: VehicleStateModel, lane: LaneDefinition) -> bool:
        if self.signal_controller.controller_phase() != PHASE_YELLOW:
            return False
        # Yellow is only a short commit window for vehicles already too close to stop comfortably.
        if self.signal_controller.phase_timer() > YELLOW_COMMIT_WINDOW:
            return False
        if lane.movement_id not in self.signal_controller.current_phase.movement_ids:
            return False
        if vehicle.speed < YELLOW_MIN_COMMIT_SPEED:
            return False

        distance_to_stop = max(0.0, lane.stop_distance - vehicle.distance_along)
        stopping_distance = (vehicle.speed * vehicle.speed) / max(2.0 * BRAKE_RATE, 1e-6)
        commit_distance = max(2.5, stopping_distance + YELLOW_REACTION_BUFFER)
        return distance_to_stop <= commit_distance

    def update_signals(self, dt: float) -> None:
        preview_brain = copy.deepcopy(self.traffic_brain)
        self.traffic_brain_state = self._build_traffic_brain_state(dt, brain=preview_brain)
        phase_demands, phase_scores, phase_has_demand = self._phase_maps_from_brain(self.traffic_brain_state)
        self.phase_demands = phase_demands
        self.phase_scores = phase_scores
        self.phase_has_demand = phase_has_demand
        transitions = self.signal_controller.update(
            dt,
            self.phase_scores,
            self.phase_has_demand,
            intersection_clear=self._vehicles_clear_of_intersection(),
        )
        self.current_state = self.signal_controller.state
        for state, stage in transitions:
            if stage == PHASE_YELLOW:
                next_phase = self.signal_controller.next_phase_name.replace("_", " ")
                self._log("INFO", f"{state.replace('_', ' ')} entered yellow before {next_phase}.")
            elif stage == PHASE_ALL_RED:
                self._log("INFO", f"{state.replace('_', ' ')} entered all-red clearance.")
            else:
                score = self.phase_scores.get(state, 0.0)
                self._log("INFO", f"{state.replace('_', ' ')} is now green. Score {score:.2f}.")

    def update_vehicles(self, dt: float) -> None:
        if dt <= 0.0:
            return

        self._vehicle_spawn_timer -= dt
        while self._vehicle_spawn_timer <= 0.0 and len(self.vehicles) < self.config.max_vehicles:
            self._spawn_vehicle()

        lanes_to_vehicles: Dict[str, List[VehicleStateModel]] = {}
        for vehicle in self.vehicles:
            lanes_to_vehicles.setdefault(vehicle.lane_id, []).append(vehicle)

        survivors: List[VehicleStateModel] = []
        for lane_id, lane_vehicles in lanes_to_vehicles.items():
            lane = self.lanes[lane_id]
            lane_vehicles.sort(key=lambda item: item.distance_along, reverse=True)
            leader_distance = math.inf
            leader_length = VEHICLE_MAX_LENGTH
            leader_speed = 0.0

            for vehicle in lane_vehicles:
                allowed_distance = lane.path.length
                can_enter_on_green = self.signal_controller.can_vehicle_move(lane.direction, vehicle.route)
                can_commit_on_yellow = self._vehicle_can_commit_on_yellow(vehicle, lane)
                if vehicle.distance_along < lane.stop_distance and not (can_enter_on_green or can_commit_on_yellow):
                    allowed_distance = min(
                        allowed_distance,
                        max(0.0, lane.stop_distance - ((vehicle.length / 2.0) + STOP_LINE_BUFFER)),
                    )

                if leader_distance < math.inf:
                    spacing_limit = leader_distance - (((leader_length + vehicle.length) / 2.0) + FOLLOW_GAP)
                    allowed_distance = min(allowed_distance, spacing_limit)

                allowed_distance = max(vehicle.distance_along, allowed_distance)
                target_speed = vehicle.cruise_speed if allowed_distance > vehicle.distance_along + MIN_MOVEMENT_STEP else 0.0

                if leader_distance < math.inf:
                    gap_to_leader = leader_distance - vehicle.distance_along - (((leader_length + vehicle.length) / 2.0) + FOLLOW_GAP)
                    follow_ratio = _clamp(gap_to_leader / FOLLOW_RESPONSE_DISTANCE, 0.0, 1.0)
                    target_speed = min(target_speed, _lerp(leader_speed, vehicle.cruise_speed, follow_ratio))

                rate = ACCELERATION if target_speed >= vehicle.speed else BRAKE_RATE
                updated_speed = _move_toward(vehicle.speed, target_speed, rate * dt)
                candidate_distance = min(lane.path.length, vehicle.distance_along + (updated_speed * dt))
                next_distance = min(candidate_distance, allowed_distance)

                if next_distance <= vehicle.distance_along + MIN_MOVEMENT_STEP:
                    next_distance = vehicle.distance_along
                    updated_speed = 0.0

                actual_speed = (next_distance - vehicle.distance_along) / dt if dt > 0.0 else 0.0
                next_progress = next_distance / lane.path.length
                tangent = lane.path.tangent_at(next_progress)

                vehicle.position = lane.path.point_at(next_progress)
                vehicle.distance_along = next_distance
                vehicle.progress = next_progress
                vehicle.heading = math.atan2(tangent.x, tangent.y)
                vehicle.velocity_x = tangent.x * actual_speed
                vehicle.velocity_y = tangent.y * actual_speed
                vehicle.speed = actual_speed
                vehicle.state = "MOVING" if actual_speed > MIN_MOVEMENT_STEP else "STOPPED"
                vehicle.wait_time = vehicle.wait_time + dt if vehicle.state == "STOPPED" else 0.0

                if next_distance >= lane.path.length - MIN_MOVEMENT_STEP:
                    self.processed_vehicles += 1
                    self._vehicles_processed_last_tick += 1
                    self._vehicles_processed_by_approach_last_tick[lane.direction] += 1
                else:
                    survivors.append(vehicle)
                    leader_distance = next_distance
                    leader_length = vehicle.length
                    leader_speed = actual_speed

        self.vehicles = survivors

    def update_pedestrians(self, dt: float) -> None:
        if dt <= 0.0:
            return

        self._pedestrian_spawn_timer -= dt
        while self._pedestrian_spawn_timer <= 0.0 and len(self.pedestrians) < self.config.max_pedestrians:
            self._spawn_pedestrian()

        remaining_green = self.signal_controller.phase_time_remaining()
        survivors: List[PedestrianStateModel] = []

        for pedestrian in self.pedestrians:
            total_distance = max(_distance(pedestrian.start_position, pedestrian.target_position), 1e-6)
            crossing_time = total_distance / max(pedestrian.speed, 1e-6)

            if pedestrian.state == "WAITING":
                pedestrian.velocity_x = 0.0
                pedestrian.velocity_y = 0.0
                if self.signal_controller.pedestrians_can_cross(pedestrian.crossing) and remaining_green >= crossing_time + 0.15:
                    pedestrian.state = "CROSSING"
                    pedestrian.wait_time = 0.0
                else:
                    pedestrian.wait_time += dt
                    survivors.append(pedestrian)
                    continue

            direction = _normalize(
                pedestrian.target_position.x - pedestrian.position.x,
                pedestrian.target_position.y - pedestrian.position.y,
            )
            remaining_distance = _distance(pedestrian.position, pedestrian.target_position)
            if remaining_distance <= PEDESTRIAN_SNAP_DISTANCE:
                continue

            travel = min(pedestrian.speed * dt, remaining_distance)
            pedestrian.position = Point2D(
                x=pedestrian.position.x + (direction.x * travel),
                y=pedestrian.position.y + (direction.y * travel),
            )
            after_move = _distance(pedestrian.position, pedestrian.target_position)
            if after_move <= PEDESTRIAN_SNAP_DISTANCE:
                continue

            pedestrian.progress = 1.0 - (after_move / total_distance)
            pedestrian.velocity_x = direction.x * (travel / dt)
            pedestrian.velocity_y = direction.y * (travel / dt)
            pedestrian.look_angle = math.atan2(direction.x, direction.y)
            pedestrian.wait_time = 0.0
            survivors.append(pedestrian)

        self.pedestrians = survivors

    def compute_metrics(self, dt: float) -> None:
        active_vehicles = len(self.vehicles)
        queued_vehicles = sum(1 for vehicle in self.vehicles if vehicle.state == "STOPPED")
        active_pedestrians = len(self.pedestrians)
        crossing_pedestrians = sum(1 for pedestrian in self.pedestrians if pedestrian.state == "CROSSING")
        emergency_vehicles = sum(1 for vehicle in self.vehicles if vehicle.has_siren or vehicle.kind != "car")
        avg_wait_time = sum(vehicle.wait_time for vehicle in self.vehicles) / active_vehicles if active_vehicles else 0.0
        throughput_now = self._vehicles_processed_last_tick / max(dt, FRAME_DT) if dt > 0.0 else 0.0
        self.smoothed_throughput = throughput_now if self.frame <= 1 else _lerp(self.smoothed_throughput, throughput_now, 0.18)
        queue_pressure = (queued_vehicles / active_vehicles) if active_vehicles else 0.0
        self.metrics = MetricsView(
            avg_wait_time=round(avg_wait_time, 3),
            throughput=round(self.smoothed_throughput, 3),
            vehicles_processed=self.processed_vehicles,
            queue_pressure=round(queue_pressure, 3),
            active_vehicles=active_vehicles,
            active_pedestrians=active_pedestrians,
            queued_vehicles=queued_vehicles,
            emergency_vehicles=emergency_vehicles,
            active_nodes=12,
            detections=queued_vehicles + crossing_pedestrians,
            bandwidth_savings=round(12.0 + (queue_pressure * 18.0), 2),
        )

    def _log(self, level: str, message: str) -> None:
        self.events.appendleft(EventView(timestamp=round(self.time, 3), level=level, message=message))
