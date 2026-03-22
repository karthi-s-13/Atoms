"""Pure traffic simulation engine with single-direction phases and buffered motion data."""

from __future__ import annotations

import math
import random
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List

from shared.contracts import (
    Approach,
    CrosswalkView,
    EventView,
    LaneView,
    MetricsView,
    PedestrianView,
    Point2D,
    RoadDirection,
    RouteType,
    SignalState,
    SimulationConfig,
    SnapshotView,
    VehicleKind,
    VehicleView,
)


FRAME_DT = 0.016
PHASES: tuple[Approach, ...] = ("NORTH", "SOUTH", "EAST", "WEST")
GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"
SAFE_DISTANCE = 7.0
STOP_LINE_OFFSET = 5.0
MIN_GREEN = 4.5
MAX_GREEN = 11.0
YELLOW_TIME = 1.6
PEDESTRIAN_MIN = 4.2
PEDESTRIAN_MAX = 10.0
EMERGENCY_EXTENSION = 4.0
DEADLOCK_TICK_LIMIT = 45
EMERGENCY_GAP_FACTOR = 0.62

INTERSECTION_ENTRY_POINTS: dict[Approach, Point2D] = {
    "NORTH": Point2D(0.0, 8.0),
    "SOUTH": Point2D(4.0, -8.0),
    "EAST": Point2D(8.0, 0.0),
    "WEST": Point2D(-8.0, -4.0),
}
OUTBOUND_START_POINTS: dict[Approach, Point2D] = {
    "NORTH": Point2D(4.0, 8.0),
    "SOUTH": Point2D(0.0, -8.0),
    "EAST": Point2D(8.0, -4.0),
    "WEST": Point2D(-8.0, 0.0),
}
OUTBOUND_END_POINTS: dict[Approach, Point2D] = {
    "NORTH": Point2D(4.0, 72.0),
    "SOUTH": Point2D(0.0, -72.0),
    "EAST": Point2D(72.0, -4.0),
    "WEST": Point2D(-72.0, 0.0),
}
OUTBOUND_DIRECTION_VECTORS: dict[Approach, Point2D] = {
    "NORTH": Point2D(0.0, 1.0),
    "SOUTH": Point2D(0.0, -1.0),
    "EAST": Point2D(1.0, 0.0),
    "WEST": Point2D(-1.0, 0.0),
}

VEHICLE_COLORS: dict[VehicleKind, str] = {
    "car": "#38bdf8",
    "ambulance": "#f8fafc",
    "firetruck": "#ef4444",
    "police": "#60a5fa",
}
VEHICLE_PRIORITIES: dict[VehicleKind, int] = {
    "car": 0,
    "ambulance": 100,
    "firetruck": 80,
    "police": 60,
}
CRUISE_SPEEDS: dict[VehicleKind, float] = {
    "car": 10.5,
    "ambulance": 15.0,
    "firetruck": 13.5,
    "police": 14.2,
}

STRAIGHT_EXIT: dict[Approach, Approach] = {
    "NORTH": "SOUTH",
    "SOUTH": "NORTH",
    "EAST": "WEST",
    "WEST": "EAST",
}
LEFT_EXIT: dict[Approach, Approach] = {
    "NORTH": "EAST",
    "SOUTH": "WEST",
    "EAST": "NORTH",
    "WEST": "SOUTH",
}
RIGHT_EXIT: dict[Approach, Approach] = {
    "NORTH": "WEST",
    "SOUTH": "EAST",
    "EAST": "SOUTH",
    "WEST": "NORTH",
}


def _lerp(a: float, b: float, t: float) -> float:
    return a + ((b - a) * t)


def _distance(a: Point2D, b: Point2D) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def _normalize(dx: float, dy: float) -> Point2D:
    magnitude = math.hypot(dx, dy) or 1.0
    return Point2D(dx / magnitude, dy / magnitude)


def _advance_point(point: Point2D, direction: Point2D, distance: float) -> Point2D:
    return Point2D(point.x + (direction.x * distance), point.y + (direction.y * distance))


def _project_to_segment(point: Point2D, start: Point2D, end: Point2D) -> Point2D:
    dx = end.x - start.x
    dy = end.y - start.y
    segment_length_sq = (dx * dx) + (dy * dy)
    if segment_length_sq <= 1e-9:
        return Point2D(start.x, start.y)
    projection = (((point.x - start.x) * dx) + ((point.y - start.y) * dy)) / segment_length_sq
    projection = max(0.0, min(1.0, projection))
    return Point2D(start.x + (dx * projection), start.y + (dy * projection))


def _distance_along_segment(point: Point2D, start: Point2D, end: Point2D) -> float:
    projected = _project_to_segment(point, start, end)
    return _distance(start, projected)


@dataclass
class BezierPath:
    start: Point2D
    control: Point2D
    end: Point2D
    length: float

    @classmethod
    def from_points(cls, start: Point2D, control: Point2D, end: Point2D) -> "BezierPath":
        samples = [cls._point(start, control, end, step / 32.0) for step in range(33)]
        total = 0.0
        for current, nxt in zip(samples, samples[1:]):
            total += math.hypot(nxt.x - current.x, nxt.y - current.y)
        return cls(start=start, control=control, end=end, length=max(total, 1.0))

    @staticmethod
    def _point(start: Point2D, control: Point2D, end: Point2D, t: float) -> Point2D:
        one_minus = 1.0 - t
        return Point2D(
            x=(one_minus * one_minus * start.x) + (2 * one_minus * t * control.x) + (t * t * end.x),
            y=(one_minus * one_minus * start.y) + (2 * one_minus * t * control.y) + (t * t * end.y),
        )

    def point_at(self, progress: float) -> Point2D:
        return self._point(self.start, self.control, self.end, max(0.0, min(1.0, progress)))

    def tangent_at(self, progress: float) -> Point2D:
        t = max(0.0, min(1.0, progress))
        one_minus = 1.0 - t
        return Point2D(
            x=(2 * one_minus * (self.control.x - self.start.x)) + (2 * t * (self.end.x - self.control.x)),
            y=(2 * one_minus * (self.control.y - self.start.y)) + (2 * t * (self.end.y - self.control.y)),
        )

    def nearest_progress(self, point: Point2D) -> float:
        best_progress = 0.0
        best_distance = float("inf")
        for step in range(65):
            progress = step / 64.0
            sample = self.point_at(progress)
            distance = math.hypot(sample.x - point.x, sample.y - point.y)
            if distance < best_distance:
                best_distance = distance
                best_progress = progress
        return best_progress


@dataclass
class LaneDefinition:
    id: str
    approach: Approach
    start: Point2D
    end: Point2D
    crosswalk_id: str
    stop_line_position: Point2D
    direction_vector: Point2D
    entry_point: Point2D
    stop_distance: float
    entry_distance: float

    def to_view(self) -> LaneView:
        return LaneView(
            id=self.id,
            approach=self.approach,
            start=self.start,
            end=self.end,
            crosswalk_id=self.crosswalk_id,
            stop_line_position=self.stop_line_position,
        )


@dataclass
class CrosswalkDefinition:
    id: str
    road_direction: RoadDirection
    start: Point2D
    end: Point2D
    movement: Point2D

    @property
    def length(self) -> float:
        return math.hypot(self.end.x - self.start.x, self.end.y - self.start.y)

    def point_at(self, progress: float) -> Point2D:
        return Point2D(
            x=_lerp(self.start.x, self.end.x, max(0.0, min(1.0, progress))),
            y=_lerp(self.start.y, self.end.y, max(0.0, min(1.0, progress))),
        )

    def to_view(self) -> CrosswalkView:
        return CrosswalkView(
            id=self.id,
            road_direction=self.road_direction,
            start=self.start,
            end=self.end,
            movement=self.movement,
        )


@dataclass
class VehicleState:
    id: str
    lane_id: str
    approach: Approach
    route: RouteType
    path: BezierPath
    stop_progress: float
    progress: float
    speed: float
    cruise_speed: float
    kind: VehicleKind
    has_siren: bool
    priority: int
    state: str
    wait_time: float
    color: str
    position: Point2D
    direction_vector: Point2D
    entry_point: Point2D
    exit_point: Point2D
    exit_end: Point2D
    exit_direction_vector: Point2D
    stop_distance: float
    approach_length: float
    turn_length: float
    exit_length: float
    total_length: float
    approach_distance: float = 0.0
    turn_distance: float = 0.0
    exit_distance: float = 0.0
    segment: str = "APPROACH"
    heading: float = 0.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0


@dataclass
class PedestrianStateModel:
    id: str
    crosswalk_id: str
    road_direction: RoadDirection
    progress: float
    speed: float
    wait_time: float
    state: str = "WAITING"
    velocity_x: float = 0.0
    velocity_y: float = 0.0


class TrafficSimulationEngine:
    """Pure logic engine for a four-way signalized intersection."""

    def __init__(self) -> None:
        self.random = random.Random(24)
        self.config = SimulationConfig()
        self.crosswalks = self._build_crosswalks()
        self.lanes = self._build_lanes()
        self.spawn_accumulators: Dict[Approach, float] = defaultdict(float)
        self.pedestrian_spawn_accumulator = 0.0
        self.frame = 0
        self.time = 0.0
        self.active_direction: Approach | None = "NORTH"
        self.next_direction: Approach | str | None = None
        self.phase_state: str = GREEN
        self.phase_elapsed = 0.0
        self.pedestrian_phase_active = False
        self.processed_vehicles = 0
        self.smoothed_throughput = 0.0
        self.vehicles: List[VehicleState] = []
        self.pedestrians: List[PedestrianStateModel] = []
        self.events: Deque[EventView] = deque(maxlen=40)
        self._vehicle_index = 0
        self._pedestrian_index = 0
        self.ticks_without_movement = 0
        self.vehicles_moved_last_tick = 0
        self.metrics = MetricsView(0.0, 0.0, 0, 0.0, 0, 0, 0, 0, 12, 0, 0.0)
        self._log("INFO", "Production traffic engine initialized.")

    def reset(self) -> None:
        self.spawn_accumulators = defaultdict(float)
        self.pedestrian_spawn_accumulator = 0.0
        self.frame = 0
        self.time = 0.0
        self.active_direction = "NORTH"
        self.next_direction = None
        self.phase_state = GREEN
        self.phase_elapsed = 0.0
        self.pedestrian_phase_active = False
        self.processed_vehicles = 0
        self.smoothed_throughput = 0.0
        self.vehicles = []
        self.pedestrians = []
        self._vehicle_index = 0
        self._pedestrian_index = 0
        self.events.clear()
        self.ticks_without_movement = 0
        self.vehicles_moved_last_tick = 0
        self.metrics = MetricsView(0.0, 0.0, 0, 0.0, 0, 0, 0, 0, 12, 0, 0.0)
        self._log("INFO", "Simulation reset.")

    def update_config(self, values: Dict[str, object]) -> SimulationConfig:
        if "traffic_intensity" in values:
            self.config.traffic_intensity = max(0.2, min(3.5, float(values["traffic_intensity"])))
        if "ambulance_frequency" in values:
            self.config.ambulance_frequency = max(0.0, min(1.0, float(values["ambulance_frequency"])))
        if "speed_multiplier" in values:
            self.config.speed_multiplier = max(0.25, min(4.0, float(values["speed_multiplier"])))
        if "paused" in values:
            self.config.paused = bool(values["paused"])
        if "max_vehicles" in values:
            self.config.max_vehicles = max(8, min(120, int(values["max_vehicles"])))
        if "max_pedestrians" in values:
            self.config.max_pedestrians = max(2, min(60, int(values["max_pedestrians"])))
        if "ai_mode" in values:
            mode = str(values["ai_mode"]).strip().lower()
            self.config.ai_mode = "fixed" if mode == "fixed" else "emergency" if mode == "emergency" else "adaptive"
        return self.config

    def tick(self, dt: float = FRAME_DT) -> Dict[str, object]:
        sim_dt = max(FRAME_DT, float(dt))
        if self.config.paused:
            sim_dt = 0.0
        else:
            sim_dt *= self.config.speed_multiplier

        self.frame += 1
        if sim_dt > 0.0:
            self._ensure_live_phase()
            self.time += sim_dt
            self.update_signals(sim_dt)
            self.spawn_vehicles(sim_dt)
            self.update_vehicles(sim_dt)
            self.update_pedestrians(sim_dt)
            if not self.vehicles:
                self.vehicles.append(self._make_vehicle(self.active_direction or "NORTH"))
        self.compute_metrics(sim_dt)
        return self.snapshot().to_dict()

    def get_state(self) -> Dict[str, object]:
        return self.snapshot().to_dict()

    def snapshot(self) -> SnapshotView:
        return SnapshotView(
            frame=self.frame,
            timestamp=round(self.time, 3),
            active_direction=self.active_direction,
            vehicles=[self._vehicle_view(vehicle) for vehicle in self.vehicles],
            pedestrians=[self._pedestrian_view(pedestrian) for pedestrian in self.pedestrians],
            lanes=[lane.to_view() for lane in self.lanes.values()],
            crosswalks=[crosswalk.to_view() for crosswalk in self.crosswalks.values()],
            signals=self._signal_snapshot(),
            pedestrian_phase_active=self.pedestrian_phase_active,
            metrics=self.metrics,
            events=list(self.events),
            config=self.config,
        )

    def _build_crosswalks(self) -> Dict[str, CrosswalkDefinition]:
        return {
            "north_crosswalk": CrosswalkDefinition(
                id="north_crosswalk",
                road_direction="NS",
                start=Point2D(-12.0, 12.0),
                end=Point2D(12.0, 12.0),
                movement=Point2D(1.0, 0.0),
            ),
            "south_crosswalk": CrosswalkDefinition(
                id="south_crosswalk",
                road_direction="NS",
                start=Point2D(12.0, -12.0),
                end=Point2D(-12.0, -12.0),
                movement=Point2D(-1.0, 0.0),
            ),
            "east_crosswalk": CrosswalkDefinition(
                id="east_crosswalk",
                road_direction="EW",
                start=Point2D(12.0, -12.0),
                end=Point2D(12.0, 12.0),
                movement=Point2D(0.0, 1.0),
            ),
            "west_crosswalk": CrosswalkDefinition(
                id="west_crosswalk",
                road_direction="EW",
                start=Point2D(-12.0, 12.0),
                end=Point2D(-12.0, -12.0),
                movement=Point2D(0.0, -1.0),
            ),
        }

    def _build_lanes(self) -> Dict[str, LaneDefinition]:
        return {
            "lane_north": LaneDefinition(
                "lane_north",
                "NORTH",
                Point2D(0.0, 72.0),
                Point2D(0.0, -72.0),
                "north_crosswalk",
                Point2D(0.0, 17.0),
                Point2D(0.0, -1.0),
                INTERSECTION_ENTRY_POINTS["NORTH"],
                _distance(Point2D(0.0, 72.0), Point2D(0.0, 17.0)),
                _distance(Point2D(0.0, 72.0), INTERSECTION_ENTRY_POINTS["NORTH"]),
            ),
            "lane_south": LaneDefinition(
                "lane_south",
                "SOUTH",
                Point2D(4.0, -72.0),
                Point2D(4.0, 72.0),
                "south_crosswalk",
                Point2D(4.0, -17.0),
                Point2D(0.0, 1.0),
                INTERSECTION_ENTRY_POINTS["SOUTH"],
                _distance(Point2D(4.0, -72.0), Point2D(4.0, -17.0)),
                _distance(Point2D(4.0, -72.0), INTERSECTION_ENTRY_POINTS["SOUTH"]),
            ),
            "lane_east": LaneDefinition(
                "lane_east",
                "EAST",
                Point2D(72.0, 0.0),
                Point2D(-72.0, 0.0),
                "east_crosswalk",
                Point2D(17.0, 0.0),
                Point2D(-1.0, 0.0),
                INTERSECTION_ENTRY_POINTS["EAST"],
                _distance(Point2D(72.0, 0.0), Point2D(17.0, 0.0)),
                _distance(Point2D(72.0, 0.0), INTERSECTION_ENTRY_POINTS["EAST"]),
            ),
            "lane_west": LaneDefinition(
                "lane_west",
                "WEST",
                Point2D(-72.0, -4.0),
                Point2D(72.0, -4.0),
                "west_crosswalk",
                Point2D(-17.0, -4.0),
                Point2D(1.0, 0.0),
                INTERSECTION_ENTRY_POINTS["WEST"],
                _distance(Point2D(-72.0, -4.0), Point2D(-17.0, -4.0)),
                _distance(Point2D(-72.0, -4.0), INTERSECTION_ENTRY_POINTS["WEST"]),
            ),
        }

    def _signal_snapshot(self) -> Dict[str, SignalState]:
        if self.pedestrian_phase_active or self.active_direction is None:
            direction_states = {phase: RED for phase in PHASES}
        else:
            direction_states = {
                phase: (self.phase_state if phase == self.active_direction else RED)
                for phase in PHASES
            }
        direction_states["PED"] = GREEN if self.pedestrian_phase_active else RED
        return direction_states

    def _phase_score(self, approach: Approach) -> float:
        queued = 0
        total_wait = 0.0
        for vehicle in self.vehicles:
            if vehicle.approach != approach:
                continue
            if vehicle.segment != "APPROACH":
                continue
            queued += 1
            total_wait += vehicle.wait_time
        return (queued * 2.0) + (total_wait * 1.5)

    def _next_fixed_direction(self) -> Approach:
        current_index = PHASES.index(self.active_direction or "NORTH")
        return PHASES[(current_index + 1) % len(PHASES)]

    def _highest_priority_siren(self) -> Approach | None:
        best: tuple[int, float, Approach] | None = None
        for vehicle in self.vehicles:
            if not vehicle.has_siren:
                continue
            if vehicle.segment != "APPROACH":
                continue
            candidate = (vehicle.priority, vehicle.wait_time, vehicle.approach)
            if best is None or candidate > best:
                best = candidate
        return best[2] if best else None

    def _highest_priority_emergency_vehicle(self) -> Approach | None:
        best: tuple[int, float, Approach] | None = None
        for vehicle in self.vehicles:
            if vehicle.priority <= 0:
                continue
            if vehicle.segment != "APPROACH":
                continue
            candidate = (vehicle.priority, vehicle.wait_time, vehicle.approach)
            if best is None or candidate > best:
                best = candidate
        return best[2] if best else None

    def _select_adaptive_direction(self) -> Approach:
        scores = {phase: self._phase_score(phase) for phase in PHASES}
        return max(PHASES, key=lambda phase: (scores[phase], -PHASES.index(phase)))

    def _choose_next_direction(self) -> Approach:
        siren_direction = self._highest_priority_siren()
        if siren_direction:
            return siren_direction
        if self.config.ai_mode == "fixed":
            return self._next_fixed_direction()
        if self.config.ai_mode == "emergency":
            emergency_direction = self._highest_priority_emergency_vehicle()
            if emergency_direction:
                return emergency_direction
        return self._select_adaptive_direction()

    def _ensure_live_phase(self) -> None:
        if self.pedestrian_phase_active:
            return
        if self.active_direction in PHASES:
            return
        self._force_direction(self.random.choice(PHASES), "inactive signal recovery")

    def _force_direction(self, direction: Approach, reason: str) -> None:
        self.active_direction = direction
        self.phase_state = GREEN
        self.phase_elapsed = 0.0
        self.next_direction = None
        self.pedestrian_phase_active = False
        self._log("WARN", f"{direction} forced GREEN ({reason}).")

    def _begin_yellow(self, next_direction: Approach | str | None, reason: str) -> None:
        if self.phase_state == YELLOW:
            return
        self.phase_state = YELLOW
        self.next_direction = next_direction
        self.phase_elapsed = 0.0
        self._log("INFO", f"{self.active_direction or 'ALL_RED'} changed to YELLOW ({reason}).")

    def _activate_direction(self, direction: Approach) -> None:
        self.active_direction = direction
        self.next_direction = None
        self.phase_state = GREEN
        self.phase_elapsed = 0.0
        self.pedestrian_phase_active = False
        self._log("INFO", f"{direction} is now GREEN.")

    def _activate_pedestrian_phase(self) -> None:
        self.active_direction = None
        self.next_direction = None
        self.phase_state = RED
        self.phase_elapsed = 0.0
        self.pedestrian_phase_active = True
        self._log("INFO", "Pedestrian crossing phase active. All vehicle directions forced RED.")

    def _has_waiting_pedestrians(self) -> bool:
        return any(pedestrian.state == "WAITING" for pedestrian in self.pedestrians)

    def _has_crossing_pedestrians(self) -> bool:
        return any(pedestrian.state == "CROSSING" for pedestrian in self.pedestrians)

    def _can_start_pedestrian_phase(self) -> bool:
        if not self._has_waiting_pedestrians():
            return False
        if self._highest_priority_siren():
            return False
        for vehicle in self.vehicles:
            if vehicle.segment != "APPROACH":
                return False
            lane_distance = self._approach_distance(vehicle)
            distance_to_stop = max(0.0, vehicle.stop_distance - lane_distance)
            if lane_distance > vehicle.stop_distance + 0.012:
                return False
            if 0.0 < distance_to_stop < max(7.0, vehicle.speed * 1.35):
                return False
        return True

    def update_signals(self, dt: float) -> None:
        self.phase_elapsed += dt
        emergency_direction = self._highest_priority_siren()

        if self.pedestrian_phase_active:
            if self.phase_elapsed >= PEDESTRIAN_MAX:
                self._log("WARN", "Pedestrian phase timed out. Releasing vehicle flow.")
                self._activate_direction(emergency_direction or self._choose_next_direction())
                return
            if not self._has_crossing_pedestrians() and self.phase_elapsed >= PEDESTRIAN_MIN:
                self._activate_direction(emergency_direction or self._choose_next_direction())
            return

        if self.phase_state == YELLOW:
            if self.phase_elapsed >= YELLOW_TIME:
                if self.next_direction == "PEDESTRIAN":
                    self._activate_pedestrian_phase()
                else:
                    self._activate_direction(self.next_direction or self._choose_next_direction())
            return

        if emergency_direction:
            if self.active_direction != emergency_direction or self.phase_state != GREEN:
                self._force_direction(emergency_direction, "emergency preemption")
                return
            if self.phase_elapsed < MAX_GREEN + EMERGENCY_EXTENSION:
                return

        if self.phase_elapsed >= MIN_GREEN and self._can_start_pedestrian_phase():
            self._begin_yellow("PEDESTRIAN", "pedestrian demand")
            return

        if self.phase_elapsed < MIN_GREEN:
            return

        if self.config.ai_mode == "fixed":
            if self.phase_elapsed >= MAX_GREEN:
                self._begin_yellow(self._next_fixed_direction(), "fixed rotation")
            return

        best_direction = self._choose_next_direction()
        current_score = self._phase_score(self.active_direction or "NORTH")
        best_score = self._phase_score(best_direction)
        if self.phase_elapsed >= MAX_GREEN:
            self._begin_yellow(best_direction, "max green reached")
        elif best_direction != self.active_direction and best_score > current_score + 1.2:
            self._begin_yellow(best_direction, "higher demand")

    def spawn_vehicles(self, dt: float) -> None:
        if len(self.vehicles) >= self.config.max_vehicles:
            return

        base_rate = 0.56 * self.config.traffic_intensity
        for approach in PHASES:
            self.spawn_accumulators[approach] += dt * base_rate
            if self.spawn_accumulators[approach] < 1.0:
                continue
            self.spawn_accumulators[approach] -= 1.0
            if len(self.vehicles) >= self.config.max_vehicles:
                break
            if self._entry_blocked(approach):
                continue
            self.vehicles.append(self._make_vehicle(approach))

        if not self.vehicles and len(self.vehicles) < self.config.max_vehicles:
            self.vehicles.append(self._make_vehicle("NORTH"))

    def _entry_blocked(self, approach: Approach) -> bool:
        for vehicle in self.vehicles:
            if vehicle.approach != approach:
                continue
            if vehicle.segment == "APPROACH" and self._approach_distance(vehicle) < SAFE_DISTANCE:
                return True
        return False

    def _sample_vehicle_kind(self) -> tuple[VehicleKind, bool]:
        emergency_roll = self.random.random()
        if emergency_roll < self.config.ambulance_frequency * 0.28:
            kind = self.random.choices(
                ["ambulance", "firetruck", "police"],
                weights=[0.52, 0.28, 0.20],
                k=1,
            )[0]
            return kind, True
        return "car", False

    def _build_path(self, approach: Approach, route: RouteType) -> tuple[BezierPath, Point2D, Point2D, Point2D, Point2D]:
        lane = self.lanes[f"lane_{approach.lower()}"]
        if route == "straight":
            exit_direction = STRAIGHT_EXIT[approach]
        elif route == "left":
            exit_direction = LEFT_EXIT[approach]
        else:
            exit_direction = RIGHT_EXIT[approach]

        entry_point = lane.entry_point
        exit_point = OUTBOUND_START_POINTS[exit_direction]
        end_point = OUTBOUND_END_POINTS[exit_direction]
        if route == "straight":
            control = Point2D((entry_point.x + exit_point.x) / 2.0, (entry_point.y + exit_point.y) / 2.0)
        elif route == "right":
            control = Point2D(exit_point.x, entry_point.y)
        else:
            control = Point2D(
                (entry_point.x + exit_point.x) / 2.0,
                (entry_point.y + exit_point.y) / 2.0,
            )

        path = BezierPath.from_points(entry_point, control, exit_point)
        return path, entry_point, exit_point, end_point, OUTBOUND_DIRECTION_VECTORS[exit_direction]

    def _make_vehicle(self, approach: Approach) -> VehicleState:
        self._vehicle_index += 1
        kind, has_siren = self._sample_vehicle_kind()
        route = self.random.choices(["straight", "left", "right"], weights=[0.56, 0.24, 0.20], k=1)[0]
        lane = self.lanes[f"lane_{approach.lower()}"]
        path, entry_point, exit_point, exit_end, exit_direction_vector = self._build_path(approach, route)
        approach_length = lane.entry_distance
        turn_length = max(path.length, 1.0)
        exit_length = max(_distance(exit_point, exit_end), 1.0)
        total_length = max(approach_length + turn_length + exit_length, 1.0)
        stop_progress = lane.stop_distance / total_length
        priority = VEHICLE_PRIORITIES[kind] if has_siren else 0
        vehicle = VehicleState(
            id=f"veh-{self._vehicle_index}",
            lane_id=f"lane_{approach.lower()}",
            approach=approach,
            route=route,
            path=path,
            stop_progress=stop_progress,
            progress=0.0,
            speed=CRUISE_SPEEDS[kind] * 0.35,
            cruise_speed=CRUISE_SPEEDS[kind],
            kind=kind,
            has_siren=has_siren,
            priority=priority,
            state="MOVING",
            wait_time=0.0,
            color=VEHICLE_COLORS[kind],
            position=Point2D(lane.start.x, lane.start.y),
            direction_vector=lane.direction_vector,
            entry_point=entry_point,
            exit_point=exit_point,
            exit_end=exit_end,
            exit_direction_vector=exit_direction_vector,
            stop_distance=lane.stop_distance,
            approach_length=approach_length,
            turn_length=turn_length,
            exit_length=exit_length,
            total_length=total_length,
        )
        self._update_vehicle_progress(vehicle)
        self._update_vehicle_kinematics(vehicle)
        self._log("WARN" if has_siren else "INFO", f"{kind.title()} entered from {approach}.")
        return vehicle

    def _vehicle_has_right_of_way(self, vehicle: VehicleState) -> bool:
        if vehicle.segment != "APPROACH":
            return True
        if self.pedestrian_phase_active or self._has_crossing_pedestrians():
            return False
        return self.active_direction == vehicle.approach and self.phase_state == GREEN

    def _update_vehicle_progress(self, vehicle: VehicleState) -> None:
        travelled = vehicle.approach_distance + vehicle.turn_distance + vehicle.exit_distance
        vehicle.progress = min(1.0, travelled / max(vehicle.total_length, 1.0))

    def _approach_distance(self, vehicle: VehicleState) -> float:
        lane = self.lanes[vehicle.lane_id]
        if vehicle.segment == "APPROACH":
            return _distance_along_segment(vehicle.position, lane.start, lane.entry_point)
        if vehicle.segment == "TURNING":
            return lane.entry_distance + min(vehicle.turn_distance, vehicle.turn_length * 0.25)
        return lane.entry_distance + vehicle.turn_length + vehicle.exit_distance

    def _clamp_to_approach_lane(self, vehicle: VehicleState) -> None:
        lane = self.lanes[vehicle.lane_id]
        vehicle.position = _project_to_segment(vehicle.position, lane.start, lane.entry_point)
        vehicle.direction_vector = lane.direction_vector
        vehicle.approach_distance = _distance_along_segment(vehicle.position, lane.start, lane.entry_point)
        self._update_vehicle_progress(vehicle)

    def _clamp_to_exit_lane(self, vehicle: VehicleState) -> None:
        vehicle.position = _project_to_segment(vehicle.position, vehicle.exit_point, vehicle.exit_end)
        vehicle.direction_vector = vehicle.exit_direction_vector
        vehicle.exit_distance = _distance_along_segment(vehicle.position, vehicle.exit_point, vehicle.exit_end)
        self._update_vehicle_progress(vehicle)

    def _advance_vehicle(self, vehicle: VehicleState, distance: float) -> bool:
        remaining = max(0.0, distance)

        while remaining > 1e-9:
            if vehicle.segment == "APPROACH":
                lane = self.lanes[vehicle.lane_id]
                available = max(0.0, lane.entry_distance - vehicle.approach_distance)
                step = min(remaining, available)
                vehicle.position = _advance_point(vehicle.position, lane.direction_vector, step)
                self._clamp_to_approach_lane(vehicle)
                remaining -= step
                if vehicle.approach_distance >= lane.entry_distance - 1e-4:
                    vehicle.segment = "TURNING"
                    vehicle.position = Point2D(vehicle.entry_point.x, vehicle.entry_point.y)
                    vehicle.direction_vector = _normalize(
                        vehicle.path.tangent_at(0.0).x,
                        vehicle.path.tangent_at(0.0).y,
                    )
                    self._update_vehicle_progress(vehicle)
                else:
                    break
            elif vehicle.segment == "TURNING":
                available = max(0.0, vehicle.turn_length - vehicle.turn_distance)
                step = min(remaining, available)
                vehicle.turn_distance += step
                turn_progress = min(1.0, vehicle.turn_distance / max(vehicle.turn_length, 1.0))
                vehicle.position = vehicle.path.point_at(turn_progress)
                remaining -= step
                self._update_vehicle_progress(vehicle)
                if turn_progress >= 1.0 - 1e-6:
                    vehicle.segment = "EXIT"
                    vehicle.position = Point2D(vehicle.exit_point.x, vehicle.exit_point.y)
                    vehicle.direction_vector = vehicle.exit_direction_vector
                else:
                    break
            else:
                available = max(0.0, vehicle.exit_length - vehicle.exit_distance)
                step = min(remaining, available)
                vehicle.position = _advance_point(vehicle.position, vehicle.exit_direction_vector, step)
                self._clamp_to_exit_lane(vehicle)
                remaining -= step
                if vehicle.exit_distance >= vehicle.exit_length - 1e-4:
                    vehicle.progress = 1.0
                    return True
                break

        return vehicle.progress >= 1.0

    def update_vehicles(self, dt: float) -> None:
        buckets: Dict[Approach, List[VehicleState]] = defaultdict(list)
        for vehicle in self.vehicles:
            buckets[vehicle.approach].append(vehicle)

        processed_this_tick = 0
        moved_this_tick = 0
        survivors: List[VehicleState] = []
        for approach, vehicles in buckets.items():
            turning_and_exit = [vehicle for vehicle in vehicles if vehicle.segment != "APPROACH"]
            approach_queue = [vehicle for vehicle in vehicles if vehicle.segment == "APPROACH"]

            for vehicle in turning_and_exit:
                previous_position = Point2D(vehicle.position.x, vehicle.position.y)
                target_speed = vehicle.cruise_speed * (1.08 if vehicle.has_siren else 1.0)
                acceleration = 18.0 if target_speed > vehicle.speed else 24.0
                speed_delta = target_speed - vehicle.speed
                vehicle.speed += max(-acceleration * dt, min(acceleration * dt, speed_delta))

                if self._advance_vehicle(vehicle, vehicle.speed * dt):
                    processed_this_tick += 1
                    self.processed_vehicles += 1
                    continue

                vehicle.state = "TURNING" if vehicle.segment == "TURNING" else "MOVING"
                if _distance(previous_position, vehicle.position) > 1e-5:
                    moved_this_tick += 1
                self._update_vehicle_kinematics(vehicle)
                survivors.append(vehicle)

            approach_queue.sort(key=self._approach_distance, reverse=True)
            leader: VehicleState | None = None
            for vehicle in approach_queue:
                previous_position = Point2D(vehicle.position.x, vehicle.position.y)
                target_speed = vehicle.cruise_speed
                has_right_of_way = self._vehicle_has_right_of_way(vehicle)
                lane = self.lanes[vehicle.lane_id]
                lane_distance = self._approach_distance(vehicle)
                distance_to_stop = max(0.0, lane.stop_distance - lane_distance)

                if not has_right_of_way:
                    if distance_to_stop <= 0.6:
                        vehicle.position = Point2D(lane.stop_line_position.x, lane.stop_line_position.y)
                        vehicle.approach_distance = lane.stop_distance
                        vehicle.progress = vehicle.stop_progress
                        vehicle.speed = 0.0
                        vehicle.wait_time += dt
                        vehicle.state = "WAITING"
                        self._update_vehicle_kinematics(vehicle)
                        survivors.append(vehicle)
                        leader = vehicle
                        continue
                    if lane_distance >= lane.stop_distance - 1e-3:
                        vehicle.position = Point2D(lane.stop_line_position.x, lane.stop_line_position.y)
                        vehicle.approach_distance = lane.stop_distance
                        vehicle.progress = vehicle.stop_progress
                        vehicle.speed = 0.0
                        vehicle.wait_time += dt
                        vehicle.state = "WAITING"
                        self._update_vehicle_kinematics(vehicle)
                        survivors.append(vehicle)
                        leader = vehicle
                        continue
                    braking_window = max(SAFE_DISTANCE * 1.8, vehicle.speed * 1.6)
                    if distance_to_stop <= braking_window:
                        target_speed = min(target_speed, max(0.0, (distance_to_stop - 0.5) * 1.2))

                if leader is not None:
                    emergency_gap = SAFE_DISTANCE * (EMERGENCY_GAP_FACTOR if vehicle.has_siren else 1.0)
                    gap = max(0.0, self._approach_distance(leader) - lane_distance)
                    if gap < emergency_gap:
                        target_speed = min(target_speed, max(0.0, (gap - 1.0) * 0.9), leader.speed)

                acceleration = 16.0 if target_speed > vehicle.speed else 25.0
                speed_delta = target_speed - vehicle.speed
                vehicle.speed += max(-acceleration * dt, min(acceleration * dt, speed_delta))

                if not has_right_of_way and distance_to_stop <= 1.0 and vehicle.speed < 1.0:
                    vehicle.position = Point2D(lane.stop_line_position.x, lane.stop_line_position.y)
                    vehicle.approach_distance = lane.stop_distance
                    vehicle.progress = vehicle.stop_progress
                    vehicle.speed = 0.0
                    vehicle.wait_time += dt
                    vehicle.state = "WAITING"
                    self._update_vehicle_kinematics(vehicle)
                    survivors.append(vehicle)
                    leader = vehicle
                    continue

                move_distance = vehicle.speed * dt
                if not has_right_of_way and lane_distance + move_distance >= lane.stop_distance:
                    move_distance = max(0.0, lane.stop_distance - lane_distance)
                    vehicle.speed = 0.0

                if self._advance_vehicle(vehicle, move_distance):
                    processed_this_tick += 1
                    self.processed_vehicles += 1
                    continue

                if vehicle.speed < 0.8:
                    vehicle.wait_time += dt
                    vehicle.state = "WAITING"
                else:
                    vehicle.state = "TURNING" if vehicle.segment == "TURNING" else "MOVING"

                if _distance(previous_position, vehicle.position) > 1e-5:
                    moved_this_tick += 1
                self._update_vehicle_kinematics(vehicle)
                survivors.append(vehicle)
                leader = vehicle if vehicle.segment == "APPROACH" else None

        self.vehicles = survivors
        self.vehicles_moved_last_tick = moved_this_tick + processed_this_tick
        if self.vehicles_moved_last_tick == 0 and self.vehicles:
            self.ticks_without_movement += 1
        else:
            self.ticks_without_movement = 0
        if self.ticks_without_movement >= DEADLOCK_TICK_LIMIT and not self.pedestrian_phase_active:
            self._force_direction(self.random.choice(PHASES), "movement deadlock recovery")
            self.ticks_without_movement = 0
        instant_throughput = processed_this_tick / dt if dt > 0.0 else 0.0
        self.smoothed_throughput = (self.smoothed_throughput * 0.72) + (instant_throughput * 0.28)

    def _update_vehicle_kinematics(self, vehicle: VehicleState) -> None:
        if vehicle.segment == "TURNING":
            turn_progress = min(1.0, vehicle.turn_distance / max(vehicle.turn_length, 1.0))
            tangent = vehicle.path.tangent_at(turn_progress)
            vehicle.direction_vector = _normalize(tangent.x, tangent.y)
        vehicle.velocity_x = vehicle.direction_vector.x * vehicle.speed
        vehicle.velocity_y = vehicle.direction_vector.y * vehicle.speed
        vehicle.heading = math.atan2(vehicle.direction_vector.x, vehicle.direction_vector.y)

    def update_pedestrians(self, dt: float) -> None:
        self.pedestrian_spawn_accumulator += dt * 0.45
        if self.pedestrian_spawn_accumulator >= 1.0 and len(self.pedestrians) < self.config.max_pedestrians:
            self.pedestrian_spawn_accumulator -= 1.0
            crosswalk = self.crosswalks[self.random.choice(list(self.crosswalks.keys()))]
            self._pedestrian_index += 1
            self.pedestrians.append(
                PedestrianStateModel(
                    id=f"ped-{self._pedestrian_index}",
                    crosswalk_id=crosswalk.id,
                    road_direction=crosswalk.road_direction,
                    progress=0.0,
                    speed=2.5,
                    wait_time=0.0,
                )
            )

        survivors: List[PedestrianStateModel] = []
        for pedestrian in self.pedestrians:
            crosswalk = self.crosswalks[pedestrian.crosswalk_id]
            if pedestrian.state == "WAITING":
                pedestrian.wait_time += dt
                pedestrian.velocity_x = 0.0
                pedestrian.velocity_y = 0.0
                if self.pedestrian_phase_active:
                    pedestrian.state = "CROSSING"
                    self._log("INFO", f"Pedestrian started crossing {crosswalk.id}.")
            if pedestrian.state == "CROSSING":
                pedestrian.progress += (pedestrian.speed / max(crosswalk.length, 1.0)) * dt
                pedestrian.velocity_x = crosswalk.movement.x * pedestrian.speed
                pedestrian.velocity_y = crosswalk.movement.y * pedestrian.speed
                if pedestrian.progress >= 1.0:
                    self._log("INFO", f"Pedestrian completed {crosswalk.id}.")
                    continue
            survivors.append(pedestrian)
        self.pedestrians = survivors

    def compute_metrics(self, dt: float) -> None:
        queued = sum(1 for vehicle in self.vehicles if vehicle.state == "WAITING")
        total_wait = sum(vehicle.wait_time for vehicle in self.vehicles)
        avg_wait = total_wait / len(self.vehicles) if self.vehicles else 0.0
        queue_pressure = min(1.0, ((queued * 1.8) + len(self.vehicles)) / max(1, self.config.max_vehicles * 1.8))
        detections = len(self.events)
        emergency_count = sum(1 for vehicle in self.vehicles if vehicle.priority > 0)
        throughput = self.smoothed_throughput if self.processed_vehicles else (0.0 if not self.vehicles else max(0.6, self.smoothed_throughput))
        self.metrics = MetricsView(
            avg_wait_time=round(avg_wait, 3),
            throughput=round(throughput, 3),
            vehicles_processed=self.processed_vehicles,
            queue_pressure=round(queue_pressure, 3),
            active_vehicles=len(self.vehicles),
            active_pedestrians=len(self.pedestrians),
            queued_vehicles=queued,
            emergency_vehicles=emergency_count,
            active_nodes=12,
            detections=detections,
            bandwidth_savings=round(18.0 + (throughput * 1.75) + (emergency_count * 0.9), 2),
        )

    def _vehicle_view(self, vehicle: VehicleState) -> VehicleView:
        return VehicleView(
            id=vehicle.id,
            lane_id=vehicle.lane_id,
            approach=vehicle.approach,
            route=vehicle.route,
            progress=round(vehicle.progress, 4),
            speed=round(vehicle.speed, 3),
            velocity_x=round(vehicle.velocity_x, 3),
            velocity_y=round(vehicle.velocity_y, 3),
            heading=round(vehicle.heading, 4),
            x=round(vehicle.position.x, 3),
            y=round(vehicle.position.y, 3),
            kind=vehicle.kind,
            has_siren=vehicle.has_siren,
            priority=vehicle.priority,
            state=vehicle.state,
            wait_time=round(vehicle.wait_time, 3),
            color=vehicle.color,
        )

    def _pedestrian_view(self, pedestrian: PedestrianStateModel) -> PedestrianView:
        crosswalk = self.crosswalks[pedestrian.crosswalk_id]
        position = crosswalk.point_at(pedestrian.progress)
        return PedestrianView(
            id=pedestrian.id,
            crosswalk_id=pedestrian.crosswalk_id,
            road_direction=pedestrian.road_direction,
            progress=round(pedestrian.progress, 4),
            speed=round(pedestrian.speed, 3),
            velocity_x=round(pedestrian.velocity_x, 3),
            velocity_y=round(pedestrian.velocity_y, 3),
            x=round(position.x, 3),
            y=round(position.y, 3),
            state=pedestrian.state,
            wait_time=round(pedestrian.wait_time, 3),
        )

    def _log(self, level: str, message: str) -> None:
        self.events.appendleft(EventView(timestamp=round(self.time, 3), level=level, message=message))
