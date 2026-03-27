export default function MetricCard({ label, value, detail, tone = "cyan" }) {
  const toneClass = {
    cyan: "from-cyan-400/30 to-sky-500/5",
    green: "from-emerald-400/30 to-emerald-500/5",
    amber: "from-amber-400/30 to-orange-500/5",
    rose: "from-rose-400/30 to-red-500/5",
  }[tone];

  return (
    <div className={`glass-panel rounded-3xl bg-gradient-to-br ${toneClass} p-5`}>
      <p className="metric-label">{label}</p>
      <div className="mt-3 flex items-end justify-between gap-3">
        <p className="metric-value">{value}</p>
        {detail ? <p className="text-sm text-slate-300">{detail}</p> : null}
      </div>
    </div>
  );
}
