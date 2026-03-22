"""Shared contracts for the production traffic digital twin."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Literal


SignalState = Literal["GREEN", "YELLOW", "RED"]
Approach = Literal["NORTH", "SOUTH", "EAST", "WEST"]
RoadDirection = Literal["NS", "EW"]
ActorState = Literal["MOVING", "WAITING", "TURNING", "CROSSING"]
PedestrianState = Literal["WAITING", "CROSSING"]
VehicleKind = Literal["car", "ambulance", "firetruck", "police"]
AiMode = Literal["fixed", "adaptive", "emergency"]
RouteType = Literal["straight", "left", "right"]


@dataclass
class Point2D:
    x: float
    y: float


@dataclass
class LaneView:
    id: str
    approach: Approach
    start: Point2D
    end: Point2D
    crosswalk_id: str
    stop_line_position: Point2D


@dataclass
class CrosswalkView:
    id: str
    road_direction: RoadDirection
    start: Point2D
    end: Point2D
    movement: Point2D


@dataclass
class VehicleView:
    id: str
    lane_id: str
    approach: Approach
    route: RouteType
    progress: float
    speed: float
    velocity_x: float
    velocity_y: float
    heading: float
    x: float
    y: float
    kind: VehicleKind
    has_siren: bool
    priority: int
    state: ActorState
    wait_time: float
    color: str


@dataclass
class PedestrianView:
    id: str
    crosswalk_id: str
    road_direction: RoadDirection
    progress: float
    speed: float
    velocity_x: float
    velocity_y: float
    x: float
    y: float
    state: PedestrianState
    wait_time: float


@dataclass
class MetricsView:
    avg_wait_time: float
    throughput: float
    vehicles_processed: int
    queue_pressure: float
    active_vehicles: int
    active_pedestrians: int
    queued_vehicles: int
    emergency_vehicles: int
    active_nodes: int
    detections: int
    bandwidth_savings: float


@dataclass
class EventView:
    timestamp: float
    level: str
    message: str


@dataclass
class SimulationConfig:
    traffic_intensity: float = 1.0
    ambulance_frequency: float = 0.08
    ai_mode: AiMode = "adaptive"
    speed_multiplier: float = 1.0
    paused: bool = False
    max_vehicles: int = 42
    max_pedestrians: int = 18


@dataclass
class SnapshotView:
    frame: int
    timestamp: float
    active_direction: Approach | None
    vehicles: List[VehicleView] = field(default_factory=list)
    pedestrians: List[PedestrianView] = field(default_factory=list)
    lanes: List[LaneView] = field(default_factory=list)
    crosswalks: List[CrosswalkView] = field(default_factory=list)
    signals: Dict[str, SignalState] = field(default_factory=dict)
    pedestrian_phase_active: bool = False
    metrics: MetricsView = field(
        default_factory=lambda: MetricsView(0.0, 0.0, 0, 0.0, 0, 0, 0, 0, 0, 0, 0.0)
    )
    events: List[EventView] = field(default_factory=list)
    config: SimulationConfig = field(default_factory=SimulationConfig)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
