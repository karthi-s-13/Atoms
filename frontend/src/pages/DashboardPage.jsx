import { useDeferredValue } from "react";
import DonutChart from "../components/DonutChart";
import EventLog from "../components/EventLog";
import LineChart from "../components/LineChart";
import MetricCard from "../components/MetricCard";

const VEHICLE_KIND_STYLES = {
  car: { label: "Cars", color: "#3b82f6" },
  ambulance: { label: "Ambulances", color: "#22c55e" },
  firetruck: { label: "Firetrucks", color: "#ef4444" },
  police: { label: "Police", color: "#facc15" },
};

export default function DashboardPage({ snapshot, history }) {
  const deferredSnapshot = useDeferredValue(snapshot);
  const metrics = deferredSnapshot.metrics;
  const distribution = deferredSnapshot.vehicles.reduce(
    (counts, vehicle) => {
      counts[vehicle.kind] = (counts[vehicle.kind] || 0) + 1;
      return counts;
    },
    { car: 0 },
  );
  const vehicleDistributionItems = Object.entries(VEHICLE_KIND_STYLES).map(([kind, style]) => ({
    label: style.label,
    value: distribution[kind] || 0,
    color: style.color,
  }));

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Active Nodes" value={metrics.active_nodes} detail="signals + sensors" tone="cyan" />
        <MetricCard label="Detections" value={metrics.detections} detail="live events" tone="green" />
        <MetricCard label="Active Vehicles" value={metrics.active_vehicles} detail="lane actors" tone="amber" />
        <MetricCard label="Savings" value={`${metrics.bandwidth_savings.toFixed(1)}%`} detail="telemetry efficiency" tone="rose" />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.2fr_1.2fr_0.9fr]">
        <LineChart title="Traffic Timeline" valueLabel="veh / sec" points={history.throughput} stroke="#22d3ee" />
        <LineChart title="Queue Pressure" valueLabel="percent" points={history.queue} stroke="#f59e0b" />
        <DonutChart title="Vehicle Distribution" items={vehicleDistributionItems} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-1">
          <div className="glass-panel rounded-[2rem] p-5">
            <p className="panel-title">Wait Time</p>
            <p className="mt-3 text-3xl font-semibold text-white">{metrics.avg_wait_time.toFixed(2)}s</p>
            <p className="mt-2 text-sm text-slate-400">Average delay for active vehicles.</p>
          </div>
          <div className="glass-panel rounded-[2rem] p-5">
            <p className="panel-title">Processed Trips</p>
            <p className="mt-3 text-3xl font-semibold text-white">{metrics.vehicles_processed}</p>
            <p className="mt-2 text-sm text-slate-400">Vehicles that completed intersection travel.</p>
          </div>
        </div>

        <EventLog events={deferredSnapshot.events} />
      </section>
    </div>
  );
}
