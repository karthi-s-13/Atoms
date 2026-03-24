import { useState } from "react";
import MetricCard from "../components/MetricCard";

export default function ImpactPage({ snapshot }) {
  const [cities, setCities] = useState(6);
  const metrics = snapshot.metrics;
  const livesSaved = Math.round(cities * (2.8 + metrics.emergency_vehicles * 0.6 + metrics.bandwidth_savings * 0.04));
  const accidentsPrevented = Math.round(cities * (12 + metrics.queue_pressure * 18));
  const economicValue = (cities * 2.35 * 1000000) + (metrics.vehicles_processed * 1200);

  return (
    <div className="space-y-6">
      <section className="glass-panel rounded-[2rem] p-8">
        <p className="panel-title">Impact Calculator</p>
        <h2 className="mt-4 text-4xl font-semibold tracking-tight text-white">Scale the digital twin across multiple cities.</h2>
        <p className="mt-4 max-w-2xl text-base leading-8 text-slate-300">
          Use the slider to model a multi-city rollout. The estimates blend live simulation outcomes with deployment multipliers to
          show how emergency preemption, queue reduction, and adaptive phasing compound at scale.
        </p>
        <div className="mt-6 rounded-3xl border border-white/10 bg-white/[0.04] p-5">
          <div className="flex items-center justify-between text-sm text-slate-300">
            <span>Cities Deployed</span>
            <span className="font-semibold text-white">{cities}</span>
          </div>
          <input className="mt-4 w-full accent-cyan-400" type="range" min="1" max="30" step="1" value={cities} onChange={(event) => setCities(Number(event.target.value))} />
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Lives Saved" value={livesSaved} detail="annualized estimate" tone="green" />
        <MetricCard label="Accidents Prevented" value={accidentsPrevented} detail="per year" tone="cyan" />
        <MetricCard label="Economic Value" value={`$${(economicValue / 1000000).toFixed(1)}M`} detail="impact estimate" tone="amber" />
        <MetricCard label="Cities Modeled" value={cities} detail="deployment scale" tone="rose" />
      </section>

      <section className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div className="glass-panel rounded-[2rem] p-6">
          <p className="panel-title">Why It Matters</p>
          <div className="mt-4 space-y-4 text-sm leading-7 text-slate-300">
            <p>Adaptive timing cuts risky stop-and-go waves before queues spill back through the junction.</p>
            <p>Emergency preemption reduces response delay where every second matters.</p>
            <p>Buffered realtime telemetry lowers operator fatigue by keeping motion smooth and readable.</p>
          </div>
        </div>
        <div className="glass-panel rounded-[2rem] p-6">
          <p className="panel-title">Live Inputs</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-sm text-slate-400">Current Throughput</p>
              <p className="mt-2 text-2xl font-semibold text-white">{metrics.throughput.toFixed(2)}</p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-sm text-slate-400">Queue Pressure</p>
              <p className="mt-2 text-2xl font-semibold text-white">{Math.round(metrics.queue_pressure * 100)}%</p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-sm text-slate-400">Emergency Vehicles</p>
              <p className="mt-2 text-2xl font-semibold text-white">{metrics.emergency_vehicles}</p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-sm text-slate-400">Bandwidth Savings</p>
              <p className="mt-2 text-2xl font-semibold text-white">{metrics.bandwidth_savings.toFixed(1)}%</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
