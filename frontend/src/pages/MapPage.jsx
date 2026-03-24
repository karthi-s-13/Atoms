import polyline from '@mapbox/polyline';
import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const INITIAL_COORDINATION = {
  emergency: { active: false, stage: 'idle', route: [], locked_junctions: [], alerts: [] },
  coordination: {},
  green_wave: { active: false, path: [], path_coords: [], avg_speed_kmph: 0, timings: [] },
};

const INITIAL_STATUS = {
  congestion_index: 0,
  active_emergencies: 0,
  system_health: 'stable',
  active_cameras: 0,
  degraded_cameras: 0,
  uncertain_junctions: 0,
};

const INITIAL_CONFIG = {
  junctions: [],
  hospitals: [],
  starting_points: [],
  activation_junction_id: 'J1',
  emergency_route_nodes: [],
};

const INITIAL_PLAN = {
  mode: 'idle',
  startingPoint: null,
  hospital: null,
  normalEta: 0,
  optimizedEta: 0,
  timeSaved: 0,
  timeSavedPercent: 0,
  routeDistanceKm: 0,
  activationJunctionId: 'J1',
  plannedRouteNodes: [],
  approachRoute: [],
  emergencyRoute: [],
  fullRoute: [],
  directions: [],
  googleMapsUrl: '',
  googleRouteAvailable: false,
  googleRouteError: null,
  speedMultiplier: 1,
};

const SIGNAL_DIRECTIONS = ['N', 'S', 'E', 'W'];
const ROUTE_JUNCTION_COUNT = 3;
const SIGNAL_YELLOW_MS = 1000;
const SIGNAL_ALL_RED_MS = 1000;
const SIGNAL_MIN_GREEN_MS = 5000;

function normalizeSnapshot(payload) {
  return {
    junctions: Array.isArray(payload?.junctions) ? payload.junctions : [],
    coordination: payload?.coordination ?? INITIAL_COORDINATION,
    globalStatus: payload?.global_status ?? INITIAL_STATUS,
  };
}

function toLatLng(record) {
  return Array.isArray(record) ? record : [Number(record?.lat ?? 0), Number(record?.lng ?? 0)];
}

function formatCountdown(totalSeconds) {
  const safe = Math.max(Math.round(totalSeconds || 0), 0);
  const minutes = String(Math.floor(safe / 60)).padStart(2, '0');
  const seconds = String(safe % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
}

function distanceMeters(a, b) {
  const radius = 6371000;
  const lat1 = (a[0] * Math.PI) / 180;
  const lat2 = (b[0] * Math.PI) / 180;
  const deltaLat = ((b[0] - a[0]) * Math.PI) / 180;
  const deltaLng = ((b[1] - a[1]) * Math.PI) / 180;
  const chord =
    Math.sin(deltaLat / 2) * Math.sin(deltaLat / 2) +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLng / 2) * Math.sin(deltaLng / 2);
  return 2 * radius * Math.atan2(Math.sqrt(chord), Math.sqrt(Math.max(1e-12, 1 - chord)));
}

function easeInOut(value) {
  return value < 0.5 ? 2 * value * value : 1 - Math.pow(-2 * value + 2, 2) / 2;
}

function titleCase(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function signalShort(value) {
  if (value === 'GREEN') return 'G';
  if (value === 'YELLOW') return 'Y';
  return 'R';
}

function buildSignals(activeDirection, phase) {
  if (phase === 'YELLOW') {
    return Object.fromEntries(SIGNAL_DIRECTIONS.map((direction) => [direction, direction === activeDirection ? 'YELLOW' : 'RED']));
  }
  if (phase === 'GREEN') {
    return Object.fromEntries(SIGNAL_DIRECTIONS.map((direction) => [direction, direction === activeDirection ? 'GREEN' : 'RED']));
  }
  return Object.fromEntries(SIGNAL_DIRECTIONS.map((direction) => [direction, 'RED']));
}

function nextSignalDirection(direction) {
  const currentIndex = SIGNAL_DIRECTIONS.indexOf(direction);
  const safeIndex = currentIndex >= 0 ? currentIndex : 0;
  return SIGNAL_DIRECTIONS[(safeIndex + 1) % SIGNAL_DIRECTIONS.length];
}

function approachDirection(from, to) {
  const latDelta = from[0] - to[0];
  const lngDelta = from[1] - to[1];
  if (Math.abs(latDelta) >= Math.abs(lngDelta)) {
    return latDelta < 0 ? 'S' : 'N';
  }
  return lngDelta < 0 ? 'W' : 'E';
}

function cumulativeRouteDistances(points) {
  if (!points.length) return [];
  const distances = [0];
  for (let index = 1; index < points.length; index += 1) {
    distances.push(distances[index - 1] + distanceMeters(points[index - 1], points[index]));
  }
  return distances;
}

function pointAtRouteDistance(points, cumulative, targetDistance) {
  if (!points.length) return null;
  if (points.length === 1) return points[0];
  const lastDistance = cumulative[cumulative.length - 1] ?? 0;
  if (targetDistance <= 0) return points[0];
  if (targetDistance >= lastDistance) return points[points.length - 1];

  for (let index = 1; index < cumulative.length; index += 1) {
    if (cumulative[index] >= targetDistance) {
      const previousDistance = cumulative[index - 1];
      const segmentDistance = Math.max(cumulative[index] - previousDistance, 1e-6);
      const ratio = (targetDistance - previousDistance) / segmentDistance;
      return [
        points[index - 1][0] + ((points[index][0] - points[index - 1][0]) * ratio),
        points[index - 1][1] + ((points[index][1] - points[index - 1][1]) * ratio),
      ];
    }
  }

  return points[points.length - 1];
}

function routeProgressDistance(points, cumulative, position) {
  if (!points.length || !position) return 0;
  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  points.forEach((point, index) => {
    const dist = distanceMeters(point, position);
    if (dist < bestDistance) {
      bestDistance = dist;
      bestIndex = index;
    }
  });
  return cumulative[bestIndex] ?? 0;
}

function createGeneratedJunctionSpecs(approachPoints, emergencyPoints, activationJunctionId, count = ROUTE_JUNCTION_COUNT) {
  if (!emergencyPoints.length) return [];
  const approachCumulative = cumulativeRouteDistances(approachPoints);
  const emergencyCumulative = cumulativeRouteDistances(emergencyPoints);
  const approachDistance = approachCumulative[approachCumulative.length - 1] ?? 0;
  const emergencyDistance = emergencyCumulative[emergencyCumulative.length - 1] ?? 0;

  const junctions = [
    {
      id: 'route-J1',
      displayId: activationJunctionId || 'J1',
      name: 'Route Detection Junction',
      lat: emergencyPoints[0][0],
      lng: emergencyPoints[0][1],
      fullDistanceAlong: approachDistance,
      emergencyDistanceAlong: 0,
      generated: false,
    },
  ];

  for (let index = 1; index <= count; index += 1) {
    if (emergencyDistance <= 0) break;
    const targetDistance = (emergencyDistance * index) / (count + 1);
    const point = pointAtRouteDistance(emergencyPoints, emergencyCumulative, targetDistance);
    if (!point) continue;
    junctions.push({
      id: `route-J${index + 2}`,
      displayId: `J${index + 2}`,
      name: `Generated Corridor Junction ${index}`,
      lat: point[0],
      lng: point[1],
      fullDistanceAlong: approachDistance + targetDistance,
      emergencyDistanceAlong: targetDistance,
      generated: true,
    });
  }

  return junctions;
}

function createRouteSignalJunction(spec, index) {
  const activeDirection = SIGNAL_DIRECTIONS[index % SIGNAL_DIRECTIONS.length];
  return {
    ...spec,
    signals: buildSignals(activeDirection, 'GREEN'),
    phase: 'GREEN',
    activeDirection,
    pendingDirection: null,
    phaseStartedAt: Date.now(),
    greenStartedAt: Date.now(),
    statusLabel: 'Normal cycle active',
    distanceM: null,
    etaSec: null,
    locked: false,
    passed: false,
    approachSignal: activeDirection,
  };
}

function getJunctionColor(junction) {
  if (junction.phase === 'GREEN') return '#16a34a';
  if (junction.phase === 'YELLOW') return '#eab308';
  if (junction.status === 'degraded') return '#dc2626';
  if (junction.emergency) return '#22c55e';
  return '#ef4444';
}

function createJunctionIcon(junction, selectedJunctionId) {
  const color = getJunctionColor(junction);
  const selected = junction.junction_id === selectedJunctionId ? 'junction-selected' : '';
  return L.divIcon({
    className: `junction-shell ${selected}`,
    html: `
      <div class="junction-badge" style="border-color:${color}">
        <span class="junction-dot" style="background:${color}"></span>
        <span class="junction-label">${junction.junction_id}</span>
      </div>
    `,
    iconSize: [48, 24],
    iconAnchor: [24, 12],
  });
}

function createHospitalIcon(label) {
  return L.divIcon({
    className: 'hospital-shell',
    html: `<div class="hospital-badge">${label}</div>`,
    iconSize: [38, 24],
    iconAnchor: [19, 12],
  });
}

function createStartIcon(label, isSelected) {
  return L.divIcon({
    className: 'start-shell',
    html: `<div class="start-badge ${isSelected ? 'start-selected' : ''}">${label}</div>`,
    iconSize: [38, 24],
    iconAnchor: [19, 12],
  });
}

function createAmbulanceIcon(heading) {
  return L.divIcon({
    className: 'ambulance-shell',
    html: `<div class="ambulance-badge" style="transform: rotate(${heading}deg)">AMB</div>`,
    iconSize: [50, 24],
    iconAnchor: [25, 12],
  });
}

function createRouteJunctionIcon(junction) {
  const color = junction.phase === 'GREEN' ? '#16a34a' : junction.phase === 'YELLOW' ? '#eab308' : '#ef4444';
  return L.divIcon({
    className: 'route-junction-shell',
    html: `
      <div class="route-junction-badge">
        <div class="route-junction-ring" style="border-color:${color}">
          <span class="route-junction-center" style="background:${color}"></span>
        </div>
        <span class="route-junction-text">${junction.displayId}</span>
      </div>
    `,
    iconSize: [42, 42],
    iconAnchor: [21, 21],
  });
}

function FitToRoute({ points }) {
  const map = useMap();

  useEffect(() => {
    if (points.length > 1) {
      map.fitBounds(points, { padding: [72, 72], maxZoom: 15 });
    }
  }, [map, points]);

  return null;
}

function SummaryCard({ title, value, detail, tone = 'text-white' }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.04] px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">{title}</p>
      <p className={`mt-2 text-2xl font-semibold ${tone}`}>{value}</p>
      <p className="mt-1 text-sm text-slate-300">{detail}</p>
    </div>
  );
}

export default function MapPage() {
  const [junctionMap, setJunctionMap] = useState({});
  const [coordinationState, setCoordinationState] = useState(INITIAL_COORDINATION);
  const [globalStatus, setGlobalStatus] = useState(INITIAL_STATUS);
  const [config, setConfig] = useState(INITIAL_CONFIG);
  const [selectedStartId, setSelectedStartId] = useState('');
  const [selectedJunctionId, setSelectedJunctionId] = useState('');
  const [simulationPlan, setSimulationPlan] = useState(INITIAL_PLAN);
  const [routeSignalJunctions, setRouteSignalJunctions] = useState([]);
  const [displayedAmbulance, setDisplayedAmbulance] = useState(null);
  const [ambulanceHeading, setAmbulanceHeading] = useState(0);
  const [speedControl, setSpeedControl] = useState({ desired: 1, applied: 1, syncing: false });
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [connectionState, setConnectionState] = useState('connecting');
  const motionFrameRef = useRef(0);
  const speedSyncTimeoutRef = useRef(0);
  const displayedAmbulanceRef = useRef(null);
  const routeSignalJunctionsRef = useRef([]);
  const routeSignalTimeoutsRef = useRef({});
  const ambulanceMotionRef = useRef({ position: null, timestamp: 0, speedMps: 0 });

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      fetch('/api/map/junctions'),
      fetch('/api/map/signal-coordination'),
      fetch('/api/map/status'),
      fetch('/api/emergency/config'),
    ])
      .then(async ([junctionRes, coordinationRes, statusRes, configRes]) => {
        if (!junctionRes.ok || !coordinationRes.ok || !statusRes.ok || !configRes.ok) {
          throw new Error('Could not load traffic map state.');
        }

        const snapshot = normalizeSnapshot({
          junctions: await junctionRes.json(),
          coordination: await coordinationRes.json(),
          global_status: await statusRes.json(),
        });
        const emergencyConfig = await configRes.json();

        if (cancelled) return;

        startTransition(() => {
          setJunctionMap(Object.fromEntries(snapshot.junctions.map((junction) => [junction.junction_id, junction])));
          setCoordinationState(snapshot.coordination);
          setGlobalStatus(snapshot.globalStatus);
          setConfig({
            junctions: Array.isArray(emergencyConfig?.junctions) ? emergencyConfig.junctions : [],
            hospitals: Array.isArray(emergencyConfig?.hospitals) ? emergencyConfig.hospitals : [],
            starting_points: Array.isArray(emergencyConfig?.starting_points) ? emergencyConfig.starting_points : [],
            activation_junction_id: emergencyConfig?.activation_junction_id ?? 'J1',
            emergency_route_nodes: Array.isArray(emergencyConfig?.emergency_route_nodes) ? emergencyConfig.emergency_route_nodes : [],
          });
          const firstStartId = emergencyConfig?.starting_points?.[0]?.id ?? '';
          setSelectedStartId(firstStartId);
          setSelectedJunctionId(emergencyConfig?.activation_junction_id ?? 'J1');
          setLoading(false);
        });
      })
      .catch((error) => {
        console.error('Error loading traffic workspace:', error);
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.hostname || 'localhost';
    const socket = new WebSocket(`${protocol}://${host}:8000/ws/map-stream`);

    socket.addEventListener('open', () => setConnectionState('live'));
    socket.addEventListener('close', () => setConnectionState('offline'));
    socket.addEventListener('error', () => setConnectionState('error'));
    socket.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload?.type === 'snapshot') {
          const snapshot = normalizeSnapshot(payload.snapshot);
          startTransition(() => {
            setJunctionMap(Object.fromEntries(snapshot.junctions.map((junction) => [junction.junction_id, junction])));
            setCoordinationState(snapshot.coordination);
            setGlobalStatus(snapshot.globalStatus);
          });
          return;
        }

        if (payload?.type === 'delta') {
          startTransition(() => {
            setJunctionMap((current) => {
              const next = { ...current };
              (payload.removed_junction_ids ?? []).forEach((junctionId) => delete next[junctionId]);
              (payload.updates ?? []).forEach((entry) => {
                next[entry.junction_id] = { ...(next[entry.junction_id] ?? {}), ...(entry.updates ?? {}) };
              });
              return next;
            });
            if (payload.coordination) setCoordinationState(payload.coordination);
            if (payload.global_status) setGlobalStatus(payload.global_status);
          });
        }
      } catch (error) {
        console.error('Map stream parse error:', error);
      }
    });

    const ping = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'ping' }));
      }
    }, 12000);

    return () => {
      window.clearInterval(ping);
      socket.close();
    };
  }, []);

  const junctions = useMemo(
    () => Object.values(junctionMap).sort((left, right) => (right.coordination_priority ?? 0) - (left.coordination_priority ?? 0)),
    [junctionMap],
  );
  const deferredJunctions = useDeferredValue(junctions);
  const emergencyState = coordinationState?.emergency ?? INITIAL_COORDINATION.emergency;
  const selectedStart = config.starting_points.find((item) => item.id === selectedStartId) ?? null;

  useEffect(() => {
    if (!simulationPlan.fullRoute.length) {
      const liveFullRoute = emergencyState?.full_route_coords ?? [];
      if (Array.isArray(liveFullRoute) && liveFullRoute.length > 1) {
        setSimulationPlan((current) => ({
          ...current,
          mode: emergencyState.mode ?? current.mode,
          startingPoint: emergencyState.starting_point ?? current.startingPoint,
          hospital: emergencyState.hospital ?? current.hospital,
          normalEta: Number(emergencyState.normal_eta ?? current.normalEta),
          optimizedEta: Number(emergencyState.optimized_eta ?? current.optimizedEta),
          timeSaved: Number(emergencyState.time_saved ?? current.timeSaved),
          timeSavedPercent: Number(emergencyState.time_saved_percent ?? current.timeSavedPercent),
          routeDistanceKm: Number(emergencyState.route_distance_km ?? current.routeDistanceKm),
          activationJunctionId: emergencyState.activation_junction_id ?? current.activationJunctionId,
          plannedRouteNodes: Array.isArray(emergencyState.planned_route_nodes) ? emergencyState.planned_route_nodes : current.plannedRouteNodes,
          approachRoute: Array.isArray(emergencyState.approach_route_coords) ? emergencyState.approach_route_coords : current.approachRoute,
          emergencyRoute: Array.isArray(emergencyState.emergency_route_coords) ? emergencyState.emergency_route_coords : current.emergencyRoute,
          fullRoute: liveFullRoute,
        }));
      }
    }
  }, [emergencyState, simulationPlan.fullRoute.length]);

  useEffect(() => {
    displayedAmbulanceRef.current = displayedAmbulance;
  }, [displayedAmbulance]);

  useEffect(() => {
    routeSignalJunctionsRef.current = routeSignalJunctions;
  }, [routeSignalJunctions]);

  useEffect(() => {
    const targetRecord = emergencyState?.ambulance_position;
    if (!targetRecord) {
      if (motionFrameRef.current) window.cancelAnimationFrame(motionFrameRef.current);
      setDisplayedAmbulance(null);
      displayedAmbulanceRef.current = null;
      return undefined;
    }

    const target = [Number(targetRecord.lat), Number(targetRecord.lng)];
    const origin = displayedAmbulanceRef.current ?? target;
    const now = performance.now();
    const previousMotion = ambulanceMotionRef.current;
    if (previousMotion.position && previousMotion.timestamp > 0) {
      const deltaSeconds = Math.max((now - previousMotion.timestamp) / 1000, 0.001);
      ambulanceMotionRef.current = {
        position: target,
        timestamp: now,
        speedMps: distanceMeters(previousMotion.position, target) / deltaSeconds,
      };
    } else {
      ambulanceMotionRef.current = { position: target, timestamp: now, speedMps: 0 };
    }
    if (motionFrameRef.current) window.cancelAnimationFrame(motionFrameRef.current);

    let startedAt = 0;
    const durationMs = 820;
    const deltaLat = target[0] - origin[0];
    const deltaLng = target[1] - origin[1];
    if (Math.abs(deltaLat) > 1e-8 || Math.abs(deltaLng) > 1e-8) {
      setAmbulanceHeading((Math.atan2(deltaLng, deltaLat) * 180) / Math.PI);
    }

    const animate = (timestamp) => {
      if (!startedAt) startedAt = timestamp;
      const progress = Math.min((timestamp - startedAt) / durationMs, 1);
      const eased = easeInOut(progress);
      setDisplayedAmbulance([
        origin[0] + (deltaLat * eased),
        origin[1] + (deltaLng * eased),
      ]);
      if (progress < 1) {
        motionFrameRef.current = window.requestAnimationFrame(animate);
      }
    };

    motionFrameRef.current = window.requestAnimationFrame(animate);
    return () => {
      if (motionFrameRef.current) window.cancelAnimationFrame(motionFrameRef.current);
    };
  }, [emergencyState?.ambulance_position?.lat, emergencyState?.ambulance_position?.lng]);

  const approachRoutePoints = useMemo(
    () => (simulationPlan.approachRoute ?? []).map(toLatLng),
    [simulationPlan.approachRoute],
  );
  const emergencyRoutePoints = useMemo(
    () => (simulationPlan.emergencyRoute ?? []).map(toLatLng),
    [simulationPlan.emergencyRoute],
  );
  const fullRoutePoints = useMemo(
    () => (simulationPlan.fullRoute ?? []).map(toLatLng),
    [simulationPlan.fullRoute],
  );
  const fullRouteCumulative = useMemo(() => cumulativeRouteDistances(fullRoutePoints), [fullRoutePoints]);
  const generatedRouteJunctionSpecs = useMemo(
    () => createGeneratedJunctionSpecs(approachRoutePoints, emergencyRoutePoints, simulationPlan.activationJunctionId || 'J1'),
    [approachRoutePoints, emergencyRoutePoints, simulationPlan.activationJunctionId],
  );
  const routeFocusPoints = fullRoutePoints.length > 1 ? fullRoutePoints : [];
  const recentAlerts = [...(emergencyState?.alerts ?? [])].slice(-4).reverse();
  const displayedDirections = (simulationPlan.directions ?? []).slice(0, 4);
  const liveCountdown = emergencyState?.remaining_eta_sec ?? 0;
  const simulationLive = Boolean(
    simulationPlan.fullRoute.length ||
      emergencyState?.stage === 'approach' ||
      emergencyState?.stage === 'emergency' ||
      emergencyState?.completed,
  );
  const nextRouteJunction = routeSignalJunctions.find((junction) => !junction.passed) ?? null;
  const liveCurrentJunction = nextRouteJunction?.displayId ?? emergencyState?.current_junction ?? 'Monitoring';
  const liveNextTarget = nextRouteJunction?.displayId ?? emergencyState?.next_target ?? simulationPlan.hospital?.id ?? 'Waiting';
  const liveSignalDirection = titleCase(nextRouteJunction?.activeDirection ?? emergencyState?.active_signal_direction ?? 'pending');

  useEffect(() => {
    const liveSpeed = Number(emergencyState?.speed_multiplier ?? 1);
    if (!Number.isFinite(liveSpeed)) return;
    setSpeedControl((current) => {
      if (Math.abs(current.applied - liveSpeed) < 0.01 && Math.abs(current.desired - liveSpeed) < 0.01 && !current.syncing) {
        return current;
      }
      return {
        desired: current.syncing ? current.desired : liveSpeed,
        applied: liveSpeed,
        syncing: false,
      };
    });
  }, [emergencyState?.speed_multiplier]);

  useEffect(() => {
    Object.values(routeSignalTimeoutsRef.current).forEach((handles) => {
      if (handles?.yellowTimeout) window.clearTimeout(handles.yellowTimeout);
      if (handles?.greenTimeout) window.clearTimeout(handles.greenTimeout);
    });
    routeSignalTimeoutsRef.current = {};
    setRouteSignalJunctions(generatedRouteJunctionSpecs.map((junction, index) => createRouteSignalJunction(junction, index)));
  }, [generatedRouteJunctionSpecs]);

  const requestRouteSignalSwitch = (junctionId, targetDirection, reason, lockForAmbulance = false) => {
    const current = routeSignalJunctionsRef.current.find((junction) => junction.id === junctionId);
    if (!current) return;
    if (current.phase === 'GREEN' && current.activeDirection === targetDirection && (lockForAmbulance || current.locked)) {
      setRouteSignalJunctions((items) =>
        items.map((junction) =>
          junction.id === junctionId
            ? {
                ...junction,
                locked: lockForAmbulance,
                statusLabel: reason,
                greenStartedAt: Date.now(),
              }
            : junction,
        ),
      );
      return;
    }
    const existing = routeSignalTimeoutsRef.current[junctionId];
    if (existing) {
      window.clearTimeout(existing.yellowTimeout);
      window.clearTimeout(existing.greenTimeout);
    }

    setRouteSignalJunctions((items) =>
      items.map((junction) =>
        junction.id === junctionId
          ? {
              ...junction,
              phase: 'YELLOW',
              pendingDirection: targetDirection,
              signals: buildSignals(junction.activeDirection, 'YELLOW'),
              statusLabel: reason,
              locked: lockForAmbulance,
              phaseStartedAt: Date.now(),
            }
          : junction,
      ),
    );

    const yellowTimeout = window.setTimeout(() => {
      setRouteSignalJunctions((items) =>
        items.map((junction) =>
          junction.id === junctionId
            ? {
                ...junction,
                phase: 'RED',
                signals: buildSignals(junction.activeDirection, 'RED'),
                statusLabel: `${junction.displayId} all-red safety buffer`,
                phaseStartedAt: Date.now(),
              }
            : junction,
        ),
      );
    }, SIGNAL_YELLOW_MS);

    const greenTimeout = window.setTimeout(() => {
      setRouteSignalJunctions((items) =>
        items.map((junction) =>
          junction.id === junctionId
            ? {
                ...junction,
                phase: 'GREEN',
                activeDirection: targetDirection,
                pendingDirection: null,
                signals: buildSignals(targetDirection, 'GREEN'),
                statusLabel: reason,
                locked: lockForAmbulance,
                phaseStartedAt: Date.now(),
                greenStartedAt: Date.now(),
              }
            : junction,
        ),
      );
      delete routeSignalTimeoutsRef.current[junctionId];
    }, SIGNAL_YELLOW_MS + SIGNAL_ALL_RED_MS);

    routeSignalTimeoutsRef.current[junctionId] = { yellowTimeout, greenTimeout, targetDirection };
  };

  useEffect(() => {
    if (!simulationLive || !generatedRouteJunctionSpecs.length || !displayedAmbulanceRef.current) return undefined;

    const interval = window.setInterval(() => {
      const ambulancePosition = displayedAmbulanceRef.current;
      if (!ambulancePosition) return;

      const progressDistance = routeProgressDistance(fullRoutePoints, fullRouteCumulative, ambulancePosition);
      const routeTotalDistance = fullRouteCumulative[fullRouteCumulative.length - 1] ?? 0;
      const liveSpeed = ambulanceMotionRef.current.speedMps;
      const fallbackSpeed = liveCountdown > 0 ? Math.max((routeTotalDistance - progressDistance) / Math.max(liveCountdown, 1), 1) : 1;
      const speedMps = Math.max(liveSpeed, fallbackSpeed, 1);
      const now = Date.now();

      const nextRequests = [];
      setRouteSignalJunctions((items) =>
        items.map((junction) => {
          const remainingDistance = Math.max(junction.fullDistanceAlong - progressDistance, 0);
          const passed = emergencyState?.completed || progressDistance > junction.fullDistanceAlong + 12;
          const etaSec = passed ? 0 : remainingDistance / speedMps;
          const signalDirection = approachDirection(ambulancePosition, [junction.lat, junction.lng]);
          let statusLabel = junction.statusLabel;

          if (passed) {
            statusLabel = `${junction.displayId} cleared`;
          } else if (etaSec < 5) {
            statusLabel = `${junction.displayId} preparing ${signalDirection} green`;
            nextRequests.push({
              junctionId: junction.id,
              targetDirection: signalDirection,
              reason: `${junction.displayId} corridor open for ambulance arrival`,
              lockForAmbulance: true,
            });
          } else if (junction.phase === 'GREEN' && !junction.locked && now - junction.greenStartedAt >= SIGNAL_MIN_GREEN_MS) {
            nextRequests.push({
              junctionId: junction.id,
              targetDirection: nextSignalDirection(junction.activeDirection),
              reason: `${junction.displayId} normal cycle`,
              lockForAmbulance: false,
            });
            statusLabel = `${junction.displayId} normal phase rotation`;
          } else if (!junction.locked && !passed) {
            statusLabel = `${junction.displayId} normal cycle active`;
          }

          return {
            ...junction,
            passed,
            distanceM: remainingDistance,
            etaSec,
            approachSignal: signalDirection,
            statusLabel,
            locked: passed ? false : junction.locked,
          };
        }),
      );

      nextRequests.forEach((request) => {
        requestRouteSignalSwitch(request.junctionId, request.targetDirection, request.reason, request.lockForAmbulance);
      });
    }, 300);

    return () => window.clearInterval(interval);
  }, [simulationLive, generatedRouteJunctionSpecs, fullRoutePoints, fullRouteCumulative, liveCountdown, emergencyState?.completed]);

  useEffect(() => {
    if (!simulationLive || Math.abs(speedControl.desired - speedControl.applied) < 0.01) return undefined;

    speedSyncTimeoutRef.current = window.setTimeout(async () => {
      setSpeedControl((current) => ({ ...current, syncing: true }));
      try {
        const response = await fetch('/api/emergency/speed', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ speed_multiplier: speedControl.desired }),
        });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const payload = await response.json();
        if (payload?.emergency_state) {
          setCoordinationState((current) => ({
            ...current,
            emergency: payload.emergency_state,
          }));
        }
        setSpeedControl({
          desired: Number(payload?.speed_multiplier ?? speedControl.desired),
          applied: Number(payload?.speed_multiplier ?? speedControl.desired),
          syncing: false,
        });
      } catch (error) {
        console.error('Emergency speed update failed:', error);
        setSpeedControl((current) => ({ ...current, desired: current.applied, syncing: false }));
      }
    }, 180);

    return () => {
      if (speedSyncTimeoutRef.current) {
        window.clearTimeout(speedSyncTimeoutRef.current);
      }
    };
  }, [simulationLive, speedControl.desired, speedControl.applied]);

  const startEmergency = async () => {
    if (!selectedStartId) return;
    setStarting(true);
    try {
      const response = await fetch('/api/emergency/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_point_id: selectedStartId, speed_multiplier: speedControl.desired }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || 'Failed to start emergency simulation.');
      }
      const data = await response.json();
      const emergency = data.emergency_state ?? {};
      const approachRoute = data.approach_polyline ? polyline.decode(data.approach_polyline).map(([lat, lng]) => [lat, lng]) : [];
      const emergencyRoute = data.emergency_polyline ? polyline.decode(data.emergency_polyline).map(([lat, lng]) => [lat, lng]) : [];
      const fullRoute = [
        ...approachRoute,
        ...(emergencyRoute.length > 1 ? emergencyRoute.slice(1) : emergencyRoute),
      ];
      setSimulationPlan({
        mode: data.mode ?? 'structured_demo',
        startingPoint: data.starting_point ?? emergency.starting_point ?? selectedStart,
        hospital: data.hospital ?? emergency.hospital ?? null,
        normalEta: Number(data.normal_eta ?? emergency.normal_eta ?? 0),
        optimizedEta: Number(data.optimized_eta ?? emergency.optimized_eta ?? 0),
        timeSaved: Number(data.time_saved ?? emergency.time_saved ?? 0),
        timeSavedPercent: Number(data.time_saved_percent ?? emergency.time_saved_percent ?? 0),
        routeDistanceKm: Number(data.route_distance_km ?? emergency.route_distance_km ?? 0),
        activationJunctionId: data.activation_junction_id ?? emergency.activation_junction_id ?? config.activation_junction_id,
        plannedRouteNodes: Array.isArray(data.planned_route_nodes) ? data.planned_route_nodes : emergency.planned_route_nodes ?? [],
        approachRoute: approachRoute.length ? approachRoute : Array.isArray(data.approach_route_coords) ? data.approach_route_coords : emergency.approach_route_coords ?? [],
        emergencyRoute: emergencyRoute.length ? emergencyRoute : Array.isArray(data.emergency_route_coords) ? data.emergency_route_coords : emergency.emergency_route_coords ?? [],
        fullRoute: fullRoute.length ? fullRoute : Array.isArray(data.full_route_coords) ? data.full_route_coords : emergency.full_route_coords ?? [],
        directions: Array.isArray(data.directions) ? data.directions : [],
        googleMapsUrl: data.google_maps_url ?? '',
        googleRouteAvailable: Boolean(data.google_route_available && fullRoute.length > 1),
        googleRouteError: data.google_route_error ?? null,
        speedMultiplier: Number(emergency?.speed_multiplier ?? speedControl.desired),
      });
      setSpeedControl({
        desired: Number(emergency?.speed_multiplier ?? speedControl.desired),
        applied: Number(emergency?.speed_multiplier ?? speedControl.desired),
        syncing: false,
      });
      if (emergency?.ambulance_position) {
        setDisplayedAmbulance([Number(emergency.ambulance_position.lat), Number(emergency.ambulance_position.lng)]);
      }
    } catch (error) {
      console.error('Structured emergency simulation failed:', error);
      window.alert('Emergency simulation could not be started. Please verify the backend state and try again.');
    } finally {
      setStarting(false);
    }
  };

  const clearEmergency = async () => {
    if (motionFrameRef.current) window.cancelAnimationFrame(motionFrameRef.current);
    Object.values(routeSignalTimeoutsRef.current).forEach((handles) => {
      if (handles?.yellowTimeout) window.clearTimeout(handles.yellowTimeout);
      if (handles?.greenTimeout) window.clearTimeout(handles.greenTimeout);
    });
    routeSignalTimeoutsRef.current = {};
    setDisplayedAmbulance(null);
    setAmbulanceHeading(0);
    setRouteSignalJunctions([]);
    setSimulationPlan(INITIAL_PLAN);
    setSpeedControl({ desired: 1, applied: 1, syncing: false });
    try {
      await fetch('/api/emergency/clear', { method: 'POST' });
    } catch (error) {
      console.error('Emergency clear failed:', error);
    }
  };

  useEffect(() => () => {
    Object.values(routeSignalTimeoutsRef.current).forEach((handles) => {
      if (handles?.yellowTimeout) window.clearTimeout(handles.yellowTimeout);
      if (handles?.greenTimeout) window.clearTimeout(handles.greenTimeout);
    });
  }, []);

  if (loading) {
    return <div className="flex h-screen items-center justify-center bg-[#06101b] text-white">Loading emergency traffic workspace...</div>;
  }

  return (
    <div className="relative h-screen overflow-hidden bg-[#06101b] text-slate-100">
      <style>{`
        .junction-shell, .hospital-shell, .ambulance-shell, .start-shell, .route-junction-shell {
          background: transparent;
          border: 0;
        }
        .junction-badge, .hospital-badge, .start-badge, .ambulance-badge {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          border-radius: 999px;
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 0.12em;
          box-shadow: 0 12px 28px rgba(6,16,27,0.28);
          transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
        }
        .junction-badge {
          min-width: 48px;
          height: 24px;
          padding: 0 10px 0 8px;
          border: 1px solid rgba(255,255,255,0.16);
          background: rgba(15,23,42,0.9);
          color: #f8fafc;
        }
        .junction-selected .junction-badge {
          transform: translateY(-1px);
          box-shadow: 0 14px 32px rgba(6,16,27,0.36);
        }
        .junction-dot {
          width: 8px;
          height: 8px;
          border-radius: 999px;
        }
        .junction-label {
          line-height: 1;
        }
        .hospital-badge {
          min-width: 38px;
          height: 24px;
          padding: 0 10px;
          background: #dc2626;
          border: 1px solid rgba(255,255,255,0.28);
          color: white;
        }
        .start-badge {
          min-width: 38px;
          height: 24px;
          padding: 0 10px;
          background: rgba(180,83,9,0.88);
          border: 1px solid rgba(255,255,255,0.18);
          color: white;
        }
        .start-selected {
          background: rgba(245,158,11,0.95);
        }
        .ambulance-badge {
          min-width: 50px;
          height: 24px;
          padding: 0 10px;
          background: linear-gradient(135deg, #ffffff, #e2e8f0);
          border: 1px solid rgba(15,23,42,0.12);
          color: #0f172a;
          transform-origin: center;
        }
        .route-junction-badge {
          width: 42px;
          height: 42px;
          display: grid;
          place-items: center;
          border-radius: 999px;
          background: rgba(2,6,23,0.88);
          border: 2px solid rgba(255,255,255,0.88);
          box-shadow: 0 12px 28px rgba(6,16,27,0.36);
          position: relative;
        }
        .route-junction-ring {
          width: 22px;
          height: 22px;
          border-radius: 999px;
          border: 3px solid #16a34a;
          display: grid;
          place-items: center;
        }
        .route-junction-center {
          width: 8px;
          height: 8px;
          border-radius: 999px;
        }
        .route-junction-text {
          position: absolute;
          bottom: -16px;
          left: 50%;
          transform: translateX(-50%);
          padding: 2px 6px;
          border-radius: 999px;
          background: rgba(2,6,23,0.88);
          color: #f8fafc;
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 0.1em;
          white-space: nowrap;
          border: 1px solid rgba(255,255,255,0.18);
        }
        .signal-chip {
          display: inline-flex;
          min-width: 22px;
          justify-content: center;
          border-radius: 999px;
          padding: 2px 6px;
          font-size: 10px;
          font-weight: 700;
        }
      `}</style>

      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.14),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(34,197,94,0.12),transparent_24%)]" />

      <div className="absolute left-4 top-4 z-[1000] max-h-[calc(100vh-2rem)] w-[min(470px,calc(100%-2rem))] space-y-3 overflow-y-auto rounded-[30px] border border-white/10 bg-slate-950/84 p-4 shadow-2xl backdrop-blur-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.3em] text-cyan-300/85">Emergency Traffic Simulation</p>
            <h2 className="mt-1 text-2xl font-semibold text-white">Adaptive Route Control</h2>
            <p className="mt-2 text-sm text-slate-300">
              Control the ambulance speed, watch it follow the routed road, and monitor how generated route junctions open a dynamic
              4-way green corridor ahead of arrival.
            </p>
          </div>
          <div className="space-y-2 text-right">
            <div className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.18em] text-slate-200">
              {connectionState}
            </div>
            <div className="rounded-full border border-cyan-300/20 bg-cyan-400/10 px-3 py-2 text-xs font-semibold text-cyan-200">
              {speedControl.applied.toFixed(2)}x speed
            </div>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <SummaryCard
            title="Congestion"
            value={`${Math.round((globalStatus.congestion_index ?? 0) * 100)}%`}
            detail="Live density blend across the city view"
            tone="text-cyan-300"
          />
          <SummaryCard
            title="Camera Health"
            value={`${globalStatus.active_cameras}/${deferredJunctions.length}`}
            detail={`${globalStatus.degraded_cameras} degraded feeds`}
            tone="text-emerald-300"
          />
          <SummaryCard
            title="Ambulance Speed"
            value={`${speedControl.applied.toFixed(2)}x`}
            detail={speedControl.syncing ? 'Applying speed change...' : 'Live simulation multiplier'}
            tone="text-fuchsia-300"
          />
        </div>

        <div className="grid gap-3 md:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
            <p className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Dispatch Control</p>
            <select
              value={selectedStartId}
              onChange={(event) => setSelectedStartId(event.target.value)}
              className="mt-3 w-full rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-sm text-white outline-none"
            >
              {config.starting_points.map((startPoint) => (
                <option key={startPoint.id} value={startPoint.id}>
                  {startPoint.id} - {startPoint.name}
                </option>
              ))}
            </select>
            {selectedStart && (
              <div className="mt-3 rounded-2xl border border-amber-300/20 bg-amber-400/10 px-3 py-3 text-sm text-amber-50">
                Normal mode remains active near {config.activation_junction_id} and J2 until the ambulance reaches the first junction.
              </div>
            )}
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={startEmergency}
                disabled={starting || !selectedStartId}
                className="rounded-full bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {starting ? 'Starting...' : 'Start Emergency Simulation'}
              </button>
              <button
                type="button"
                onClick={clearEmergency}
                disabled={!simulationLive}
                className="rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Reset
              </button>
            </div>
          </div>

          <div className="rounded-3xl border border-fuchsia-400/20 bg-fuchsia-400/10 p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11px] uppercase tracking-[0.26em] text-fuchsia-200">Speed Control</p>
              <span className="rounded-full bg-slate-950/50 px-2 py-1 text-xs font-semibold text-fuchsia-100">
                {speedControl.desired.toFixed(2)}x
              </span>
            </div>
            <input
              type="range"
              min="0.5"
              max="2.5"
              step="0.05"
              value={speedControl.desired}
              onChange={(event) => setSpeedControl((current) => ({ ...current, desired: Number(event.target.value) }))}
              className="mt-4 h-2 w-full cursor-pointer accent-fuchsia-400"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              {[0.75, 1, 1.5, 2].map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setSpeedControl((current) => ({ ...current, desired: value }))}
                  className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                    Math.abs(speedControl.desired - value) < 0.01
                      ? 'bg-fuchsia-300 text-slate-950'
                      : 'border border-white/10 bg-white/5 text-white hover:bg-white/10'
                  }`}
                >
                  {value.toFixed(2)}x
                </button>
              ))}
            </div>
            <p className="mt-3 text-sm text-fuchsia-50/90">
              {speedControl.syncing
                ? 'Applying speed change to the live simulation...'
                : 'Adjust how fast the ambulance advances and how early route junctions prepare green.'}
            </p>
          </div>
        </div>

        <div className="rounded-3xl border border-emerald-400/30 bg-emerald-400/10 p-4">
          <p className="text-[11px] uppercase tracking-[0.26em] text-emerald-200">ETA Optimization</p>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <SummaryCard title="Normal ETA" value={`${simulationPlan.normalEta || 0} min`} detail="Without signal corridor" tone="text-amber-300" />
            <SummaryCard title="Optimized ETA" value={`${simulationPlan.optimizedEta || 0} min`} detail="With adaptive green wave" tone="text-emerald-300" />
            <SummaryCard title="Time Saved" value={`${simulationPlan.timeSaved || 0} min`} detail={`${Math.round(simulationPlan.timeSavedPercent || 0)}% faster`} tone="text-cyan-300" />
            <SummaryCard
              title="Live Countdown"
              value={formatCountdown(liveCountdown)}
              detail={emergencyState?.completed ? 'Ambulance arrived at hospital' : 'Realtime simulation countdown'}
              tone="text-white"
            />
          </div>
          {simulationPlan.hospital && (
            <p className="mt-3 text-sm text-slate-200">
              Destination: {simulationPlan.hospital.name} | Route: {simulationPlan.routeDistanceKm.toFixed(2)} km
            </p>
          )}
          {!simulationPlan.googleRouteAvailable && simulationPlan.googleRouteError && (
            <p className="mt-3 text-sm text-amber-100">
              Google Directions unavailable: {simulationPlan.googleRouteError}
            </p>
          )}
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
            <p className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Live Operations</p>
            <div className="mt-3 space-y-3 text-sm text-slate-200">
              <div>
                <div className="text-slate-400">Stage</div>
                <div className="mt-1 font-semibold text-white">{titleCase(emergencyState?.stage ?? 'idle')}</div>
              </div>
              <div>
                <div className="text-slate-400">Current Junction</div>
                <div className="mt-1 font-semibold text-white">{liveCurrentJunction}</div>
              </div>
              <div>
                <div className="text-slate-400">Next Target</div>
                <div className="mt-1 font-semibold text-white">{liveNextTarget}</div>
              </div>
              <div>
                <div className="text-slate-400">Distance To Next</div>
                <div className="mt-1 font-semibold text-white">
                  {Math.round(nextRouteJunction?.distanceM ?? emergencyState?.distance_to_next_m ?? 0)} m
                </div>
              </div>
              <div>
                <div className="text-slate-400">Signal Direction</div>
                <div className="mt-1 font-semibold text-white">{liveSignalDirection}</div>
              </div>
              <div>
                <div className="text-slate-400">Speed Profile</div>
                <div className="mt-1 font-semibold text-white">{speedControl.applied.toFixed(2)}x simulation speed</div>
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
            <p className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Junction Alerts</p>
            <div className="mt-3 space-y-2 text-sm text-slate-200">
              {recentAlerts.length === 0 && <div className="rounded-2xl bg-slate-900/70 px-3 py-2">No emergency alerts yet. Signals are cycling normally.</div>}
              {recentAlerts.map((alert, index) => (
                <div key={`${alert.timestamp}-${index}`} className="rounded-2xl bg-slate-900/70 px-3 py-2">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{titleCase(alert.stage)}</div>
                  <div className="mt-1 text-slate-200">{alert.message}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Route Junction Signals</p>
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
              {routeSignalJunctions.length} visible on route
            </div>
          </div>
          <div className="mt-3 space-y-2 text-sm text-slate-200">
            {routeSignalJunctions.length === 0 && (
              <div className="rounded-2xl bg-slate-900/70 px-3 py-2">
                Start a simulation to generate route-aligned 4-way junctions on the Google road path.
              </div>
            )}
            {routeSignalJunctions.map((junction) => (
              <div key={junction.id} className="rounded-2xl bg-slate-900/70 px-3 py-2">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold text-white">{junction.displayId}</div>
                    <div className="text-xs uppercase tracking-[0.18em] text-slate-400">{junction.generated ? 'Generated On Route' : 'Route Anchor'}</div>
                  </div>
                  <div className={`rounded-full px-2 py-1 text-xs font-semibold ${
                    junction.phase === 'GREEN'
                      ? 'bg-emerald-500/15 text-emerald-300'
                      : junction.phase === 'YELLOW'
                        ? 'bg-amber-400/15 text-amber-300'
                        : 'bg-rose-500/15 text-rose-300'
                  }`}>
                    {junction.phase}
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {SIGNAL_DIRECTIONS.map((direction) => {
                    const signalValue = junction.signals?.[direction] ?? 'RED';
                    const chipClass =
                      signalValue === 'GREEN'
                        ? 'bg-emerald-500/15 text-emerald-300'
                        : signalValue === 'YELLOW'
                          ? 'bg-amber-400/15 text-amber-300'
                          : 'bg-rose-500/15 text-rose-300';
                    return (
                      <span key={direction} className={`signal-chip ${chipClass}`}>
                        {direction}:{signalShort(signalValue)}
                      </span>
                    );
                  })}
                </div>
                <div className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                  {Math.round(junction.distanceM ?? 0)} m | ETA {Math.max(Math.round(junction.etaSec ?? 0), 0)} sec | {junction.statusLabel}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Google Directions</p>
            {simulationPlan.googleMapsUrl && (
              <a
                href={simulationPlan.googleMapsUrl}
                target="_blank"
                rel="noreferrer"
                className="rounded-full border border-cyan-300/30 bg-cyan-400/10 px-3 py-1 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-400/20"
              >
                Open In Google Maps
              </a>
            )}
          </div>
          <div className="mt-3 space-y-2 text-sm text-slate-200">
            {displayedDirections.length === 0 && (
              <div className="rounded-2xl bg-slate-900/70 px-3 py-2">
                Start a simulation to load Google road routing and turn-by-turn guidance.
              </div>
            )}
            {displayedDirections.map((step) => (
              <div key={step.index} className="rounded-2xl bg-slate-900/70 px-3 py-2">
                <div className="font-medium text-white">{step.instruction || 'Continue on the current road'}</div>
                <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">
                  {titleCase(step.phase ?? 'route')} | {Math.round((step.distance_m ?? 0) / 10) / 100} km | {Math.ceil((step.duration_s ?? 0) / 60)} min
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="absolute bottom-4 right-4 z-[1000] hidden w-[280px] rounded-[24px] border border-white/10 bg-slate-950/82 p-4 text-slate-100 shadow-2xl backdrop-blur-xl lg:block">
        <p className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Map Legend</p>
        <div className="mt-3 space-y-2 text-sm">
          <div className="flex items-center gap-3">
            <span className="h-1.5 w-10 rounded-full bg-cyan-400" />
            <span>Dispatch route to first junction</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="h-1.5 w-10 rounded-full bg-emerald-400" />
            <span>Emergency corridor route</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="h-4 w-4 rounded-full border-2 border-emerald-400 bg-slate-950" />
            <span>Generated route junction</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-black text-slate-950">AMB</span>
            <span>Ambulance position</span>
          </div>
        </div>
      </div>

      <MapContainer center={[13.0674, 80.2425]} zoom={13} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />

        <FitToRoute points={routeFocusPoints} />

        {approachRoutePoints.length > 1 && (
          <Polyline
            positions={approachRoutePoints}
            pathOptions={{ color: '#38bdf8', weight: 5, opacity: 0.88, dashArray: '10 8', lineCap: 'round' }}
          />
        )}
        {emergencyRoutePoints.length > 1 && (
          <Polyline
            positions={emergencyRoutePoints}
            pathOptions={{ color: '#22c55e', weight: 6, opacity: 0.92, lineCap: 'round', lineJoin: 'round' }}
          />
        )}

        {config.starting_points.map((startPoint) => (
          <Marker
            key={startPoint.id}
            position={[startPoint.lat, startPoint.lng]}
            icon={createStartIcon(startPoint.id, startPoint.id === selectedStartId)}
            eventHandlers={{ click: () => setSelectedStartId(startPoint.id) }}
          >
            <Tooltip direction="top" offset={[0, -8]} opacity={0.94}>
              {startPoint.id} - {startPoint.name}
            </Tooltip>
          </Marker>
        ))}

        {config.hospitals.map((hospital) => (
          <Marker key={hospital.id ?? hospital.name} position={[hospital.lat, hospital.lng]} icon={createHospitalIcon(hospital.id ?? 'H')}>
            <Tooltip direction="top" offset={[0, -8]} opacity={0.94}>
              {hospital.name}
            </Tooltip>
          </Marker>
        ))}

        {displayedAmbulance && (
          <Marker position={displayedAmbulance} icon={createAmbulanceIcon(ambulanceHeading)}>
            <Tooltip direction="top" offset={[0, -8]} opacity={0.94}>
              Ambulance | ETA {formatCountdown(liveCountdown)}
            </Tooltip>
          </Marker>
        )}

        {routeSignalJunctions.map((junction) => (
          <Marker key={junction.id} position={[junction.lat, junction.lng]} icon={createRouteJunctionIcon(junction)}>
            <Tooltip direction="top" offset={[0, -18]} opacity={0.95}>
              {junction.displayId} | {junction.phase}
            </Tooltip>
            <Popup>
              <div className="min-w-[240px] p-1 text-slate-900">
                <h3 className="text-lg font-bold">{junction.displayId}</h3>
                <div className="mt-2 space-y-1 text-sm">
                  <p><strong>Type:</strong> {junction.generated ? 'Generated route junction' : 'Route anchor junction'}</p>
                  <p><strong>Phase:</strong> {junction.phase}</p>
                  <p><strong>Active Direction:</strong> {junction.activeDirection}</p>
                  <p><strong>Distance:</strong> {Math.round(junction.distanceM ?? 0)} m</p>
                  <p><strong>ETA:</strong> {Math.max(Math.round(junction.etaSec ?? 0), 0)} sec</p>
                  <p><strong>Status:</strong> {junction.statusLabel}</p>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {SIGNAL_DIRECTIONS.map((direction) => (
                      <span key={direction} className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-800">
                        {direction}:{signalShort(junction.signals?.[direction] ?? 'RED')}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </Popup>
          </Marker>
        ))}

        {deferredJunctions.map((junction) => (
          <Marker
            key={junction.junction_id}
            position={[junction.lat, junction.lng]}
            icon={createJunctionIcon(junction, selectedJunctionId)}
            eventHandlers={{ click: () => setSelectedJunctionId(junction.junction_id) }}
          >
            <Popup>
              <div className="min-w-[250px] p-1 text-slate-900">
                <h3 className="text-lg font-bold">{junction.name}</h3>
                <div className="mt-2 space-y-1 text-sm">
                  <p><strong>Junction:</strong> {junction.junction_id}</p>
                  <p><strong>Phase:</strong> {junction.phase}</p>
                  <p><strong>Active Direction:</strong> {junction.active_direction ?? 'N/A'}</p>
                  <p><strong>Queue Length:</strong> {junction.queue_length}</p>
                  <p><strong>Density:</strong> {Math.round((junction.density ?? 0) * 100)}%</p>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {['N', 'S', 'E', 'W'].map((direction) => {
                      const signalValue = junction.signals?.[direction] ?? 'RED';
                      const chipClass =
                        signalValue === 'GREEN'
                          ? 'bg-emerald-500/15 text-emerald-700'
                          : signalValue === 'YELLOW'
                            ? 'bg-amber-400/20 text-amber-700'
                            : 'bg-rose-500/15 text-rose-700';
                      return (
                        <span key={direction} className={`signal-chip ${chipClass}`}>
                          {direction}:{signalShort(signalValue)}
                        </span>
                      );
                    })}
                  </div>
                  {junction.signal_alert && <p><strong>Alert:</strong> {junction.signal_alert}</p>}
                </div>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
