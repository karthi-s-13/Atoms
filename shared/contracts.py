"""Shared contracts for the production traffic digital twin."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Literal


SignalState = Literal["GREEN", "GREEN_LEFT", "YELLOW", "RED"]
ControllerPhase = Literal["PHASE_GREEN", "PHASE_YELLOW", "PHASE_ALL_RED"]
SignalCycleState = Literal["NS_STRAIGHT", "EW_STRAIGHT", "NS_LEFT", "EW_LEFT"]
Approach = Literal["NORTH", "SOUTH", "EAST", "WEST"]
RoadDirection = Literal["NS", "EW"]
ActorState = Literal["MOVING", "STOPPED"]
PedestrianState = Literal["WAITING", "CROSSING"]
VehicleKind = Literal["car", "ambulance", "firetruck", "police"]
AiMode = Literal["fixed", "adaptive", "emergency", "pedestrian"]
RouteType = Literal["straight", "right", "left"]
LaneKind = Literal["main", "slip"]
LaneMovement = Literal["STRAIGHT", "RIGHT", "LEFT"]


@dataclass
class Point2D:
    x: float
    y: float


@dataclass
class LaneView:
    id: str
    kind: LaneKind
    approach: Approach
    direction: Approach
    movement: LaneMovement
    start: Point2D
    end: Point2D
    path: List[Point2D]
    crosswalk_id: str
    stop_line_position: Point2D
    crosswalk_start: Point2D


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
    length: float
    width: float


@dataclass
class PedestrianView:
    id: str
    crossing: RoadDirection
    target_crosswalk: str
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
    is_elderly: bool
    is_impatient: bool
    risky_crossing: bool
    look_angle: float


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
class DirectionMetricView:
    approach: Approach
    queue_length: float
    avg_wait_time: float
    flow_rate: float
    queue_delta: float
    congestion_trend: float
    emergency_vehicles: int
    alert_level: str = "normal"


@dataclass
class PhaseScoreView:
    phase: SignalCycleState
    score: float
    queue_component: float
    wait_time_component: float
    congestion_component: float
    flow_component: float
    fairness_boost: float
    emergency_boost: float
    queue_length: float
    avg_wait_time: float
    flow_rate: float
    pedestrian_demand: float
    demand_active: bool
    recommended_hold: bool
    decision_reason: str = ""


@dataclass
class CongestionAlertView:
    approach: Approach
    level: str
    message: str
    queue_length: float
    queue_delta: float


@dataclass
class EmergencyPriorityView:
    detected: bool = False
    preferred_phase: SignalCycleState | None = None
    approach: Approach | None = None
    vehicle_id: str = ""
    eta_seconds: float = 0.0
    state: str = "idle"


@dataclass
class TrafficBrainView:
    active_phase_score: float
    top_phase: SignalCycleState
    strategy: str
    direction_metrics: Dict[str, DirectionMetricView] = field(default_factory=dict)
    phase_scores: Dict[str, PhaseScoreView] = field(default_factory=dict)
    congestion_alerts: List[CongestionAlertView] = field(default_factory=list)
    emergency: EmergencyPriorityView = field(default_factory=EmergencyPriorityView)


@dataclass
class EventView:
    timestamp: float
    level: str
    message: str


@dataclass
class SimulationConfig:
    traffic_intensity: float = 1.0
    ambulance_frequency: float = 0.08
    ai_mode: AiMode = "fixed"
    speed_multiplier: float = 1.0
    paused: bool = False
    max_vehicles: int = 48
    max_pedestrians: int = 20


@dataclass
class SnapshotView:
    frame: int
    timestamp: float
    current_state: SignalCycleState
    active_direction: RoadDirection | None
    controller_phase: ControllerPhase = "PHASE_GREEN"
    phase_timer: float = 0.0
    phase_duration: float = 0.0
    min_green_remaining: float = 0.0
    vehicles: List[VehicleView] = field(default_factory=list)
    pedestrians: List[PedestrianView] = field(default_factory=list)
    lanes: List[LaneView] = field(default_factory=list)
    crosswalks: List[CrosswalkView] = field(default_factory=list)
    signals: Dict[str, SignalState] = field(default_factory=dict)
    pedestrian_phase_active: bool = False
    metrics: MetricsView = field(
        default_factory=lambda: MetricsView(0.0, 0.0, 0, 0.0, 0, 0, 0, 0, 0, 0, 0.0)
    )
    traffic_brain: TrafficBrainView = field(
        default_factory=lambda: TrafficBrainView(0.0, "NS_STRAIGHT", "Awaiting telemetry.")
    )
    events: List[EventView] = field(default_factory=list)
    config: SimulationConfig = field(default_factory=SimulationConfig)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
