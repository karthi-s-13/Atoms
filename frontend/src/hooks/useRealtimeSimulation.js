import { startTransition, useEffect, useRef, useState } from "react";

const APPROACHES = ["NORTH", "SOUTH", "EAST", "WEST"];
const PHASES = ["NS_STRAIGHT", "NS_LEFT", "EW_STRAIGHT", "EW_LEFT"];

const DEFAULT_CONFIG = {
  traffic_intensity: 1,
  ambulance_frequency: 0.08,
  ai_mode: "adaptive",
  speed_multiplier: 1,
  paused: false,
  max_vehicles: 36,
  max_pedestrians: 12,
};

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
    fairness_boost: 0,
    emergency_boost: 0,
    queue_length: 0,
    avg_wait_time: 0,
    flow_rate: 0,
    pedestrian_demand: 0,
    demand_active: false,
    recommended_hold: false,
    decision_reason: "Awaiting telemetry.",
  };
}

const DEFAULT_TRAFFIC_BRAIN = {
  active_phase_score: 0,
  top_phase: "NS_STRAIGHT",
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
    state: "idle",
  },
};

const DEFAULT_SNAPSHOT = {
  frame: 0,
  timestamp: 0,
  current_state: "NS_STRAIGHT",
  active_direction: "NS",
  controller_phase: "PHASE_GREEN",
  phase_timer: 0,
  phase_duration: 11.5,
  min_green_remaining: 4.5,
  vehicles: [],
  pedestrians: [],
  lanes: [],
  crosswalks: [],
  signals: {
    NORTH: "GREEN",
    SOUTH: "GREEN",
    EAST: "RED",
    WEST: "RED",
  },
  pedestrian_phase_active: true,
  metrics: {
    avg_wait_time: 0,
    throughput: 0,
    vehicles_processed: 0,
    queue_pressure: 0,
    active_vehicles: 0,
    active_pedestrians: 0,
    queued_vehicles: 0,
    emergency_vehicles: 0,
    active_nodes: 12,
    detections: 0,
    bandwidth_savings: 0,
  },
  traffic_brain: DEFAULT_TRAFFIC_BRAIN,
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
    pedestrians: Array.isArray(snapshot.pedestrians) ? snapshot.pedestrians : [],
    lanes: Array.isArray(snapshot.lanes) ? snapshot.lanes : [],
    crosswalks: Array.isArray(snapshot.crosswalks) ? snapshot.crosswalks : [],
    events: Array.isArray(snapshot.events) ? snapshot.events : [],
    signals: { ...DEFAULT_SNAPSHOT.signals, ...(snapshot.signals ?? {}) },
    pedestrian_phase_active: Boolean(snapshot.pedestrian_phase_active),
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
    config: { ...DEFAULT_CONFIG, ...(snapshot.config ?? {}) },
  };
}

function makeBufferedFrame(snapshot, receivedAt) {
  return {
    snapshot,
    receivedAt,
    vehicleMap: new Map(snapshot.vehicles.map((vehicle) => [vehicle.id, vehicle])),
    pedestrianMap: new Map(snapshot.pedestrians.map((pedestrian) => [pedestrian.id, pedestrian])),
    laneMap: new Map(snapshot.lanes.map((lane) => [lane.id, lane])),
    crosswalkMap: new Map(snapshot.crosswalks.map((crosswalk) => [crosswalk.id, crosswalk])),
  };
}

function nextHistoryEntry(list, point) {
  const next = [...list, point];
  return next.slice(-120);
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

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.hostname || "localhost";
    const socket = new WebSocket(`${protocol}://${host}:8000/ws`);
    socketRef.current = socket;

    const publish = (incomingSnapshot) => {
      const snapshot = normalizeSnapshot(incomingSnapshot);
      const now = performance.now();
      const nextFrame = makeBufferedFrame(snapshot, now);
      sceneBufferRef.current.frames = [...sceneBufferRef.current.frames, nextFrame].slice(-180);

      if (now - lastScenePublishRef.current >= 96) {
        lastScenePublishRef.current = now;
        startTransition(() => {
          setSceneSnapshot(snapshot);
        });
      }

      if (now - lastDashboardPublishRef.current >= 180) {
        lastDashboardPublishRef.current = now;
        startTransition(() => {
          setDashboardSnapshot(snapshot);
          setControls(snapshot.config);
        });
      }

      if (now - lastHistoryPublishRef.current >= 500) {
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

  const updateConfig = (partialConfig) => {
    const nextConfig = { ...controls, ...partialConfig };
    setControls(nextConfig);
    send({ type: "set_config", config: partialConfig });
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
    setHistory({ throughput: [], wait: [], queue: [], emergencies: [] });
    sceneBufferRef.current.frames = [makeBufferedFrame(DEFAULT_SNAPSHOT, performance.now())];
    setSceneSnapshot(DEFAULT_SNAPSHOT);
    setDashboardSnapshot(DEFAULT_SNAPSHOT);
    setControls(DEFAULT_CONFIG);
    send({ type: "reset" });
  };

  return {
    connectionState,
    sceneSnapshot,
    dashboardSnapshot,
    sceneBufferRef,
    cameraStateRef,
    history,
    controls,
    updateConfig,
    play,
    pause,
    reset,
  };
}
