"""Shared contracts for the production traffic digital twin."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Literal


SignalState = Literal["GREEN", "GREEN_LEFT", "YELLOW", "RED"]
ControllerPhase = Literal["PHASE_GREEN", "PHASE_YELLOW", "PHASE_ALL_RED"]
GlobalDirection = Literal["NORTH", "SOUTH", "EAST", "WEST"]
SignalCycleState = GlobalDirection
Approach = GlobalDirection
LaneType = Literal["INCOMING", "OUTGOING"]
ActorState = Literal["MOVING", "STOPPED"]
VehicleKind = Literal["car", "ambulance", "firetruck", "police"]
AiMode = Literal["fixed", "adaptive", "emergency"]
RouteType = Literal["straight", "left", "right"]
VehicleIntent = Literal["LEFT", "STRAIGHT", "RIGHT"]
SubPathSide = Literal["LEFT", "RIGHT"]
LaneKind = Literal["main"]
LaneMovement = Literal["STRAIGHT", "LEFT", "RIGHT"]


@dataclass
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class DirectionAxisView:
    x: float
    z: float


GLOBAL_DIRECTIONS: tuple[GlobalDirection, ...] = ("NORTH", "EAST", "SOUTH", "WEST")
LANE_TYPES: tuple[LaneType, ...] = ("INCOMING", "OUTGOING")
WORLD_DIRECTION_AXES: Dict[GlobalDirection, DirectionAxisView] = {
    "NORTH": DirectionAxisView(x=0.0, z=-1.0),
    "SOUTH": DirectionAxisView(x=0.0, z=1.0),
    "EAST": DirectionAxisView(x=1.0, z=0.0),
    "WEST": DirectionAxisView(x=-1.0, z=0.0),
}

DEFAULT_ROUTE_DISTRIBUTION: Dict[str, float] = {
    "NORTH->SOUTH": 5,
    "NORTH->EAST": 2,
    "NORTH->WEST": 2,
    "EAST->WEST": 5,
    "EAST->SOUTH": 2,
    "EAST->NORTH": 2,
    "SOUTH->NORTH": 5,
    "SOUTH->WEST": 2,
    "SOUTH->EAST": 2,
    "WEST->EAST": 5,
    "WEST->NORTH": 2,
    "WEST->SOUTH": 2,
}


def default_direction_axes() -> Dict[GlobalDirection, DirectionAxisView]:
    return {
        direction: DirectionAxisView(x=axis.x, z=axis.z)
        for direction, axis in WORLD_DIRECTION_AXES.items()
    }


def default_route_distribution() -> Dict[str, float]:
    return dict(DEFAULT_ROUTE_DISTRIBUTION)


@dataclass
class LaneArcView:
    center: Point2D
    radius: float
    inner_radius: float
    outer_radius: float
    start_angle: float
    end_angle: float
    clockwise: bool


@dataclass
class LaneView:
    id: str
    kind: LaneKind
    approach: Approach
    direction: GlobalDirection
    lane_type: LaneType
    lane_index: int
    lane_slot: str
    movement: LaneMovement
    start: Point2D
    end: Point2D
    path: List[Point2D]
    stop_zone_id: str
    stop_line_position: Point2D
    stop_reference_point: Point2D
    left_sub_path: List[Point2D]
    right_sub_path: List[Point2D]
    arc: LaneArcView | None = None
    turn_entry: Point2D | None = None
    turn_exit: Point2D | None = None


@dataclass
class VehicleView:
    id: str
    lane_id: str
    current_lane_id: str
    approach: Approach
    origin_direction: GlobalDirection
    route: RouteType
    intent: VehicleIntent
    sub_path_side: SubPathSide
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
class MetricsView:
    avg_wait_time: float
    throughput: float
    vehicles_processed: int
    queue_pressure: float
    active_vehicles: int
    queued_vehicles: int
    emergency_vehicles: int
    active_nodes: int
    detections: int
    bandwidth_savings: float
    vehicles_cleared_per_cycle: int = 0


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
    arrival_rate: float = 0.0


@dataclass
class PhaseScoreView:
    phase: SignalCycleState
    score: float
    queue_component: float
    wait_time_component: float
    congestion_component: float
    flow_component: float
    lane_weight_component: float
    fairness_boost: float
    emergency_boost: float
    queue_length: float
    avg_wait_time: float
    flow_rate: float
    demand_active: bool
    recommended_hold: bool
    decision_reason: str = ""
    neighbor_arrival_boost: float = 0.0
    green_wave_boost: float = 0.0
    downstream_congestion_penalty: float = 0.0
    arrival_rate: float = 0.0


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
    vehicle_count: int = 0
    priority_score: float = 0.0
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
class NetworkLinkView:
    id: str
    source_intersection_id: str
    target_intersection_id: str
    source_exit: Approach
    target_approach: Approach
    travel_time: float
    in_transit_vehicles: int
    outgoing_flow_rate: float
    incoming_estimate: float
    congestion_gate: str
    green_wave_eta: float = 0.0


@dataclass
class IntersectionNetworkView:
    id: str
    label: str
    offset: Point2D
    active_phase: SignalCycleState
    controller_phase: ControllerPhase
    congestion_level: float
    outgoing_flow_rate: float
    incoming_estimate: float
    queued_vehicles: int
    vehicle_count: int
    signals: Dict[str, SignalState] = field(default_factory=dict)
    metrics: MetricsView = field(
        default_factory=lambda: MetricsView(0.0, 0.0, 0, 0.0, 0, 0, 0, 0, 0, 0, 0.0)
    )
    traffic_brain: TrafficBrainView = field(
        default_factory=lambda: TrafficBrainView(0.0, "NORTH", "Awaiting telemetry.")
    )


@dataclass
class TrafficNetworkView:
    focus_intersection_id: str
    coordination_mode: str
    intersections: Dict[str, IntersectionNetworkView] = field(default_factory=dict)
    links: List[NetworkLinkView] = field(default_factory=list)
    congestion_zones: List[str] = field(default_factory=list)


@dataclass
class SimulationConfig:
    traffic_intensity: float = 0.48
    ambulance_frequency: float = 0.04
    ai_mode: AiMode = "fixed"
    speed_multiplier: float = 1.0
    spawn_rate_multiplier: float = 0.92
    safe_gap_multiplier: float = 1.0
    turn_smoothness: float = 1.0
    max_emergency_vehicles: int = 3
    paused: bool = True
    max_vehicles: int = 28
    route_distribution: Dict[str, float] = field(default_factory=default_route_distribution)


@dataclass
class SnapshotView:
    frame: int
    timestamp: float
    current_state: SignalCycleState
    active_direction: Approach | None
    direction_axes: Dict[GlobalDirection, DirectionAxisView] = field(default_factory=default_direction_axes)
    intersection_id: str = ""
    controller_phase: ControllerPhase = "PHASE_GREEN"
    phase_timer: float = 0.0
    phase_duration: float = 0.0
    min_green_remaining: float = 0.0
    vehicles: List[VehicleView] = field(default_factory=list)
    lanes: List[LaneView] = field(default_factory=list)
    signals: Dict[str, SignalState] = field(default_factory=dict)
    metrics: MetricsView = field(
        default_factory=lambda: MetricsView(0.0, 0.0, 0, 0.0, 0, 0, 0, 0, 0, 0, 0.0)
    )
    traffic_brain: TrafficBrainView = field(
        default_factory=lambda: TrafficBrainView(0.0, "NORTH", "Awaiting telemetry.")
    )
    network: TrafficNetworkView | None = None
    events: List[EventView] = field(default_factory=list)
    config: SimulationConfig = field(default_factory=SimulationConfig)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
