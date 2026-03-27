export default function DonutChart({ title, items }) {
  const totalValue = items.reduce((sum, item) => sum + item.value, 0);
  const safeTotal = totalValue || 1;
  let offset = 0;
  const segments = items
    .filter((item) => item.value > 0)
    .map((item) => {
      const start = offset;
      const span = (item.value / safeTotal) * 360;
      offset += span;
      return `${item.color} ${start}deg ${offset}deg`;
    })
    .join(", ");

  return (
    <div className="glass-panel rounded-3xl p-5">
      <p className="panel-title">{title}</p>
      <div className="mt-5 flex items-center gap-6">
        <div
          className="h-36 w-36 rounded-full border border-white/10"
          style={{
            background: `conic-gradient(${segments || "#1e293b 0deg 360deg"})`,
          }}
        >
          <div className="m-6 flex h-24 w-24 items-center justify-center rounded-full bg-slate-950/90 text-xl font-semibold text-white">
            {totalValue}
          </div>
        </div>
        <div className="flex-1 space-y-3">
          {items.map((item) => (
            <div key={item.label} className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="h-3 w-3 rounded-full" style={{ background: item.color }} />
                <span className="text-sm text-slate-300">{item.label}</span>
              </div>
              <span className="text-sm font-medium text-white">{item.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
