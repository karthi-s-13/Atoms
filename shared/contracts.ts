export type SignalState = "GREEN" | "YELLOW" | "RED";
export type Approach = "NORTH" | "SOUTH" | "EAST" | "WEST";
export type RoadDirection = "NS" | "EW";
export type ActorState = "MOVING" | "WAITING" | "TURNING" | "CROSSING";
export type PedestrianState = "WAITING" | "CROSSING";
export type VehicleKind = "car" | "ambulance" | "firetruck" | "police";
export type AiMode = "fixed" | "adaptive" | "emergency";
export type RouteType = "straight" | "left" | "right";

export interface Point2D {
  x: number;
  y: number;
}

export interface LaneView {
  id: string;
  approach: Approach;
  start: Point2D;
  end: Point2D;
  crosswalk_id: string;
  stop_line_position: Point2D;
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
}

export interface PedestrianView {
  id: string;
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
  active_direction: Approach | null;
  vehicles: VehicleView[];
  pedestrians: PedestrianView[];
  lanes: LaneView[];
  crosswalks: CrosswalkView[];
  signals: Record<string, SignalState>;
  pedestrian_phase_active: boolean;
  metrics: MetricsView;
  events: EventView[];
  config: SimulationConfig;
}
