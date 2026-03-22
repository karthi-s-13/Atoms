import { useDeferredValue } from "react";
import MetricCard from "../components/MetricCard";
import SimulationCanvas from "../components/SimulationCanvas";

const speedOptions = [0.5, 1, 2, 4];
const directions = ["NORTH", "SOUTH", "EAST", "WEST"];

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

  return (
    <div className="grid gap-6 xl:grid-cols-[1.6fr_0.92fr]">
      <div className="space-y-6">
        <SimulationCanvas sceneSnapshot={sceneSnapshot} sceneBufferRef={sceneBufferRef} cameraStateRef={cameraStateRef} />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Vehicles Processed" value={metrics.vehicles_processed} detail="completed trips" tone="cyan" />
          <MetricCard label="Avg Wait" value={`${metrics.avg_wait_time.toFixed(2)}s`} detail="network delay" tone="amber" />
          <MetricCard label="Queue Pressure" value={`${Math.round(metrics.queue_pressure * 100)}%`} detail="live pressure" tone="rose" />
          <MetricCard label="Pedestrians" value={metrics.active_pedestrians} detail="crossing actors" tone="green" />
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
            <Slider label="Traffic Intensity" value={controls.traffic_intensity} min={0.4} max={3} step={0.1} onChange={(value) => updateConfig({ traffic_intensity: value })} />
            <Slider label="Ambulance Frequency" value={controls.ambulance_frequency} min={0} max={1} step={0.01} onChange={(value) => updateConfig({ ambulance_frequency: value })} />
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm text-slate-300">AI Mode</span>
              <select className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none" value={controls.ai_mode} onChange={(event) => updateConfig({ ai_mode: event.target.value })}>
                <option value="fixed">Fixed</option>
                <option value="adaptive">Adaptive</option>
                <option value="emergency">Emergency</option>
              </select>
            </label>

            <div>
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
          </div>
        </section>

        <section className="glass-panel rounded-[2rem] p-6">
          <p className="panel-title">Signal Panel</p>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {directions.map((direction) => (
              <div key={direction} className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{direction}</p>
                <p className="mt-2 text-2xl font-semibold text-white">{hudSnapshot.signals[direction]}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Pedestrian Phase</p>
            <p className="mt-2 text-2xl font-semibold text-white">{hudSnapshot.pedestrian_phase_active ? "ACTIVE" : "IDLE"}</p>
          </div>
          <div className="mt-4 text-sm leading-7 text-slate-300">
            Only one incoming direction runs green at a time. Emergency sirens preempt selection, pedestrians trigger a protected
            all-red phase, and vehicles stop at the painted stop line before the zebra.
          </div>
        </section>
      </div>
    </div>
  );
}
