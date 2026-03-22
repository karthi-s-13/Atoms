import MetricCard from "../components/MetricCard";

const problemCards = [
  { title: "Accident Detection", copy: "Realtime state streaming surfaces queue buildups, unsafe crossings, and signal pressure before they cascade." },
  { title: "Smart Signals", copy: "A one-direction phase controller prioritizes the highest queue and wait burden instead of moving two roads blindly together." },
  { title: "Emergency Routing", copy: "Siren-bearing ambulances, firetrucks, and police vehicles trigger protected preemption with phase extension." },
  { title: "City Optimization", copy: "Impact metrics, throughput trends, and queue pressure snapshots help operators tune deployment strategy." },
];

const features = [
  "Pure Python simulation engine",
  "FastAPI websocket bridge",
  "Buffered interpolation for smooth motion",
  "Persistent camera state",
  "Protected pedestrian phase",
  "Bezier-based turning paths",
];

export default function HomePage({ snapshot, connectionState }) {
  const metrics = snapshot.metrics;

  return (
    <div className="space-y-6">
      <section className="grid gap-6 lg:grid-cols-[1.35fr_0.95fr]">
        <div className="glass-panel rounded-[2rem] p-8">
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-300">Hero</p>
          <h2 className="mt-4 max-w-3xl text-5xl font-semibold tracking-tight text-white">
            Production-grade traffic control with protected crossings, emergency preemption, and a premium operator view.
          </h2>
          <p className="mt-5 max-w-2xl text-base leading-8 text-slate-300">
            The platform is split into a pure simulation engine, a dedicated realtime websocket server, and a React + Three.js
            control room that renders buffered motion without UI flicker or camera reset.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <MetricCard label="Connection" value={connectionState} detail="runtime status" tone="cyan" />
            <MetricCard label="Active Phase" value={snapshot.active_direction ?? "PEDESTRIAN"} detail="current green" tone="green" />
            <MetricCard label="Vehicles" value={metrics.active_vehicles} detail="live actors" tone="amber" />
          </div>
        </div>

        <div className="glass-panel rounded-[2rem] p-8">
          <p className="panel-title">System Overview</p>
          <div className="mt-5 space-y-4 text-sm leading-7 text-slate-300">
            <p>Simulation Engine: path-following vehicles, single-direction phases, siren priorities, and crosswalk-safe pedestrians.</p>
            <p>Realtime Server: authoritative 60 FPS clock, websocket streaming, health endpoint, and control acknowledgements.</p>
            <p>Frontend: buffered interpolation, persistent camera, operator controls, analytics dashboard, and impact modeling.</p>
          </div>
          <div className="mt-6 rounded-3xl border border-white/10 bg-white/[0.04] p-5">
            <p className="metric-label">Live Snapshot</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div>
                <p className="text-sm text-slate-400">Pedestrian Phase</p>
                <p className="text-lg font-semibold text-white">{snapshot.pedestrian_phase_active ? "ACTIVE" : "IDLE"}</p>
              </div>
              <div>
                <p className="text-sm text-slate-400">Emergency Units</p>
                <p className="text-lg font-semibold text-white">{metrics.emergency_vehicles}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {problemCards.map((card, index) => (
          <div key={card.title} className={`glass-panel rounded-[2rem] p-6 ${index % 2 === 0 ? "bg-white/[0.06]" : "bg-cyan-400/[0.04]"}`}>
            <p className="metric-label">{card.title}</p>
            <p className="mt-4 text-sm leading-7 text-slate-300">{card.copy}</p>
          </div>
        ))}
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.15fr_1fr]">
        <div className="glass-panel rounded-[2rem] p-8">
          <p className="panel-title">Features Grid</p>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {features.map((feature) => (
              <div key={feature} className="rounded-3xl border border-white/10 bg-white/[0.04] p-5 text-sm text-slate-200">
                {feature}
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
          <MetricCard label="Queue Pressure" value={`${Math.round(metrics.queue_pressure * 100)}%`} detail="network burden" tone="rose" />
          <MetricCard label="Detections" value={metrics.detections} detail="event intelligence" tone="cyan" />
          <MetricCard label="Savings" value={`${metrics.bandwidth_savings.toFixed(1)}%`} detail="telemetry reduction" tone="green" />
        </div>
      </section>
    </div>
  );
}
