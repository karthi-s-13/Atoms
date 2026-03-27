import polyline from '@mapbox/polyline';
import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
import { getBackendWsUrl } from '../lib/backend';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
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
const MAX_ROUTE_PANEL_JUNCTIONS = 4;
const MAP_THEME_STORAGE_KEY = 'atoms-map-theme';
const MAP_STREAM_PING_MS = 12000;
const MAP_RECONNECT_BASE_DELAY_MS = 900;
const MAP_RECONNECT_MAX_DELAY_MS = 6000;
const MAP_PAGE_HEIGHT_CLASS = 'h-[calc(100vh-12rem)] min-h-[720px]';
const MAP_TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const CORRIDOR_OPEN_WINDOW_SEC = 5;
const CORRIDOR_ARM_WINDOW_SEC = 10;
const CORRIDOR_WATCH_WINDOW_SEC = 18;
const MAP_TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const MAP_THEMES = {
  dark: {
    label: 'Dark',
    routeApproachColor: '#38bdf8',
    routeEmergencyColor: '#22c55e',
    routeGlowColor: '#34d399',
    routeProgressColor: '#67e8f9',
    trafficDotColor: '#f8fafc',
    trafficMutedDotColor: '#94a3b8',
    trafficCorridorColor: '#34d399',
    networkLineColor: 'rgba(148,163,184,0.22)',
    rootClass: 'bg-[#06101b] text-slate-100',
    overlayPanelClass: 'border-white/10 bg-slate-950/84 text-slate-100 shadow-2xl backdrop-blur-xl',
    summaryCardClass: 'border-white/10 bg-white/[0.04]',
    sectionCardClass: 'border-white/10 bg-white/[0.04]',
    surfaceCardClass: 'border-white/10 bg-slate-900/70',
    kickerTextClass: 'text-cyan-300/85',
    headingTextClass: 'text-white',
    bodyTextClass: 'text-slate-300',
    strongTextClass: 'text-slate-200',
    mutedTextClass: 'text-slate-400',
    faintTextClass: 'text-slate-500',
    connectionPillClass: 'border-white/10 bg-white/5 text-slate-200',
    speedPillClass: 'border-cyan-300/20 bg-cyan-400/10 text-cyan-200',
    selectClass: 'border-white/10 bg-slate-900/80 text-white',
    primaryButtonClass: 'bg-cyan-400 text-slate-950 hover:bg-cyan-300',
    secondaryButtonClass: 'border border-white/15 bg-white/5 text-white hover:bg-white/10',
    noteClass: 'border border-amber-300/20 bg-amber-400/10 text-amber-50',
    speedPanelClass: 'border-fuchsia-400/20 bg-fuchsia-400/10',
    speedPanelTitleClass: 'text-fuchsia-200',
    speedPanelBadgeClass: 'bg-slate-950/50 text-fuchsia-100',
    speedPanelCopyClass: 'text-fuchsia-50/90',
    speedPresetActiveClass: 'bg-fuchsia-300 text-slate-950',
    speedPresetInactiveClass: 'border border-white/10 bg-white/5 text-white hover:bg-white/10',
    etaPanelClass: 'border-emerald-400/30 bg-emerald-400/10',
    etaTitleClass: 'text-emerald-200',
    linkButtonClass: 'border-cyan-300/30 bg-cyan-400/10 text-cyan-200 hover:bg-cyan-400/20',
    themeToggleBaseClass: 'border-white/10 bg-white/5 text-slate-200 hover:bg-white/10',
    themeToggleActiveClass: 'border-transparent bg-cyan-300 text-slate-950',
    popupContentClass: 'text-slate-100',
    popupMutedClass: 'text-slate-400',
    popupNeutralChipClass: 'bg-white/10 text-slate-100',
    popupSignalToneClasses: {
      GREEN: 'bg-emerald-500/15 text-emerald-300',
      YELLOW: 'bg-amber-400/15 text-amber-300',
      RED: 'bg-rose-500/15 text-rose-300',
    },
    backdropStyle: {
      backgroundImage:
        'radial-gradient(circle at top left, rgba(14,165,233,0.14), transparent 30%), radial-gradient(circle at bottom right, rgba(34,197,94,0.12), transparent 24%)',
    },
    cssVars: {
      '--map-page-bg': '#06101b',
      '--map-marker-shadow': '0 12px 28px rgba(6,16,27,0.28)',
      '--map-marker-selected-shadow': '0 14px 32px rgba(6,16,27,0.36)',
      '--map-junction-bg': 'rgba(15,23,42,0.9)',
      '--map-junction-text': '#f8fafc',
      '--map-hospital-bg': '#dc2626',
      '--map-hospital-text': '#ffffff',
      '--map-start-bg': 'rgba(180,83,9,0.88)',
      '--map-start-selected-bg': 'rgba(245,158,11,0.95)',
      '--map-start-text': '#ffffff',
      '--map-ambulance-bg': 'linear-gradient(135deg, #ffffff, #e2e8f0)',
      '--map-ambulance-text': '#0f172a',
      '--map-route-badge-bg': 'rgba(2,6,23,0.88)',
      '--map-route-badge-border': 'rgba(255,255,255,0.88)',
      '--map-route-label-bg': 'rgba(2,6,23,0.88)',
      '--map-route-label-text': '#f8fafc',
      '--map-popup-bg': 'rgba(2,6,23,0.95)',
      '--map-popup-border': 'rgba(148,163,184,0.22)',
      '--map-popup-text': '#e2e8f0',
      '--map-popup-muted': '#94a3b8',
      '--map-tooltip-bg': 'rgba(2,6,23,0.92)',
      '--map-tooltip-border': 'rgba(148,163,184,0.2)',
      '--map-tooltip-text': '#e2e8f0',
      '--map-zoom-bg': 'rgba(15,23,42,0.9)',
      '--map-zoom-text': '#e2e8f0',
      '--map-zoom-border': 'rgba(148,163,184,0.18)',
      '--map-zoom-hover': 'rgba(30,41,59,0.96)',
      '--map-attribution-bg': 'rgba(2,6,23,0.76)',
      '--map-attribution-text': '#94a3b8',
      '--map-tile-fallback': '#020617',
      '--map-tile-filter': 'brightness(0.72) invert(1) contrast(1.08) hue-rotate(185deg) saturate(0.42)',
      '--map-tile-opacity': '0.96',
      '--map-route-glow': '#34d399',
      '--map-corridor-glow': 'rgba(52,211,153,0.2)',
      '--map-route-progress': '#67e8f9',
      '--map-traffic-dot': '#f8fafc',
      '--map-traffic-dot-muted': 'rgba(148,163,184,0.78)',
      '--map-traffic-corridor': '#34d399',
      '--map-traffic-line': 'rgba(148,163,184,0.22)',
      '--map-progress-track': 'rgba(255,255,255,0.08)',
      '--map-progress-fill-start': '#38bdf8',
      '--map-progress-fill-end': '#22c55e',
      '--map-ambulance-siren': '#22d3ee',
      '--map-ambulance-siren-alt': '#fb7185',
    },
  },
  light: {
    label: 'Light',
    routeApproachColor: '#0284c7',
    routeEmergencyColor: '#16a34a',
    routeGlowColor: '#16a34a',
    routeProgressColor: '#0284c7',
    trafficDotColor: '#0f172a',
    trafficMutedDotColor: '#64748b',
    trafficCorridorColor: '#16a34a',
    networkLineColor: 'rgba(100,116,139,0.2)',
    rootClass: 'bg-[#ebf3fb] text-slate-900',
    overlayPanelClass: 'border-slate-300/70 bg-white/82 text-slate-900 shadow-[0_28px_70px_rgba(148,163,184,0.24)] backdrop-blur-xl',
    summaryCardClass: 'border-slate-200/90 bg-white/88',
    sectionCardClass: 'border-slate-200/90 bg-white/88',
    surfaceCardClass: 'border-slate-200/90 bg-slate-50/95',
    kickerTextClass: 'text-cyan-700',
    headingTextClass: 'text-slate-900',
    bodyTextClass: 'text-slate-600',
    strongTextClass: 'text-slate-800',
    mutedTextClass: 'text-slate-500',
    faintTextClass: 'text-slate-400',
    connectionPillClass: 'border-slate-300/80 bg-white/90 text-slate-700',
    speedPillClass: 'border-cyan-400/30 bg-cyan-50 text-cyan-700',
    selectClass: 'border-slate-300 bg-white text-slate-900 shadow-sm',
    primaryButtonClass: 'bg-cyan-600 text-white hover:bg-cyan-500',
    secondaryButtonClass: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
    noteClass: 'border border-amber-300/70 bg-amber-50 text-amber-800',
    speedPanelClass: 'border-fuchsia-300/40 bg-fuchsia-50',
    speedPanelTitleClass: 'text-fuchsia-700',
    speedPanelBadgeClass: 'bg-white/90 text-fuchsia-700',
    speedPanelCopyClass: 'text-fuchsia-700/90',
    speedPresetActiveClass: 'bg-fuchsia-600 text-white',
    speedPresetInactiveClass: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
    etaPanelClass: 'border-emerald-300/60 bg-emerald-50',
    etaTitleClass: 'text-emerald-700',
    linkButtonClass: 'border-cyan-400/30 bg-cyan-50 text-cyan-700 hover:bg-cyan-100',
    themeToggleBaseClass: 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50',
    themeToggleActiveClass: 'border-transparent bg-slate-900 text-white',
    popupContentClass: 'text-slate-900',
    popupMutedClass: 'text-slate-500',
    popupNeutralChipClass: 'bg-slate-100 text-slate-800',
    popupSignalToneClasses: {
      GREEN: 'bg-emerald-100 text-emerald-700',
      YELLOW: 'bg-amber-100 text-amber-700',
      RED: 'bg-rose-100 text-rose-700',
    },
    backdropStyle: {
      backgroundImage:
        'radial-gradient(circle at top left, rgba(14,165,233,0.14), transparent 28%), radial-gradient(circle at bottom right, rgba(59,130,246,0.1), transparent 22%), linear-gradient(180deg, rgba(255,255,255,0.25), rgba(226,232,240,0.18))',
    },
    cssVars: {
      '--map-page-bg': '#ebf3fb',
      '--map-marker-shadow': '0 12px 24px rgba(148,163,184,0.24)',
      '--map-marker-selected-shadow': '0 14px 30px rgba(59,130,246,0.24)',
      '--map-junction-bg': 'rgba(255,255,255,0.96)',
      '--map-junction-text': '#0f172a',
      '--map-hospital-bg': '#dc2626',
      '--map-hospital-text': '#ffffff',
      '--map-start-bg': '#b45309',
      '--map-start-selected-bg': '#f59e0b',
      '--map-start-text': '#ffffff',
      '--map-ambulance-bg': 'linear-gradient(135deg, #ffffff, #f8fafc)',
      '--map-ambulance-text': '#0f172a',
      '--map-route-badge-bg': 'rgba(255,255,255,0.96)',
      '--map-route-badge-border': 'rgba(15,23,42,0.12)',
      '--map-route-label-bg': 'rgba(255,255,255,0.96)',
      '--map-route-label-text': '#0f172a',
      '--map-popup-bg': 'rgba(255,255,255,0.98)',
      '--map-popup-border': 'rgba(148,163,184,0.4)',
      '--map-popup-text': '#0f172a',
      '--map-popup-muted': '#64748b',
      '--map-tooltip-bg': 'rgba(255,255,255,0.96)',
      '--map-tooltip-border': 'rgba(148,163,184,0.35)',
      '--map-tooltip-text': '#0f172a',
      '--map-zoom-bg': 'rgba(255,255,255,0.96)',
      '--map-zoom-text': '#0f172a',
      '--map-zoom-border': 'rgba(148,163,184,0.4)',
      '--map-zoom-hover': 'rgba(241,245,249,0.98)',
      '--map-attribution-bg': 'rgba(255,255,255,0.86)',
      '--map-attribution-text': '#475569',
      '--map-tile-fallback': '#dbeafe',
      '--map-tile-filter': 'none',
      '--map-tile-opacity': '1',
      '--map-route-glow': '#16a34a',
      '--map-corridor-glow': 'rgba(22,163,74,0.18)',
      '--map-route-progress': '#0284c7',
      '--map-traffic-dot': '#0f172a',
      '--map-traffic-dot-muted': 'rgba(71,85,105,0.72)',
      '--map-traffic-corridor': '#16a34a',
      '--map-traffic-line': 'rgba(100,116,139,0.2)',
      '--map-progress-track': 'rgba(148,163,184,0.2)',
      '--map-progress-fill-start': '#0ea5e9',
      '--map-progress-fill-end': '#16a34a',
      '--map-ambulance-siren': '#0891b2',
      '--map-ambulance-siren-alt': '#e11d48',
    },
  },
};

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

function normalizeSignalPhase(phase) {
  const normalized = String(phase || 'RED').toUpperCase();
  return ['GREEN', 'YELLOW', 'RED'].includes(normalized) ? normalized : 'RED';
}

function normalizeSignalDirection(direction) {
  const normalized = String(direction || '').toUpperCase();
  if (SIGNAL_DIRECTIONS.includes(normalized)) return normalized;
  if (normalized === 'NORTH') return 'N';
  if (normalized === 'SOUTH') return 'S';
  if (normalized === 'EAST') return 'E';
  if (normalized === 'WEST') return 'W';
  return 'N';
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
  const boundedDistance = Math.max(0, Math.min(targetDistance, cumulative[cumulative.length - 1] ?? 0));

  for (let index = 1; index < cumulative.length; index += 1) {
    if (cumulative[index] >= boundedDistance) {
      const previousDistance = cumulative[index - 1];
      const segmentDistance = Math.max(cumulative[index] - previousDistance, 1e-6);
      const ratio = (boundedDistance - previousDistance) / segmentDistance;
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

function routeDirection(from, to) {
  if (!from || !to) return 'N';
  const latDelta = to[0] - from[0];
  const lngDelta = to[1] - from[1];
  if (Math.abs(latDelta) >= Math.abs(lngDelta)) {
    return latDelta >= 0 ? 'N' : 'S';
  }
  return lngDelta >= 0 ? 'E' : 'W';
}

function seededUnit(seed, index) {
  let hash = 2166136261;
  const text = `${seed}:${index}`;
  for (let cursor = 0; cursor < text.length; cursor += 1) {
    hash ^= text.charCodeAt(cursor);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) % 1000) / 1000;
}

function buildCorridorFractions(seed, count = 4) {
  const lowerBound = 0.16;
  const upperBound = 0.86;
  const bucket = (upperBound - lowerBound) / count;
  return Array.from({ length: count }, (_, index) => {
    const offset = 0.18 + (seededUnit(seed, index) * 0.48);
    return lowerBound + (bucket * index) + (bucket * offset);
  });
}

function naturalSignalState(index, nowMs) {
  const cycleMs = 10000 + (index * 1400);
  const shiftedNow = nowMs + (index * 1900);
  const directionStep = Math.floor(shiftedNow / cycleMs);
  const activeDirection = SIGNAL_DIRECTIONS[(index + directionStep) % SIGNAL_DIRECTIONS.length];
  const phaseProgress = (shiftedNow % cycleMs) / cycleMs;
  const phase = phaseProgress < 0.66 ? 'GREEN' : phaseProgress < 0.82 ? 'YELLOW' : 'RED';
  return {
    phase,
    activeDirection,
    signals: buildSignals(activeDirection, phase),
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
  const waveClass = junction.green_wave_active ? 'junction-wave' : '';
  const lockedClass = junction.signal_locked ? 'junction-locked' : '';
  return L.divIcon({
    className: `junction-shell ${selected} ${waveClass} ${lockedClass}`,
    html: `
      <div class="junction-badge" style="border-color:${color}; background:${color}">
        <span class="junction-aura" style="background:${color}"></span>
        <span class="junction-dot"></span>
      </div>
    `,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
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
    html: `
      <div class="ambulance-rotor" style="transform: rotate(${heading}deg)">
        <span class="ambulance-siren ambulance-siren-left"></span>
        <span class="ambulance-siren ambulance-siren-right"></span>
        <div class="ambulance-badge">
          <span class="ambulance-emblem">+</span>
          <span class="ambulance-label">AMB</span>
        </div>
      </div>
    `,
    iconSize: [76, 34],
    iconAnchor: [38, 17],
  });
}

function createRouteJunctionIcon(junction) {
  const color = junction.phase === 'GREEN' ? '#16a34a' : junction.phase === 'YELLOW' ? '#eab308' : '#ef4444';
  const corridorState = junction.passed ? 'cleared' : junction.corridorState ?? 'monitor';
  const compactLabel = String(junction.displayId || '').replace(/^J/i, '');
  return L.divIcon({
    className: 'route-junction-shell',
    html: `
      <div class="route-junction-badge state-${corridorState}">
        <span class="route-junction-halo"></span>
        <div class="route-junction-ring" style="border-color:${color}">
          <span class="route-junction-center" style="background:${color}"></span>
        </div>
        <span class="route-junction-text">${compactLabel}</span>
      </div>
    `,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
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

function SummaryCard({ title, value, detail, tone, theme }) {
  const valueTone = tone ?? theme.headingTextClass;
  return (
    <div className={`rounded-3xl border px-4 py-3 ${theme.summaryCardClass}`}>
      <p className={`text-[11px] uppercase tracking-[0.24em] ${theme.mutedTextClass}`}>{title}</p>
      <p className={`mt-2 text-2xl font-semibold ${valueTone}`}>{value}</p>
      <p className={`mt-1 text-sm ${theme.bodyTextClass}`}>{detail}</p>
    </div>
  );
}

function corridorStateLabel(state) {
  if (state === 'open') return 'Open';
  if (state === 'arming') return 'Arming';
  if (state === 'watch') return 'Watch';
  if (state === 'cleared') return 'Cleared';
  return 'Cycle';
}

export default function MapPage() {
  const [mapTheme, setMapTheme] = useState(() => {
    if (typeof window === 'undefined') {
      return 'dark';
    }
    try {
      const stored = window.localStorage.getItem(MAP_THEME_STORAGE_KEY);
      return stored === 'light' ? 'light' : 'dark';
    } catch {
      return 'dark';
    }
  });
  const [junctionMap, setJunctionMap] = useState({});
  const [coordinationState, setCoordinationState] = useState(INITIAL_COORDINATION);
  const [globalStatus, setGlobalStatus] = useState(INITIAL_STATUS);
  const [config, setConfig] = useState(INITIAL_CONFIG);
  const [selectedStartId, setSelectedStartId] = useState('');
  const [selectedJunctionId, setSelectedJunctionId] = useState('');
  const [simulationPlan, setSimulationPlan] = useState(INITIAL_PLAN);
  const [displayedAmbulance, setDisplayedAmbulance] = useState(null);
  const [ambulanceHeading, setAmbulanceHeading] = useState(0);
  const [speedControl, setSpeedControl] = useState({ desired: 1, applied: 1, syncing: false });
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [connectionState, setConnectionState] = useState('connecting');
  const activeTheme = MAP_THEMES[mapTheme] ?? MAP_THEMES.dark;
  const motionFrameRef = useRef(0);
  const speedSyncTimeoutRef = useRef(0);
  const displayedAmbulanceRef = useRef(null);
  const ambulanceMotionRef = useRef({ position: null, timestamp: 0, speedMps: 0 });
  const mapStreamSocketRef = useRef(null);
  const mapStreamReconnectTimeoutRef = useRef(0);
  const mapStreamReconnectAttemptRef = useRef(0);

  useEffect(() => {
    try {
      window.localStorage.setItem(MAP_THEME_STORAGE_KEY, mapTheme);
    } catch {
      // Ignore storage write failures and keep the in-memory theme.
    }
  }, [mapTheme]);

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
          const firstActivationJunctionId = emergencyConfig?.starting_points?.[0]?.activation_junction_id
            ?? emergencyConfig?.activation_junction_id
            ?? 'J1';
          setSelectedStartId(firstStartId);
          setSelectedJunctionId(firstActivationJunctionId);
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
    let cancelled = false;
    const socketUrl = getBackendWsUrl('/ws/map-stream');

    const clearReconnectTimeout = () => {
      if (mapStreamReconnectTimeoutRef.current) {
        window.clearTimeout(mapStreamReconnectTimeoutRef.current);
        mapStreamReconnectTimeoutRef.current = 0;
      }
    };

    const handleStreamPayload = (payload) => {
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
    };

    const scheduleReconnect = () => {
      if (cancelled) {
        return;
      }
      clearReconnectTimeout();
      mapStreamReconnectAttemptRef.current += 1;
      const delay = Math.min(
        MAP_RECONNECT_MAX_DELAY_MS,
        MAP_RECONNECT_BASE_DELAY_MS * (2 ** Math.max(mapStreamReconnectAttemptRef.current - 1, 0)),
      );
      setConnectionState('connecting');
      mapStreamReconnectTimeoutRef.current = window.setTimeout(() => {
        mapStreamReconnectTimeoutRef.current = 0;
        connect();
      }, delay);
    };

    const connect = () => {
      if (cancelled) {
        return;
      }
      setConnectionState('connecting');
      const socket = new WebSocket(socketUrl);
      mapStreamSocketRef.current = socket;
      let pingHandle = 0;

      socket.addEventListener('open', () => {
        if (cancelled || mapStreamSocketRef.current !== socket) {
          return;
        }
        mapStreamReconnectAttemptRef.current = 0;
        setConnectionState('live');
        pingHandle = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }));
          }
        }, MAP_STREAM_PING_MS);
      });

      socket.addEventListener('close', () => {
        if (pingHandle) {
          window.clearInterval(pingHandle);
        }
        if (cancelled || mapStreamSocketRef.current !== socket) {
          return;
        }
        mapStreamSocketRef.current = null;
        scheduleReconnect();
      });

      socket.addEventListener('error', () => {
        if (cancelled || mapStreamSocketRef.current !== socket) {
          return;
        }
        setConnectionState('error');
      });

      socket.addEventListener('message', (event) => {
        if (cancelled || mapStreamSocketRef.current !== socket) {
          return;
        }
        try {
          handleStreamPayload(JSON.parse(event.data));
        } catch (error) {
          console.error('Map stream parse error:', error);
          setConnectionState('error');
        }
      });
    };

    connect();

    return () => {
      cancelled = true;
      clearReconnectTimeout();
      if (mapStreamSocketRef.current) {
        mapStreamSocketRef.current.close();
        mapStreamSocketRef.current = null;
      }
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
    if (selectedStart?.activation_junction_id && !simulationPlan.fullRoute.length) {
      setSelectedJunctionId(selectedStart.activation_junction_id);
    }
  }, [selectedStart?.activation_junction_id, simulationPlan.fullRoute.length]);

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
  const recentAlerts = [...(emergencyState?.alerts ?? [])].slice(-4).reverse();
  const displayedDirections = (simulationPlan.directions ?? []).slice(0, 4);
  const liveCountdown = emergencyState?.remaining_eta_sec ?? 0;
  const simulationLive = Boolean(
    simulationPlan.fullRoute.length ||
      emergencyState?.stage === 'approach' ||
      emergencyState?.stage === 'emergency' ||
      emergencyState?.completed,
  );
  const corridorRoutePoints = useMemo(
    () => (emergencyRoutePoints.length > 1 ? emergencyRoutePoints : fullRoutePoints),
    [emergencyRoutePoints, fullRoutePoints],
  );
  const corridorRouteCumulative = useMemo(
    () => cumulativeRouteDistances(corridorRoutePoints),
    [corridorRoutePoints],
  );
  const routeSeed = simulationPlan.startingPoint?.id ?? emergencyState?.starting_point?.id ?? selectedStartId ?? 'corridor-demo';
  const routeSignalJunctions = useMemo(() => {
    if (!simulationLive || corridorRoutePoints.length < 2 || corridorRouteCumulative.length < 2) {
      return [];
    }

    const routeTotalDistance = corridorRouteCumulative[corridorRouteCumulative.length - 1] ?? 0;
    if (routeTotalDistance <= 60) {
      return [];
    }

    const progressDistance = displayedAmbulance
      ? routeProgressDistance(corridorRoutePoints, corridorRouteCumulative, displayedAmbulance)
      : 0;
    const remainingDistance = Math.max(routeTotalDistance - progressDistance, 0);
    const fallbackSpeed = liveCountdown > 0 ? Math.max(remainingDistance / Math.max(liveCountdown, 1), 1) : 1;
    const speedMps = Math.max(Number(ambulanceMotionRef.current.speedMps || 0), fallbackSpeed, 1);
    const nowMs = Date.now();

    const generated = buildCorridorFractions(routeSeed, MAX_ROUTE_PANEL_JUNCTIONS)
      .map((fraction, index) => {
        const targetDistance = routeTotalDistance * fraction;
        const point = pointAtRouteDistance(corridorRoutePoints, corridorRouteCumulative, targetDistance);
        if (!point) return null;
        const before = pointAtRouteDistance(
          corridorRoutePoints,
          corridorRouteCumulative,
          Math.max(targetDistance - 22, 0),
        ) ?? point;
        const after = pointAtRouteDistance(
          corridorRoutePoints,
          corridorRouteCumulative,
          Math.min(targetDistance + 22, routeTotalDistance),
        ) ?? point;
        const natural = naturalSignalState(index, nowMs);
        const pathDirection = normalizeSignalDirection(routeDirection(before, after));
        const passed = Boolean(emergencyState?.completed) || progressDistance > targetDistance + 18;
        const distanceM = passed ? null : Math.max(targetDistance - progressDistance, 0);
        const etaSec = distanceM == null ? null : distanceM / speedMps;
        return {
          id: `corridor-${index + 1}`,
          displayId: `J${index + 1}`,
          name: `Corridor Junction ${index + 1}`,
          lat: point[0],
          lng: point[1],
          targetDistance,
          pathDirection,
          distanceM,
          etaSec,
          passed,
          locked: false,
          corridorState: 'cycle',
          statusLabel: `${index === 0 ? 'Lead' : 'Downstream'} junction on the optimized route`,
          emergency: false,
          status: 'stable',
          ...natural,
        };
      })
      .filter(Boolean);

    const nextActiveIndex = generated.findIndex((junction) => !junction.passed);

    return generated.map((junction, index) => {
      const natural = naturalSignalState(index, nowMs);
      if (junction.passed) {
        return {
          ...junction,
          ...natural,
          corridorState: 'cleared',
          statusLabel: `${junction.displayId} released after ambulance passage`,
        };
      }

      if (index === nextActiveIndex) {
        if ((junction.etaSec ?? Infinity) <= CORRIDOR_OPEN_WINDOW_SEC) {
          return {
            ...junction,
            phase: 'GREEN',
            activeDirection: junction.pathDirection,
            signals: buildSignals(junction.pathDirection, 'GREEN'),
            locked: true,
            corridorState: 'open',
            statusLabel: `${junction.displayId} green corridor active on the route`,
          };
        }
        if ((junction.etaSec ?? Infinity) <= CORRIDOR_ARM_WINDOW_SEC) {
          return {
            ...junction,
            phase: 'YELLOW',
            activeDirection: junction.pathDirection,
            signals: buildSignals(junction.pathDirection, 'YELLOW'),
            corridorState: 'arming',
            statusLabel: `${junction.displayId} switching toward ambulance approach`,
          };
        }
        return {
          ...junction,
          ...natural,
          corridorState: 'watch',
          statusLabel: `${junction.displayId} monitoring the incoming ambulance`,
        };
      }

      if (index === nextActiveIndex + 1) {
        if ((junction.etaSec ?? Infinity) <= CORRIDOR_ARM_WINDOW_SEC * 1.5) {
          return {
            ...junction,
            phase: 'YELLOW',
            activeDirection: junction.pathDirection,
            signals: buildSignals(junction.pathDirection, 'YELLOW'),
            corridorState: 'watch',
            statusLabel: `${junction.displayId} queued as the next handoff`,
          };
        }
        return {
          ...junction,
          ...natural,
          corridorState: 'watch',
          statusLabel: `${junction.displayId} staged downstream on the optimized path`,
        };
      }

      return {
        ...junction,
        ...natural,
        corridorState: 'cycle',
        statusLabel: `${junction.displayId} holding a normal cycle until preemption`,
      };
    });
  }, [
    corridorRouteCumulative,
    corridorRoutePoints,
    displayedAmbulance,
    emergencyState?.completed,
    emergencyState?.starting_point?.id,
    liveCountdown,
    routeSeed,
    simulationLive,
  ]);
  const displayApproachRoutePoints = simulationLive ? approachRoutePoints : [];
  const displayEmergencyRoutePoints = simulationLive ? emergencyRoutePoints : [];
  const routeFocusPoints = simulationLive
    ? (fullRoutePoints.length > 1 ? fullRoutePoints : corridorRoutePoints)
    : [];
  const nextRouteJunction = routeSignalJunctions.find((junction) => !junction.passed) ?? null;
  const visibleRouteSignalJunctions = routeSignalJunctions;
  const routePanelJunctions = routeSignalJunctions.slice(0, MAX_ROUTE_PANEL_JUNCTIONS);
  const visibleStartPoints = useMemo(() => {
    const activeStartId = simulationPlan.startingPoint?.id ?? selectedStartId;
    if (!activeStartId) return config.starting_points;
    return config.starting_points.filter((startPoint) => startPoint.id === activeStartId);
  }, [config.starting_points, selectedStartId, simulationPlan.startingPoint]);
  const visibleHospitals = useMemo(() => {
    const activeHospitalId = simulationLive
      ? simulationPlan.hospital?.id ?? simulationPlan.hospital?.name
      : selectedStart?.hospital_id ?? null;
    if (!activeHospitalId) return config.hospitals;
    return config.hospitals.filter((hospital) => (hospital.id ?? hospital.name) === activeHospitalId);
  }, [config.hospitals, selectedStart?.hospital_id, simulationLive, simulationPlan.hospital]);
  const visibleCityJunctions = [];
  const liveCurrentJunction = !simulationLive
    ? 'Awaiting Dispatch'
    : emergencyState?.completed
    ? 'Route Cleared'
    : nextRouteJunction?.displayId ?? 'Transit';
  const liveNextTarget = simulationLive
    ? (emergencyState?.completed ? simulationPlan.hospital?.id ?? simulationPlan.hospital?.name ?? 'Hospital' : nextRouteJunction?.displayId ?? simulationPlan.hospital?.id ?? 'Waiting')
    : simulationPlan.hospital?.id ?? selectedStart?.hospital_id ?? 'Waiting';
  const liveSignalDirection = simulationLive
    ? titleCase(nextRouteJunction?.activeDirection ?? emergencyState?.active_signal_direction ?? 'pending')
    : 'Pending';
  const mapWorkspaceStyle = useMemo(
    () => ({
      colorScheme: mapTheme,
      ...activeTheme.cssVars,
    }),
    [activeTheme, mapTheme],
  );

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
    setDisplayedAmbulance(null);
    setAmbulanceHeading(0);
    setSimulationPlan(INITIAL_PLAN);
    setSpeedControl({ desired: 1, applied: 1, syncing: false });
    try {
      await fetch('/api/emergency/clear', { method: 'POST' });
    } catch (error) {
      console.error('Emergency clear failed:', error);
    }
  };

  if (loading) {
    return (
      <div
        className={`flex ${MAP_PAGE_HEIGHT_CLASS} items-center justify-center rounded-[2rem] ${activeTheme.rootClass}`}
        style={mapWorkspaceStyle}
      >
        Loading emergency traffic workspace...
      </div>
    );
  }

  return (
    <div className={`map-workspace relative ${MAP_PAGE_HEIGHT_CLASS} overflow-hidden rounded-[2rem] ${activeTheme.rootClass}`} style={mapWorkspaceStyle}>
      <style>{`
        .map-workspace .leaflet-container {
          background: var(--map-tile-fallback);
        }
        .map-workspace .leaflet-tile {
          filter: var(--map-tile-filter);
          opacity: var(--map-tile-opacity);
          transition: filter 180ms ease, opacity 180ms ease;
        }
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
          box-shadow: var(--map-marker-shadow);
          transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
        }
        .junction-badge {
          width: 18px;
          height: 18px;
          padding: 0;
          border: 2px solid rgba(255,255,255,0.4);
          position: relative;
          isolation: isolate;
        }
        .junction-selected .junction-badge {
          transform: scale(1.06);
          box-shadow: var(--map-marker-selected-shadow);
        }
        .junction-aura {
          position: absolute;
          inset: -6px;
          border-radius: 999px;
          opacity: 0;
          filter: blur(10px);
          z-index: -1;
          transition: opacity 180ms ease;
        }
        .junction-wave .junction-aura {
          opacity: 0.42;
          animation: junctionPulse 1.8s ease-in-out infinite;
        }
        .junction-locked .junction-badge {
          box-shadow: 0 0 0 1px rgba(255,255,255,0.14), 0 0 0 8px var(--map-corridor-glow);
        }
        .junction-dot {
          width: 6px;
          height: 6px;
          border-radius: 999px;
          background: rgba(255,255,255,0.95);
        }
        .hospital-badge {
          min-width: 38px;
          height: 24px;
          padding: 0 10px;
          background: var(--map-hospital-bg);
          border: 1px solid rgba(255,255,255,0.28);
          color: var(--map-hospital-text);
        }
        .start-badge {
          min-width: 38px;
          height: 24px;
          padding: 0 10px;
          background: var(--map-start-bg);
          border: 1px solid rgba(255,255,255,0.18);
          color: var(--map-start-text);
        }
        .start-selected {
          background: var(--map-start-selected-bg);
        }
        .ambulance-rotor {
          position: relative;
          width: 76px;
          height: 34px;
          transform-origin: center;
        }
        .ambulance-badge {
          position: absolute;
          left: 50%;
          top: 50%;
          min-width: 58px;
          height: 24px;
          padding: 0 10px;
          background: var(--map-ambulance-bg);
          border: 1px solid rgba(15,23,42,0.12);
          color: var(--map-ambulance-text);
          transform: translate(-50%, -50%);
          box-shadow: 0 0 0 1px rgba(255,255,255,0.2), var(--map-marker-selected-shadow);
        }
        .ambulance-emblem {
          display: inline-grid;
          place-items: center;
          width: 14px;
          height: 14px;
          border-radius: 999px;
          background: rgba(239,68,68,0.14);
          color: #dc2626;
          font-size: 11px;
          line-height: 1;
          font-weight: 900;
        }
        .ambulance-label {
          letter-spacing: 0.16em;
          font-size: 10px;
          font-weight: 900;
        }
        .ambulance-siren {
          position: absolute;
          top: 50%;
          width: 16px;
          height: 8px;
          margin-top: -4px;
          border-radius: 999px;
          opacity: 0.85;
          filter: blur(0.2px);
          animation: sirenFlash 0.9s ease-in-out infinite alternate;
        }
        .ambulance-siren-left {
          left: 2px;
          background: radial-gradient(circle at left, var(--map-ambulance-siren), transparent 72%);
        }
        .ambulance-siren-right {
          right: 2px;
          background: radial-gradient(circle at right, var(--map-ambulance-siren-alt), transparent 72%);
          animation-delay: 0.18s;
        }
        .route-junction-badge {
          width: 36px;
          height: 36px;
          display: grid;
          place-items: center;
          border-radius: 999px;
          background: var(--map-route-badge-bg);
          border: 2px solid var(--map-route-badge-border);
          box-shadow: var(--map-marker-selected-shadow);
          position: relative;
          isolation: isolate;
        }
        .route-junction-halo {
          position: absolute;
          inset: -6px;
          border-radius: 999px;
          background: var(--map-corridor-glow);
          opacity: 0;
          z-index: -1;
        }
        .route-junction-badge.state-open .route-junction-halo {
          opacity: 0.9;
          animation: corridorPulse 1.4s ease-out infinite;
        }
        .route-junction-badge.state-arming .route-junction-halo {
          opacity: 0.5;
          animation: corridorPulse 2.2s ease-out infinite;
        }
        .route-junction-badge.state-watch .route-junction-halo {
          opacity: 0.26;
        }
        .route-junction-badge.state-cleared {
          opacity: 0.58;
          transform: scale(0.95);
        }
        .route-junction-ring {
          width: 18px;
          height: 18px;
          border-radius: 999px;
          border: 2px solid #16a34a;
          display: grid;
          place-items: center;
        }
        .route-junction-center {
          width: 6px;
          height: 6px;
          border-radius: 999px;
        }
        .route-junction-text {
          position: absolute;
          left: 50%;
          top: 50%;
          transform: translate(-50%, -50%);
          color: var(--map-route-label-text);
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 0.1em;
          white-space: nowrap;
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
        .map-workspace .leaflet-popup-content-wrapper {
          background: var(--map-popup-bg);
          color: var(--map-popup-text);
          border: 1px solid var(--map-popup-border);
          box-shadow: 0 18px 45px rgba(15,23,42,0.22);
        }
        .map-workspace .leaflet-popup-tip {
          background: var(--map-popup-bg);
          border: 1px solid var(--map-popup-border);
        }
        .map-workspace .leaflet-popup-close-button {
          color: var(--map-popup-text) !important;
        }
        .map-workspace .leaflet-tooltip {
          background: var(--map-tooltip-bg);
          border: 1px solid var(--map-tooltip-border);
          color: var(--map-tooltip-text);
          box-shadow: 0 12px 30px rgba(15,23,42,0.16);
        }
        .map-workspace .leaflet-tooltip-top:before {
          border-top-color: var(--map-tooltip-bg);
        }
        .map-workspace .leaflet-control-zoom a {
          background: var(--map-zoom-bg);
          color: var(--map-zoom-text);
          border-color: var(--map-zoom-border);
        }
        .map-workspace .leaflet-control-zoom a:hover {
          background: var(--map-zoom-hover);
        }
        .map-workspace .leaflet-control-attribution {
          background: var(--map-attribution-bg);
          color: var(--map-attribution-text);
        }
        .map-workspace .leaflet-control-attribution a {
          color: inherit;
        }
        @keyframes corridorPulse {
          0% { transform: scale(0.82); opacity: 0.68; }
          100% { transform: scale(1.5); opacity: 0; }
        }
        @keyframes junctionPulse {
          0%, 100% { transform: scale(0.96); opacity: 0.3; }
          50% { transform: scale(1.06); opacity: 0.52; }
        }
        @keyframes sirenFlash {
          0% { opacity: 0.22; transform: scaleX(0.9); }
          100% { opacity: 0.95; transform: scaleX(1.12); }
        }
      `}</style>

      <div className="absolute inset-0" style={activeTheme.backdropStyle} />

      <div className={`absolute left-4 top-4 z-[1000] max-h-[calc(100%-2rem)] w-[min(470px,calc(100%-2rem))] space-y-3 overflow-y-auto rounded-[30px] border p-4 ${activeTheme.overlayPanelClass}`}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className={`text-[11px] uppercase tracking-[0.3em] ${activeTheme.kickerTextClass}`}>Emergency Traffic Simulation</p>
            <h2 className={`mt-1 text-2xl font-semibold ${activeTheme.headingTextClass}`}>Adaptive Route Control</h2>
            <p className={`mt-2 text-sm ${activeTheme.bodyTextClass}`}>
              Select a dispatch preset, start the run, and the map will drop 4 demo corridor junctions directly on the optimized
              ambulance path so the handoffs stay visually connected to the route.
            </p>
          </div>
          <div className="space-y-2 text-right">
            <div className={`rounded-full px-3 py-2 text-xs uppercase tracking-[0.18em] ${activeTheme.connectionPillClass}`}>
              {connectionState}
            </div>
            <div className={`rounded-full px-3 py-2 text-xs font-semibold ${activeTheme.speedPillClass}`}>
              {speedControl.applied.toFixed(2)}x speed
            </div>
            <div className={`rounded-[1.15rem] border px-3 py-2 ${activeTheme.summaryCardClass}`}>
              <p className={`text-[10px] uppercase tracking-[0.22em] ${activeTheme.mutedTextClass}`}>Theme</p>
              <div className="mt-2 flex justify-end gap-2">
                {Object.entries(MAP_THEMES).map(([themeKey, themeValue]) => (
                  <button
                    key={themeKey}
                    type="button"
                    aria-pressed={mapTheme === themeKey}
                    onClick={() => setMapTheme(themeKey)}
                    className={`rounded-full border px-3 py-1.5 text-[11px] font-semibold transition ${
                      mapTheme === themeKey ? activeTheme.themeToggleActiveClass : activeTheme.themeToggleBaseClass
                    }`}
                  >
                    {themeValue.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <SummaryCard
            title="Congestion"
            value={`${Math.round((globalStatus.congestion_index ?? 0) * 100)}%`}
            detail="Live density blend across the city view"
            tone={mapTheme === 'dark' ? 'text-cyan-300' : 'text-cyan-700'}
            theme={activeTheme}
          />
          <SummaryCard
            title="Camera Health"
            value={`${globalStatus.active_cameras}/${deferredJunctions.length}`}
            detail={`${globalStatus.degraded_cameras} degraded feeds`}
            tone={mapTheme === 'dark' ? 'text-emerald-300' : 'text-emerald-700'}
            theme={activeTheme}
          />
          <SummaryCard
            title="Ambulance Speed"
            value={`${speedControl.applied.toFixed(2)}x`}
            detail={speedControl.syncing ? 'Applying speed change...' : 'Live simulation multiplier'}
            tone={mapTheme === 'dark' ? 'text-fuchsia-300' : 'text-fuchsia-700'}
            theme={activeTheme}
          />
        </div>

        <div className="grid gap-3 md:grid-cols-[1.15fr_0.85fr]">
          <div className={`rounded-3xl border p-4 ${activeTheme.sectionCardClass}`}>
            <p className={`text-[11px] uppercase tracking-[0.26em] ${activeTheme.mutedTextClass}`}>Dispatch Control</p>
            <select
              value={selectedStartId}
              onChange={(event) => setSelectedStartId(event.target.value)}
              className={`mt-3 w-full rounded-2xl border px-4 py-3 text-sm outline-none ${activeTheme.selectClass}`}
            >
              {config.starting_points.map((startPoint) => (
                <option key={startPoint.id} value={startPoint.id}>
                  {startPoint.id} - {startPoint.name}
                </option>
              ))}
            </select>
            {selectedStart && (
              <div className={`mt-3 rounded-2xl px-3 py-3 text-sm ${activeTheme.noteClass}`}>
                <div>{selectedStart.dispatch_note ?? 'The demo will place corridor junctions directly on the optimized ambulance route once the run starts.'}</div>
                <div className="mt-2 text-xs uppercase tracking-[0.16em] opacity-80">
                  Junction markers appear only after simulation start
                </div>
              </div>
            )}
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={startEmergency}
                disabled={starting || !selectedStartId}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${activeTheme.primaryButtonClass}`}
              >
                {starting ? 'Starting...' : 'Start Emergency Simulation'}
              </button>
              <button
                type="button"
                onClick={clearEmergency}
                disabled={!simulationLive}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${activeTheme.secondaryButtonClass}`}
              >
                Reset
              </button>
            </div>
          </div>

          <div className={`rounded-3xl border p-4 ${activeTheme.speedPanelClass}`}>
            <div className="flex items-center justify-between gap-3">
              <p className={`text-[11px] uppercase tracking-[0.26em] ${activeTheme.speedPanelTitleClass}`}>Speed Control</p>
              <span className={`rounded-full px-2 py-1 text-xs font-semibold ${activeTheme.speedPanelBadgeClass}`}>
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
                      ? activeTheme.speedPresetActiveClass
                      : activeTheme.speedPresetInactiveClass
                  }`}
                >
                  {value.toFixed(2)}x
                </button>
              ))}
            </div>
            <p className={`mt-3 text-sm ${activeTheme.speedPanelCopyClass}`}>
              {speedControl.syncing
                ? 'Applying speed change to the live simulation...'
                : 'Adjust how fast the ambulance advances and how early route junctions prepare green.'}
            </p>
          </div>
        </div>

        <div className={`rounded-3xl border p-4 ${activeTheme.etaPanelClass}`}>
          <p className={`text-[11px] uppercase tracking-[0.26em] ${activeTheme.etaTitleClass}`}>ETA Optimization</p>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <SummaryCard title="Normal ETA" value={`${simulationPlan.normalEta || 0} min`} detail="Without signal corridor" tone={mapTheme === 'dark' ? 'text-amber-300' : 'text-amber-700'} theme={activeTheme} />
            <SummaryCard title="Optimized ETA" value={`${simulationPlan.optimizedEta || 0} min`} detail="With adaptive green wave" tone={mapTheme === 'dark' ? 'text-emerald-300' : 'text-emerald-700'} theme={activeTheme} />
            <SummaryCard title="Time Saved" value={`${simulationPlan.timeSaved || 0} min`} detail={`${Math.round(simulationPlan.timeSavedPercent || 0)}% faster`} tone={mapTheme === 'dark' ? 'text-cyan-300' : 'text-cyan-700'} theme={activeTheme} />
            <SummaryCard
              title="Live Countdown"
              value={formatCountdown(liveCountdown)}
              detail={emergencyState?.completed ? 'Ambulance arrived at hospital' : 'Realtime simulation countdown'}
              tone={activeTheme.headingTextClass}
              theme={activeTheme}
            />
          </div>
          {simulationPlan.hospital && (
            <p className={`mt-3 text-sm ${activeTheme.strongTextClass}`}>
              Destination: {simulationPlan.hospital.name} | Route: {simulationPlan.routeDistanceKm.toFixed(2)} km
            </p>
          )}
          {!simulationPlan.googleRouteAvailable && simulationPlan.googleRouteError && (
            <p className={`mt-3 text-sm ${mapTheme === 'dark' ? 'text-amber-100' : 'text-amber-700'}`}>
              Google Directions unavailable: {simulationPlan.googleRouteError}
            </p>
          )}
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className={`rounded-3xl border p-4 ${activeTheme.sectionCardClass}`}>
            <p className={`text-[11px] uppercase tracking-[0.26em] ${activeTheme.mutedTextClass}`}>Live Operations</p>
            <div className={`mt-3 space-y-3 text-sm ${activeTheme.strongTextClass}`}>
              <div>
                <div className={activeTheme.mutedTextClass}>Stage</div>
                <div className={`mt-1 font-semibold ${activeTheme.headingTextClass}`}>{titleCase(emergencyState?.stage ?? 'idle')}</div>
              </div>
              <div>
                <div className={activeTheme.mutedTextClass}>Current Junction</div>
                <div className={`mt-1 font-semibold ${activeTheme.headingTextClass}`}>{liveCurrentJunction}</div>
              </div>
              <div>
                <div className={activeTheme.mutedTextClass}>Next Target</div>
                <div className={`mt-1 font-semibold ${activeTheme.headingTextClass}`}>{liveNextTarget}</div>
              </div>
              <div>
                <div className={activeTheme.mutedTextClass}>Distance To Next</div>
                <div className={`mt-1 font-semibold ${activeTheme.headingTextClass}`}>
                  {Math.round(nextRouteJunction?.distanceM ?? emergencyState?.distance_to_next_m ?? 0)} m
                </div>
              </div>
              <div>
                <div className={activeTheme.mutedTextClass}>Signal Direction</div>
                <div className={`mt-1 font-semibold ${activeTheme.headingTextClass}`}>{liveSignalDirection}</div>
              </div>
              <div>
                <div className={activeTheme.mutedTextClass}>Speed Profile</div>
                <div className={`mt-1 font-semibold ${activeTheme.headingTextClass}`}>{speedControl.applied.toFixed(2)}x simulation speed</div>
              </div>
            </div>
          </div>

          <div className={`rounded-3xl border p-4 ${activeTheme.sectionCardClass}`}>
            <p className={`text-[11px] uppercase tracking-[0.26em] ${activeTheme.mutedTextClass}`}>Junction Alerts</p>
            <div className={`mt-3 space-y-2 text-sm ${activeTheme.strongTextClass}`}>
              {recentAlerts.length === 0 && <div className={`rounded-2xl border px-3 py-2 ${activeTheme.surfaceCardClass}`}>No emergency alerts yet. Signals are cycling normally.</div>}
              {recentAlerts.map((alert, index) => (
                <div key={`${alert.timestamp}-${index}`} className={`rounded-2xl border px-3 py-2 ${activeTheme.surfaceCardClass}`}>
                  <div className={`text-[11px] uppercase tracking-[0.18em] ${activeTheme.mutedTextClass}`}>{titleCase(alert.stage)}</div>
                  <div className={`mt-1 ${activeTheme.strongTextClass}`}>{alert.message}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className={`rounded-3xl border p-4 ${activeTheme.sectionCardClass}`}>
          <div className="flex items-center justify-between gap-3">
            <p className={`text-[11px] uppercase tracking-[0.26em] ${activeTheme.mutedTextClass}`}>Emergency Junction Handoffs</p>
            <div className={`text-xs uppercase tracking-[0.18em] ${activeTheme.faintTextClass}`}>
              {routePanelJunctions.length} configured on route
            </div>
          </div>
          <div className={`mt-3 space-y-2 text-sm ${activeTheme.strongTextClass}`}>
            {routePanelJunctions.length === 0 && (
              <div className={`rounded-2xl border px-3 py-2 ${activeTheme.surfaceCardClass}`}>
                Start the simulation to place 4 corridor junctions on the optimized path.
              </div>
            )}
            {routePanelJunctions.map((junction) => (
              <div key={junction.id} className={`rounded-2xl border px-3 py-2 ${activeTheme.surfaceCardClass}`}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className={`font-semibold ${activeTheme.headingTextClass}`}>{junction.displayId}</div>
                    <div className={`text-xs uppercase tracking-[0.18em] ${activeTheme.mutedTextClass}`}>
                      {simulationLive ? (junction === nextRouteJunction ? 'Immediate Handoff' : 'Queued Handoff') : (junction === nextRouteJunction ? 'Activation Junction' : 'Downstream Junction')}
                    </div>
                  </div>
                  <div className={`rounded-full px-2 py-1 text-xs font-semibold ${
                    junction.phase === 'GREEN'
                      ? mapTheme === 'dark' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-emerald-100 text-emerald-700'
                      : junction.phase === 'YELLOW'
                        ? mapTheme === 'dark' ? 'bg-amber-400/15 text-amber-300' : 'bg-amber-100 text-amber-700'
                        : mapTheme === 'dark' ? 'bg-rose-500/15 text-rose-300' : 'bg-rose-100 text-rose-700'
                  }`}>
                    {junction.phase}
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {SIGNAL_DIRECTIONS.map((direction) => {
                    const signalValue = junction.signals?.[direction] ?? 'RED';
                    const chipClass =
                      signalValue === 'GREEN'
                        ? mapTheme === 'dark' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-emerald-100 text-emerald-700'
                        : signalValue === 'YELLOW'
                          ? mapTheme === 'dark' ? 'bg-amber-400/15 text-amber-300' : 'bg-amber-100 text-amber-700'
                          : mapTheme === 'dark' ? 'bg-rose-500/15 text-rose-300' : 'bg-rose-100 text-rose-700';
                    return (
                      <span key={direction} className={`signal-chip ${chipClass}`}>
                        {direction}:{signalShort(signalValue)}
                      </span>
                    );
                  })}
                </div>
                <div className={`mt-2 text-xs uppercase tracking-[0.18em] ${activeTheme.mutedTextClass}`}>
                  {junction.distanceM != null ? `${Math.round(junction.distanceM)} m | ` : ''}
                  {junction.etaSec != null ? `ETA ${Math.max(Math.round(junction.etaSec), 0)} sec | ` : ''}
                  {corridorStateLabel(junction.corridorState)}
                </div>
                <div className={`mt-1 text-sm ${activeTheme.bodyTextClass}`}>{junction.statusLabel}</div>
              </div>
            ))}
          </div>
        </div>

        <div className={`rounded-3xl border p-4 ${activeTheme.sectionCardClass}`}>
          <div className="flex items-center justify-between gap-3">
            <p className={`text-[11px] uppercase tracking-[0.26em] ${activeTheme.mutedTextClass}`}>Google Directions</p>
            {simulationPlan.googleMapsUrl && (
              <a
                href={simulationPlan.googleMapsUrl}
                target="_blank"
                rel="noreferrer"
                className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${activeTheme.linkButtonClass}`}
              >
                Open In Google Maps
              </a>
            )}
          </div>
          <div className={`mt-3 space-y-2 text-sm ${activeTheme.strongTextClass}`}>
            {displayedDirections.length === 0 && (
              <div className={`rounded-2xl border px-3 py-2 ${activeTheme.surfaceCardClass}`}>
                Start a simulation to load Google road routing and turn-by-turn guidance.
              </div>
            )}
            {displayedDirections.map((step) => (
              <div key={step.index} className={`rounded-2xl border px-3 py-2 ${activeTheme.surfaceCardClass}`}>
                <div className={`font-medium ${activeTheme.headingTextClass}`}>{step.instruction || 'Continue on the current road'}</div>
                <div className={`mt-1 text-xs uppercase tracking-[0.18em] ${activeTheme.mutedTextClass}`}>
                  {titleCase(step.phase ?? 'route')} | {Math.round((step.distance_m ?? 0) / 10) / 100} km | {Math.ceil((step.duration_s ?? 0) / 60)} min
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className={`absolute bottom-4 right-4 z-[1000] hidden w-[280px] rounded-[24px] border p-4 lg:block ${activeTheme.overlayPanelClass}`}>
        <p className={`text-[11px] uppercase tracking-[0.26em] ${activeTheme.mutedTextClass}`}>Map Legend</p>
          <div className="mt-3 space-y-2 text-sm">
            <div className="flex items-center gap-3">
              <span className="h-1.5 w-10 rounded-full" style={{ background: activeTheme.routeApproachColor }} />
              <span>Dispatch route to first junction</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="h-1.5 w-10 rounded-full" style={{ background: activeTheme.routeEmergencyColor }} />
              <span>Emergency corridor route</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="h-4 w-4 rounded-full border-2 border-emerald-400" style={{ background: 'var(--map-route-badge-bg)' }} />
              <span>Demo corridor junction</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-black text-slate-950">AMB</span>
              <span>Ambulance position</span>
            </div>
        </div>
      </div>

      <MapContainer center={[13.0674, 80.2425]} zoom={13} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          key={mapTheme}
          url={MAP_TILE_URL}
          attribution={MAP_TILE_ATTRIBUTION}
        />

        <FitToRoute points={routeFocusPoints} />

        {displayApproachRoutePoints.length > 1 && (
          <Polyline
            positions={displayApproachRoutePoints}
            pathOptions={{ color: activeTheme.routeApproachColor, weight: 5, opacity: 0.88, dashArray: '10 8', lineCap: 'round' }}
          />
        )}
        {displayEmergencyRoutePoints.length > 1 && (
          <Polyline
            positions={displayEmergencyRoutePoints}
            pathOptions={{ color: activeTheme.routeEmergencyColor, weight: 11, opacity: 0.16, lineCap: 'round', lineJoin: 'round' }}
          />
        )}
        {displayEmergencyRoutePoints.length > 1 && (
          <Polyline
            positions={displayEmergencyRoutePoints}
            pathOptions={{ color: activeTheme.routeEmergencyColor, weight: 5.5, opacity: 0.96, lineCap: 'round', lineJoin: 'round' }}
          />
        )}

        {visibleStartPoints.map((startPoint) => (
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

        {visibleHospitals.map((hospital) => (
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

        {visibleRouteSignalJunctions.map((junction) => (
          <Marker key={junction.id} position={[junction.lat, junction.lng]} icon={createRouteJunctionIcon(junction)}>
            <Popup>
              <div className={`min-w-[240px] p-1 ${activeTheme.popupContentClass}`}>
                <h3 className="text-lg font-bold">{junction.displayId}</h3>
                <div className="mt-2 space-y-1 text-sm">
                  <p><strong>Type:</strong> Emergency corridor junction</p>
                  <p><strong>Phase:</strong> {junction.phase}</p>
                  <p><strong>Active Direction:</strong> {junction.activeDirection}</p>
                  {junction.distanceM != null && <p><strong>Distance:</strong> {Math.round(junction.distanceM)} m</p>}
                  {junction.etaSec != null && <p><strong>ETA:</strong> {Math.max(Math.round(junction.etaSec), 0)} sec</p>}
                  <p><strong>Status:</strong> {junction.statusLabel}</p>
                  <p><strong>Corridor State:</strong> {corridorStateLabel(junction.corridorState)}</p>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {SIGNAL_DIRECTIONS.map((direction) => (
                      <span key={direction} className={`rounded-full px-2 py-1 text-xs font-semibold ${activeTheme.popupNeutralChipClass}`}>
                        {direction}:{signalShort(junction.signals?.[direction] ?? 'RED')}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </Popup>
          </Marker>
        ))}

        {visibleCityJunctions.map((junction) => (
          <Marker
            key={junction.junction_id}
            position={[junction.lat, junction.lng]}
            icon={createJunctionIcon(junction, selectedJunctionId)}
            eventHandlers={{ click: () => setSelectedJunctionId(junction.junction_id) }}
          >
            <Popup>
              <div className={`min-w-[250px] p-1 ${activeTheme.popupContentClass}`}>
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
                      const chipClass = activeTheme.popupSignalToneClasses[signalValue] ?? activeTheme.popupSignalToneClasses.RED;
                      return (
                        <span key={direction} className={`signal-chip ${chipClass}`}>
                          {direction}:{signalShort(signalValue)}
                        </span>
                      );
                    })}
                  </div>
                  {junction.signal_alert && <p className={activeTheme.popupMutedClass}><strong>Alert:</strong> {junction.signal_alert}</p>}
                </div>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
