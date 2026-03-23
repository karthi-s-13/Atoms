import { useDeferredValue } from "react";
import MetricCard from "../components/MetricCard";
import SimulationCanvas from "../components/SimulationCanvas";

const speedOptions = [0.5, 1, 2, 4];
const phaseLabels = [
  ["NORTH", "North"],
  ["EAST", "East"],
  ["SOUTH", "South"],
  ["WEST", "West"],
];
const signalGroups = [
  ["NORTH", "North Signal"],
  ["SOUTH", "South Signal"],
  ["EAST", "East Signal"],
  ["WEST", "West Signal"],
];

function formatPhase(value) {
  return String(value || "").split("_").join(" ");
}

function formatStage(value) {
  return String(value || "").replace(/^PHASE_/, "").split("_").join(" ");
}

function formatSignal(value) {
  return String(value || "RED").split("_").join(" ");
}

function alertAccent(level) {
  if (level === "high") {
    return "border-rose-400/40 bg-rose-500/10 text-rose-100";
  }
  if (level === "medium") {
    return "border-amber-300/40 bg-amber-400/10 text-amber-50";
  }
  return "border-emerald-400/30 bg-emerald-500/10 text-emerald-50";
}

function Slider({ label, value, min, max, step, onChange }) {
  return (
    <label className="block">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="text-slate-300">{label}</span>
        <span className="font-medium text-white">{value}</span>
      </div>
      <input className="w-full accent-cyan-400" type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
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
}) {
  const hudSnapshot = useDeferredValue(dashboardSnapshot);
  const metrics = hudSnapshot.metrics;
  const intelligence = hudSnapshot.traffic_brain;
  const network = hudSnapshot.network;
  const networkIntersections = Object.values(network?.intersections ?? {});
  const activePhaseScore = intelligence.phase_scores?.[hudSnapshot.current_state] ?? intelligence.phase_scores?.NORTH;
  const pedestriansEnabled = (hudSnapshot.config?.max_pedestrians ?? 0) > 0;
  const pedestrianMode = pedestriansEnabled
    ? (hudSnapshot.pedestrian_phase_active ? "ACTIVE" : "CONTROLLED")
    : "DISABLED";
  const vehicleStates = hudSnapshot.vehicles.reduce(
    (counts, vehicle) => {
      counts[vehicle.state] = (counts[vehicle.state] || 0) + 1;
      counts[vehicle.approach] = (counts[vehicle.approach] || 0) + 1;
      counts[vehicle.route] = (counts[vehicle.route] || 0) + 1;
      return counts;
    },
    { MOVING: 0, STOPPED: 0, NORTH: 0, SOUTH: 0, EAST: 0, WEST: 0, straight: 0, right: 0 },
  );
  const pedestrianStates = hudSnapshot.pedestrians.reduce(
    (counts, pedestrian) => {
      counts[pedestrian.state] = (counts[pedestrian.state] || 0) + 1;
      return counts;
    },
    { WAITING: 0, CROSSING: 0, EXITING: 0 },
  );

  return (
    <div className="grid gap-6 xl:grid-cols-[1.6fr_0.92fr]">
      <div className="space-y-6">
        <SimulationCanvas sceneSnapshot={sceneSnapshot} sceneBufferRef={sceneBufferRef} cameraStateRef={cameraStateRef} />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Vehicles Processed" value={metrics.vehicles_processed} detail="completed trips" tone="cyan" />
          <MetricCard label="Avg Wait" value={`${metrics.avg_wait_time.toFixed(2)}s`} detail="lane delay" tone="amber" />
          <MetricCard label="Queue Pressure" value={`${Math.round(metrics.queue_pressure * 100)}%`} detail="stopped cars" tone="rose" />
          <MetricCard label="Throughput" value={`${metrics.throughput.toFixed(1)}/s`} detail="clearing rate" tone="green" />
        </div>
      </div>

      <div className="space-y-6">
        <section className="glass-panel rounded-[2rem] p-6">
          <p className="panel-title">Controls</p>
          <div className="mt-5 flex flex-wrap gap-3">
            <button className="rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950" onClick={play}>Play</button>
            <button className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white" onClick={pause}>Pause</button>
            <button className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white" onClick={reset}>Reset</button>
          </div>

          <div className="mt-6 space-y-5">
            <Slider label="Traffic Intensity" value={controls.traffic_intensity} min={0} max={1} step={0.01} onChange={(value) => updateConfig({ traffic_intensity: value })} />
          </div>

          <div className="mt-6">
            <span className="mb-2 block text-sm text-slate-300">Speed</span>
            <div className="flex flex-wrap gap-2">
              {speedOptions.map((speed) => (
                <button
                  key={speed}
                  className={`rounded-full px-4 py-2 text-sm ${
                    controls.speed_multiplier === speed
                      ? "bg-emerald-400 font-medium text-slate-950"
                      : "border border-white/10 bg-white/5 text-slate-200"
                  }`}
                  onClick={() => updateConfig({ speed_multiplier: speed })}
                >
                  {speed}x
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="glass-panel rounded-[2rem] p-6">
          <p className="panel-title">Signal Panel</p>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Current Green</p>
              <p className="mt-2 text-2xl font-semibold text-white">{formatPhase(hudSnapshot.current_state)}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Cycle Mode</p>
              <p className="mt-2 text-2xl font-semibold text-white">{formatStage(hudSnapshot.controller_phase)}</p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Timer</p>
              <p className="mt-2 text-2xl font-semibold text-white">{hudSnapshot.phase_timer.toFixed(1)}s</p>
              <p className="mt-1 text-xs text-slate-400">of {hudSnapshot.phase_duration.toFixed(1)}s</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Time Remaining</p>
              <p className="mt-2 text-2xl font-semibold text-white">{hudSnapshot.min_green_remaining.toFixed(1)}s</p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {phaseLabels.map(([phase, label]) => (
              <div key={phase} className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{label}</p>
                <p className="mt-2 text-2xl font-semibold text-white">{(intelligence.phase_scores?.[phase]?.score ?? 0).toFixed(2)}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">
                  {hudSnapshot.current_state === phase && hudSnapshot.controller_phase === "PHASE_GREEN"
                    ? "Active"
                    : intelligence.top_phase === phase
                      ? "Top score"
                      : "Standby"}
                </p>
                <p className="mt-2 text-xs leading-5 text-slate-400">{intelligence.phase_scores?.[phase]?.decision_reason}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {signalGroups.map(([group, label]) => (
              <div key={group} className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{label}</p>
                <p className="mt-2 text-lg font-semibold text-white">{formatSignal(hudSnapshot.signals?.[group])}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Pedestrian System</p>
            <p className="mt-2 text-2xl font-semibold text-white">{pedestrianMode}</p>
            <p className="mt-2 text-sm text-slate-300">
              {pedestriansEnabled
                ? `Waiting ${pedestrianStates.WAITING} | Crossing ${pedestrianStates.CROSSING} | Exiting ${pedestrianStates.EXITING}`
                : "Pedestrian spawning is parked for this strict vehicle-discipline run."}
            </p>
          </div>
          <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Active Flow</p>
            <p className="mt-2 text-2xl font-semibold text-white">{hudSnapshot.active_direction ?? "NONE"}</p>
          </div>
          <div className="mt-4 text-sm leading-7 text-slate-300">
            The controller keeps exactly one approach green at a time, cycles in a fixed{" "}
            <code>NORTH -&gt; EAST -&gt; SOUTH -&gt; WEST</code> order, keeps straight traffic in the outer left-side lane,
            keeps right turns in the inner curb-side lane, disables left turns completely, and holds every other
            approach at red until the active traffic clears.
          </div>
        </section>

        <section className="glass-panel rounded-[2rem] p-6">
          <p className="panel-title">Traffic Intelligence</p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/10 p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-cyan-100/80">Active Direction Score</p>
              <p className="mt-2 text-3xl font-semibold text-white">{(intelligence.active_phase_score ?? 0).toFixed(2)}</p>
              <p className="mt-2 text-sm text-slate-300">{activePhaseScore?.decision_reason}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Highest Demand</p>
              <p className="mt-2 text-2xl font-semibold text-white">{formatPhase(intelligence.top_phase)}</p>
              <p className="mt-2 text-sm text-slate-300">{intelligence.strategy}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Emergency Prep</p>
              <p className="mt-2 text-2xl font-semibold text-white">
                {intelligence.emergency?.detected ? `${intelligence.emergency.state}`.toUpperCase() : "IDLE"}
              </p>
              <p className="mt-2 text-sm text-slate-300">
                {intelligence.emergency?.detected
                  ? `${intelligence.emergency.approach} ETA ${Number(intelligence.emergency.eta_seconds || 0).toFixed(1)}s`
                  : "No approaching emergency vehicles."}
              </p>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3">
            {signalGroups.map(([approach, label]) => {
              const metric = intelligence.direction_metrics?.[approach];
              return (
                <div key={approach} className={`rounded-2xl border p-4 ${alertAccent(metric?.alert_level)}`}>
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs uppercase tracking-[0.24em] text-white/70">{label}</p>
                    <span className="rounded-full border border-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-white/80">
                      {metric?.alert_level ?? "normal"}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-sm text-white">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.18em] text-white/60">Queue</p>
                      <p className="mt-1 text-lg font-semibold">{Number(metric?.queue_length ?? 0).toFixed(1)}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.18em] text-white/60">Wait</p>
                      <p className="mt-1 text-lg font-semibold">{Number(metric?.avg_wait_time ?? 0).toFixed(1)}s</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.18em] text-white/60">Flow</p>
                      <p className="mt-1 text-lg font-semibold">{Number(metric?.flow_rate ?? 0).toFixed(1)}/s</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Congestion Alerts</p>
            <div className="mt-3 space-y-3">
              {intelligence.congestion_alerts?.length ? (
                intelligence.congestion_alerts.map((alert) => (
                  <div key={`${alert.approach}-${alert.level}`} className={`rounded-2xl border p-3 ${alertAccent(alert.level)}`}>
                    <p className="text-sm font-medium text-white">{alert.message}</p>
                    <p className="mt-1 text-xs text-white/70">
                      Queue {Number(alert.queue_length ?? 0).toFixed(1)} | Delta {Number(alert.queue_delta ?? 0).toFixed(1)}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-300">No active congestion alerts. Local conditions are stable.</p>
              )}
            </div>
          </div>
        </section>

        {networkIntersections.length || (Array.isArray(network?.links) && network.links.length) ? (
          <section className="glass-panel rounded-[2rem] p-6">
            <p className="panel-title">Network Overview</p>
            <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Coordination Mode</p>
              <p className="mt-2 text-2xl font-semibold text-white">{network?.coordination_mode ?? "Local control"}</p>
            </div>
          </section>
        ) : null}

        <section className="glass-panel rounded-[2rem] p-6">
          <p className="panel-title">Debug Surface</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Vehicle State</p>
                  <p className="mt-2 text-sm text-white">Moving: {vehicleStates.MOVING}</p>
                  <p className="mt-1 text-sm text-white">Stopped: {vehicleStates.STOPPED}</p>
                  <p className="mt-1 text-sm text-white">Straight: {vehicleStates.straight}</p>
                  <p className="mt-1 text-sm text-white">Right: {vehicleStates.right}</p>
                </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Approach Load</p>
              <p className="mt-2 text-sm text-white">North: {vehicleStates.NORTH}</p>
              <p className="mt-1 text-sm text-white">South: {vehicleStates.SOUTH}</p>
              <p className="mt-1 text-sm text-white">East: {vehicleStates.EAST}</p>
              <p className="mt-1 text-sm text-white">West: {vehicleStates.WEST}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Pedestrian State</p>
              <p className="mt-2 text-sm text-white">
                {pedestriansEnabled
                  ? `Waiting: ${pedestrianStates.WAITING}`
                  : "Disabled in current config"}
              </p>
              <p className="mt-1 text-sm text-white">Crossing: {pedestrianStates.CROSSING}</p>
              <p className="mt-1 text-sm text-white">Exiting: {pedestrianStates.EXITING}</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
