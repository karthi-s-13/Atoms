const DEFAULT_ROUTE_DISTRIBUTION = {
  "NORTH->SOUTH": 5,
  "NORTH->EAST": 2,
  "EAST->WEST": 5,
  "EAST->SOUTH": 2,
  "SOUTH->NORTH": 5,
  "SOUTH->WEST": 2,
  "WEST->EAST": 5,
  "WEST->NORTH": 2,
};

export const DEFAULT_TRAFFIC_MODE_ID = "moderate";

export const TRAFFIC_MODE_PRESETS = [
  {
    id: "deserted",
    label: "Deserted",
    config: {
      traffic_intensity: 0.08,
      spawn_rate_multiplier: 0.4,
      speed_multiplier: 1.08,
      safe_gap_multiplier: 0.82,
      ambulance_frequency: 0.01,
      max_emergency_vehicles: 1,
      max_vehicles: 10,
      route_distribution: DEFAULT_ROUTE_DISTRIBUTION,
    },
  },
  {
    id: "moderate",
    label: "Moderate",
    config: {
      traffic_intensity: 0.48,
      spawn_rate_multiplier: 0.92,
      speed_multiplier: 1,
      safe_gap_multiplier: 1,
      ambulance_frequency: 0.04,
      max_emergency_vehicles: 3,
      max_vehicles: 28,
      route_distribution: DEFAULT_ROUTE_DISTRIBUTION,
    },
  },
  {
    id: "heavy",
    label: "Heavy",
    config: {
      traffic_intensity: 0.9,
      spawn_rate_multiplier: 1.38,
      speed_multiplier: 0.92,
      safe_gap_multiplier: 0.84,
      ambulance_frequency: 0.06,
      max_emergency_vehicles: 4,
      max_vehicles: 52,
      route_distribution: DEFAULT_ROUTE_DISTRIBUTION,
    },
  },
  {
    id: "emergency",
    label: "Emergency",
    config: {
      traffic_intensity: 0.7,
      spawn_rate_multiplier: 1.12,
      speed_multiplier: 0.96,
      safe_gap_multiplier: 0.96,
      ambulance_frequency: 0.32,
      max_emergency_vehicles: 9,
      max_vehicles: 40,
      route_distribution: DEFAULT_ROUTE_DISTRIBUTION,
    },
  },
];

export const TRAFFIC_MODE_OPTIONS = [
  ...TRAFFIC_MODE_PRESETS.map((mode) => ({ id: mode.id, label: mode.label })),
  { id: "custom", label: "Custom" },
];

function numberMatches(left, right) {
  return Math.abs(Number(left ?? 0) - Number(right ?? 0)) < 0.011;
}

function routeDistributionMatches(leftDistribution = {}, rightDistribution = {}) {
  return Object.keys(DEFAULT_ROUTE_DISTRIBUTION).every((routeKey) =>
    numberMatches(leftDistribution?.[routeKey], rightDistribution?.[routeKey]),
  );
}

export function formatTrafficModeLabel(modeId) {
  return TRAFFIC_MODE_OPTIONS.find((mode) => mode.id === modeId)?.label ?? "Custom";
}

export function getTrafficModePreset(modeId) {
  return TRAFFIC_MODE_PRESETS.find((mode) => mode.id === modeId) ?? null;
}

export function matchTrafficModeId(config = {}) {
  const currentConfig = config ?? {};
  return (
    TRAFFIC_MODE_PRESETS.find((preset) => (
      numberMatches(currentConfig.traffic_intensity, preset.config.traffic_intensity) &&
      numberMatches(currentConfig.spawn_rate_multiplier, preset.config.spawn_rate_multiplier) &&
      numberMatches(currentConfig.safe_gap_multiplier, preset.config.safe_gap_multiplier) &&
      numberMatches(currentConfig.ambulance_frequency, preset.config.ambulance_frequency) &&
      numberMatches(currentConfig.max_emergency_vehicles, preset.config.max_emergency_vehicles) &&
      numberMatches(currentConfig.max_vehicles, preset.config.max_vehicles) &&
      routeDistributionMatches(currentConfig.route_distribution, preset.config.route_distribution)
    ))?.id ?? "custom"
  );
}
