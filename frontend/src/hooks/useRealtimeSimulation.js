import { startTransition, useEffect, useRef, useState } from "react";
import { WORLD_DIRECTION_AXES } from "../lib/directions";

const APPROACHES = ["NORTH", "SOUTH", "EAST", "WEST"];
const PHASES = ["NORTH", "EAST", "SOUTH", "WEST"];
export const DEFAULT_ROUTE_DISTRIBUTION = {
  "NORTH->SOUTH": 5,
  "NORTH->EAST": 2,
  "EAST->WEST": 5,
  "EAST->SOUTH": 2,
  "SOUTH->NORTH": 5,
  "SOUTH->WEST": 2,
  "WEST->EAST": 5,
  "WEST->NORTH": 2,
};

export const DEFAULT_CONFIG = {
  traffic_intensity: 0.48,
  ambulance_frequency: 0.04,
  ai_mode: "fixed",
  speed_multiplier: 1,
  spawn_rate_multiplier: 0.92,
  safe_gap_multiplier: 1,
  turn_smoothness: 1,
  max_emergency_vehicles: 3,
  paused: true,
  max_vehicles: 28,
  route_distribution: DEFAULT_ROUTE_DISTRIBUTION,
};

const DEFAULT_MODE_BENCHMARKS = {
  fixed: {
    samples: 0,
    avg_wait_time: 0,
    throughput_per_minute: 0,
    queue_length: 0,
  },
  adaptive: {
    samples: 0,
    avg_wait_time: 0,
    throughput_per_minute: 0,
    queue_length: 0,
  },
};
const MAX_BUFFERED_FRAMES = 96;
const SCENE_PUBLISH_INTERVAL_MS = 48;

function defaultDirectionMetric(approach) {
  return {
    approach,
    queue_length: 0,
    avg_wait_time: 0,
    flow_rate: 0,
    queue_delta: 0,
    congestion_trend: 0,
    emergency_vehicles: 0,
    alert_level: "normal",
    arrival_rate: 0,
  };
}

function defaultPhaseScore(phase) {
  return {
    phase,
    score: 0,
    queue_component: 0,
    wait_time_component: 0,
    congestion_component: 0,
    flow_component: 0,
    lane_weight_component: 0,
    fairness_boost: 0,
    emergency_boost: 0,
    queue_length: 0,
    avg_wait_time: 0,
    flow_rate: 0,
    demand_active: false,
    recommended_hold: false,
    decision_reason: "Awaiting telemetry.",
    neighbor_arrival_boost: 0,
    green_wave_boost: 0,
    downstream_congestion_penalty: 0,
    arrival_rate: 0,
  };
}

const DEFAULT_TRAFFIC_BRAIN = {
  active_phase_score: 0,
  top_phase: "NORTH",
  strategy: "Awaiting telemetry.",
  direction_metrics: Object.fromEntries(APPROACHES.map((approach) => [approach, defaultDirectionMetric(approach)])),
  phase_scores: Object.fromEntries(PHASES.map((phase) => [phase, defaultPhaseScore(phase)])),
  congestion_alerts: [],
  emergency: {
    detected: false,
    preferred_phase: null,
    approach: null,
    vehicle_id: "",
    eta_seconds: 0,
    vehicle_count: 0,
    priority_score: 0,
    state: "idle",
  },
};

const DEFAULT_NETWORK = {
  focus_intersection_id: "",
  coordination_mode: "Single intersection",
  intersections: {},
  links: [],
  congestion_zones: [],
};

const DEFAULT_SNAPSHOT = {
  frame: 0,
  timestamp: 0,
  intersection_id: "",
  current_state: "NORTH",
  active_direction: "NORTH",
  direction_axes: WORLD_DIRECTION_AXES,
  controller_phase: "PHASE_GREEN",
  phase_timer: 0,
  phase_duration: 7,
  min_green_remaining: 7,
  vehicles: [],
  lanes: [],
  crosswalks: [],
  signals: {
    NORTH: "GREEN",
    SOUTH: "RED",
    EAST: "RED",
    WEST: "RED",
  },
  metrics: {
    avg_wait_time: 0,
    throughput: 0,
    vehicles_processed: 0,
    queue_pressure: 0,
    active_vehicles: 0,
    queued_vehicles: 0,
    emergency_vehicles: 0,
    active_nodes: 12,
    detections: 0,
    bandwidth_savings: 0,
    vehicles_cleared_per_cycle: 0,
  },
  traffic_brain: DEFAULT_TRAFFIC_BRAIN,
  network: DEFAULT_NETWORK,
  events: [],
  config: DEFAULT_CONFIG,
};

function normalizeSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") {
    return DEFAULT_SNAPSHOT;
  }
  return {
    ...DEFAULT_SNAPSHOT,
    ...snapshot,
    vehicles: Array.isArray(snapshot.vehicles) ? snapshot.vehicles : [],
    lanes: Array.isArray(snapshot.lanes) ? snapshot.lanes : [],
    crosswalks: Array.isArray(snapshot.crosswalks) ? snapshot.crosswalks : [],
    events: Array.isArray(snapshot.events) ? snapshot.events : [],
    signals: { ...DEFAULT_SNAPSHOT.signals, ...(snapshot.signals ?? {}) },
    direction_axes: { ...WORLD_DIRECTION_AXES, ...(snapshot.direction_axes ?? {}) },
    phase_timer: Number.isFinite(snapshot.phase_timer) ? snapshot.phase_timer : DEFAULT_SNAPSHOT.phase_timer,
    phase_duration: Number.isFinite(snapshot.phase_duration) ? snapshot.phase_duration : DEFAULT_SNAPSHOT.phase_duration,
    min_green_remaining: Number.isFinite(snapshot.min_green_remaining) ? snapshot.min_green_remaining : DEFAULT_SNAPSHOT.min_green_remaining,
    metrics: { ...DEFAULT_SNAPSHOT.metrics, ...(snapshot.metrics ?? {}) },
    traffic_brain: {
      ...DEFAULT_TRAFFIC_BRAIN,
      ...(snapshot.traffic_brain ?? {}),
      direction_metrics: Object.fromEntries(
        APPROACHES.map((approach) => [
          approach,
          {
            ...defaultDirectionMetric(approach),
            ...(snapshot.traffic_brain?.direction_metrics?.[approach] ?? {}),
          },
        ]),
      ),
      phase_scores: Object.fromEntries(
        PHASES.map((phase) => [
          phase,
          {
            ...defaultPhaseScore(phase),
            ...(snapshot.traffic_brain?.phase_scores?.[phase] ?? {}),
          },
        ]),
      ),
      congestion_alerts: Array.isArray(snapshot.traffic_brain?.congestion_alerts)
        ? snapshot.traffic_brain.congestion_alerts
        : [],
      emergency: {
        ...DEFAULT_TRAFFIC_BRAIN.emergency,
        ...(snapshot.traffic_brain?.emergency ?? {}),
      },
    },
    network: {
      ...DEFAULT_NETWORK,
      ...(snapshot.network ?? {}),
      intersections: snapshot.network?.intersections && typeof snapshot.network.intersections === "object"
        ? snapshot.network.intersections
        : {},
      links: Array.isArray(snapshot.network?.links) ? snapshot.network.links : [],
      congestion_zones: Array.isArray(snapshot.network?.congestion_zones) ? snapshot.network.congestion_zones : [],
    },
    config: {
      ...DEFAULT_CONFIG,
      ...(snapshot.config ?? {}),
      route_distribution: {
        ...DEFAULT_ROUTE_DISTRIBUTION,
        ...((snapshot.config?.route_distribution && typeof snapshot.config.route_distribution === "object")
          ? snapshot.config.route_distribution
          : {}),
      },
    },
  };
}

function makeBufferedFrame(snapshot, receivedAt) {
  return {
    snapshot,
    receivedAt,
    vehicleMap: new Map(snapshot.vehicles.map((vehicle) => [vehicle.id, vehicle])),
  };
}

function nextHistoryEntry(list, point) {
  const next = [...list, point];
  return next.slice(-120);
}

function mergeConfig(baseConfig, partialConfig = {}) {
  return {
    ...DEFAULT_CONFIG,
    ...baseConfig,
    ...partialConfig,
    route_distribution: {
      ...DEFAULT_ROUTE_DISTRIBUTION,
      ...(baseConfig?.route_distribution ?? {}),
      ...(partialConfig?.route_distribution ?? {}),
    },
  };
}

export function useRealtimeSimulation() {
  const socketRef = useRef(null);
  const sceneBufferRef = useRef({
    frames: [makeBufferedFrame(DEFAULT_SNAPSHOT, performance.now())],
  });
  const cameraStateRef = useRef({
    position: [68, 58, 68],
    target: [0, 0, 0],
  });
  const lastScenePublishRef = useRef(0);
  const lastDashboardPublishRef = useRef(0);
  const lastHistoryPublishRef = useRef(0);
  const [connectionState, setConnectionState] = useState("connecting");
  const [sceneSnapshot, setSceneSnapshot] = useState(DEFAULT_SNAPSHOT);
  const [dashboardSnapshot, setDashboardSnapshot] = useState(DEFAULT_SNAPSHOT);
  const [history, setHistory] = useState({
    throughput: [],
    wait: [],
    queue: [],
    emergencies: [],
  });
  const [controls, setControls] = useState(DEFAULT_CONFIG);
  const [modeBenchmarks, setModeBenchmarks] = useState(DEFAULT_MODE_BENCHMARKS);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.hostname || "localhost";
    const socket = new WebSocket(`${protocol}://${host}:8000/ws`);
    socketRef.current = socket;

    const publish = (incomingSnapshot) => {
      const snapshot = normalizeSnapshot(incomingSnapshot);
      const now = performance.now();
      const nextFrame = makeBufferedFrame(snapshot, now);
      const bufferedFrames = sceneBufferRef.current.frames;
      bufferedFrames.push(nextFrame);
      if (bufferedFrames.length > MAX_BUFFERED_FRAMES) {
        bufferedFrames.splice(0, bufferedFrames.length - MAX_BUFFERED_FRAMES);
      }

      if (now - lastScenePublishRef.current >= SCENE_PUBLISH_INTERVAL_MS) {
        lastScenePublishRef.current = now;
        setSceneSnapshot(snapshot);
      }

      if (now - lastDashboardPublishRef.current >= 180) {
        lastDashboardPublishRef.current = now;
        startTransition(() => {
          setDashboardSnapshot(snapshot);
          setControls(snapshot.config);
          if (!snapshot.config?.paused) {
            setModeBenchmarks((current) => {
              const modeKey = snapshot.config?.ai_mode === "adaptive" ? "adaptive" : "fixed";
              const previous = current[modeKey];
              const nextSamples = previous.samples + 1;
              const weight = previous.samples / nextSamples;
              const throughputPerMinute = Number(snapshot.metrics?.throughput ?? 0) * 60;
              return {
                ...current,
                [modeKey]: {
                  samples: nextSamples,
                  avg_wait_time: (previous.avg_wait_time * weight) + ((Number(snapshot.metrics?.avg_wait_time ?? 0)) / nextSamples),
                  throughput_per_minute:
                    (previous.throughput_per_minute * weight) + (throughputPerMinute / nextSamples),
                  queue_length:
                    (previous.queue_length * weight) + ((Number(snapshot.metrics?.queued_vehicles ?? 0)) / nextSamples),
                },
              };
            });
          }
        });
      }

      if (!snapshot.config?.paused && now - lastHistoryPublishRef.current >= 500) {
        lastHistoryPublishRef.current = now;
        startTransition(() => {
          setHistory((current) => ({
            throughput: nextHistoryEntry(current.throughput, { x: snapshot.timestamp, y: snapshot.metrics.throughput }),
            wait: nextHistoryEntry(current.wait, { x: snapshot.timestamp, y: snapshot.metrics.avg_wait_time }),
            queue: nextHistoryEntry(current.queue, { x: snapshot.timestamp, y: snapshot.metrics.queue_pressure * 100 }),
            emergencies: nextHistoryEntry(current.emergencies, { x: snapshot.timestamp, y: snapshot.metrics.emergency_vehicles }),
          }));
        });
      }
    };

    socket.addEventListener("open", () => {
      setConnectionState("live");
    });
    socket.addEventListener("close", () => {
      setConnectionState("offline");
    });
    socket.addEventListener("error", () => {
      setConnectionState("error");
    });
    socket.addEventListener("message", (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload?.type === "hello" || payload?.type === "snapshot" || payload?.type === "ack") {
          publish(payload.snapshot);
        }
      } catch (error) {
        setConnectionState("error");
      }
    });

    return () => {
      socket.close();
    };
  }, []);

  const send = (payload) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    socket.send(JSON.stringify(payload));
  };

  const seedLocalState = (nextConfig = DEFAULT_CONFIG) => {
    const seededSnapshot = normalizeSnapshot({ ...DEFAULT_SNAPSHOT, config: nextConfig });
    setHistory({ throughput: [], wait: [], queue: [], emergencies: [] });
    sceneBufferRef.current.frames = [makeBufferedFrame(seededSnapshot, performance.now())];
    setSceneSnapshot(seededSnapshot);
    setDashboardSnapshot(seededSnapshot);
    setControls(seededSnapshot.config);
    setModeBenchmarks(DEFAULT_MODE_BENCHMARKS);
  };

  const updateConfig = (partialConfig) => {
    setControls((current) => mergeConfig(current, partialConfig));
    const nextConfig = mergeConfig(controls, partialConfig);
    send({
      type: "set_config",
      config: partialConfig.route_distribution
        ? { ...partialConfig, route_distribution: nextConfig.route_distribution }
        : partialConfig,
    });
  };

  const play = () => {
    setControls((current) => ({ ...current, paused: false }));
    send({ type: "play" });
  };

  const pause = () => {
    setControls((current) => ({ ...current, paused: true }));
    send({ type: "pause" });
  };

  const reset = () => {
    seedLocalState(DEFAULT_CONFIG);
    send({ type: "reset" });
  };

  const restartWithConfig = (partialConfig) => {
    const nextConfig = mergeConfig(DEFAULT_CONFIG, partialConfig);
    seedLocalState(nextConfig);
    send({ type: "reset", config: nextConfig });
  };

  return {
    connectionState,
    sceneSnapshot,
    dashboardSnapshot,
    sceneBufferRef,
    cameraStateRef,
    history,
    controls,
    modeBenchmarks,
    updateConfig,
    play,
    pause,
    reset,
    restartWithConfig,
  };
}
