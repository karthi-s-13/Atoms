from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, List, Protocol

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
    LaneArcView,
    LaneKind,
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
RED = "RED"

PHASE_GREEN: ControllerPhase = "PHASE_GREEN"
PHASE_YELLOW: ControllerPhase = "PHASE_YELLOW"
PHASE_ALL_RED: ControllerPhase = "PHASE_ALL_RED"

NORTH: SignalCycleState = "NORTH"
EAST: SignalCycleState = "EAST"
SOUTH: SignalCycleState = "SOUTH"
WEST: SignalCycleState = "WEST"
SIGNAL_ORDER: tuple[SignalCycleState, ...] = (NORTH, EAST, SOUTH, WEST)

GREEN_INTERVAL = 7.0
LEFT_TURN_PROBABILITY = 0.18
RIGHT_TURN_PROBABILITY = 0.22
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
RIGHT_SPEED_MIN = 6.2
RIGHT_SPEED_MAX = 7.2
SLIP_SPEED_MIN = 6.8
SLIP_SPEED_MAX = 7.8
ACCELERATION = 8.0
BRAKE_RATE = 16.0
FOLLOW_GAP = 5.0
FOLLOW_RESPONSE_DISTANCE = 20.0
STOP_LINE_BUFFER = 0.25
MIN_MOVEMENT_STEP = 1e-3
MERGE_APPROACH_DISTANCE = 18.0
PEDESTRIAN_SIDEWALK_OFFSET = 2.2
PEDESTRIAN_MIN_SPEED = 1.1
PEDESTRIAN_MAX_SPEED = 1.55
PEDESTRIAN_SPAWN_INTERVAL = 4.0
PEDESTRIAN_ENTRY_EPSILON = 0.08
SLIP_CORNER_OFFSET = STOP_OFFSET + LANE_WIDTH
SLIP_TURN_RADIUS = SLIP_CORNER_OFFSET - OUTER_LANE_OFFSET
SLIP_TRANSITION_LENGTH = LANE_WIDTH

VEHICLE_COLOR_POOL = ("#3b82f6", "#ef4444", "#facc15", "#22c55e", "#f8fafc")
VEHICLE_APPROACHES: tuple[Approach, ...] = ("NORTH", "EAST", "SOUTH", "WEST")
PEDESTRIAN_SHIRT_COLORS = ("#ef4444", "#3b82f6", "#22c55e", "#facc15")
PEDESTRIAN_PANTS_COLORS = ("#334155", "#1f2937", "#475569", "#0f172a")


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


def _offset_point(point: Point2D, direction: Point2D, distance: float) -> Point2D:
    return Point2D(
        x=point.x + (direction.x * distance),
        y=point.y + (direction.y * distance),
    )


def _line_intersection(origin_a: Point2D, direction_a: Point2D, origin_b: Point2D, direction_b: Point2D) -> Point2D:
    determinant = (direction_a.x * direction_b.y) - (direction_a.y * direction_b.x)
    if abs(determinant) <= 1e-6:
        raise ValueError("Cannot intersect parallel slip-lane tangents.")
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


def _right_turn_exit(approach: Approach) -> Approach:
    return {
        "NORTH": "WEST",
        "EAST": "NORTH",
        "SOUTH": "EAST",
        "WEST": "SOUTH",
    }[approach]


def _left_turn_exit(approach: Approach) -> Approach:
    return {
        "NORTH": "EAST",
        "EAST": "SOUTH",
        "SOUTH": "WEST",
        "WEST": "NORTH",
    }[approach]


def _exit_direction_for_movement(approach: Approach, route: RouteType) -> Approach:
    if route == "left":
        return _left_turn_exit(approach)
    if route == "right":
        return _right_turn_exit(approach)
    return _opposite_approach(approach)


def _pedestrian_crossing_for_approach(approach: Approach) -> RoadDirection:
    return "EW" if approach in {"NORTH", "SOUTH"} else "NS"


def _crosswalk_movement_direction(crosswalk: CrosswalkView) -> RoadDirection:
    return "EW" if abs(crosswalk.movement.x) >= abs(crosswalk.movement.y) else "NS"


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
class CircularArcPath:
    points: tuple[Point2D, ...]
    arc: CircularArc
    length: float

    @classmethod
    def from_arc(cls, arc: CircularArc) -> "CircularArcPath":
        start = arc.point_at_distance(0.0)
        end = arc.point_at_distance(arc.length)
        return cls(points=(start, end), arc=arc, length=arc.length)

    def point_at_distance(self, distance_along: float) -> Point2D:
        return self.arc.point_at_distance(distance_along)

    def point_at(self, t: float) -> Point2D:
        return self.point_at_distance(self.length * _clamp(t, 0.0, 1.0))

    def tangent_at_distance(self, distance_along: float) -> Point2D:
        return self.arc.tangent_at_distance(distance_along)

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


@dataclass(frozen=True)
class LaneDefinition:
    id: str
    kind: LaneKind
    direction: Approach
    lane_index: str
    movement: LaneMovement
    movement_id: str
    path: LanePath
    stop_line_position: Point2D
    stop_distance: float
    stop_crosswalk_id: str
    crosswalk_start: Point2D
    queue_group: str
    queue_release_distance: float
    merge_group: str | None = None
    merge_distance: float | None = None
    arc: LaneArcView | None = None
    turn_entry: Point2D | None = None
    turn_exit: Point2D | None = None

    def to_view(self) -> LaneView:
        return LaneView(
            id=self.id,
            kind=self.kind,
            approach=self.direction,
            direction=self.direction,
            movement=self.movement,
            start=self.path.points[0],
            end=self.path.points[-1],
            path=list(self.path.points),
            crosswalk_id=self.stop_crosswalk_id,
            stop_line_position=self.stop_line_position,
            crosswalk_start=self.crosswalk_start,
            arc=self.arc,
            turn_entry=self.turn_entry,
            turn_exit=self.turn_exit,
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
    arc_angle: float | None = None
    arc_radius: float | None = None
    arc_center: Point2D | None = None


@dataclass
class PedestrianStateModel:
    id: str
    crossing: RoadDirection
    target_crosswalk: str
    crosswalk_id: str
    road_direction: RoadDirection
    path: PolylinePath
    distance_along: float
    speed: float
    velocity_x: float
    velocity_y: float
    position: Point2D
    state: str
    wait_time: float
    is_elderly: bool
    is_impatient: bool
    risky_crossing: bool
    look_angle: float
    shirt_color: str
    pants_color: str
    body_scale: float
    crosswalk_entry_distance: float
    crosswalk_exit_distance: float


@dataclass
class CompletedVehicleTransfer:
    id: str
    source_approach: Approach
    exit_direction: Approach
    route: RouteType
    kind: VehicleKind
    has_siren: bool
    priority: int
    color: str
    length: float
    width: float
    cruise_speed: float


class SignalController:
    """Deterministic single-green-direction controller."""

    def __init__(self) -> None:
        self.current_green_direction: SignalCycleState = NORTH
        self.elapsed = 0.0
        self.green_duration = GREEN_INTERVAL
        self.unserved_demand_time: Dict[SignalCycleState, float] = {direction: 0.0 for direction in SIGNAL_ORDER}

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
        return self.current_green_direction

    def signal_state_for_approach(self, approach: Approach) -> SignalState:
        return GREEN if approach == self.current_green_direction else RED

    def can_vehicle_move(self, approach: Approach, route: RouteType) -> bool:
        return route in {"straight", "right"} and approach == self.current_green_direction

    def update(self, dt: float, *, intersection_clear: bool) -> SignalCycleState | None:
        self.elapsed += dt
        for direction in SIGNAL_ORDER:
            if direction == self.current_green_direction:
                self.unserved_demand_time[direction] = 0.0
            else:
                self.unserved_demand_time[direction] += dt * STARVATION_SCALE

        if self.elapsed < self.green_duration or not intersection_clear:
            return None

        current_index = SIGNAL_ORDER.index(self.current_green_direction)
        self.current_green_direction = SIGNAL_ORDER[(current_index + 1) % len(SIGNAL_ORDER)]
        self.elapsed = 0.0
        return self.current_green_direction


class TrafficSimulationEngine:
    """Stable single-intersection controller with one green approach at a time."""

    def __init__(self) -> None:
        self.crosswalks = self._build_crosswalks()
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
        self._rng = random.Random(13)
        self.events: Deque[EventView] = deque(maxlen=40)
        self.traffic_brain = TrafficBrain()
        self.reset()
        self._log("INFO", "Single-green controller initialized with straight, right, and free-slip left lane routing.")

    def reset(self) -> None:
        self.config = SimulationConfig(ai_mode="fixed", max_vehicles=36, max_pedestrians=0)
        self.signal_controller = SignalController()
        self.network_phase_context: Dict[str, Any] = {}
        self.current_state: SignalCycleState = self.signal_controller.state
        self.frame = 0
        self.time = 0.0
        self.processed_vehicles = 0
        self.smoothed_throughput = 0.0
        self.vehicles: List[VehicleStateModel] = []
        self.pedestrians: List[PedestrianStateModel] = []
        self.metrics = MetricsView(0.0, 0.0, 0, 0.0, 0, 0, 0, 0, 4, 0, 4.0)
        self._vehicle_index = 0
        self._vehicle_spawn_cursor = 0
        self._vehicle_spawn_timer = self._vehicle_spawn_interval()
        self._pedestrian_index = 0
        self._pedestrian_spawn_timer = self._pedestrian_spawn_interval()
        self._color_cursor = 0
        self._vehicles_processed_last_tick = 0
        self.completed_vehicle_transfers_last_tick: List[CompletedVehicleTransfer] = []
        self._vehicles_processed_by_approach_last_tick: Dict[Approach, int] = {
            approach: 0 for approach in SIGNAL_ORDER
        }
        self.traffic_brain.reset()
        self.phase_scores: Dict[SignalCycleState, float] = {direction: 0.0 for direction in SIGNAL_ORDER}
        self.phase_has_demand: Dict[SignalCycleState, bool] = {direction: False for direction in SIGNAL_ORDER}
        self.phase_demands: Dict[SignalCycleState, Dict[str, float]] = {
            direction: {
                "queue": 0.0,
                "wait_time": 0.0,
                "pedestrian_demand": 0.0,
                "flow_rate": 0.0,
                "congestion_trend": 0.0,
                "fairness_boost": 0.0,
                "emergency_boost": 0.0,
                "score": 0.0,
            }
            for direction in SIGNAL_ORDER
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
            self.config.max_pedestrians = max(0, min(12, int(values["max_pedestrians"])))
        self.config.ai_mode = "fixed"
        return self.config

    def set_network_phase_context(self, context: Dict[str, Any] | None) -> None:
        self.network_phase_context = dict(context or {})

    def drain_completed_vehicle_transfers(self) -> List[CompletedVehicleTransfer]:
        completed = list(self.completed_vehicle_transfers_last_tick)
        self.completed_vehicle_transfers_last_tick = []
        return completed

    def can_accept_transfer(self, approach: Approach, route: RouteType) -> bool:
        lane_ids = self._lane_ids_for_route(approach, route)
        if not lane_ids:
            return False
        return self._lane_has_spawn_room(lane_ids[0])

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
        lane_ids = self._lane_ids_for_route(approach, route)
        if not lane_ids:
            return False
        lane_id = lane_ids[0]
        if not self._lane_has_spawn_room(lane_id):
            return False

        vehicle = self._make_vehicle_for_lane(lane_id, emergency=kind != "car" or has_siren)
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
        self._vehicles_processed_by_approach_last_tick = {approach: 0 for approach in SIGNAL_ORDER}
        if sim_dt > 0.0:
            self.time += sim_dt
            self.update_signals(sim_dt)
            self.update_pedestrians(sim_dt)
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
            pedestrians=[self._pedestrian_view(pedestrian) for pedestrian in self.pedestrians],
            lanes=[lane.to_view() for lane in self.lanes.values()],
            crosswalks=list(self.crosswalks.values()),
            signals=self._signal_snapshot(),
            pedestrian_phase_active=any(pedestrian.state == "CROSSING" for pedestrian in self.pedestrians),
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
            queue_group: str,
            queue_release_position: Point2D | None = None,
            *,
            kind: LaneKind = "main",
            merge_group: str | None = None,
            merge_position: Point2D | None = None,
        ) -> None:
            path = PolylinePath.from_points(points)
            lanes[lane_id] = LaneDefinition(
                id=lane_id,
                kind=kind,
                direction=approach,
                lane_index=lane_index,
                movement=movement,
                movement_id=f"{approach[0]}_{movement}",
                path=path,
                stop_line_position=stop_line_position,
                stop_distance=_distance(path.points[0], stop_line_position),
                stop_crosswalk_id=crosswalk_id,
                crosswalk_start=crosswalk_start,
                queue_group=queue_group,
                queue_release_distance=(
                    _distance(path.points[0], queue_release_position)
                    if queue_release_position is not None
                    else path.length
                ),
                merge_group=merge_group,
                merge_distance=(
                    _distance(path.points[0], merge_position)
                    if merge_position is not None
                    else None
                ),
            )

        add_lane(
            "lane_north_straight",
            "NORTH",
            "outer",
            "STRAIGHT",
            (
                Point2D(OUTER_LANE_OFFSET, PATH_ENTRY_OFFSET),
                Point2D(OUTER_LANE_OFFSET, -PATH_EXIT_OFFSET),
            ),
            Point2D(OUTER_LANE_OFFSET, STOP_OFFSET),
            "north_crosswalk",
            Point2D(OUTER_LANE_OFFSET, CROSSWALK_OUTER_OFFSET),
            "lane_north_straight",
            Point2D(OUTER_LANE_OFFSET, SLIP_CORNER_OFFSET),
            merge_group="lane_north_straight",
            merge_position=Point2D(OUTER_LANE_OFFSET, -SLIP_CORNER_OFFSET),
        )
        add_lane(
            "lane_south_straight",
            "SOUTH",
            "outer",
            "STRAIGHT",
            (
                Point2D(-OUTER_LANE_OFFSET, -PATH_ENTRY_OFFSET),
                Point2D(-OUTER_LANE_OFFSET, PATH_EXIT_OFFSET),
            ),
            Point2D(-OUTER_LANE_OFFSET, -STOP_OFFSET),
            "south_crosswalk",
            Point2D(-OUTER_LANE_OFFSET, -CROSSWALK_OUTER_OFFSET),
            "lane_south_straight",
            Point2D(-OUTER_LANE_OFFSET, -SLIP_CORNER_OFFSET),
            merge_group="lane_south_straight",
            merge_position=Point2D(-OUTER_LANE_OFFSET, SLIP_CORNER_OFFSET),
        )
        add_lane(
            "lane_east_straight",
            "EAST",
            "outer",
            "STRAIGHT",
            (
                Point2D(PATH_ENTRY_OFFSET, -OUTER_LANE_OFFSET),
                Point2D(-PATH_EXIT_OFFSET, -OUTER_LANE_OFFSET),
            ),
            Point2D(STOP_OFFSET, -OUTER_LANE_OFFSET),
            "east_crosswalk",
            Point2D(CROSSWALK_OUTER_OFFSET, -OUTER_LANE_OFFSET),
            "lane_east_straight",
            Point2D(SLIP_CORNER_OFFSET, -OUTER_LANE_OFFSET),
            merge_group="lane_east_straight",
            merge_position=Point2D(-SLIP_CORNER_OFFSET, -OUTER_LANE_OFFSET),
        )
        add_lane(
            "lane_west_straight",
            "WEST",
            "outer",
            "STRAIGHT",
            (
                Point2D(-PATH_ENTRY_OFFSET, OUTER_LANE_OFFSET),
                Point2D(PATH_EXIT_OFFSET, OUTER_LANE_OFFSET),
            ),
            Point2D(-STOP_OFFSET, OUTER_LANE_OFFSET),
            "west_crosswalk",
            Point2D(-CROSSWALK_OUTER_OFFSET, OUTER_LANE_OFFSET),
            "lane_west_straight",
            Point2D(-SLIP_CORNER_OFFSET, OUTER_LANE_OFFSET),
            merge_group="lane_west_straight",
            merge_position=Point2D(SLIP_CORNER_OFFSET, OUTER_LANE_OFFSET),
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
            queue_group: str,
            *,
            kind: LaneKind = "main",
            arc_clockwise: bool = True,
            merge_group: str | None = None,
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
            lanes[lane_id] = LaneDefinition(
                id=lane_id,
                kind=kind,
                direction=approach,
                lane_index=lane_index,
                movement=movement,
                movement_id=f"{approach[0]}_{movement}",
                path=path,
                stop_line_position=stop_line_position,
                stop_distance=_distance(path.points[0], stop_line_position),
                stop_crosswalk_id=crosswalk_id,
                crosswalk_start=crosswalk_start,
                queue_group=queue_group,
                queue_release_distance=_distance(path.points[0], turn_entry),
                merge_group=merge_group,
                merge_distance=(path.entry_length + arc.length) if merge_group is not None else None,
                arc=arc.to_view(),
                turn_entry=turn_entry,
                turn_exit=turn_exit,
            )

        def add_slip_lane(approach: Approach) -> None:
            incoming_lane_id = f"lane_{approach.lower()}_straight"
            exit_direction = _left_turn_exit(approach)
            outgoing_approach = _opposite_approach(exit_direction)
            outgoing_lane_id = f"lane_{outgoing_approach.lower()}_straight"
            incoming_lane = lanes[incoming_lane_id]
            outgoing_lane = lanes[outgoing_lane_id]

            incoming_direction = incoming_lane.path.tangent_at_distance(0.0)
            outgoing_direction = outgoing_lane.path.tangent_at_distance(0.0)
            incoming_normal = _left_normal(incoming_direction)
            outgoing_normal = _left_normal(outgoing_direction)
            if outgoing_lane.merge_distance is None:
                raise ValueError(f"Missing merge point for slip-lane destination {outgoing_lane_id}.")

            turn_entry = incoming_lane.path.point_at_distance(incoming_lane.queue_release_distance)
            turn_exit = outgoing_lane.path.point_at_distance(outgoing_lane.merge_distance)
            arc_center = _line_intersection(
                turn_entry,
                incoming_normal,
                turn_exit,
                outgoing_normal,
            )
            entry_start = _offset_point(turn_entry, incoming_direction, -SLIP_TRANSITION_LENGTH)
            exit_end = _offset_point(turn_exit, outgoing_direction, SLIP_TRANSITION_LENGTH)
            arc = CircularArc.from_center(
                arc_center,
                turn_entry,
                turn_exit,
                clockwise=False,
            )
            path = TurnArcPath.from_points(
                entry_start,
                turn_entry,
                arc,
                turn_exit,
                exit_end,
            )
            lane_id = f"lane_{approach.lower()}_left_slip"
            lanes[lane_id] = LaneDefinition(
                id=lane_id,
                kind="slip",
                direction=approach,
                lane_index="slip",
                movement="LEFT",
                movement_id=f"{approach[0]}_LEFT",
                path=path,
                stop_line_position=turn_entry,
                stop_distance=path.entry_length,
                stop_crosswalk_id=outgoing_lane.stop_crosswalk_id,
                crosswalk_start=turn_entry,
                queue_group=lane_id,
                queue_release_distance=path.entry_length + arc.length,
                merge_group=outgoing_lane_id,
                merge_distance=path.length,
                arc=arc.to_view(),
                turn_entry=turn_entry,
                turn_exit=turn_exit,
            )

        add_arc_lane(
            "lane_north_right",
            "NORTH",
            "inner",
            "RIGHT",
            Point2D(INNER_LANE_OFFSET, PATH_ENTRY_OFFSET),
            Point2D(INNER_LANE_OFFSET, STOP_OFFSET),
            Point2D(INNER_LANE_OFFSET, INTERSECTION_HALF_SIZE),
            Point2D(-INTERSECTION_HALF_SIZE, INTERSECTION_HALF_SIZE),
            Point2D(-INTERSECTION_HALF_SIZE, -INNER_LANE_OFFSET),
            Point2D(-PATH_EXIT_OFFSET, -INNER_LANE_OFFSET),
            "north_crosswalk",
            Point2D(INNER_LANE_OFFSET, CROSSWALK_OUTER_OFFSET),
            "lane_north_right",
        )
        add_arc_lane(
            "lane_south_right",
            "SOUTH",
            "inner",
            "RIGHT",
            Point2D(-INNER_LANE_OFFSET, -PATH_ENTRY_OFFSET),
            Point2D(-INNER_LANE_OFFSET, -STOP_OFFSET),
            Point2D(-INNER_LANE_OFFSET, -INTERSECTION_HALF_SIZE),
            Point2D(INTERSECTION_HALF_SIZE, -INTERSECTION_HALF_SIZE),
            Point2D(INTERSECTION_HALF_SIZE, INNER_LANE_OFFSET),
            Point2D(PATH_EXIT_OFFSET, INNER_LANE_OFFSET),
            "south_crosswalk",
            Point2D(-INNER_LANE_OFFSET, -CROSSWALK_OUTER_OFFSET),
            "lane_south_right",
        )
        add_arc_lane(
            "lane_east_right",
            "EAST",
            "inner",
            "RIGHT",
            Point2D(PATH_ENTRY_OFFSET, -INNER_LANE_OFFSET),
            Point2D(STOP_OFFSET, -INNER_LANE_OFFSET),
            Point2D(INTERSECTION_HALF_SIZE, -INNER_LANE_OFFSET),
            Point2D(INTERSECTION_HALF_SIZE, INTERSECTION_HALF_SIZE),
            Point2D(-INNER_LANE_OFFSET, INTERSECTION_HALF_SIZE),
            Point2D(-INNER_LANE_OFFSET, PATH_EXIT_OFFSET),
            "east_crosswalk",
            Point2D(CROSSWALK_OUTER_OFFSET, -INNER_LANE_OFFSET),
            "lane_east_right",
        )
        add_arc_lane(
            "lane_west_right",
            "WEST",
            "inner",
            "RIGHT",
            Point2D(-PATH_ENTRY_OFFSET, INNER_LANE_OFFSET),
            Point2D(-STOP_OFFSET, INNER_LANE_OFFSET),
            Point2D(-INTERSECTION_HALF_SIZE, INNER_LANE_OFFSET),
            Point2D(-INTERSECTION_HALF_SIZE, -INTERSECTION_HALF_SIZE),
            Point2D(INNER_LANE_OFFSET, -INTERSECTION_HALF_SIZE),
            Point2D(INNER_LANE_OFFSET, -PATH_EXIT_OFFSET),
            "west_crosswalk",
            Point2D(-CROSSWALK_OUTER_OFFSET, INNER_LANE_OFFSET),
            "lane_west_right",
        )
        for approach in SIGNAL_ORDER:
            add_slip_lane(approach)
        return lanes

    def _vehicle_spawn_interval(self) -> float:
        intensity = _clamp(self.config.traffic_intensity, 0.0, 1.0)
        return 2.7 - (1.75 * intensity)

    def _pedestrian_spawn_interval(self) -> float:
        intensity = _clamp(self.config.traffic_intensity, 0.0, 1.0)
        return PEDESTRIAN_SPAWN_INTERVAL - (1.25 * intensity)

    def _lane_ids_for_route(self, approach: Approach, route: RouteType) -> List[str]:
        movement = {"straight": "STRAIGHT", "right": "RIGHT", "left": "LEFT"}.get(route)
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
            route_roll = self._rng.random()
            if route_roll < LEFT_TURN_PROBABILITY:
                route: RouteType = "left"
            elif route_roll < LEFT_TURN_PROBABILITY + RIGHT_TURN_PROBABILITY:
                route = "right"
            else:
                route = "straight"
            if emergency_spawn and self._rng.random() < EMERGENCY_STRAIGHT_BIAS:
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
                self._log("INFO", f"Spawned {vehicle.route} vehicle on {approach.lower()} approach.")
                return
        self._vehicle_spawn_timer = 0.35

    def _lane_has_spawn_room(self, lane_id: str) -> bool:
        lane = self.lanes[lane_id]
        spawn_buffer = FOLLOW_GAP + 2.0
        for other in self.vehicles:
            other_lane = self.lanes[other.lane_id]
            if other.lane_id == lane_id:
                if other.distance_along < other.length + spawn_buffer:
                    return False
                continue
            if other_lane.queue_group != lane.queue_group:
                continue
            queue_clear_distance = other_lane.queue_release_distance + other.length + spawn_buffer
            if other.distance_along < queue_clear_distance:
                return False
        return True

    def _make_vehicle(self, approach: Approach, route: RouteType) -> VehicleStateModel:
        lane_ids = self._lane_ids_for_route(approach, route)
        if not lane_ids:
            raise ValueError(f"No lane path defined for {approach.lower()} {route}.")
        return self._make_vehicle_for_lane(lane_ids[0])

    def _lane_pose_at_distance(
        self,
        lane: LaneDefinition,
        distance_along: float,
    ) -> tuple[Point2D, Point2D, float, float | None, float | None, Point2D | None]:
        clamped_distance = _clamp(distance_along, 0.0, lane.path.length)
        if isinstance(lane.path, CircularArcPath):
            angle = lane.path.arc.angle_at_distance(clamped_distance)
            position = Point2D(
                x=lane.path.arc.center.x + (lane.path.arc.radius * math.cos(angle)),
                y=lane.path.arc.center.y + (lane.path.arc.radius * math.sin(angle)),
            )
            tangent = lane.path.arc.tangent_at_distance(clamped_distance)
            heading = lane.path.arc.heading_at_distance(clamped_distance)
            return (
                position,
                tangent,
                heading,
                angle,
                lane.path.arc.radius,
                lane.path.arc.center,
            )

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

    def _apply_vehicle_pose(
        self,
        vehicle: VehicleStateModel,
        lane: LaneDefinition,
        distance_along: float,
        *,
        speed: float,
    ) -> None:
        clamped_distance = _clamp(distance_along, 0.0, lane.path.length)
        position, tangent, heading, arc_angle, arc_radius, arc_center = self._lane_pose_at_distance(
            lane,
            clamped_distance,
        )
        vehicle.position = position
        vehicle.distance_along = clamped_distance
        vehicle.progress = clamped_distance / lane.path.length
        vehicle.heading = heading
        vehicle.velocity_x = tangent.x * speed
        vehicle.velocity_y = tangent.y * speed
        vehicle.arc_angle = arc_angle
        vehicle.arc_radius = arc_radius
        vehicle.arc_center = arc_center

    def _make_vehicle_for_lane(self, lane_id: str, *, emergency: bool = False) -> VehicleStateModel:
        lane = self.lanes[lane_id]
        start_position, _, heading, arc_angle, arc_radius, arc_center = self._lane_pose_at_distance(lane, 0.0)
        self._vehicle_index += 1
        color = VEHICLE_COLOR_POOL[self._color_cursor % len(VEHICLE_COLOR_POOL)]
        self._color_cursor += 1
        length = round(_lerp(VEHICLE_MIN_LENGTH, VEHICLE_MAX_LENGTH, self._rng.random()), 3)
        width = round(_lerp(VEHICLE_MIN_WIDTH, VEHICLE_MAX_WIDTH, self._rng.random()), 3)
        if lane.kind == "slip" or lane.movement == "LEFT":
            cruise_speed = round(_lerp(SLIP_SPEED_MIN, SLIP_SPEED_MAX, self._rng.random()), 3)
            route: RouteType = "left"
        elif lane.movement == "RIGHT":
            cruise_speed = round(_lerp(RIGHT_SPEED_MIN, RIGHT_SPEED_MAX, self._rng.random()), 3)
            route: RouteType = "right"
        else:
            cruise_speed = round(_lerp(STRAIGHT_SPEED_MIN, STRAIGHT_SPEED_MAX, self._rng.random()), 3)
            route: RouteType = "straight"

        kind: VehicleKind = "car"
        has_siren = False
        priority = 0
        if emergency:
            kind = "ambulance"
            has_siren = True
            priority = 2
            color = "#f8fafc"
            cruise_speed = round(cruise_speed * 1.08, 3)
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
            target_crosswalk=pedestrian.target_crosswalk,
            crosswalk_id=pedestrian.crosswalk_id,
            road_direction=pedestrian.road_direction,
            progress=round(pedestrian.distance_along / pedestrian.path.length, 4),
            speed=round(pedestrian.speed if pedestrian.state != "WAITING" else 0.0, 4),
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
            shirt_color=pedestrian.shirt_color,
            pants_color=pedestrian.pants_color,
            body_scale=round(pedestrian.body_scale, 3),
        )

    def _is_vehicle_queued(self, vehicle: VehicleStateModel) -> bool:
        lane = self.lanes[vehicle.lane_id]
        if lane.kind == "slip":
            return False
        return (
            vehicle.distance_along <= lane.stop_distance + 0.5
            and (vehicle.state == "STOPPED" or vehicle.wait_time > 0.0 or vehicle.speed <= MIN_MOVEMENT_STEP)
        )

    def _traffic_brain_vehicle_inputs(self) -> List[VehicleTelemetryInput]:
        telemetry: List[VehicleTelemetryInput] = []
        for vehicle in self.vehicles:
            lane = self.lanes[vehicle.lane_id]
            if lane.kind == "slip":
                continue
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

    def _crosswalk_available_for_spawn(self, crosswalk_id: str) -> bool:
        return not any(pedestrian.crosswalk_id == crosswalk_id for pedestrian in self.pedestrians)

    def _make_pedestrian(
        self,
        crosswalk_id: str,
        *,
        start_from_start: bool | None = None,
    ) -> PedestrianStateModel:
        crosswalk = self.crosswalks[crosswalk_id]
        crossing = _crosswalk_movement_direction(crosswalk)
        forward = crosswalk.movement
        if start_from_start is None:
            start_from_start = self._rng.random() < 0.5
        direction = forward if start_from_start else Point2D(-forward.x, -forward.y)
        path_start = crosswalk.start if start_from_start else crosswalk.end
        path_end = crosswalk.end if start_from_start else crosswalk.start
        sidewalk_start = Point2D(
            path_start.x - (direction.x * PEDESTRIAN_SIDEWALK_OFFSET),
            path_start.y - (direction.y * PEDESTRIAN_SIDEWALK_OFFSET),
        )
        sidewalk_end = Point2D(
            path_end.x + (direction.x * PEDESTRIAN_SIDEWALK_OFFSET),
            path_end.y + (direction.y * PEDESTRIAN_SIDEWALK_OFFSET),
        )
        path = PolylinePath.from_points((sidewalk_start, path_start, path_end, sidewalk_end))
        crosswalk_entry_distance = _distance(path.points[0], path_start)
        crosswalk_exit_distance = crosswalk_entry_distance + _distance(path_start, path_end)
        is_elderly = self._rng.random() < 0.18
        body_scale = round(_lerp(0.92, 1.08, self._rng.random()), 3)
        if is_elderly:
            body_scale = round(min(body_scale, 0.98), 3)
        base_speed = _lerp(PEDESTRIAN_MIN_SPEED, PEDESTRIAN_MAX_SPEED, self._rng.random())
        walking_speed = round(base_speed * (0.82 if is_elderly else 1.0), 3)
        self._pedestrian_index += 1
        position = path.point_at_distance(0.0)
        look_angle = math.atan2(direction.x, direction.y)
        return PedestrianStateModel(
            id=f"ped-{self._pedestrian_index}",
            crossing=crossing,
            target_crosswalk=crosswalk_id,
            crosswalk_id=crosswalk_id,
            road_direction=crosswalk.road_direction,
            path=path,
            distance_along=0.0,
            speed=walking_speed,
            velocity_x=0.0,
            velocity_y=0.0,
            position=position,
            state="WAITING",
            wait_time=0.0,
            is_elderly=is_elderly,
            is_impatient=self._rng.random() < 0.22,
            risky_crossing=False,
            look_angle=look_angle,
            shirt_color=PEDESTRIAN_SHIRT_COLORS[self._rng.randrange(len(PEDESTRIAN_SHIRT_COLORS))],
            pants_color=PEDESTRIAN_PANTS_COLORS[self._rng.randrange(len(PEDESTRIAN_PANTS_COLORS))],
            body_scale=body_scale,
            crosswalk_entry_distance=crosswalk_entry_distance,
            crosswalk_exit_distance=crosswalk_exit_distance,
        )

    def _spawn_pedestrian(self, crossing: RoadDirection | None = None, *, crosswalk_id: str | None = None) -> bool:
        if len(self.pedestrians) >= max(0, self.config.max_pedestrians):
            return False

        if crosswalk_id is not None:
            candidate_ids = [crosswalk_id]
        else:
            desired_crossing = crossing or ("EW" if self._rng.random() < 0.5 else "NS")
            candidate_ids = [
                identifier
                for identifier, crosswalk in self.crosswalks.items()
                if _crosswalk_movement_direction(crosswalk) == desired_crossing
            ]
            self._rng.shuffle(candidate_ids)

        for candidate_id in candidate_ids:
            if not self._crosswalk_available_for_spawn(candidate_id):
                continue
            pedestrian = self._make_pedestrian(candidate_id)
            self.pedestrians.append(pedestrian)
            self._pedestrian_spawn_timer = self._pedestrian_spawn_interval()
            self._log("INFO", f"Spawned pedestrian for {pedestrian.crossing} crossing at {candidate_id}.")
            return True

        self._pedestrian_spawn_timer = 0.8
        return False

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
            phase_crossings={direction: None for direction in SIGNAL_ORDER},
            phase_order=SIGNAL_ORDER,
            unserved_demand_time=self.signal_controller.unserved_demand_time,
            processed_by_approach=self._vehicles_processed_by_approach_last_tick,
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
                "pedestrian_demand": 0.0,
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
            signals[approach] = GREEN if approach == self.signal_controller.current_green_direction else RED

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

    def _pedestrian_crossing_allowed(self, crossing: RoadDirection) -> bool:
        return crossing == _pedestrian_crossing_for_approach(self.signal_controller.current_green_direction)

    def _pedestrian_occupies_crosswalk(self, pedestrian: PedestrianStateModel) -> bool:
        return (
            pedestrian.state == "CROSSING"
            and pedestrian.distance_along >= pedestrian.crosswalk_entry_distance - PEDESTRIAN_ENTRY_EPSILON
            and pedestrian.distance_along < pedestrian.crosswalk_exit_distance - PEDESTRIAN_ENTRY_EPSILON
        )

    def _crosswalk_is_active(self, crosswalk_id: str) -> bool:
        return any(
            pedestrian.crosswalk_id == crosswalk_id and self._pedestrian_occupies_crosswalk(pedestrian)
            for pedestrian in self.pedestrians
        )

    def _crosswalk_has_vehicle_commitment(self, crosswalk_id: str) -> bool:
        for vehicle in self.vehicles:
            lane = self.lanes[vehicle.lane_id]
            if lane.kind == "slip":
                continue
            if lane.stop_crosswalk_id != crosswalk_id:
                continue
            crosswalk_distance = _distance(lane.path.points[0], lane.crosswalk_start)
            vehicle_front = vehicle.distance_along + (vehicle.length / 2.0)
            if vehicle_front >= lane.stop_distance - STOP_LINE_BUFFER and vehicle.distance_along < crosswalk_distance:
                return True
        return False

    def _shared_lane_spacing_limit(
        self,
        vehicle: VehicleStateModel,
        lane: LaneDefinition,
        queue_group_vehicles: Dict[str, List[VehicleStateModel]],
    ) -> float:
        if vehicle.distance_along >= lane.queue_release_distance - MIN_MOVEMENT_STEP:
            return math.inf

        spacing_limit = math.inf
        for other in queue_group_vehicles.get(lane.queue_group, []):
            if other.id == vehicle.id or other.lane_id == vehicle.lane_id:
                continue
            if other.distance_along <= vehicle.distance_along:
                continue
            other_lane = self.lanes[other.lane_id]
            shared_leader_distance = min(other.distance_along, other_lane.queue_release_distance)
            spacing_limit = min(
                spacing_limit,
                shared_leader_distance - (((other.length + vehicle.length) / 2.0) + FOLLOW_GAP),
            )
        return spacing_limit

    def _merge_spacing_limit(
        self,
        vehicle: VehicleStateModel,
        lane: LaneDefinition,
        merge_group_vehicles: Dict[str, List[VehicleStateModel]],
    ) -> float:
        if lane.merge_group is None or lane.merge_distance is None:
            return math.inf

        distance_to_merge = lane.merge_distance - vehicle.distance_along
        if distance_to_merge > MERGE_APPROACH_DISTANCE:
            return math.inf

        vehicle_shared_progress = vehicle.distance_along - lane.merge_distance
        spacing_limit = math.inf
        for other in merge_group_vehicles.get(lane.merge_group, []):
            if other.id == vehicle.id or other.lane_id == vehicle.lane_id:
                continue
            other_lane = self.lanes[other.lane_id]
            if other_lane.merge_distance is None:
                continue
            other_distance_to_merge = other_lane.merge_distance - other.distance_along
            if other_distance_to_merge > MERGE_APPROACH_DISTANCE:
                continue
            other_shared_progress = other.distance_along - other_lane.merge_distance
            if other_shared_progress <= vehicle_shared_progress:
                continue
            equivalent_leader_distance = lane.merge_distance + other_shared_progress
            spacing_limit = min(
                spacing_limit,
                equivalent_leader_distance - (((other.length + vehicle.length) / 2.0) + FOLLOW_GAP),
            )
        return spacing_limit

    def update_signals(self, dt: float) -> None:
        next_direction = self.signal_controller.update(dt, intersection_clear=self._intersection_clear())
        self.current_state = self.signal_controller.state
        if next_direction is not None:
            self._log("INFO", f"Green switched to {next_direction.lower()} approach.")

    def update_vehicles(self, dt: float) -> None:
        if dt <= 0.0:
            return

        self._vehicle_spawn_timer -= dt
        while self._vehicle_spawn_timer <= 0.0 and len(self.vehicles) < self.config.max_vehicles:
            self._spawn_vehicle()

        lanes_to_vehicles: Dict[str, List[VehicleStateModel]] = {}
        for vehicle in self.vehicles:
            lanes_to_vehicles.setdefault(vehicle.lane_id, []).append(vehicle)
        queue_group_vehicles: Dict[str, List[VehicleStateModel]] = {}
        merge_group_vehicles: Dict[str, List[VehicleStateModel]] = {}
        for vehicle in self.vehicles:
            lane = self.lanes[vehicle.lane_id]
            queue_group_vehicles.setdefault(lane.queue_group, []).append(vehicle)
            if lane.merge_group is not None:
                merge_group_vehicles.setdefault(lane.merge_group, []).append(vehicle)

        survivors: List[VehicleStateModel] = []
        for lane_id, lane_vehicles in lanes_to_vehicles.items():
            lane = self.lanes[lane_id]
            lane_vehicles.sort(key=lambda item: item.distance_along, reverse=True)
            leader_distance = math.inf
            leader_length = VEHICLE_MAX_LENGTH
            leader_speed = 0.0

            for vehicle in lane_vehicles:
                allowed_distance = lane.path.length
                signal_controlled = lane.kind != "slip"
                can_move = True if not signal_controlled else self.signal_controller.can_vehicle_move(lane.direction, vehicle.route)
                if signal_controlled and vehicle.distance_along < lane.stop_distance and self._crosswalk_is_active(lane.stop_crosswalk_id):
                    allowed_distance = min(
                        allowed_distance,
                        max(0.0, lane.stop_distance - ((vehicle.length / 2.0) + STOP_LINE_BUFFER)),
                    )
                if signal_controlled and vehicle.distance_along < lane.stop_distance and not can_move:
                    allowed_distance = min(
                        allowed_distance,
                        max(0.0, lane.stop_distance - ((vehicle.length / 2.0) + STOP_LINE_BUFFER)),
                    )

                if leader_distance < math.inf:
                    spacing_limit = leader_distance - (((leader_length + vehicle.length) / 2.0) + FOLLOW_GAP)
                    allowed_distance = min(allowed_distance, spacing_limit)

                allowed_distance = min(
                    allowed_distance,
                    self._shared_lane_spacing_limit(vehicle, lane, queue_group_vehicles),
                )
                allowed_distance = min(
                    allowed_distance,
                    self._merge_spacing_limit(vehicle, lane, merge_group_vehicles),
                )

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
        while (
            self._pedestrian_spawn_timer <= 0.0
            and len(self.pedestrians) < min(max(0, self.config.max_pedestrians), len(self.crosswalks))
        ):
            if not self._spawn_pedestrian():
                break

        survivors: List[PedestrianStateModel] = []
        for pedestrian in self.pedestrians:
            if pedestrian.state == "WAITING":
                pedestrian.wait_time += dt
                pedestrian.velocity_x = 0.0
                pedestrian.velocity_y = 0.0
                if (
                    self._pedestrian_crossing_allowed(pedestrian.crossing)
                    and not self._crosswalk_has_vehicle_commitment(pedestrian.crosswalk_id)
                ):
                    pedestrian.state = "CROSSING"
                    pedestrian.wait_time = 0.0

            if pedestrian.state in {"CROSSING", "EXITING"}:
                next_distance = min(pedestrian.path.length, pedestrian.distance_along + (pedestrian.speed * dt))
                tangent = pedestrian.path.tangent_at_distance(next_distance)
                actual_speed = (next_distance - pedestrian.distance_along) / dt
                pedestrian.distance_along = next_distance
                pedestrian.position = pedestrian.path.point_at_distance(next_distance)
                pedestrian.velocity_x = tangent.x * actual_speed
                pedestrian.velocity_y = tangent.y * actual_speed
                pedestrian.look_angle = math.atan2(tangent.x, tangent.y)
                if pedestrian.state == "CROSSING" and next_distance >= pedestrian.crosswalk_exit_distance - PEDESTRIAN_ENTRY_EPSILON:
                    pedestrian.state = "EXITING"
                if next_distance >= pedestrian.path.length - MIN_MOVEMENT_STEP:
                    continue

            survivors.append(pedestrian)

        self.pedestrians = survivors

    def compute_metrics(self, dt: float) -> None:
        active_vehicles = len(self.vehicles)
        queued_vehicles = sum(1 for vehicle in self.vehicles if vehicle.state == "STOPPED")
        emergency_vehicles = sum(1 for vehicle in self.vehicles if vehicle.has_siren or vehicle.kind != "car")
        active_pedestrians = len(self.pedestrians)
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
            active_nodes=4,
            detections=queued_vehicles + active_pedestrians,
            bandwidth_savings=4.0,
        )

    def _log(self, level: str, message: str) -> None:
        self.events.appendleft(EventView(timestamp=round(self.time, 3), level=level, message=message))
