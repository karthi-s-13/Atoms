import { useDeferredValue, useEffect, useState } from "react";
import SimulationCanvas from "../components/SimulationCanvas";
import { DEFAULT_CONFIG, DEFAULT_ROUTE_DISTRIBUTION } from "../hooks/useRealtimeSimulation";
import {
  DEFAULT_TRAFFIC_MODE_ID,
  TRAFFIC_MODE_OPTIONS,
  getTrafficModePreset,
  matchTrafficModeId,
} from "../lib/trafficModes";

const speedOptions = [0.5, 1, 2, 4];
const signalModeOptions = [
  { id: "fixed", label: "Fixed" },
  { id: "adaptive", label: "Adaptive (AI)" },
];
const customRouteControls = [
  ["NORTH->SOUTH", "N->S"],
  ["NORTH->EAST", "N->E"],
  ["NORTH->WEST", "N->W"],
  ["EAST->WEST", "E->W"],
  ["EAST->SOUTH", "E->S"],
  ["EAST->NORTH", "E->N"],
  ["SOUTH->NORTH", "S->N"],
  ["SOUTH->WEST", "S->W"],
  ["SOUTH->EAST", "S->E"],
  ["WEST->EAST", "W->E"],
  ["WEST->NORTH", "W->N"],
  ["WEST->SOUTH", "W->S"],
];

function mergeSimulationConfig(baseConfig, partialConfig = {}) {
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

function toEngineConfig(nextConfig) {
  const mergedConfig = mergeSimulationConfig(DEFAULT_CONFIG, nextConfig);
  const { paused, ...engineConfig } = mergedConfig;
  return engineConfig;
}

function formatSignalControlMode(value) {
  return value === "adaptive" ? "Adaptive (AI-Based)" : "Fixed Timing";
}

function formatThroughputPerMinute(value) {
  return `${Number(value || 0).toFixed(1)}/min`;
}

function Panel({ title, children, className = "" }) {
  return (
    <section className={`glass-panel rounded-[2rem] p-6 ${className}`}>
      <p className="panel-title">{title}</p>
      <div className="mt-5 space-y-5">{children}</div>
    </section>
  );
}

function ActionButton({ children, tone = "primary", disabled = false, onClick }) {
  const toneClasses = {
    primary: disabled
      ? "cursor-not-allowed bg-cyan-500/25 text-slate-300"
      : "bg-cyan-400 text-slate-950 hover:bg-cyan-300",
    secondary: disabled
      ? "cursor-not-allowed border border-white/10 bg-white/5 text-slate-500"
      : "border border-white/10 bg-white/5 text-white hover:bg-white/10",
  };

  return (
    <button
      className={`inline-flex w-full items-center justify-center rounded-full px-4 py-2.5 text-sm font-medium transition ${toneClasses[tone]}`}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function SegmentedButton({ active, children, onClick }) {
  return (
    <button
      className={`rounded-full px-4 py-2 text-sm font-medium transition ${
        active
          ? "bg-emerald-400 text-slate-950 shadow-[0_10px_30px_rgba(16,185,129,0.28)]"
          : "border border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function NumberField({ label, value, min = 0, max = 20, step = 1, integer = true, onChange }) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs uppercase tracking-[0.18em] text-slate-400">{label}</span>
      <input
        className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-300/60"
        type="number"
        inputMode={integer ? "numeric" : "decimal"}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => {
          const nextValue = Number(event.target.value);
          const normalizedValue = integer ? Math.round(nextValue) : nextValue;
          onChange(Number.isFinite(normalizedValue) ? normalizedValue : min);
        }}
      />
    </label>
  );
}

function MetricTile({ label, value }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-950/45 px-5 py-4">
      <p className="metric-label">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-white">{value}</p>
    </div>
  );
}

export default function SimulationPage({
  sceneSnapshot,
  dashboardSnapshot,
  sceneBufferRef,
  cameraStateRef,
  controls,
  updateConfig,
  play,
  pause,
  reset,
  restartWithConfig,
}) {
  const hudSnapshot = useDeferredValue(dashboardSnapshot);
  const metrics = hudSnapshot.metrics;
  const [selectedModeId, setSelectedModeId] = useState(matchTrafficModeId(controls) || DEFAULT_TRAFFIC_MODE_ID);
  const [customConfig, setCustomConfig] = useState(() => mergeSimulationConfig(DEFAULT_CONFIG, controls));

  useEffect(() => {
    if (selectedModeId === "custom") {
      setCustomConfig(mergeSimulationConfig(DEFAULT_CONFIG, controls));
    }
  }, [controls, selectedModeId]);

  const applyLiveConfig = (nextConfig) => {
    updateConfig(toEngineConfig(nextConfig));
  };

  const handleModeChange = (nextModeId) => {
    setSelectedModeId(nextModeId);
    if (nextModeId === "custom") {
      setCustomConfig(mergeSimulationConfig(DEFAULT_CONFIG, controls));
      return;
    }

    const preset = getTrafficModePreset(nextModeId);
    if (!preset) {
      return;
    }

    applyLiveConfig(mergeSimulationConfig(controls, preset.config));
  };

  const handleSpeedChange = (speed) => {
    const nextConfig = mergeSimulationConfig(selectedModeId === "custom" ? customConfig : controls, {
      speed_multiplier: speed,
    });
    if (selectedModeId === "custom") {
      setCustomConfig(nextConfig);
    }
    applyLiveConfig(nextConfig);
  };

  const handleSignalModeChange = (aiMode) => {
    const nextConfig = mergeSimulationConfig(selectedModeId === "custom" ? customConfig : controls, {
      ai_mode: aiMode,
    });
    if (selectedModeId === "custom") {
      setCustomConfig(nextConfig);
    }
    applyLiveConfig(nextConfig);
  };

  const handleCustomConfigChange = (partialConfig) => {
    const nextConfig = mergeSimulationConfig(customConfig, partialConfig);
    setCustomConfig(nextConfig);
    applyLiveConfig(nextConfig);
  };

  const applyCustomAndStart = () => {
    restartWithConfig({ ...customConfig, paused: false });
  };

  const customRouteTotal = Object.values(customConfig.route_distribution ?? {}).reduce(
    (sum, value) => sum + Number(value || 0),
    0,
  );
  return (
    <div className="space-y-6">
      <div
        className={`grid gap-6 ${
          selectedModeId === "custom"
            ? "xl:grid-cols-[300px_minmax(0,1fr)_330px]"
            : "xl:grid-cols-[300px_minmax(0,1fr)]"
        }`}
      >
        <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <Panel title="Control Panel">
            <div className="grid gap-3">
              <ActionButton tone="primary" disabled={!controls.paused || selectedModeId === "custom"} onClick={play}>
                Start Simulation
              </ActionButton>
              <ActionButton tone="secondary" disabled={controls.paused} onClick={pause}>
                Pause Simulation
              </ActionButton>
              <ActionButton tone="secondary" onClick={reset}>
                Reset Simulation
              </ActionButton>
            </div>

            <div className="border-t border-white/10 pt-5">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Settings</p>

              <label className="mt-4 block">
                <span className="mb-2 block text-sm text-slate-300">Traffic Mode</span>
                <select
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-300/60"
                  value={selectedModeId}
                  onChange={(event) => handleModeChange(event.target.value)}
                >
                  {TRAFFIC_MODE_OPTIONS.map((mode) => (
                    <option key={mode.id} value={mode.id}>
                      {mode.label}
                    </option>
                  ))}
                </select>
              </label>

              <div className="mt-5">
                <span className="mb-2 block text-sm text-slate-300">Simulation Speed</span>
                <div className="flex flex-wrap gap-2">
                  {speedOptions.map((speed) => (
                    <SegmentedButton
                      key={speed}
                      active={controls.speed_multiplier === speed}
                      onClick={() => handleSpeedChange(speed)}
                    >
                      {speed}x
                    </SegmentedButton>
                  ))}
                </div>
              </div>

              <div className="mt-5">
                <span className="mb-2 block text-sm text-slate-300">Signal Mode</span>
                <div className="flex flex-wrap gap-2">
                  {signalModeOptions.map((mode) => (
                    <SegmentedButton
                      key={mode.id}
                      active={controls.ai_mode === mode.id}
                      onClick={() => handleSignalModeChange(mode.id)}
                    >
                      {mode.label}
                    </SegmentedButton>
                  ))}
                </div>
              </div>
            </div>
          </Panel>
        </aside>

        <section className="space-y-3">
          <div className="px-1">
            <p className="panel-title">Simulation View</p>
            <p className="mt-2 text-sm text-slate-300">Live 3D intersection rendering with uncluttered operator focus.</p>
          </div>

          <SimulationCanvas
            sceneSnapshot={sceneSnapshot}
            sceneBufferRef={sceneBufferRef}
            cameraStateRef={cameraStateRef}
            className="h-[560px] md:h-[640px] xl:h-[720px] 2xl:h-[780px]"
          />
        </section>

        {selectedModeId === "custom" ? (
          <aside className="space-y-6 xl:sticky xl:top-6 xl:self-start">
            <Panel title="Custom Configuration">
              <NumberField
                label="Emergency Vehicle Count"
                value={customConfig.max_emergency_vehicles}
                min={0}
                max={12}
                step={1}
                onChange={(value) => handleCustomConfigChange({ max_emergency_vehicles: Math.max(0, value) })}
              />

              <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-white">Vehicles per Direction Pair</p>
                  <span className="rounded-full border border-white/10 px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300">
                    Total {customRouteTotal}
                  </span>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  {customRouteControls.map(([routeKey, label]) => (
                    <NumberField
                      key={routeKey}
                      label={label}
                      value={customConfig.route_distribution?.[routeKey] ?? 0}
                      onChange={(value) =>
                        handleCustomConfigChange({
                          route_distribution: { [routeKey]: Math.max(0, value) },
                        })
                      }
                    />
                  ))}
                </div>
              </div>

              <ActionButton tone="primary" onClick={applyCustomAndStart}>
                Apply &amp; Start Simulation
              </ActionButton>
            </Panel>
          </aside>
        ) : null}
      </div>

      <section className="glass-panel rounded-[2rem] p-5">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile label="Active Vehicles" value={metrics.active_vehicles} />
          <MetricTile label="Avg Wait Time" value={`${Number(metrics.avg_wait_time ?? 0).toFixed(2)}s`} />
          <MetricTile label="Throughput" value={formatThroughputPerMinute(Number(metrics.throughput ?? 0) * 60)} />
          <MetricTile label="Cleared / Cycle" value={Number(metrics.vehicles_cleared_per_cycle ?? 0)} />
        </div>
      </section>
    </div>
  );
}
