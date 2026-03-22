function buildPolyline(points, width, height) {
  if (!points.length) {
    return "";
  }
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys, 1);

  return points
    .map((point) => {
      const x = maxX === minX ? width / 2 : ((point.x - minX) / (maxX - minX)) * width;
      const y = height - ((point.y / maxY) * height);
      return `${x},${y}`;
    })
    .join(" ");
}

export default function LineChart({ title, valueLabel, points, stroke = "#22d3ee" }) {
  const width = 420;
  const height = 160;
  const polyline = buildPolyline(points, width, height);
  const lastValue = points.length ? points[points.length - 1].y : 0;
  const gradientId = `line-fill-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

  return (
    <div className="glass-panel rounded-3xl p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="panel-title">{title}</p>
          <p className="mt-2 text-3xl font-semibold text-white">{lastValue.toFixed(2)}</p>
        </div>
        <p className="text-sm text-slate-400">{valueLabel}</p>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="mt-5 h-44 w-full">
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={`M0 ${height} ${polyline ? `L ${polyline}` : ""} L${width} ${height} Z`} fill={`url(#${gradientId})`} />
        <polyline
          fill="none"
          points={polyline}
          stroke={stroke}
          strokeWidth="4"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}
