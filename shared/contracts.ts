export type SignalState = "GREEN" | "GREEN_LEFT" | "YELLOW" | "RED";
export type ControllerPhase = "PHASE_GREEN" | "PHASE_YELLOW" | "PHASE_ALL_RED";
export type SignalCycleState = "NS_STRAIGHT" | "EW_STRAIGHT" | "NS_LEFT" | "EW_LEFT";
export type Approach = "NORTH" | "SOUTH" | "EAST" | "WEST";
export type RoadDirection = "NS" | "EW";
export type ActorState = "MOVING" | "STOPPED";
export type PedestrianState = "WAITING" | "CROSSING";
export type VehicleKind = "car" | "ambulance" | "firetruck" | "police";
export type AiMode = "fixed" | "adaptive" | "emergency" | "pedestrian";
export type RouteType = "straight" | "right" | "left";
export type LaneKind = "main" | "slip";
export type LaneMovement = "STRAIGHT" | "RIGHT" | "LEFT";

export interface Point2D {
  x: number;
  y: number;
}

export interface LaneView {
  id: string;
  kind: LaneKind;
  approach: Approach;
  direction: Approach;
  movement: LaneMovement;
  start: Point2D;
  end: Point2D;
  path: Point2D[];
  crosswalk_id: string;
  stop_line_position: Point2D;
  crosswalk_start: Point2D;
}

export interface CrosswalkView {
  id: string;
  road_direction: RoadDirection;
  start: Point2D;
  end: Point2D;
  movement: Point2D;
}

export interface VehicleView {
  id: string;
  lane_id: string;
  approach: Approach;
  route: RouteType;
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

export interface PedestrianView {
  id: string;
  crossing: RoadDirection;
  target_crosswalk: string;
  crosswalk_id: string;
  road_direction: RoadDirection;
  progress: number;
  speed: number;
  velocity_x: number;
  velocity_y: number;
  x: number;
  y: number;
  state: PedestrianState;
  wait_time: number;
  is_elderly: boolean;
  is_impatient: boolean;
  risky_crossing: boolean;
  look_angle: number;
}

export interface MetricsView {
  avg_wait_time: number;
  throughput: number;
  vehicles_processed: number;
  queue_pressure: number;
  active_vehicles: number;
  active_pedestrians: number;
  queued_vehicles: number;
  emergency_vehicles: number;
  active_nodes: number;
  detections: number;
  bandwidth_savings: number;
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
}

export interface PhaseScoreView {
  phase: SignalCycleState;
  score: number;
  queue_component: number;
  wait_time_component: number;
  congestion_component: number;
  flow_component: number;
  fairness_boost: number;
  emergency_boost: number;
  queue_length: number;
  avg_wait_time: number;
  flow_rate: number;
  pedestrian_demand: number;
  demand_active: boolean;
  recommended_hold: boolean;
  decision_reason: string;
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

export interface SimulationConfig {
  traffic_intensity: number;
  ambulance_frequency: number;
  ai_mode: AiMode;
  speed_multiplier: number;
  paused: boolean;
  max_vehicles: number;
  max_pedestrians: number;
}

export interface SnapshotView {
  frame: number;
  timestamp: number;
  current_state: SignalCycleState;
  active_direction: RoadDirection | null;
  controller_phase: ControllerPhase;
  phase_timer: number;
  phase_duration: number;
  min_green_remaining: number;
  vehicles: VehicleView[];
  pedestrians: PedestrianView[];
  lanes: LaneView[];
  crosswalks: CrosswalkView[];
  signals: Record<string, SignalState>;
  pedestrian_phase_active: boolean;
  metrics: MetricsView;
  traffic_brain: TrafficBrainView;
  events: EventView[];
  config: SimulationConfig;
}
