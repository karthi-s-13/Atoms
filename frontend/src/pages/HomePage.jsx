import MetricCard from "../components/MetricCard";

function formatPhase(state) {
  return String(state || "ALL_RED").split("_").join(" ");
}

const problemCards = [
  { title: "Accident Detection", copy: "Realtime state streaming surfaces queue buildups, blocked approaches, and deadlocks before they cascade." },
  { title: "Deterministic Signals", copy: "Exactly one approach stays green at a time, cycling in a fixed order for predictable operation." },
  { title: "Intent-Based Flow", copy: "Each car is assigned a straight or right intent, left turns are disabled, and every vehicle stays in its dedicated lane." },
  { title: "City Optimization", copy: "Impact metrics, throughput trends, and queue pressure snapshots help operators tune deployment strategy." },
];

const features = [
  "Pure Python simulation engine",
  "FastAPI websocket bridge",
  "Buffered interpolation for smooth motion",
  "Persistent camera state",
  "Deterministic one-direction controller",
  "Lane-disciplined turn paths",
];

export default function HomePage({ snapshot, connectionState }) {
  const metrics = snapshot.metrics;

  return (
    <div className="space-y-6">
      <section className="grid gap-6 lg:grid-cols-[1.35fr_0.95fr]">
        <div className="glass-panel rounded-[2rem] p-8">
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-300">Hero</p>
          <h2 className="mt-4 max-w-3xl text-5xl font-semibold tracking-tight text-white">
            Stable traffic control with clean path following, strict signal states, and one green approach at a time.
          </h2>
          <p className="mt-5 max-w-2xl text-base leading-8 text-slate-300">
            The platform is split into a pure simulation engine, a dedicated realtime websocket server, and a React + Three.js
            control room that renders buffered motion without UI flicker or camera reset.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <MetricCard label="Connection" value={connectionState} detail="runtime status" tone="cyan" />
            <MetricCard
              label="Active Phase"
              value={formatPhase(snapshot.current_state)}
              detail="current green"
              tone="green"
            />
            <MetricCard label="Vehicles" value={metrics.active_vehicles} detail="live actors" tone="amber" />
          </div>
        </div>

        <div className="glass-panel rounded-[2rem] p-8">
          <p className="panel-title">System Overview</p>
          <div className="mt-5 space-y-4 text-sm leading-7 text-slate-300">
            <p>Simulation Engine: path-following cars, one green direction at a time, a dedicated straight lane, a dedicated right-turn lane, and stop-line enforcement before every zebra crossing.</p>
            <p>Realtime Server: authoritative 60 FPS clock, websocket streaming, health endpoint, and control acknowledgements.</p>
            <p>Frontend: buffered interpolation, persistent camera, operator controls, analytics dashboard, and impact modeling.</p>
          </div>
          <div className="mt-6 rounded-3xl border border-white/10 bg-white/[0.04] p-5">
            <p className="metric-label">Live Snapshot</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div>
                <p className="text-sm text-slate-400">Pedestrian Mode</p>
                <p className="text-lg font-semibold text-white">{(snapshot.config?.max_pedestrians ?? 0) > 0 ? (snapshot.pedestrian_phase_active ? "ACTIVE" : "CONTROLLED") : "DISABLED"}</p>
              </div>
              <div>
                <p className="text-sm text-slate-400">Active Cars</p>
                <p className="text-lg font-semibold text-white">{metrics.active_vehicles}</p>
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
