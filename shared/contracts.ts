export type SignalState = "GREEN" | "GREEN_LEFT" | "YELLOW" | "RED";
export type ControllerPhase = "PHASE_GREEN" | "PHASE_YELLOW" | "PHASE_ALL_RED";
export type GlobalDirection = "NORTH" | "SOUTH" | "EAST" | "WEST";
export type SignalCycleState = GlobalDirection;
export type Approach = GlobalDirection;
export type LaneType = "INCOMING" | "OUTGOING";
export type ActorState = "MOVING" | "STOPPED";
export type VehicleKind = "car" | "ambulance" | "firetruck" | "police";
export type AiMode = "fixed" | "adaptive" | "emergency";
export type RouteType = "straight" | "left" | "right";
export type VehicleIntent = "LEFT" | "STRAIGHT" | "RIGHT";
export type SubPathSide = "LEFT" | "RIGHT";
export type LaneKind = "main";
export type LaneMovement = "STRAIGHT" | "LEFT" | "RIGHT";

export interface DirectionAxisView {
  x: number;
  z: number;
}

export const GLOBAL_DIRECTIONS: readonly GlobalDirection[] = ["NORTH", "EAST", "SOUTH", "WEST"];
export const LANE_TYPES: readonly LaneType[] = ["INCOMING", "OUTGOING"];
export const WORLD_DIRECTION_AXES: Readonly<Record<GlobalDirection, DirectionAxisView>> = {
  NORTH: { x: 0, z: -1 },
  SOUTH: { x: 0, z: 1 },
  EAST: { x: 1, z: 0 },
  WEST: { x: -1, z: 0 },
};

export const DEFAULT_ROUTE_DISTRIBUTION: Readonly<Record<string, number>> = {
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
};

export interface Point2D {
  x: number;
  y: number;
}

export interface LaneArcView {
  center: Point2D;
  radius: number;
  inner_radius: number;
  outer_radius: number;
  start_angle: number;
  end_angle: number;
  clockwise: boolean;
}

export interface LaneView {
  id: string;
  kind: LaneKind;
  approach: Approach;
  direction: GlobalDirection;
  lane_type: LaneType;
  lane_index: number;
  lane_slot: string;
  movement: LaneMovement;
  start: Point2D;
  end: Point2D;
  path: Point2D[];
  stop_zone_id: string;
  stop_line_position: Point2D;
  stop_reference_point: Point2D;
  left_sub_path: Point2D[];
  right_sub_path: Point2D[];
  arc?: LaneArcView | null;
  turn_entry?: Point2D | null;
  turn_exit?: Point2D | null;
}

export interface VehicleView {
  id: string;
  lane_id: string;
  current_lane_id: string;
  approach: Approach;
  origin_direction: GlobalDirection;
  route: RouteType;
  intent: VehicleIntent;
  sub_path_side: SubPathSide;
  progress: number;
  speed: number;
  velocity_x: number;
  velocity_y: number;
  heading: number;
  x: number;
  y: number;
  kind: VehicleKind;
  has_siren: boolean;
  priority: number;
  state: ActorState;
  wait_time: number;
  color: string;
  length: number;
  width: number;
}

export interface MetricsView {
  avg_wait_time: number;
  throughput: number;
  vehicles_processed: number;
  queue_pressure: number;
  active_vehicles: number;
  queued_vehicles: number;
  emergency_vehicles: number;
  active_nodes: number;
  detections: number;
  bandwidth_savings: number;
  vehicles_cleared_per_cycle: number;
}

export interface DirectionMetricView {
  approach: Approach;
  queue_length: number;
  avg_wait_time: number;
  flow_rate: number;
  queue_delta: number;
  congestion_trend: number;
  emergency_vehicles: number;
  alert_level: string;
  arrival_rate: number;
}

export interface PhaseScoreView {
  phase: SignalCycleState;
  score: number;
  queue_component: number;
  wait_time_component: number;
  congestion_component: number;
  flow_component: number;
  lane_weight_component: number;
  fairness_boost: number;
  emergency_boost: number;
  queue_length: number;
  avg_wait_time: number;
  flow_rate: number;
  demand_active: boolean;
  recommended_hold: boolean;
  decision_reason: string;
  neighbor_arrival_boost: number;
  green_wave_boost: number;
  downstream_congestion_penalty: number;
  arrival_rate: number;
}

export interface CongestionAlertView {
  approach: Approach;
  level: string;
  message: string;
  queue_length: number;
  queue_delta: number;
}

export interface EmergencyPriorityView {
  detected: boolean;
  preferred_phase: SignalCycleState | null;
  approach: Approach | null;
  vehicle_id: string;
  eta_seconds: number;
  vehicle_count: number;
  priority_score: number;
  state: string;
}

export interface TrafficBrainView {
  active_phase_score: number;
  top_phase: SignalCycleState;
  strategy: string;
  direction_metrics: Record<string, DirectionMetricView>;
  phase_scores: Record<string, PhaseScoreView>;
  congestion_alerts: CongestionAlertView[];
  emergency: EmergencyPriorityView;
}

export interface EventView {
  timestamp: number;
  level: string;
  message: string;
}

export interface NetworkLinkView {
  id: string;
  source_intersection_id: string;
  target_intersection_id: string;
  source_exit: Approach;
  target_approach: Approach;
  travel_time: number;
  in_transit_vehicles: number;
  outgoing_flow_rate: number;
  incoming_estimate: number;
  congestion_gate: string;
  green_wave_eta: number;
}

export interface IntersectionNetworkView {
  id: string;
  label: string;
  offset: Point2D;
  active_phase: SignalCycleState;
  controller_phase: ControllerPhase;
  congestion_level: number;
  outgoing_flow_rate: number;
  incoming_estimate: number;
  queued_vehicles: number;
  vehicle_count: number;
  signals: Record<string, SignalState>;
  metrics: MetricsView;
  traffic_brain: TrafficBrainView;
}

export interface TrafficNetworkView {
  focus_intersection_id: string;
  coordination_mode: string;
  intersections: Record<string, IntersectionNetworkView>;
  links: NetworkLinkView[];
  congestion_zones: string[];
}

export interface SimulationConfig {
  traffic_intensity: number;
  ambulance_frequency: number;
  ai_mode: AiMode;
  speed_multiplier: number;
  spawn_rate_multiplier: number;
  safe_gap_multiplier: number;
  turn_smoothness: number;
  max_emergency_vehicles: number;
  paused: boolean;
  max_vehicles: number;

  route_distribution: Record<string, number>;
}

export interface SnapshotView {
  frame: number;
  timestamp: number;
  current_state: SignalCycleState;
  active_direction: Approach | null;
  direction_axes: Record<GlobalDirection, DirectionAxisView>;
  intersection_id: string;
  controller_phase: ControllerPhase;
  phase_timer: number;
  phase_duration: number;
  min_green_remaining: number;
  vehicles: VehicleView[];
  lanes: LaneView[];
  signals: Record<string, SignalState>;
  metrics: MetricsView;
  traffic_brain: TrafficBrainView;
  network: TrafficNetworkView | null;
  events: EventView[];
  config: SimulationConfig;
}
