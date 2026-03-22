export default function EventLog({ events }) {
  return (
    <div className="glass-panel rounded-3xl p-5">
      <div className="flex items-center justify-between">
        <p className="panel-title">Event Log</p>
        <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Live</p>
      </div>
      <div className="mt-4 max-h-80 space-y-3 overflow-auto pr-2">
        {events.length ? (
          events.map((event, index) => (
            <div key={`${event.timestamp}-${index}`} className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">{event.level}</span>
                <span className="text-xs text-slate-500">{event.timestamp.toFixed(2)}s</span>
              </div>
              <p className="mt-2 text-sm text-slate-200">{event.message}</p>
            </div>
          ))
        ) : (
          <div className="rounded-2xl border border-dashed border-white/10 p-5 text-sm text-slate-400">
            Awaiting simulation events.
          </div>
        )}
      </div>
    </div>
  );
}
