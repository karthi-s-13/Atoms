from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, List, Protocol

from simulation_engine.traffic_brain import (
    TrafficBrain,
    VehicleTelemetryInput,
)
from shared.contracts import (
    Approach,
    ControllerPhase,
    CrosswalkView,
    EmergencyPriorityView,
    EventView,
    LaneArcView,
    LaneKind,
    LaneMovement,
    LaneType,
    LaneView,
    MetricsView,
    Point2D,
    RouteType,
    SignalCycleState,
    SignalState,
    SimulationConfig,
    SnapshotView,
    SubPathSide,
    VehicleIntent,
    VehicleKind,
    VehicleView,
    default_route_distribution,
)

FRAME_DT = 0.016

GREEN = "GREEN"
RED = "RED"

PHASE_GREEN: ControllerPhase = "PHASE_GREEN"
PHASE_YELLOW: ControllerPhase = "PHASE_YELLOW"
PHASE_ALL_RED: ControllerPhase = "PHASE_ALL_RED"

NORTH: SignalCycleState = "NORTH"
EAST: SignalCycleState = "EAST"
SOUTH: SignalCycleState = "SOUTH"
WEST: SignalCycleState = "WEST"
SIGNAL_ORDER: tuple[SignalCycleState, ...] = (NORTH, EAST, SOUTH, WEST)
PHASE_SEQUENCE: tuple[SignalCycleState, ...] = SIGNAL_ORDER

GREEN_INTERVAL = 7.0
ADAPTIVE_MIN_GREEN = 5.0
ADAPTIVE_MAX_GREEN = 25.0
ADAPTIVE_BASE_GREEN = 5.0
ADAPTIVE_GREEN_QUEUE_DURATION_SCALE = 1.7
ADAPTIVE_DURATION_SMOOTHING = 0.6
ADAPTIVE_SWITCH_MARGIN = 2.4
ADAPTIVE_STABILITY_WINDOW = 0.25
ADAPTIVE_EMERGENCY_DURATION_BONUS = 1.25
EMERGENCY_PREEMPT_MIN_GREEN = 2.2
EMERGENCY_ACTIVE_MIN_GREEN = 7.0
EMERGENCY_PREEMPT_ETA_THRESHOLD = 8.0
EMERGENCY_PRIORITY_FORCE_THRESHOLD = 6.0
EMERGENCY_CRITICAL_ETA_THRESHOLD = 2.5
EMERGENCY_CRITICAL_PRIORITY_THRESHOLD = 12.0
EMERGENCY_CRITICAL_VEHICLE_COUNT = 3
EMERGENCY_RELIEF_UNSERVED_TIME = 10.0
EMERGENCY_MAX_CONTINUOUS_GREEN = 12.0
EMERGENCY_RELIEF_LOCK_MIN_GREEN = ADAPTIVE_MIN_GREEN
STARVATION_GRACE_PERIOD = 8.0
STARVATION_FORCE_SWITCH_TIME = 18.0
LEFT_TURN_PROBABILITY = 0.18
RIGHT_INTENT_PROBABILITY = 0.16
EMERGENCY_STRAIGHT_BIAS = 0.82
STARVATION_SCALE = 1.0

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
PATH_ENTRY_OFFSET = ROAD_EXTENT
PATH_EXIT_OFFSET = ROAD_EXTENT
INTERSECTION_CLEAR_MARGIN = 1.2

VEHICLE_MIN_LENGTH = 4.2
VEHICLE_MAX_LENGTH = 4.8
VEHICLE_MIN_WIDTH = 1.85
VEHICLE_MAX_WIDTH = 2.1
STRAIGHT_SPEED_MIN = 8.8
STRAIGHT_SPEED_MAX = 10.6
LEFT_SPEED_MIN = 6.8
LEFT_SPEED_MAX = 7.8
ACCELERATION = 8.0
BRAKE_RATE = 16.0
MIN_FOLLOW_BUFFER = 0.35
DESIRED_FOLLOW_BUFFER = 5.0
STOP_LINE_BUFFER = 0.25
MIN_MOVEMENT_STEP = 1e-3
OBJECT_AWARENESS_HORIZON_SECONDS = 2.6
OBJECT_AWARENESS_SAMPLE_STEP = 1.2
OBJECT_AWARENESS_BUFFER = 0.8
AWARENESS_REACTION_BUFFER = 1.2
MIN_AWARENESS_SPEED = 1.0
MIN_LEFT_TURN_RADIUS = 2.8
LEFT_TURN_RADIUS = max(MIN_LEFT_TURN_RADIUS, CROSSWALK_OUTER_OFFSET - OUTER_LANE_OFFSET - 0.15)
MIN_RIGHT_TURN_RADIUS = 4.2
RIGHT_TURN_RADIUS = max(MIN_RIGHT_TURN_RADIUS, CROSSWALK_OUTER_OFFSET - INNER_LANE_OFFSET - 0.45)
SUB_PATH_OFFSET = min(0.5, LANE_WIDTH / 7.0)
SUB_PATH_SAMPLE_STEP = 10.0
DEADLOCK_UNBLOCK_TIME = 4.5
DEADLOCK_CREEP_SPEED = 1.35
STRAIGHT_INTERSECTION_CAPACITY = 2
TURN_INTERSECTION_CAPACITY = 1
DEFAULT_MAX_VEHICLES = 28
DEFAULT_MAX_EMERGENCY_VEHICLES = 3
MIN_SPAWN_RATE_MULTIPLIER = 0.35
MAX_SPAWN_RATE_MULTIPLIER = 2.5
DETERMINISTIC_RANDOM_SEED = 13

ROUTE_SPAWN_ORDER: tuple[tuple[str, Approach, VehicleIntent], ...] = (
    ("NORTH->SOUTH", "NORTH", "STRAIGHT"),
    ("NORTH->EAST", "NORTH", "LEFT"),
    ("NORTH->WEST", "NORTH", "RIGHT"),
    ("EAST->WEST", "EAST", "STRAIGHT"),
    ("EAST->SOUTH", "EAST", "LEFT"),
    ("EAST->NORTH", "EAST", "RIGHT"),
    ("SOUTH->NORTH", "SOUTH", "STRAIGHT"),
    ("SOUTH->WEST", "SOUTH", "LEFT"),
    ("SOUTH->EAST", "SOUTH", "RIGHT"),
    ("WEST->EAST", "WEST", "STRAIGHT"),
    ("WEST->NORTH", "WEST", "LEFT"),
    ("WEST->SOUTH", "WEST", "RIGHT"),
)

VEHICLE_COLOR_POOL = ("#3b82f6", "#ef4444", "#facc15", "#22c55e", "#f8fafc")
VEHICLE_APPROACHES: tuple[Approach, ...] = ("NORTH", "EAST", "SOUTH", "WEST")
EMERGENCY_KIND_POOL: tuple[VehicleKind, ...] = ("ambulance", "firetruck", "police")
LANE_SLOT_INDEX: dict[str, int] = {"outer": 0, "inner": 1}
INCOMING_LANE_TYPE: LaneType = "INCOMING"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _lerp(a: float, b: float, t: float) -> float:
    return a + ((b - a) * t)


def _distance(a: Point2D, b: Point2D) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def _normalize(dx: float, dy: float) -> Point2D:
    magnitude = math.hypot(dx, dy) or 1.0
    return Point2D(dx / magnitude, dy / magnitude)


def _left_normal(direction: Point2D) -> Point2D:
    return Point2D(-direction.y, direction.x)


def _right_normal(direction: Point2D) -> Point2D:
    return Point2D(direction.y, -direction.x)


def _lane_perpendicular(direction: Point2D) -> Point2D:
    return _right_normal(direction)


def _offset_point(point: Point2D, direction: Point2D, distance: float) -> Point2D:
    return Point2D(
        x=point.x + (direction.x * distance),
        y=point.y + (direction.y * distance),
    )


def _line_intersection(origin_a: Point2D, direction_a: Point2D, origin_b: Point2D, direction_b: Point2D) -> Point2D:
    determinant = (direction_a.x * direction_b.y) - (direction_a.y * direction_b.x)
    if abs(determinant) <= 1e-6:
        raise ValueError("Cannot intersect parallel lane tangents.")
    delta_x = origin_b.x - origin_a.x
    delta_y = origin_b.y - origin_a.y
    t = ((delta_x * direction_b.y) - (delta_y * direction_b.x)) / determinant
    return Point2D(
        x=origin_a.x + (direction_a.x * t),
        y=origin_a.y + (direction_a.y * t),
    )


def _move_toward(current: float, target: float, max_delta: float) -> float:
    if current < target:
        return min(current + max_delta, target)
    return max(current - max_delta, target)


def _lane_index_value(lane_slot: str) -> int:
    return LANE_SLOT_INDEX.get(lane_slot, 0)


def _route_for_intent(intent: VehicleIntent) -> RouteType:
    if intent == "LEFT":
        return "left"
    if intent == "RIGHT":
        return "right"
    return "straight"


def _intent_for_route_value(route: str) -> VehicleIntent:
    normalized = str(route).strip().lower()
    if normalized == "left":
        return "LEFT"
    if normalized == "right":
        return "RIGHT"
    return "STRAIGHT"


def _sub_path_side_for_intent(intent: VehicleIntent) -> SubPathSide:
    return "LEFT" if intent == "LEFT" else "RIGHT"


def _default_config() -> SimulationConfig:
    return SimulationConfig(
        ai_mode="fixed",
        max_vehicles=DEFAULT_MAX_VEHICLES,
        max_emergency_vehicles=DEFAULT_MAX_EMERGENCY_VEHICLES,
        route_distribution=default_route_distribution(),
    )


def _route_distribution_key(approach: Approach, intent: VehicleIntent) -> str:
    if intent == "LEFT":
        exit_direction = _left_turn_exit(approach)
    elif intent == "RIGHT":
        exit_direction = _right_turn_exit(approach)
    else:
        exit_direction = _opposite_approach(approach)
    return f"{approach}->{exit_direction}"


def _normalize_route_distribution(values: Dict[str, object] | None) -> Dict[str, float]:
    normalized = default_route_distribution()
    if not isinstance(values, dict):
        return normalized
    for key, _, _ in ROUTE_SPAWN_ORDER:
        candidate = values.get(key)
        if candidate is None:
            continue
        try:
            normalized[key] = float(max(0, round(float(candidate))))
        except (TypeError, ValueError):
            continue
    return normalized


def _sample_path_distances(path: LanePath) -> List[float]:
    sample_count = max(2, int(math.ceil(path.length / SUB_PATH_SAMPLE_STEP)) + 1)
    return [
        path.length * (index / max(1, sample_count - 1))
        for index in range(sample_count)
    ]


def _point_in_intersection(point: Point2D) -> bool:
    return abs(point.x) <= INTERSECTION_HALF_SIZE and abs(point.y) <= INTERSECTION_HALF_SIZE


def _intersection_window(path: LanePath) -> tuple[float, float]:
    sample_count = max(2, int(math.ceil(path.length / 0.25)) + 1)
    inside_distances = [
        path.length * (index / max(1, sample_count - 1))
        for index in range(sample_count)
        if _point_in_intersection(path.point_at_distance(path.length * (index / max(1, sample_count - 1))))
    ]
    if not inside_distances:
        return path.length, path.length
    return inside_distances[0], inside_distances[-1]


def _angle_span(start_angle: float, end_angle: float, *, clockwise: bool) -> float:
    if clockwise:
        span = (start_angle - end_angle) % math.tau
    else:
        span = (end_angle - start_angle) % math.tau
    return span if span > 1e-6 else math.tau


def _opposite_approach(approach: Approach) -> Approach:
    return {
        "NORTH": "SOUTH",
        "SOUTH": "NORTH",
        "EAST": "WEST",
        "WEST": "EAST",
    }[approach]


def _left_turn_exit(approach: Approach) -> Approach:
    return {
        "NORTH": "EAST",
        "EAST": "SOUTH",
        "SOUTH": "WEST",
        "WEST": "NORTH",
    }[approach]


def _right_turn_exit(approach: Approach) -> Approach:
    return {
        "NORTH": "WEST",
        "EAST": "NORTH",
        "SOUTH": "EAST",
        "WEST": "SOUTH",
    }[approach]


def _exit_direction_for_movement(approach: Approach, route: RouteType) -> Approach:
    if route == "left":
        return _left_turn_exit(approach)
    if route == "right":
        return _right_turn_exit(approach)
    return _opposite_approach(approach)


def _phase_anchor(direction: SignalCycleState) -> SignalCycleState:
    return direction


def _phase_approaches(direction: SignalCycleState) -> tuple[Approach, ...]:
    return (direction,)


def _phase_serves_approach(direction: SignalCycleState, approach: Approach) -> bool:
    return approach in _phase_approaches(direction)


def _phase_label(direction: SignalCycleState) -> str:
    return direction.lower()


def _approach_travel_direction(approach: Approach) -> Point2D:
    return {
        "NORTH": Point2D(0.0, -1.0),
        "EAST": Point2D(-1.0, 0.0),
        "SOUTH": Point2D(0.0, 1.0),
        "WEST": Point2D(1.0, 0.0),
    }[approach]


def _lane_center_anchor(direction: Point2D, lane_offset: float) -> Point2D:
    return _offset_point(Point2D(0.0, 0.0), _left_normal(direction), lane_offset)


class LanePath(Protocol):
    points: tuple[Point2D, ...]
    length: float

    def point_at_distance(self, distance_along: float) -> Point2D:
        ...

    def point_at(self, t: float) -> Point2D:
        ...

    def tangent_at_distance(self, distance_along: float) -> Point2D:
        ...

    def tangent_at(self, t: float) -> Point2D:
        ...


@dataclass(frozen=True)
class CircularArc:
    center: Point2D
    radius: float
    start_angle: float
    end_angle: float
    clockwise: bool

    @classmethod
    def from_center(
        cls,
        center: Point2D,
        start: Point2D,
        end: Point2D,
        *,
        clockwise: bool,
    ) -> "CircularArc":
        radius = _distance(center, start)
        if abs(radius - _distance(center, end)) > 1e-6:
            raise ValueError("Arc endpoints must lie on the same circle.")
        return cls(
            center=center,
            radius=max(radius, 1e-6),
            start_angle=math.atan2(start.y - center.y, start.x - center.x),
            end_angle=math.atan2(end.y - center.y, end.x - center.x),
            clockwise=clockwise,
        )

    @property
    def angle_span(self) -> float:
        return _angle_span(self.start_angle, self.end_angle, clockwise=self.clockwise)

    @property
    def length(self) -> float:
        return self.radius * self.angle_span

    def angle_at_distance(self, distance_along: float) -> float:
        travelled = min(_clamp(distance_along, 0.0, self.length) / self.radius, self.angle_span)
        direction = -1.0 if self.clockwise else 1.0
        return self.start_angle + (direction * travelled)

    def point_at_distance(self, distance_along: float) -> Point2D:
        angle = self.angle_at_distance(distance_along)
        return Point2D(
            x=self.center.x + (self.radius * math.cos(angle)),
            y=self.center.y + (self.radius * math.sin(angle)),
        )

    def heading_at_distance(self, distance_along: float) -> float:
        angle = self.angle_at_distance(distance_along)
        offset = math.pi if self.clockwise else 0.0
        heading = -angle + offset
        return math.atan2(math.sin(heading), math.cos(heading))

    def tangent_at_distance(self, distance_along: float) -> Point2D:
        angle = self.angle_at_distance(distance_along)
        if self.clockwise:
            return Point2D(math.sin(angle), -math.cos(angle))
        return Point2D(-math.sin(angle), math.cos(angle))

    def to_view(self) -> LaneArcView:
        return LaneArcView(
            center=self.center,
            radius=round(self.radius, 6),
            inner_radius=round(max(0.0, self.radius - (LANE_WIDTH / 2.0)), 6),
            outer_radius=round(self.radius + (LANE_WIDTH / 2.0), 6),
            start_angle=round(self.start_angle, 6),
            end_angle=round(self.end_angle, 6),
            clockwise=self.clockwise,
        )


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
class TurnArcPath:
    points: tuple[Point2D, ...]
    arc: CircularArc
    entry_length: float
    exit_length: float
    length: float

    @classmethod
    def from_points(
        cls,
        entry_start: Point2D,
        turn_entry: Point2D,
        arc: CircularArc,
        turn_exit: Point2D,
        exit_end: Point2D,
    ) -> "TurnArcPath":
        entry_length = _distance(entry_start, turn_entry)
        exit_length = _distance(turn_exit, exit_end)
        total_length = max(entry_length + arc.length + exit_length, 1e-6)
        return cls(
            points=(entry_start, turn_entry, turn_exit, exit_end),
            arc=arc,
            entry_length=entry_length,
            exit_length=exit_length,
            length=total_length,
        )

    def point_at_distance(self, distance_along: float) -> Point2D:
        target = _clamp(distance_along, 0.0, self.length)
        entry_start, turn_entry, turn_exit, exit_end = self.points
        if self.entry_length > 1e-6 and target <= self.entry_length:
            ratio = target / self.entry_length
            return Point2D(
                x=_lerp(entry_start.x, turn_entry.x, ratio),
                y=_lerp(entry_start.y, turn_entry.y, ratio),
            )

        arc_distance = target - self.entry_length
        if arc_distance <= self.arc.length or self.exit_length <= 1e-6:
            return self.arc.point_at_distance(max(0.0, arc_distance))

        ratio = min((arc_distance - self.arc.length) / self.exit_length, 1.0)
        return Point2D(
            x=_lerp(turn_exit.x, exit_end.x, ratio),
            y=_lerp(turn_exit.y, exit_end.y, ratio),
        )

    def point_at(self, t: float) -> Point2D:
        return self.point_at_distance(self.length * _clamp(t, 0.0, 1.0))

    def tangent_at_distance(self, distance_along: float) -> Point2D:
        target = _clamp(distance_along, 0.0, self.length)
        entry_start, turn_entry, turn_exit, exit_end = self.points
        if self.entry_length > 1e-6 and target <= self.entry_length:
            return _normalize(turn_entry.x - entry_start.x, turn_entry.y - entry_start.y)

        arc_distance = target - self.entry_length
        if arc_distance <= self.arc.length or self.exit_length <= 1e-6:
            return self.arc.tangent_at_distance(max(0.0, arc_distance))

        return _normalize(exit_end.x - turn_exit.x, exit_end.y - turn_exit.y)

    def tangent_at(self, t: float) -> Point2D:
        return self.tangent_at_distance(self.length * _clamp(t, 0.0, 1.0))


def _offset_sub_path_point(position: Point2D, tangent: Point2D, sub_path_side: SubPathSide) -> Point2D:
    perpendicular = _lane_perpendicular(tangent)
    offset_distance = -SUB_PATH_OFFSET if sub_path_side == "LEFT" else SUB_PATH_OFFSET
    return _offset_point(position, perpendicular, offset_distance)


def _sample_sub_path_points(path: LanePath, sub_path_side: SubPathSide) -> List[Point2D]:
    return [
        _offset_sub_path_point(
            path.point_at_distance(distance_along),
            path.tangent_at_distance(distance_along),
            sub_path_side,
        )
        for distance_along in _sample_path_distances(path)
    ]


@dataclass(frozen=True)
class LaneDefinition:
    id: str
    kind: LaneKind
    shared_lane_id: str
    direction: Approach
    lane_index: str
    movement: LaneMovement
    movement_id: str
    path: LanePath
    stop_line_position: Point2D
    stop_distance: float
    stop_crosswalk_id: str
    crosswalk_start: Point2D
    intersection_entry_distance: float
    intersection_exit_distance: float
    arc: LaneArcView | None = None
    turn_entry: Point2D | None = None
    turn_exit: Point2D | None = None

    def to_view(self) -> LaneView:
        return LaneView(
            id=self.id,
            kind=self.kind,
            approach=self.direction,
            direction=self.direction,
            lane_type=INCOMING_LANE_TYPE,
            lane_index=_lane_index_value(self.lane_index),
            lane_slot=self.lane_index,
            movement=self.movement,
            start=self.path.points[0],
            end=self.path.points[-1],
            path=list(self.path.points),
            crosswalk_id=self.stop_crosswalk_id,
            stop_line_position=self.stop_line_position,
            crosswalk_start=self.crosswalk_start,
            left_sub_path=_sample_sub_path_points(self.path, "LEFT"),
            right_sub_path=_sample_sub_path_points(self.path, "RIGHT"),
            arc=self.arc,
            turn_entry=self.turn_entry,
            turn_exit=self.turn_exit,
        )


@dataclass
class VehicleStateModel:
    id: str
    lane_id: str
    origin_direction: Approach
    route: RouteType
    intent: VehicleIntent
    sub_path_side: SubPathSide
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
    arc_angle: float | None = None
    arc_radius: float | None = None
    arc_center: Point2D | None = None


@dataclass
class CompletedVehicleTransfer:
    id: str
    source_approach: Approach
    exit_direction: Approach
    route: RouteType
    intent: VehicleIntent
    kind: VehicleKind
    has_siren: bool
    priority: int
    color: str
    length: float
    width: float
    cruise_speed: float


class SignalController:
    """Single-green controller that serves one incoming approach at a time."""

    def __init__(self) -> None:
        self.current_green_direction: SignalCycleState = NORTH
        self.elapsed = 0.0
        self.green_duration = GREEN_INTERVAL
        self.continuous_green_time = 0.0
        self.phase_duration_memory: Dict[SignalCycleState, float] = {
            direction: GREEN_INTERVAL for direction in SIGNAL_ORDER
        }
        self.unserved_demand_time: Dict[SignalCycleState, float] = {direction: 0.0 for direction in SIGNAL_ORDER}
        self.emergency_relief_lock_direction: SignalCycleState | None = None

    @property
    def state(self) -> SignalCycleState:
        return self.current_green_direction

    def stage_duration(self) -> float:
        return self.green_duration

    def phase_timer(self) -> float:
        return self.elapsed

    def phase_time_remaining(self) -> float:
        return max(0.0, self.green_duration - self.elapsed)

    def min_green_remaining(self) -> float:
        return self.phase_time_remaining()

    def controller_phase(self) -> ControllerPhase:
        return PHASE_GREEN

    def active_direction(self) -> Approach:
        return self.state

    def signal_state_for_approach(self, approach: Approach) -> SignalState:
        return GREEN if self.state == approach else RED

    def can_vehicle_move(self, approach: Approach, route: RouteType) -> bool:
        del route
        return self.state == approach

    def _phase_demand(
        self,
        direction: SignalCycleState,
        phase_demands: Dict[SignalCycleState, Dict[str, float]],
    ) -> Dict[str, float]:
        approaches = _phase_approaches(direction)
        wait_samples = [float(phase_demands.get(approach, {}).get("wait_time", 0.0)) for approach in approaches]
        return {
            "queue": sum(float(phase_demands.get(approach, {}).get("queue", 0.0)) for approach in approaches),
            "wait_time": max(wait_samples) if wait_samples else 0.0,
            "arrival_rate": sum(float(phase_demands.get(approach, {}).get("arrival_rate", 0.0)) for approach in approaches),
            "fairness_boost": sum(float(phase_demands.get(approach, {}).get("fairness_boost", 0.0)) for approach in approaches),
            "emergency_boost": max(float(phase_demands.get(approach, {}).get("emergency_boost", 0.0)) for approach in approaches),
            "score": sum(float(phase_demands.get(approach, {}).get("score", 0.0)) for approach in approaches),
        }

    def _phase_score(
        self,
        direction: SignalCycleState,
        phase_scores: Dict[SignalCycleState, float],
    ) -> float:
        return sum(float(phase_scores.get(approach, 0.0)) for approach in _phase_approaches(direction))

    def _phase_has_demand(
        self,
        direction: SignalCycleState,
        phase_has_demand: Dict[SignalCycleState, bool],
    ) -> bool:
        return any(bool(phase_has_demand.get(approach, False)) for approach in _phase_approaches(direction))

    def _phase_unserved_time(self, direction: SignalCycleState) -> float:
        return max(self.unserved_demand_time.get(approach, 0.0) for approach in _phase_approaches(direction))

    def _next_direction_in_sequence(self, direction: SignalCycleState) -> SignalCycleState:
        current_index = SIGNAL_ORDER.index(direction)
        return SIGNAL_ORDER[(current_index + 1) % len(SIGNAL_ORDER)]

    def _sequence_distance(self, start: SignalCycleState, target: SignalCycleState) -> int:
        return (SIGNAL_ORDER.index(target) - SIGNAL_ORDER.index(start)) % len(SIGNAL_ORDER)

    def _hold_current(self, duration: float) -> SignalCycleState | None:
        self.current_green_direction = self.state
        self.green_duration = duration
        self.elapsed = 0.0
        return None

    def _switch_to(self, direction: SignalCycleState, duration: float) -> SignalCycleState | None:
        if direction == self.state:
            self.green_duration = duration
            self.current_green_direction = direction
            return None
        if self.emergency_relief_lock_direction != direction:
            self.emergency_relief_lock_direction = None
        self.current_green_direction = direction
        self.green_duration = duration
        self.elapsed = 0.0
        self.continuous_green_time = 0.0
        return direction

    def _switch_to_emergency_relief(self, direction: SignalCycleState, duration: float) -> SignalCycleState | None:
        self.emergency_relief_lock_direction = direction
        return self._switch_to(direction, duration)

    def _adaptive_duration(
        self,
        direction: SignalCycleState,
        phase_demands: Dict[SignalCycleState, Dict[str, float]],
    ) -> float:
        demand = self._phase_demand(direction, phase_demands)
        queue = float(demand.get("queue", 0.0))
        emergency_boost = float(demand.get("emergency_boost", 0.0))
        raw_hold_time = ADAPTIVE_BASE_GREEN + (queue * ADAPTIVE_GREEN_QUEUE_DURATION_SCALE)
        if emergency_boost > 0.0:
            raw_hold_time += ADAPTIVE_EMERGENCY_DURATION_BONUS
        previous_duration = self.phase_duration_memory.get(direction, GREEN_INTERVAL)
        hold_time = (
            raw_hold_time
            if abs(previous_duration - raw_hold_time) <= 0.5
            else _lerp(previous_duration, raw_hold_time, ADAPTIVE_DURATION_SMOOTHING)
        )
        hold_time = _clamp(hold_time, ADAPTIVE_MIN_GREEN, ADAPTIVE_MAX_GREEN)
        self.phase_duration_memory[direction] = hold_time
        return hold_time

    def _priority_score(
        self,
        direction: SignalCycleState,
        phase_demands: Dict[SignalCycleState, Dict[str, float]],
    ) -> float:
        return float(self._phase_demand(direction, phase_demands).get("score", 0.0))

    def _emergency_is_critical(
        self,
        *,
        emergency_direction: SignalCycleState | None,
        emergency_eta: float,
        emergency_severity: float,
        emergency_vehicle_count: int,
    ) -> bool:
        return emergency_direction is not None and (
            emergency_eta <= EMERGENCY_CRITICAL_ETA_THRESHOLD
            or emergency_severity >= EMERGENCY_CRITICAL_PRIORITY_THRESHOLD
            or emergency_vehicle_count >= EMERGENCY_CRITICAL_VEHICLE_COUNT
        )

    def _best_relief_candidate(
        self,
        current_direction: SignalCycleState,
        phase_has_demand: Dict[SignalCycleState, bool],
        phase_demands: Dict[SignalCycleState, Dict[str, float]],
    ) -> SignalCycleState | None:
        relief_candidates = [
            direction
            for direction in SIGNAL_ORDER
            if direction != current_direction and bool(phase_has_demand.get(direction, False))
        ]
        if not relief_candidates:
            return None
        return max(
            relief_candidates,
            key=lambda direction: (
                self.unserved_demand_time.get(direction, 0.0),
                self._priority_score(direction, phase_demands),
                -self._sequence_distance(current_direction, direction),
            ),
        )

    def _emergency_relief_candidate(
        self,
        *,
        current_direction: SignalCycleState,
        phase_has_demand: Dict[SignalCycleState, bool],
        phase_demands: Dict[SignalCycleState, Dict[str, float]],
        emergency_is_critical: bool,
    ) -> SignalCycleState | None:
        if emergency_is_critical:
            return None
        relief_direction = self._best_relief_candidate(current_direction, phase_has_demand, phase_demands)
        if relief_direction is None:
            return None
        relief_unserved = self.unserved_demand_time.get(relief_direction, 0.0)
        relief_score = self._priority_score(relief_direction, phase_demands)
        current_score = self._priority_score(current_direction, phase_demands)
        if relief_unserved >= EMERGENCY_RELIEF_UNSERVED_TIME:
            return relief_direction
        if self.continuous_green_time >= EMERGENCY_MAX_CONTINUOUS_GREEN and relief_score > 0.0:
            return relief_direction
        if relief_unserved >= STARVATION_GRACE_PERIOD and relief_score > current_score + ADAPTIVE_SWITCH_MARGIN:
            return relief_direction
        return None

    def update(
        self,
        dt: float,
        *,
        intersection_clear: bool,
        ai_mode: str,
        phase_scores: Dict[SignalCycleState, float],
        phase_has_demand: Dict[SignalCycleState, bool],
        phase_demands: Dict[SignalCycleState, Dict[str, float]],
        emergency_priority: EmergencyPriorityView | None = None,
    ) -> SignalCycleState | None:
        del phase_scores
        self.elapsed += dt
        self.continuous_green_time += dt
        if self.emergency_relief_lock_direction is not None and self.emergency_relief_lock_direction != self.state:
            self.emergency_relief_lock_direction = None
        for direction in SIGNAL_ORDER:
            if self.state == direction:
                self.unserved_demand_time[direction] = 0.0
            else:
                self.unserved_demand_time[direction] += dt * STARVATION_SCALE

        if ai_mode != "adaptive":
            self.green_duration = GREEN_INTERVAL
            if self.elapsed < self.green_duration or not intersection_clear:
                return None

            return self._switch_to(
                self._next_direction_in_sequence(self.state),
                GREEN_INTERVAL,
            )

        current_direction = self.state
        current_duration = self._adaptive_duration(current_direction, phase_demands)
        emergency_direction = (
            emergency_priority.preferred_phase
            if emergency_priority is not None and emergency_priority.detected and emergency_priority.preferred_phase in SIGNAL_ORDER
            else None
        )
        emergency_eta = (
            float(emergency_priority.eta_seconds)
            if emergency_priority is not None and emergency_priority.detected
            else float("inf")
        )
        emergency_vehicle_count = (
            max(0, int(getattr(emergency_priority, "vehicle_count", 0)))
            if emergency_priority is not None and emergency_priority.detected
            else 0
        )
        emergency_severity = (
            max(0.0, float(getattr(emergency_priority, "priority_score", 0.0)))
            if emergency_priority is not None and emergency_priority.detected
            else 0.0
        )
        emergency_is_critical = self._emergency_is_critical(
            emergency_direction=emergency_direction,
            emergency_eta=emergency_eta,
            emergency_severity=emergency_severity,
            emergency_vehicle_count=emergency_vehicle_count,
        )
        emergency_on_current = emergency_direction == current_direction
        emergency_preempt_pending = (
            emergency_direction is not None
            and emergency_direction != current_direction
            and (
                emergency_eta <= EMERGENCY_PREEMPT_ETA_THRESHOLD
                or emergency_severity >= EMERGENCY_PRIORITY_FORCE_THRESHOLD
                or emergency_vehicle_count > 1
            )
        )
        emergency_hold_floor = EMERGENCY_ACTIVE_MIN_GREEN + min(
            3.5,
            max(0, emergency_vehicle_count - 1) * 0.9,
        ) + min(2.0, emergency_severity * 0.18)
        current_duration = max(
            current_duration,
            emergency_hold_floor if emergency_on_current else 0.0,
        )
        self.green_duration = current_duration
        relief_lock_active = self.emergency_relief_lock_direction == current_direction
        required_min_green = ADAPTIVE_MIN_GREEN
        if emergency_preempt_pending and (not relief_lock_active or emergency_is_critical):
            required_min_green = EMERGENCY_PREEMPT_MIN_GREEN
        elif relief_lock_active:
            required_min_green = EMERGENCY_RELIEF_LOCK_MIN_GREEN
        if self.elapsed < required_min_green or not intersection_clear:
            return None

        current_has_demand = bool(phase_has_demand.get(current_direction, False))
        current_score = self._priority_score(current_direction, phase_demands) if current_has_demand else 0.0

        if emergency_preempt_pending and emergency_direction is not None:
            emergency_duration = max(
                self._adaptive_duration(emergency_direction, phase_demands),
                emergency_hold_floor,
            )
            return self._switch_to(emergency_direction, emergency_duration)

        if emergency_on_current:
            relief_direction = self._emergency_relief_candidate(
                current_direction=current_direction,
                phase_has_demand=phase_has_demand,
                phase_demands=phase_demands,
                emergency_is_critical=emergency_is_critical,
            )
            if relief_direction is not None and self.elapsed >= EMERGENCY_ACTIVE_MIN_GREEN:
                return self._switch_to_emergency_relief(
                    relief_direction,
                    self._adaptive_duration(relief_direction, phase_demands),
                )
            if self.elapsed < current_duration:
                return None
            return self._hold_current(current_duration)

        demand_candidates = [
            direction
            for direction in SIGNAL_ORDER
            if direction != current_direction and bool(phase_has_demand.get(direction, False))
        ]
        forced_candidates = [
            direction
            for direction in demand_candidates
            if self.unserved_demand_time.get(direction, 0.0) >= STARVATION_FORCE_SWITCH_TIME
        ]
        if forced_candidates:
            forced_direction = min(
                forced_candidates,
                key=lambda direction: (
                    -self.unserved_demand_time.get(direction, 0.0),
                    self._sequence_distance(current_direction, direction),
                    -self._priority_score(direction, phase_demands),
                ),
            )
            return self._switch_to(forced_direction, self._adaptive_duration(forced_direction, phase_demands))

        best_direction = (
            max(
                demand_candidates,
                key=lambda direction: (
                    self._priority_score(direction, phase_demands),
                    self.unserved_demand_time.get(direction, 0.0),
                    -self._sequence_distance(current_direction, direction),
                ),
            )
            if demand_candidates
            else None
        )
        best_score = self._priority_score(best_direction, phase_demands) if best_direction is not None else 0.0

        if current_has_demand and best_direction is not None and best_score > current_score + ADAPTIVE_SWITCH_MARGIN:
            return self._switch_to(best_direction, self._adaptive_duration(best_direction, phase_demands))

        if current_has_demand and self.elapsed < current_duration:
            return None

        if best_direction is not None and (
            not current_has_demand or best_score >= current_score - ADAPTIVE_SWITCH_MARGIN
        ):
            return self._switch_to(best_direction, self._adaptive_duration(best_direction, phase_demands))

        if current_has_demand:
            return self._hold_current(self._adaptive_duration(current_direction, phase_demands))

        if best_direction is not None:
            return self._switch_to(best_direction, self._adaptive_duration(best_direction, phase_demands))

        return self._hold_current(GREEN_INTERVAL)


class TrafficSimulationEngine:
    """Stable single-intersection controller with one active green approach at a time."""

    def __init__(self) -> None:
        self.config = _default_config()
        self.crosswalks = self._build_crosswalks()
        self.lanes: Dict[str, LaneDefinition] = {}
        self.phase_lane_ids: Dict[Approach, tuple[str, ...]] = {}
        self.lane_phase_map: Dict[str, Approach] = {}
        self._rng = random.Random(DETERMINISTIC_RANDOM_SEED)
        self.events: Deque[EventView] = deque(maxlen=40)
        self.traffic_brain = TrafficBrain()
        self.reset()
        self._log("INFO", "Single-green controller initialized with adaptive per-approach routing and protected turn paths.")

    def reset(self, config_override: Dict[str, object] | None = None) -> None:
        self._rng = random.Random(DETERMINISTIC_RANDOM_SEED)
        self.config = _default_config()
        self.signal_controller = SignalController()
        self.network_phase_context: Dict[str, Any] = {}
        self.current_state: SignalCycleState = self.signal_controller.state
        self.frame = 0
        self.time = 0.0
        self.processed_vehicles = 0
        self.smoothed_throughput = 0.0
        self.vehicles: List[VehicleStateModel] = []
        self.metrics = MetricsView(0.0, 0.0, 0, 0.0, 0, 0, 0, 0, 4, 0, 4.0)
        self._vehicle_index = 0
        self._vehicle_spawn_cursor = 0
        self._vehicle_spawn_timer = self._vehicle_spawn_interval()
        self._color_cursor = 0
        self._vehicles_processed_last_tick = 0
        self.completed_vehicle_transfers_last_tick: List[CompletedVehicleTransfer] = []
        self._vehicles_arrived_by_approach_last_tick: Dict[Approach, int] = {
            approach: 0 for approach in SIGNAL_ORDER
        }
        self._vehicles_processed_by_approach_last_tick: Dict[Approach, int] = {
            approach: 0 for approach in SIGNAL_ORDER
        }
        self._vehicles_cleared_current_cycle = 0
        self._vehicles_cleared_last_cycle = 0
        self._completed_signal_cycles = 0
        self.traffic_brain.reset()
        self.phase_scores: Dict[SignalCycleState, float] = {direction: 0.0 for direction in SIGNAL_ORDER}
        self.phase_has_demand: Dict[SignalCycleState, bool] = {direction: False for direction in SIGNAL_ORDER}
        self.phase_demands: Dict[SignalCycleState, Dict[str, float]] = {
            direction: {
                "queue": 0.0,
                "wait_time": 0.0,
                "arrival_rate": 0.0,
                "flow_rate": 0.0,
                "congestion_trend": 0.0,
                "fairness_boost": 0.0,
                "emergency_boost": 0.0,
                "score": 0.0,
            }
            for direction in SIGNAL_ORDER
        }
        self._refresh_lane_geometry()
        if config_override:
            self.update_config(config_override)
            self._vehicle_spawn_timer = self._vehicle_spawn_interval()
        self.events.clear()
        self._refresh_phase_demand_cache(0.0)

    def update_config(self, values: Dict[str, object]) -> SimulationConfig:
        refresh_lanes = False
        if "traffic_intensity" in values:
            self.config.traffic_intensity = _clamp(float(values["traffic_intensity"]), 0.0, 1.0)
            self._vehicle_spawn_timer = min(self._vehicle_spawn_timer, self._vehicle_spawn_interval())
        if "ambulance_frequency" in values:
            self.config.ambulance_frequency = _clamp(float(values["ambulance_frequency"]), 0.0, 1.0)
        if "ai_mode" in values:
            requested_mode = str(values["ai_mode"]).strip().lower()
            if requested_mode in {"fixed", "adaptive"}:
                self.config.ai_mode = requested_mode
        if "speed_multiplier" in values:
            self.config.speed_multiplier = _clamp(float(values["speed_multiplier"]), 0.25, 4.0)
        if "spawn_rate_multiplier" in values:
            self.config.spawn_rate_multiplier = _clamp(
                float(values["spawn_rate_multiplier"]),
                MIN_SPAWN_RATE_MULTIPLIER,
                MAX_SPAWN_RATE_MULTIPLIER,
            )
            self._vehicle_spawn_timer = min(self._vehicle_spawn_timer, self._vehicle_spawn_interval())
        if "safe_gap_multiplier" in values:
            self.config.safe_gap_multiplier = _clamp(float(values["safe_gap_multiplier"]), 0.55, 1.75)
        if "turn_smoothness" in values:
            next_turn_smoothness = _clamp(float(values["turn_smoothness"]), 0.0, 1.0)
            refresh_lanes = refresh_lanes or abs(next_turn_smoothness - self.config.turn_smoothness) > 1e-6
            self.config.turn_smoothness = next_turn_smoothness
        if "max_emergency_vehicles" in values:
            self.config.max_emergency_vehicles = max(0, min(20, int(values["max_emergency_vehicles"])))
        if "paused" in values:
            self.config.paused = bool(values["paused"])
        if "max_vehicles" in values:
            self.config.max_vehicles = max(0, min(80, int(values["max_vehicles"])))
        if "route_distribution" in values:
            self.config.route_distribution = _normalize_route_distribution(values["route_distribution"])
        if refresh_lanes:
            self._refresh_lane_geometry()
        return self.config

    def _refresh_lane_geometry(self) -> None:
        self.lanes = self._build_lanes()
        self.phase_lane_ids = {
            direction: tuple(
                lane_id
                for lane_id, lane in self.lanes.items()
                if lane.direction == direction and lane.kind == "main"
            )
            for direction in SIGNAL_ORDER
        }
        self.lane_phase_map = {
            lane_id: lane.direction for lane_id, lane in self.lanes.items() if lane.kind == "main"
        }
        for vehicle in self.vehicles:
            lane = self.lanes.get(vehicle.lane_id)
            if lane is None:
                continue
            self._apply_vehicle_pose(
                vehicle,
                lane,
                min(vehicle.distance_along, lane.path.length),
                speed=vehicle.speed,
            )

    def _turn_radius(self) -> float:
        return _lerp(
            MIN_LEFT_TURN_RADIUS,
            LEFT_TURN_RADIUS,
            _clamp(self.config.turn_smoothness, 0.0, 1.0),
        )

    def _right_turn_radius(self) -> float:
        return _lerp(
            MIN_RIGHT_TURN_RADIUS,
            RIGHT_TURN_RADIUS,
            _clamp(self.config.turn_smoothness, 0.0, 1.0),
        )

    def set_network_phase_context(self, context: Dict[str, Any] | None) -> None:
        self.network_phase_context = dict(context or {})

    def drain_completed_vehicle_transfers(self) -> List[CompletedVehicleTransfer]:
        completed = list(self.completed_vehicle_transfers_last_tick)
        self.completed_vehicle_transfers_last_tick = []
        return completed

    def can_accept_transfer(self, approach: Approach, route: RouteType) -> bool:
        intent = _intent_for_route_value(route)
        lane_ids = self._lane_ids_for_route(approach, _route_for_intent(intent))
        if not lane_ids:
            return False
        return self._lane_has_spawn_room(lane_ids[0], _sub_path_side_for_intent(intent))

    def inject_transferred_vehicle(
        self,
        approach: Approach,
        route: RouteType,
        *,
        vehicle_id: str,
        kind: VehicleKind = "car",
        has_siren: bool = False,
        priority: int = 0,
        color: str | None = None,
        length: float | None = None,
        width: float | None = None,
        cruise_speed: float | None = None,
    ) -> bool:
        intent = _intent_for_route_value(route)
        lane_ids = self._lane_ids_for_route(approach, _route_for_intent(intent))
        if not lane_ids:
            return False
        lane_id = lane_ids[0]
        if not self._lane_has_spawn_room(lane_id, _sub_path_side_for_intent(intent)):
            return False

        emergency_kind = kind if kind != "car" or has_siren else None
        vehicle = self._make_vehicle_for_lane(lane_id, emergency_kind=emergency_kind, intent=intent)
        vehicle.id = vehicle_id
        vehicle.kind = kind
        vehicle.has_siren = has_siren
        vehicle.priority = priority
        if color is not None:
            vehicle.color = color
        if length is not None:
            vehicle.length = round(length, 3)
        if width is not None:
            vehicle.width = round(width, 3)
        if cruise_speed is not None:
            vehicle.cruise_speed = round(cruise_speed, 3)

        self.vehicles.append(vehicle)
        self._record_vehicle_arrival(approach)
        self._refresh_phase_demand_cache(0.0)
        self.compute_metrics(0.0)
        return True

    def tick(self, dt: float = FRAME_DT) -> Dict[str, object]:
        sim_dt = max(0.0, float(dt))
        if self.config.paused:
            sim_dt = 0.0
        else:
            sim_dt *= self.config.speed_multiplier

        self.frame += 1
        self._vehicles_processed_last_tick = 0
        self.completed_vehicle_transfers_last_tick = []
        self._vehicles_arrived_by_approach_last_tick = {approach: 0 for approach in SIGNAL_ORDER}
        self._vehicles_processed_by_approach_last_tick = {approach: 0 for approach in SIGNAL_ORDER}
        if sim_dt > 0.0:
            self.time += sim_dt
            self._refresh_phase_demand_cache(0.0)
            self.update_signals(sim_dt)
            self.update_vehicles(sim_dt)
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
            lanes=[lane.to_view() for lane in self.lanes.values()],
            crosswalks=list(self.crosswalks.values()),
            signals=self._signal_snapshot(),
            metrics=self.metrics,
            traffic_brain=self.traffic_brain_state,
            events=list(self.events),
            config=self.config,
        )

    def _build_crosswalks(self) -> Dict[str, CrosswalkView]:
        return {
            "north_crosswalk": CrosswalkView(
                id="north_crosswalk",
                road_direction="NS",
                start=Point2D(-ROAD_SURFACE_HALF_WIDTH, CROSSWALK_CENTER_OFFSET),
                end=Point2D(ROAD_SURFACE_HALF_WIDTH, CROSSWALK_CENTER_OFFSET),
                movement=Point2D(1.0, 0.0),
            ),
            "south_crosswalk": CrosswalkView(
                id="south_crosswalk",
                road_direction="NS",
                start=Point2D(-ROAD_SURFACE_HALF_WIDTH, -CROSSWALK_CENTER_OFFSET),
                end=Point2D(ROAD_SURFACE_HALF_WIDTH, -CROSSWALK_CENTER_OFFSET),
                movement=Point2D(1.0, 0.0),
            ),
            "east_crosswalk": CrosswalkView(
                id="east_crosswalk",
                road_direction="EW",
                start=Point2D(CROSSWALK_CENTER_OFFSET, -ROAD_SURFACE_HALF_WIDTH),
                end=Point2D(CROSSWALK_CENTER_OFFSET, ROAD_SURFACE_HALF_WIDTH),
                movement=Point2D(0.0, 1.0),
            ),
            "west_crosswalk": CrosswalkView(
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
            points: Iterable[Point2D],
            stop_line_position: Point2D,
            crosswalk_id: str,
            crosswalk_start: Point2D,
            *,
            kind: LaneKind = "main",
            shared_lane_id: str | None = None,
        ) -> None:
            path = PolylinePath.from_points(points)
            intersection_entry_distance, intersection_exit_distance = _intersection_window(path)
            lanes[lane_id] = LaneDefinition(
                id=lane_id,
                kind=kind,
                shared_lane_id=shared_lane_id or lane_id,
                direction=approach,
                lane_index=lane_index,
                movement=movement,
                movement_id=f"{approach[0]}_{movement}",
                path=path,
                stop_line_position=stop_line_position,
                stop_distance=_distance(path.points[0], stop_line_position),
                stop_crosswalk_id=crosswalk_id,
                crosswalk_start=crosswalk_start,
                intersection_entry_distance=intersection_entry_distance,
                intersection_exit_distance=intersection_exit_distance,
            )

        add_lane(
            "lane_north_straight",
            "NORTH",
            "inner",
            "STRAIGHT",
            (
                Point2D(INNER_LANE_OFFSET, PATH_ENTRY_OFFSET),
                Point2D(INNER_LANE_OFFSET, -PATH_EXIT_OFFSET),
            ),
            Point2D(INNER_LANE_OFFSET, STOP_OFFSET),
            "north_crosswalk",
            Point2D(INNER_LANE_OFFSET, CROSSWALK_OUTER_OFFSET),
            shared_lane_id="north_inner",
        )
        add_lane(
            "lane_south_straight",
            "SOUTH",
            "inner",
            "STRAIGHT",
            (
                Point2D(-INNER_LANE_OFFSET, -PATH_ENTRY_OFFSET),
                Point2D(-INNER_LANE_OFFSET, PATH_EXIT_OFFSET),
            ),
            Point2D(-INNER_LANE_OFFSET, -STOP_OFFSET),
            "south_crosswalk",
            Point2D(-INNER_LANE_OFFSET, -CROSSWALK_OUTER_OFFSET),
            shared_lane_id="south_inner",
        )
        add_lane(
            "lane_east_straight",
            "EAST",
            "inner",
            "STRAIGHT",
            (
                Point2D(PATH_ENTRY_OFFSET, -INNER_LANE_OFFSET),
                Point2D(-PATH_EXIT_OFFSET, -INNER_LANE_OFFSET),
            ),
            Point2D(STOP_OFFSET, -INNER_LANE_OFFSET),
            "east_crosswalk",
            Point2D(CROSSWALK_OUTER_OFFSET, -INNER_LANE_OFFSET),
            shared_lane_id="east_inner",
        )
        add_lane(
            "lane_west_straight",
            "WEST",
            "inner",
            "STRAIGHT",
            (
                Point2D(-PATH_ENTRY_OFFSET, INNER_LANE_OFFSET),
                Point2D(PATH_EXIT_OFFSET, INNER_LANE_OFFSET),
            ),
            Point2D(-STOP_OFFSET, INNER_LANE_OFFSET),
            "west_crosswalk",
            Point2D(-CROSSWALK_OUTER_OFFSET, INNER_LANE_OFFSET),
            shared_lane_id="west_inner",
        )

        def add_arc_lane(
            lane_id: str,
            approach: Approach,
            lane_index: str,
            movement: LaneMovement,
            entry_start: Point2D,
            stop_line_position: Point2D,
            turn_entry: Point2D,
            arc_center: Point2D,
            turn_exit: Point2D,
            exit_end: Point2D,
            crosswalk_id: str,
            crosswalk_start: Point2D,
            *,
            kind: LaneKind = "main",
            arc_clockwise: bool = True,
            shared_lane_id: str | None = None,
        ) -> None:
            arc = CircularArc.from_center(
                arc_center,
                turn_entry,
                turn_exit,
                clockwise=arc_clockwise,
            )
            path = TurnArcPath.from_points(
                entry_start,
                turn_entry,
                arc,
                turn_exit,
                exit_end,
            )
            intersection_entry_distance, intersection_exit_distance = _intersection_window(path)
            lanes[lane_id] = LaneDefinition(
                id=lane_id,
                kind=kind,
                shared_lane_id=shared_lane_id or lane_id,
                direction=approach,
                lane_index=lane_index,
                movement=movement,
                movement_id=f"{approach[0]}_{movement}",
                path=path,
                stop_line_position=stop_line_position,
                stop_distance=_distance(path.points[0], stop_line_position),
                stop_crosswalk_id=crosswalk_id,
                crosswalk_start=crosswalk_start,
                intersection_entry_distance=intersection_entry_distance,
                intersection_exit_distance=intersection_exit_distance,
                arc=arc.to_view(),
                turn_entry=turn_entry,
                turn_exit=turn_exit,
            )

        def add_turn_lane(
            lane_id: str,
            approach: Approach,
            lane_index: str,
            movement: LaneMovement,
            *,
            outgoing_direction: Point2D,
            lane_offset: float,
            turn_radius: float,
            arc_clockwise: bool,
            shared_lane_id: str,
        ) -> None:
            incoming_direction = _approach_travel_direction(approach)
            incoming_anchor = _lane_center_anchor(incoming_direction, lane_offset)
            outgoing_anchor = _lane_center_anchor(outgoing_direction, lane_offset)
            curve_normal = _right_normal if arc_clockwise else _left_normal
            turn_center = _line_intersection(
                _offset_point(incoming_anchor, curve_normal(incoming_direction), turn_radius),
                incoming_direction,
                _offset_point(outgoing_anchor, curve_normal(outgoing_direction), turn_radius),
                outgoing_direction,
            )
            turn_entry = _offset_point(turn_center, curve_normal(incoming_direction), -turn_radius)
            turn_exit = _offset_point(turn_center, curve_normal(outgoing_direction), -turn_radius)
            entry_start = _offset_point(incoming_anchor, incoming_direction, -PATH_ENTRY_OFFSET)
            stop_line_position = _offset_point(incoming_anchor, incoming_direction, -STOP_OFFSET)
            crosswalk_start = _offset_point(incoming_anchor, incoming_direction, -CROSSWALK_OUTER_OFFSET)
            exit_end = _offset_point(outgoing_anchor, outgoing_direction, PATH_EXIT_OFFSET)

            add_arc_lane(
                lane_id,
                approach,
                lane_index,
                movement,
                entry_start,
                stop_line_position,
                turn_entry,
                turn_center,
                turn_exit,
                exit_end,
                f"{approach.lower()}_crosswalk",
                crosswalk_start,
                arc_clockwise=arc_clockwise,
                shared_lane_id=shared_lane_id,
            )

        def add_left_turn_lane(approach: Approach) -> None:
            incoming_direction = _approach_travel_direction(approach)
            add_turn_lane(
                f"lane_{approach.lower()}_left",
                approach,
                "outer",
                "LEFT",
                outgoing_direction=_left_normal(incoming_direction),
                lane_offset=OUTER_LANE_OFFSET,
                turn_radius=self._turn_radius(),
                arc_clockwise=False,
                shared_lane_id=f"{approach.lower()}_outer",
            )

        def add_right_turn_lane(approach: Approach) -> None:
            incoming_direction = _approach_travel_direction(approach)
            add_turn_lane(
                f"lane_{approach.lower()}_right",
                approach,
                "inner",
                "RIGHT",
                outgoing_direction=_right_normal(incoming_direction),
                lane_offset=INNER_LANE_OFFSET,
                turn_radius=self._right_turn_radius(),
                arc_clockwise=True,
                shared_lane_id=f"{approach.lower()}_inner",
            )

        for approach in SIGNAL_ORDER:
            add_right_turn_lane(approach)
            add_left_turn_lane(approach)
        return lanes

    def _vehicle_spawn_interval(self) -> float:
        intensity = _clamp(self.config.traffic_intensity, 0.0, 1.0)
        base_interval = 2.7 - (1.75 * intensity)
        active_vehicles = len(self.vehicles)
        cap = max(1, self.config.max_vehicles)
        density = active_vehicles / cap
        queued_vehicles = sum(1 for vehicle in self.vehicles if vehicle.state == "STOPPED")
        queue_pressure = (queued_vehicles / active_vehicles) if active_vehicles else 0.0
        congestion_factor = 1.0 + (density * 0.9) + (queue_pressure * 1.4)
        if density < 0.35 and queue_pressure < 0.2:
            congestion_factor *= 0.78
        interval = (base_interval * congestion_factor) / max(self.config.spawn_rate_multiplier, 1e-6)
        return _clamp(interval, 0.35, 4.8)

    def _spawn_follow_buffer(self) -> float:
        return (DESIRED_FOLLOW_BUFFER * self.config.safe_gap_multiplier) + 2.0

    def _record_vehicle_arrival(self, approach: Approach) -> None:
        self._vehicles_arrived_by_approach_last_tick[approach] = (
            self._vehicles_arrived_by_approach_last_tick.get(approach, 0) + 1
        )

    def _lane_ids_for_route(self, approach: Approach, route: RouteType) -> List[str]:
        movement = {"straight": "STRAIGHT", "left": "LEFT", "right": "RIGHT"}.get(route)
        if movement is None:
            return []
        lane_ids = [
            lane_id
            for lane_id, lane in self.lanes.items()
            if lane.direction == approach and lane.movement == movement
        ]
        return sorted(lane_ids)

    def _choose_emergency_kind(self) -> VehicleKind:
        return EMERGENCY_KIND_POOL[self._rng.randrange(len(EMERGENCY_KIND_POOL))]

    def _current_emergency_vehicle_count(self) -> int:
        return sum(1 for vehicle in self.vehicles if vehicle.kind != "car" or vehicle.has_siren)

    def _spawn_candidates(self) -> List[tuple[float, str, Approach, VehicleIntent, str]]:
        shared_lane_loads = {
            shared_lane_id: sum(
                1
                for vehicle in self.vehicles
                if self.lanes[vehicle.lane_id].shared_lane_id == shared_lane_id
            )
            for shared_lane_id in {lane.shared_lane_id for lane in self.lanes.values()}
        }
        direction_loads = {
            approach: sum(1 for vehicle in self.vehicles if vehicle.origin_direction == approach)
            for approach in SIGNAL_ORDER
        }
        distribution = self.config.route_distribution or default_route_distribution()
        candidates: List[tuple[float, str, Approach, VehicleIntent, str]] = []
        for route_key, approach, intent in ROUTE_SPAWN_ORDER:
            base_weight = max(0.0, float(distribution.get(route_key, 0.0)))
            if base_weight <= 0.0:
                continue
            lane_ids = self._lane_ids_for_route(approach, _route_for_intent(intent))
            if not lane_ids:
                continue
            lane_id = lane_ids[0]
            shared_lane_id = self.lanes[lane_id].shared_lane_id
            load_penalty = 1.0 + (shared_lane_loads.get(shared_lane_id, 0) * 0.75) + (direction_loads.get(approach, 0) * 0.22)
            candidates.append((base_weight / load_penalty, route_key, approach, intent, lane_id))
        return candidates

    def _spawn_vehicle(self) -> None:
        if len(self.vehicles) >= self.config.max_vehicles:
            return

        emergency_room = max(0, self.config.max_emergency_vehicles - self._current_emergency_vehicle_count())
        emergency_target = max(1, self.config.max_emergency_vehicles)
        emergency_spawn = (
            emergency_room > 0
            and self._rng.random()
            < (self.config.ambulance_frequency * _clamp((emergency_room / emergency_target) + 0.25, 0.25, 1.0))
        )

        candidates = self._spawn_candidates()
        while candidates:
            total_weight = sum(candidate[0] for candidate in candidates)
            if total_weight <= 0.0:
                break
            roll = self._rng.random() * total_weight
            running = 0.0
            selected_index = 0
            for index, candidate in enumerate(candidates):
                running += candidate[0]
                if running >= roll:
                    selected_index = index
                    break
            _, route_key, approach, intent, lane_id = candidates.pop(selected_index)
            spawn_intent = "STRAIGHT" if emergency_spawn and self._rng.random() < EMERGENCY_STRAIGHT_BIAS else intent
            if spawn_intent != intent:
                replacement_lane_ids = self._lane_ids_for_route(approach, _route_for_intent(spawn_intent))
                if not replacement_lane_ids:
                    continue
                lane_id = replacement_lane_ids[0]
            sub_path_side = _sub_path_side_for_intent(spawn_intent)
            if self._lane_has_spawn_room(lane_id, sub_path_side):
                emergency_kind = self._choose_emergency_kind() if emergency_spawn else None
                vehicle = self._make_vehicle_for_lane(lane_id, emergency_kind=emergency_kind, intent=spawn_intent)
                self.vehicles.append(vehicle)
                self._record_vehicle_arrival(approach)
                self._vehicle_spawn_timer = self._vehicle_spawn_interval()
                self._log(
                    "INFO",
                    f"Spawned {vehicle.intent.lower()} {vehicle.kind} for {route_key.lower()}.",
                )
                return
        self._vehicle_spawn_timer = 0.35

    def _lane_has_spawn_room(self, lane_id: str, sub_path_side: SubPathSide) -> bool:
        spawn_buffer = self._spawn_follow_buffer()
        lane = self.lanes[lane_id]
        for other in self.vehicles:
            other_lane = self.lanes.get(other.lane_id)
            if (
                other_lane is None
                or other_lane.shared_lane_id != lane.shared_lane_id
                or other.distance_along >= other.length + spawn_buffer
            ):
                continue
            return False
        return True

    def _make_vehicle(self, approach: Approach, route: RouteType) -> VehicleStateModel:
        intent = _intent_for_route_value(route)
        lane_ids = self._lane_ids_for_route(approach, _route_for_intent(intent))
        if not lane_ids:
            raise ValueError(f"No lane path defined for {approach.lower()} {route}.")
        return self._make_vehicle_for_lane(lane_ids[0], intent=intent)

    def _lane_pose_at_distance(
        self,
        lane: LaneDefinition,
        distance_along: float,
    ) -> tuple[Point2D, Point2D, float, float | None, float | None, Point2D | None]:
        clamped_distance = _clamp(distance_along, 0.0, lane.path.length)
        if isinstance(lane.path, TurnArcPath):
            entry_start, turn_entry, turn_exit, exit_end = lane.path.points
            if lane.path.entry_length > 1e-6 and clamped_distance < lane.path.entry_length:
                position = lane.path.point_at_distance(clamped_distance)
                tangent = _normalize(turn_entry.x - entry_start.x, turn_entry.y - entry_start.y)
                heading = math.atan2(tangent.x, tangent.y)
                return position, tangent, heading, None, None, None

            arc_distance = clamped_distance - lane.path.entry_length
            if 0.0 <= arc_distance <= lane.path.arc.length:
                angle = lane.path.arc.angle_at_distance(max(0.0, arc_distance))
                position = Point2D(
                    x=lane.path.arc.center.x + (lane.path.arc.radius * math.cos(angle)),
                    y=lane.path.arc.center.y + (lane.path.arc.radius * math.sin(angle)),
                )
                tangent = lane.path.arc.tangent_at_distance(max(0.0, arc_distance))
                heading = lane.path.arc.heading_at_distance(max(0.0, arc_distance))
                return (
                    position,
                    tangent,
                    heading,
                    angle,
                    lane.path.arc.radius,
                    lane.path.arc.center,
                )

            position = lane.path.point_at_distance(clamped_distance)
            tangent = _normalize(exit_end.x - turn_exit.x, exit_end.y - turn_exit.y)
            heading = math.atan2(tangent.x, tangent.y)
            return position, tangent, heading, None, None, None

        position = lane.path.point_at_distance(clamped_distance)
        tangent = lane.path.tangent_at_distance(clamped_distance)
        heading = math.atan2(tangent.x, tangent.y)
        return position, tangent, heading, None, None, None

    def _distance_limited_speed(self, max_speed: float, remaining_distance: float) -> float:
        if remaining_distance <= MIN_MOVEMENT_STEP:
            return 0.0
        return min(max_speed, math.sqrt(2.0 * BRAKE_RATE * remaining_distance))

    def _sub_path_distance_at(
        self,
        lane: LaneDefinition,
        distance_along: float,
        sub_path_side: SubPathSide,
    ) -> float:
        clamped_distance = _clamp(distance_along, 0.0, lane.path.length)
        if not isinstance(lane.path, TurnArcPath):
            return clamped_distance

        if clamped_distance <= lane.path.entry_length:
            return clamped_distance

        mid_arc_distance = lane.path.entry_length + min(lane.path.arc.length * 0.5, max(0.0, lane.path.arc.length - MIN_MOVEMENT_STEP))
        arc_position, arc_tangent, _, _, _, _ = self._lane_pose_at_distance(lane, mid_arc_distance)
        offset_arc_position = _offset_sub_path_point(arc_position, arc_tangent, sub_path_side)
        offset_arc_radius = _distance(lane.path.arc.center, offset_arc_position)
        offset_arc_length = offset_arc_radius * lane.path.arc.angle_span
        arc_distance = clamped_distance - lane.path.entry_length

        if arc_distance <= lane.path.arc.length:
            arc_ratio = arc_distance / max(lane.path.arc.length, 1e-6)
            return lane.path.entry_length + (offset_arc_length * arc_ratio)

        exit_distance = max(0.0, arc_distance - lane.path.arc.length)
        return lane.path.entry_length + offset_arc_length + exit_distance

    def _sub_path_total_length(self, lane: LaneDefinition, sub_path_side: SubPathSide) -> float:
        return self._sub_path_distance_at(lane, lane.path.length, sub_path_side)

    def _distance_between_vehicles_on_path(
        self,
        lane: LaneDefinition,
        leader: VehicleStateModel,
        follower: VehicleStateModel,
    ) -> float:
        leader_distance = self._sub_path_distance_at(lane, leader.distance_along, leader.sub_path_side)
        follower_distance = self._sub_path_distance_at(lane, follower.distance_along, follower.sub_path_side)
        return leader_distance - follower_distance

    def _spacing_limited_distance(
        self,
        lane: LaneDefinition,
        leader: VehicleStateModel,
        follower: VehicleStateModel,
        distance_limit: float,
    ) -> float:
        upper_bound = min(lane.path.length, max(follower.distance_along, distance_limit))
        required_gap = self._minimum_follow_distance(follower, leader)
        gap_at_upper_bound = self._sub_path_distance_at(lane, leader.distance_along, leader.sub_path_side) - self._sub_path_distance_at(
            lane,
            upper_bound,
            follower.sub_path_side,
        )
        if gap_at_upper_bound >= required_gap - MIN_MOVEMENT_STEP:
            return upper_bound

        lower_bound = follower.distance_along
        for _ in range(24):
            midpoint = (lower_bound + upper_bound) / 2.0
            gap_at_midpoint = self._sub_path_distance_at(lane, leader.distance_along, leader.sub_path_side) - self._sub_path_distance_at(
                lane,
                midpoint,
                follower.sub_path_side,
            )
            if gap_at_midpoint >= required_gap:
                lower_bound = midpoint
            else:
                upper_bound = midpoint

        return max(follower.distance_along, lower_bound)

    def _shared_lane_release_distance(
        self,
        leader_lane: LaneDefinition,
        follower: VehicleStateModel,
        leader: VehicleStateModel,
    ) -> float:
        if leader_lane.movement == "RIGHT" and isinstance(leader_lane.path, TurnArcPath):
            return min(
                leader_lane.path.length,
                leader_lane.path.entry_length + max(leader.length + 1.2, self._desired_follow_distance(follower, leader) * 0.45),
            )
        return min(
            leader_lane.path.length,
            leader_lane.intersection_entry_distance + max((INTERSECTION_SIZE * 0.42), self._desired_follow_distance(follower, leader) * 0.65),
        )

    def _shared_lane_spacing_limit(
        self,
        vehicle: VehicleStateModel,
        lane: LaneDefinition,
        leader: VehicleStateModel | None,
        distance_limit: float,
    ) -> float:
        if leader is None:
            return distance_limit

        leader_lane = self.lanes[leader.lane_id]
        if leader_lane.shared_lane_id != lane.shared_lane_id or leader_lane.id == lane.id:
            return distance_limit

        required_gap = self._minimum_follow_distance(vehicle, leader)
        shared_limit = max(vehicle.distance_along, leader.distance_along - required_gap)

        leader_has_entered_intersection = leader.distance_along >= leader_lane.intersection_entry_distance - MIN_MOVEMENT_STEP
        leader_releases_shared_lane = leader.distance_along >= self._shared_lane_release_distance(leader_lane, vehicle, leader)
        if (
            vehicle.distance_along < lane.intersection_entry_distance - MIN_MOVEMENT_STEP
            and leader_has_entered_intersection
            and not leader_releases_shared_lane
        ):
            shared_limit = min(
                shared_limit,
                max(
                    vehicle.distance_along,
                    lane.intersection_entry_distance - ((vehicle.length / 2.0) + STOP_LINE_BUFFER),
                ),
            )

        return min(distance_limit, shared_limit)

    def _shared_lane_leader(
        self,
        vehicle: VehicleStateModel,
        lane: LaneDefinition,
        other_vehicles: List[VehicleStateModel],
    ) -> VehicleStateModel | None:
        candidates = []
        for other in other_vehicles:
            other_lane = self.lanes[other.lane_id]
            if other_lane.shared_lane_id != lane.shared_lane_id or other_lane.id == lane.id:
                continue
            if other.distance_along < vehicle.distance_along - max(vehicle.length, other.length):
                continue
            candidates.append(other)

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda other: (
                max(0.0, other.distance_along - vehicle.distance_along),
                _distance(vehicle.position, other.position),
            ),
        )

    def _shared_lane_conflict_limit(
        self,
        vehicle: VehicleStateModel,
        lane: LaneDefinition,
        leader: VehicleStateModel | None,
        distance_limit: float,
    ) -> float:
        if leader is None:
            return distance_limit

        leader_lane = self.lanes[leader.lane_id]
        if leader_lane.shared_lane_id != lane.shared_lane_id or leader_lane.id == lane.id:
            return distance_limit

        clamped_limit = min(lane.path.length, max(vehicle.distance_along, distance_limit))
        clearance = self._vehicle_clearance_radius(vehicle) + self._vehicle_clearance_radius(leader) + 0.45
        sample_step = max(0.45, OBJECT_AWARENESS_SAMPLE_STEP * 0.5)
        sample_distance = vehicle.distance_along
        last_safe_distance = vehicle.distance_along

        while sample_distance < clamped_limit - MIN_MOVEMENT_STEP:
            sample_distance = min(clamped_limit, sample_distance + sample_step)
            sample_point = self._sub_path_pose_at_distance(lane, sample_distance, vehicle.sub_path_side)[0]
            if _distance(sample_point, leader.position) < clearance:
                return last_safe_distance
            last_safe_distance = sample_distance

        return clamped_limit

    def _sub_path_pose_at_distance(
        self,
        lane: LaneDefinition,
        distance_along: float,
        sub_path_side: SubPathSide,
    ) -> tuple[Point2D, Point2D, float, float | None, float | None, Point2D | None]:
        position, tangent, heading, arc_angle, arc_radius, arc_center = self._lane_pose_at_distance(
            lane,
            distance_along,
        )
        offset_position = _offset_sub_path_point(position, tangent, sub_path_side)
        if arc_center is not None:
            arc_radius = _distance(arc_center, offset_position)
            arc_angle = math.atan2(offset_position.y - arc_center.y, offset_position.x - arc_center.x)
        return offset_position, tangent, heading, arc_angle, arc_radius, arc_center

    def _apply_vehicle_pose(
        self,
        vehicle: VehicleStateModel,
        lane: LaneDefinition,
        distance_along: float,
        *,
        speed: float,
    ) -> None:
        clamped_distance = _clamp(distance_along, 0.0, lane.path.length)
        position, tangent, heading, arc_angle, arc_radius, arc_center = self._sub_path_pose_at_distance(
            lane,
            clamped_distance,
            vehicle.sub_path_side,
        )
        vehicle.position = position
        vehicle.distance_along = clamped_distance
        vehicle.progress = self._sub_path_distance_at(lane, clamped_distance, vehicle.sub_path_side) / max(
            self._sub_path_total_length(lane, vehicle.sub_path_side),
            1e-6,
        )
        vehicle.heading = heading
        vehicle.velocity_x = tangent.x * speed
        vehicle.velocity_y = tangent.y * speed
        vehicle.arc_angle = arc_angle
        vehicle.arc_radius = arc_radius
        vehicle.arc_center = arc_center

    def _make_vehicle_for_lane(
        self,
        lane_id: str,
        *,
        emergency_kind: VehicleKind | None = None,
        intent: VehicleIntent | None = None,
    ) -> VehicleStateModel:
        lane = self.lanes[lane_id]
        resolved_intent = intent or ("LEFT" if lane.movement == "LEFT" else "STRAIGHT")
        sub_path_side = _sub_path_side_for_intent(resolved_intent)
        start_position, _, heading, arc_angle, arc_radius, arc_center = self._sub_path_pose_at_distance(
            lane,
            0.0,
            sub_path_side,
        )
        self._vehicle_index += 1
        color = VEHICLE_COLOR_POOL[self._color_cursor % len(VEHICLE_COLOR_POOL)]
        self._color_cursor += 1
        length = round(_lerp(VEHICLE_MIN_LENGTH, VEHICLE_MAX_LENGTH, self._rng.random()), 3)
        width = round(_lerp(VEHICLE_MIN_WIDTH, VEHICLE_MAX_WIDTH, self._rng.random()), 3)
        route = _route_for_intent(resolved_intent)
        if route == "left":
            cruise_speed = round(_lerp(LEFT_SPEED_MIN, LEFT_SPEED_MAX, self._rng.random()), 3)
        else:
            cruise_speed = round(_lerp(STRAIGHT_SPEED_MIN, STRAIGHT_SPEED_MAX, self._rng.random()), 3)

        kind: VehicleKind = "car"
        has_siren = False
        priority = 0
        if emergency_kind is not None and emergency_kind != "car":
            kind = emergency_kind
            has_siren = True
            priority = 2
            emergency_profiles = {
                "ambulance": {"color": "#f8fafc", "speed_scale": 1.12, "length": 5.1, "width": 2.05},
                "firetruck": {"color": "#dc2626", "speed_scale": 1.06, "length": 6.6, "width": 2.2},
                "police": {"color": "#2563eb", "speed_scale": 1.16, "length": 4.8, "width": 1.95},
            }
            profile = emergency_profiles[kind]
            color = profile["color"]
            cruise_speed = round(cruise_speed * profile["speed_scale"], 3)
            length = round(max(length, profile["length"]), 3)
            width = round(max(width, profile["width"]), 3)

        return VehicleStateModel(
            id=f"veh-{self._vehicle_index}",
            lane_id=lane_id,
            origin_direction=lane.direction,
            route=route,
            intent=resolved_intent,
            sub_path_side=sub_path_side,
            progress=0.0,
            speed=0.0,
            state="MOVING",
            position=start_position,
            heading=heading,
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
            arc_angle=arc_angle,
            arc_radius=arc_radius,
            arc_center=arc_center,
        )

    def _vehicle_view(self, vehicle: VehicleStateModel) -> VehicleView:
        lane = self.lanes[vehicle.lane_id]
        return VehicleView(
            id=vehicle.id,
            lane_id=vehicle.lane_id,
            current_lane_id=vehicle.lane_id,
            approach=lane.direction,
            origin_direction=vehicle.origin_direction,
            route=vehicle.route,
            intent=vehicle.intent,
            sub_path_side=vehicle.sub_path_side,
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
                    priority=vehicle.priority,
                )
            )
        return telemetry

    def _build_traffic_brain_state(self, dt: float, *, brain: TrafficBrain | None = None):
        active_brain = brain or self.traffic_brain
        return active_brain.evaluate(
            dt=dt,
            ai_mode=self.config.ai_mode,
            current_phase=self.signal_controller.state,
            controller_phase=self.signal_controller.controller_phase(),
            vehicles=self._traffic_brain_vehicle_inputs(),
            lane_phase_map=self.lane_phase_map,
            phase_lane_ids=self.phase_lane_ids,
            unserved_demand_time=self.signal_controller.unserved_demand_time,
            processed_by_approach=self._vehicles_processed_by_approach_last_tick,
            arrivals_by_approach=self._vehicles_arrived_by_approach_last_tick,
            network_context=self.network_phase_context,
        )

    def _phase_maps_from_brain(self, brain_state) -> tuple[Dict[SignalCycleState, Dict[str, float]], Dict[SignalCycleState, float], Dict[SignalCycleState, bool]]:
        phase_demands: Dict[SignalCycleState, Dict[str, float]] = {}
        phase_scores: Dict[SignalCycleState, float] = {}
        phase_has_demand: Dict[SignalCycleState, bool] = {}

        for direction in SIGNAL_ORDER:
            score_view = brain_state.phase_scores[direction]
            phase_demands[direction] = {
                "queue": round(score_view.queue_length, 3),
                "wait_time": round(score_view.avg_wait_time, 3),
                "arrival_rate": round(getattr(score_view, "arrival_rate", 0.0), 3),
                "flow_rate": round(score_view.flow_rate, 3),
                "congestion_trend": round(score_view.congestion_component, 3),
                "fairness_boost": round(score_view.fairness_boost, 3),
                "emergency_boost": round(score_view.emergency_boost, 3),
                "score": round(score_view.score, 3),
            }
            phase_scores[direction] = round(score_view.score, 3)
            phase_has_demand[direction] = bool(score_view.demand_active)

        return phase_demands, phase_scores, phase_has_demand

    def calculate_phase_demands(
        self,
    ) -> tuple[Dict[SignalCycleState, Dict[str, float]], Dict[SignalCycleState, float], Dict[SignalCycleState, bool]]:
        brain_state = self._build_traffic_brain_state(0.0)
        return self._phase_maps_from_brain(brain_state)

    def _refresh_phase_demand_cache(self, dt: float) -> None:
        self.traffic_brain_state = self._build_traffic_brain_state(dt)
        phase_demands, phase_scores, phase_has_demand = self._phase_maps_from_brain(self.traffic_brain_state)
        self.phase_demands = phase_demands
        self.phase_scores = phase_scores
        self.phase_has_demand = phase_has_demand

    def _reset_signals(self) -> Dict[str, SignalState]:
        return {approach: RED for approach in SIGNAL_ORDER}

    def _apply_signals(self, signals: Dict[str, SignalState]) -> None:
        for approach in SIGNAL_ORDER:
            signals[approach] = self.signal_controller.signal_state_for_approach(approach)

    def _signal_snapshot(self) -> Dict[str, SignalState]:
        signals = self._reset_signals()
        self._apply_signals(signals)
        return signals

    def _intersection_clear(self) -> bool:
        for vehicle in self.vehicles:
            clearance_margin = max(vehicle.length, vehicle.width) / 2.0
            if (
                abs(vehicle.position.x) <= INTERSECTION_HALF_SIZE + clearance_margin + INTERSECTION_CLEAR_MARGIN
                and abs(vehicle.position.y) <= INTERSECTION_HALF_SIZE + clearance_margin + INTERSECTION_CLEAR_MARGIN
            ):
                return False
        return True

    def _vehicle_awareness_speed(self, vehicle: VehicleStateModel) -> float:
        return max(MIN_AWARENESS_SPEED, vehicle.speed, vehicle.cruise_speed * 0.55)

    def _vehicle_clearance_radius(self, vehicle: VehicleStateModel) -> float:
        return math.hypot(vehicle.length / 2.0, vehicle.width / 2.0)

    def _minimum_follow_distance(self, vehicle: VehicleStateModel, leader: VehicleStateModel) -> float:
        return ((vehicle.length + leader.length) / 2.0) + MIN_FOLLOW_BUFFER

    def _desired_follow_distance(self, vehicle: VehicleStateModel, leader: VehicleStateModel) -> float:
        minimum_gap = self._minimum_follow_distance(vehicle, leader)
        comfort_buffer = DESIRED_FOLLOW_BUFFER * self.config.safe_gap_multiplier
        return max(
            minimum_gap + 0.6,
            max(vehicle.length, leader.length) + comfort_buffer,
        )

    def _safe_follow_distance(self, vehicle: VehicleStateModel, leader: VehicleStateModel) -> float:
        return self._desired_follow_distance(vehicle, leader)

    def _follow_speed_target(
        self,
        vehicle: VehicleStateModel,
        leader: VehicleStateModel,
        distance_to_leader: float,
    ) -> float:
        minimum_gap = self._minimum_follow_distance(vehicle, leader)
        desired_gap = self._desired_follow_distance(vehicle, leader)
        if distance_to_leader <= minimum_gap + MIN_MOVEMENT_STEP:
            return 0.0
        if distance_to_leader >= desired_gap:
            return vehicle.cruise_speed
        normalized_distance = _clamp(distance_to_leader / max(desired_gap, 1e-6), 0.0, 1.0)
        comfort_speed = vehicle.cruise_speed * normalized_distance
        leader_release_speed = min(
            vehicle.cruise_speed,
            leader.speed + max(0.0, distance_to_leader - minimum_gap),
        )
        return min(
            vehicle.cruise_speed,
            max(comfort_speed, min(leader.speed, vehicle.cruise_speed) * 0.85),
            leader_release_speed,
        )

    def _deadlock_creep_speed(self, vehicle: VehicleStateModel, allowed_distance: float) -> float:
        room_ahead = allowed_distance - vehicle.distance_along
        if room_ahead <= MIN_MOVEMENT_STEP or vehicle.wait_time < DEADLOCK_UNBLOCK_TIME:
            return 0.0
        release_ratio = _clamp((vehicle.wait_time - DEADLOCK_UNBLOCK_TIME) / 2.5, 0.0, 1.0)
        return min(
            vehicle.cruise_speed * 0.35,
            DEADLOCK_CREEP_SPEED + (0.6 * release_ratio),
            room_ahead * 1.5,
        )

    def _intersection_capacity(self, lane: LaneDefinition) -> int:
        return TURN_INTERSECTION_CAPACITY if isinstance(lane.path, TurnArcPath) else STRAIGHT_INTERSECTION_CAPACITY

    def _intersection_entry_limit(
        self,
        vehicle: VehicleStateModel,
        lane: LaneDefinition,
        processed_lane_vehicles: List[VehicleStateModel],
    ) -> float:
        entry_distance = lane.path.entry_length if isinstance(lane.path, TurnArcPath) else lane.intersection_entry_distance
        exit_distance = lane.intersection_exit_distance
        if (
            entry_distance >= lane.path.length
            or vehicle.distance_along >= entry_distance - MIN_MOVEMENT_STEP
        ):
            return math.inf

        inside_vehicles = [
            other
            for other in processed_lane_vehicles
            if entry_distance - MIN_MOVEMENT_STEP <= other.distance_along <= exit_distance + MIN_MOVEMENT_STEP
        ]
        if len(inside_vehicles) >= self._intersection_capacity(lane):
            return max(
                vehicle.distance_along,
                entry_distance - ((vehicle.length / 2.0) + STOP_LINE_BUFFER),
            )

        downstream_vehicles = [
            other
            for other in processed_lane_vehicles
            if other.distance_along >= entry_distance - MIN_MOVEMENT_STEP
        ]
        closest_downstream = min(downstream_vehicles, key=lambda other: other.distance_along) if downstream_vehicles else None
        if closest_downstream is not None:
            release_distance = exit_distance + self._desired_follow_distance(vehicle, closest_downstream)
            if closest_downstream.distance_along < release_distance:
                return max(
                    vehicle.distance_along,
                    entry_distance - ((vehicle.length / 2.0) + STOP_LINE_BUFFER),
                )

        if isinstance(lane.path, TurnArcPath) and inside_vehicles:
            closest_inside = min(inside_vehicles, key=lambda other: other.distance_along)
            release_distance = exit_distance + self._desired_follow_distance(vehicle, closest_inside)
            if closest_inside.distance_along < release_distance:
                return max(
                    vehicle.distance_along,
                    entry_distance - ((vehicle.length / 2.0) + STOP_LINE_BUFFER),
                )

        return math.inf

    def _turn_path_queue_limit(
        self,
        vehicle: VehicleStateModel,
        lane: LaneDefinition,
        leader: VehicleStateModel | None,
        *,
        leader_entry_progress: float | None = None,
    ) -> float:
        if leader is None or not isinstance(lane.path, TurnArcPath):
            return math.inf

        turn_entry_distance = lane.path.entry_length
        if vehicle.distance_along >= turn_entry_distance - MIN_MOVEMENT_STEP:
            return math.inf
        leader_progress = leader.distance_along if leader_entry_progress is None else leader_entry_progress
        if leader_progress < turn_entry_distance - MIN_MOVEMENT_STEP:
            return math.inf

        release_distance = min(
            lane.path.length,
            turn_entry_distance + lane.path.arc.length + self._safe_follow_distance(vehicle, leader),
        )
        if leader_progress >= release_distance:
            return math.inf

        return max(
            vehicle.distance_along,
            turn_entry_distance - ((vehicle.length / 2.0) + STOP_LINE_BUFFER),
        )

    def _predict_vehicle_position(self, vehicle: VehicleStateModel, travel_time: float) -> Point2D:
        if travel_time <= 0.0 or vehicle.state == "STOPPED" or vehicle.speed <= MIN_MOVEMENT_STEP:
            return vehicle.position

        lane = self.lanes[vehicle.lane_id]
        projected_travel = min(
            vehicle.cruise_speed * travel_time,
            (vehicle.speed * travel_time) + (0.5 * ACCELERATION * travel_time * travel_time),
        )
        predicted_distance = min(lane.path.length, vehicle.distance_along + projected_travel)
        return self._sub_path_pose_at_distance(lane, predicted_distance, vehicle.sub_path_side)[0]

    def _predict_vehicle_pose(
        self,
        vehicle: VehicleStateModel,
        travel_time: float,
    ) -> tuple[Point2D, Point2D]:
        lane = self.lanes[vehicle.lane_id]
        if travel_time <= 0.0 or vehicle.state == "STOPPED" or vehicle.speed <= MIN_MOVEMENT_STEP:
            predicted_distance = vehicle.distance_along
        else:
            projected_travel = min(
                vehicle.cruise_speed * travel_time,
                (vehicle.speed * travel_time) + (0.5 * ACCELERATION * travel_time * travel_time),
            )
            predicted_distance = min(lane.path.length, vehicle.distance_along + projected_travel)
        predicted_position, predicted_tangent, _, _, _, _ = self._sub_path_pose_at_distance(
            lane,
            predicted_distance,
            vehicle.sub_path_side,
        )
        return predicted_position, predicted_tangent

    def _sample_point_conflicts_with_objects(
        self,
        vehicle: VehicleStateModel,
        sample_point: Point2D,
        travel_time: float,
        other_vehicles: List[VehicleStateModel],
        sample_lane: LaneDefinition | None = None,
        sample_tangent: Point2D | None = None,
    ) -> bool:
        vehicle_clearance = self._vehicle_clearance_radius(vehicle)

        for other in other_vehicles:
            if other.id == vehicle.id:
                continue
            other_lane = self.lanes[other.lane_id]
            if sample_lane is not None and other_lane.shared_lane_id == sample_lane.shared_lane_id:
                continue
            shared_lane_conflict = sample_lane is not None and other_lane.shared_lane_id == sample_lane.shared_lane_id
            prediction_time = 0.0 if shared_lane_conflict else travel_time
            predicted_position, predicted_tangent = self._predict_vehicle_pose(other, prediction_time)
            if sample_tangent is not None:
                relative_x = predicted_position.x - sample_point.x
                relative_y = predicted_position.y - sample_point.y
                longitudinal = (relative_x * sample_tangent.x) + (relative_y * sample_tangent.y)
                lateral = abs((relative_x * sample_tangent.y) - (relative_y * sample_tangent.x))
                if longitudinal < -max(vehicle.length, other.length):
                    continue
                heading_alignment = (sample_tangent.x * predicted_tangent.x) + (sample_tangent.y * predicted_tangent.y)
                if shared_lane_conflict:
                    corridor_half_width = ((vehicle.width + other.width) / 2.0) + (LANE_WIDTH * 0.4)
                elif heading_alignment < -0.45:
                    corridor_half_width = max(vehicle.width, other.width) * 0.78
                elif heading_alignment > 0.7:
                    corridor_half_width = ((vehicle.width + other.width) / 2.0) + (LANE_WIDTH * 0.22)
                else:
                    corridor_half_width = ((vehicle.width + other.width) / 2.0) + (LANE_WIDTH * 0.3)
                if lateral > corridor_half_width:
                    continue
            clearance = (
                vehicle_clearance
                + self._vehicle_clearance_radius(other)
                + OBJECT_AWARENESS_BUFFER
                + AWARENESS_REACTION_BUFFER
            )
            if _distance(sample_point, predicted_position) < clearance:
                return True

        return False

    def _object_awareness_limit(
        self,
        vehicle: VehicleStateModel,
        lane: LaneDefinition,
        other_vehicles: List[VehicleStateModel],
        distance_limit: float,
    ) -> float:
        clamped_limit = min(lane.path.length, max(vehicle.distance_along, distance_limit))
        forward = lane.path.tangent_at_distance(vehicle.distance_along)
        relevant_vehicles = [
            other
            for other in other_vehicles
            if (
                ((other.position.x - vehicle.position.x) * forward.x) + ((other.position.y - vehicle.position.y) * forward.y)
            ) >= -max(vehicle.length, other.length)
        ]
        awareness_horizon = max(
            self._spawn_follow_buffer() + 8.0,
            self._vehicle_awareness_speed(vehicle) * OBJECT_AWARENESS_HORIZON_SECONDS,
        )
        awareness_speed = self._vehicle_awareness_speed(vehicle)
        sample_limit = min(clamped_limit, vehicle.distance_along + awareness_horizon)
        if sample_limit <= vehicle.distance_along + MIN_MOVEMENT_STEP:
            return clamped_limit

        if self._sample_point_conflicts_with_objects(
            vehicle,
            vehicle.position,
            0.0,
            relevant_vehicles,
            sample_lane=lane,
            sample_tangent=forward,
        ):
            return vehicle.distance_along

        sample_distance = vehicle.distance_along
        last_safe_distance = vehicle.distance_along
        sample_step = 0.45
        while sample_distance < sample_limit - MIN_MOVEMENT_STEP:
            sample_distance = min(sample_limit, sample_distance + sample_step)
            sample_travel_time = max(0.0, sample_distance - vehicle.distance_along) / max(awareness_speed, MIN_AWARENESS_SPEED)
            sample_point, sample_tangent, _, _, _, _ = self._sub_path_pose_at_distance(lane, sample_distance, vehicle.sub_path_side)
            if self._sample_point_conflicts_with_objects(
                vehicle,
                sample_point,
                sample_travel_time,
                relevant_vehicles,
                sample_lane=lane,
                sample_tangent=sample_tangent,
            ):
                return last_safe_distance
            last_safe_distance = sample_distance

        return clamped_limit

    def _vehicle_collides_with_any_object(
        self,
        vehicle: VehicleStateModel,
        other_vehicles: List[VehicleStateModel],
    ) -> bool:
        vehicle_clearance = self._vehicle_clearance_radius(vehicle)

        for other in other_vehicles:
            if other.id == vehicle.id:
                continue
            clearance = vehicle_clearance + self._vehicle_clearance_radius(other)
            if _distance(vehicle.position, other.position) < clearance:
                return True

        return False

    def update_signals(self, dt: float) -> None:
        emergency_priority = getattr(self.traffic_brain_state, "emergency", EmergencyPriorityView())
        next_direction = self.signal_controller.update(
            dt,
            intersection_clear=self._intersection_clear(),
            ai_mode=self.config.ai_mode,
            phase_scores=self.phase_scores,
            phase_has_demand=self.phase_has_demand,
            phase_demands=self.phase_demands,
            emergency_priority=emergency_priority,
        )
        self.current_state = self.signal_controller.state
        if next_direction is not None:
            self._vehicles_cleared_last_cycle = self._vehicles_cleared_current_cycle
            self._vehicles_cleared_current_cycle = 0
            self._completed_signal_cycles += 1
            if self.config.ai_mode == "adaptive" and emergency_priority.detected and emergency_priority.preferred_phase == next_direction:
                self._log("INFO", f"AI emergency preemption switched green to the {_phase_label(next_direction)} approach.")
            else:
                mode_label = "AI" if self.config.ai_mode == "adaptive" else "Normal"
                self._log("INFO", f"{mode_label} signal switched green to the {_phase_label(next_direction)} approach.")

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
            lane_queue: List[VehicleStateModel] = []

            for vehicle in lane_vehicles:
                leader = lane_queue[-1] if lane_queue else None
                allowed_distance = lane.path.length
                can_move = self.signal_controller.can_vehicle_move(lane.direction, vehicle.route)
                if vehicle.distance_along < lane.stop_distance and not can_move:
                    allowed_distance = min(
                        allowed_distance,
                        max(0.0, lane.stop_distance - ((vehicle.length / 2.0) + STOP_LINE_BUFFER)),
                    )

                minimum_gap = math.inf
                if leader is not None:
                    minimum_gap = self._minimum_follow_distance(vehicle, leader)
                    allowed_distance = self._spacing_limited_distance(
                        lane,
                        leader,
                        vehicle,
                        allowed_distance,
                    )

                other_vehicles = [other for other in self.vehicles if other.id != vehicle.id]
                shared_lane_leader = self._shared_lane_leader(vehicle, lane, other_vehicles)
                allowed_distance = self._shared_lane_spacing_limit(
                    vehicle,
                    lane,
                    shared_lane_leader,
                    allowed_distance,
                )
                allowed_distance = self._shared_lane_conflict_limit(
                    vehicle,
                    lane,
                    shared_lane_leader,
                    allowed_distance,
                )
                allowed_distance = min(
                    allowed_distance,
                    self._object_awareness_limit(
                        vehicle,
                        lane,
                        other_vehicles,
                        allowed_distance,
                    ),
                )
                allowed_distance = min(
                    allowed_distance,
                    self._intersection_entry_limit(vehicle, lane, lane_queue),
                )

                allowed_distance = max(vehicle.distance_along, allowed_distance)
                remaining_distance = max(0.0, allowed_distance - vehicle.distance_along)
                target_speed = self._distance_limited_speed(vehicle.cruise_speed, remaining_distance)

                if leader is not None:
                    distance_to_leader = self._distance_between_vehicles_on_path(lane, leader, vehicle)
                    target_speed = min(target_speed, self._follow_speed_target(vehicle, leader, distance_to_leader))

                rate = ACCELERATION if target_speed >= vehicle.speed else BRAKE_RATE
                updated_speed = _move_toward(vehicle.speed, target_speed, rate * dt)
                candidate_distance = min(lane.path.length, vehicle.distance_along + (updated_speed * dt))
                next_distance = min(candidate_distance, allowed_distance)

                if next_distance <= vehicle.distance_along + MIN_MOVEMENT_STEP:
                    next_distance = vehicle.distance_along
                    updated_speed = 0.0

                actual_speed = (next_distance - vehicle.distance_along) / dt if dt > 0.0 else 0.0
                self._apply_vehicle_pose(
                    vehicle,
                    lane,
                    next_distance,
                    speed=actual_speed,
                )
                vehicle.speed = actual_speed
                vehicle.state = "MOVING" if actual_speed > MIN_MOVEMENT_STEP else "STOPPED"
                vehicle.wait_time = vehicle.wait_time + dt if vehicle.state == "STOPPED" else 0.0

                if next_distance >= lane.path.length - MIN_MOVEMENT_STEP:
                    self.completed_vehicle_transfers_last_tick.append(
                        CompletedVehicleTransfer(
                            id=vehicle.id,
                            source_approach=lane.direction,
                            exit_direction=_exit_direction_for_movement(lane.direction, vehicle.route),
                            route=vehicle.route,
                            intent=vehicle.intent,
                            kind=vehicle.kind,
                            has_siren=vehicle.has_siren,
                            priority=vehicle.priority,
                            color=vehicle.color,
                            length=vehicle.length,
                            width=vehicle.width,
                            cruise_speed=vehicle.cruise_speed,
                        )
                    )
                    self.processed_vehicles += 1
                    self._vehicles_processed_last_tick += 1
                    self._vehicles_processed_by_approach_last_tick[lane.direction] += 1
                    self._vehicles_cleared_current_cycle += 1
                else:
                    survivors.append(vehicle)
                    lane_queue.append(vehicle)

        self.vehicles = survivors

    def compute_metrics(self, dt: float) -> None:
        active_vehicles = len(self.vehicles)
        queued_vehicles = sum(1 for vehicle in self.vehicles if vehicle.state == "STOPPED")
        emergency_vehicles = sum(1 for vehicle in self.vehicles if vehicle.has_siren or vehicle.kind != "car")
        avg_wait_time = sum(vehicle.wait_time for vehicle in self.vehicles) / active_vehicles if active_vehicles else 0.0
        throughput_now = self._vehicles_processed_last_tick / max(dt, FRAME_DT) if dt > 0.0 else 0.0
        self.smoothed_throughput = throughput_now if self.frame <= 1 else _lerp(self.smoothed_throughput, throughput_now, 0.18)
        queue_pressure = (queued_vehicles / active_vehicles) if active_vehicles else 0.0
        vehicles_cleared_per_cycle = (
            self._vehicles_cleared_last_cycle
            if self._completed_signal_cycles > 0
            else self._vehicles_cleared_current_cycle
        )
        self.metrics = MetricsView(
            avg_wait_time=round(avg_wait_time, 3),
            throughput=round(self.smoothed_throughput, 3),
            vehicles_processed=self.processed_vehicles,
            queue_pressure=round(queue_pressure, 3),
            active_vehicles=active_vehicles,
            queued_vehicles=queued_vehicles,
            emergency_vehicles=emergency_vehicles,
            active_nodes=4,
            detections=queued_vehicles,
            bandwidth_savings=4.0,
            vehicles_cleared_per_cycle=vehicles_cleared_per_cycle,
        )

    def _log(self, level: str, message: str) -> None:
        self.events.appendleft(EventView(timestamp=round(self.time, 3), level=level, message=message))
