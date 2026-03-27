import { useState, useCallback, useRef, useEffect } from "react";
import DemoCanvas from "../components/DemoCanvas";
import { useRealtimeSimulation } from "../hooks/useRealtimeSimulation";

const DEMO_TIMELINE = [
  { time:  0, label: "LIGHT TRAFFIC",      color: "emerald" },
  { time: 10, label: "HEAVY TRAFFIC",      color: "amber"   },
  { time: 20, label: "CONGESTION",         color: "rose"    },
  { time: 30, label: "EMERGENCY PRIORITY", color: "red"     },
  { time: 40, label: "CLEARANCE",          color: "sky"     },
  { time: 50, label: "RECOVERY",           color: "violet"  },
  { time: 55, label: "BALANCED FLOW",      color: "cyan"    },
];

const PHASE_COLORS = {
  emerald: { ring: "border-emerald-500/40", dot: "bg-emerald-400", text: "text-emerald-300", glow: "shadow-[0_0_30px_rgba(52,211,153,0.12)]", badge: "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" },
  amber:   { ring: "border-amber-500/40",   dot: "bg-amber-400",   text: "text-amber-300",   glow: "shadow-[0_0_30px_rgba(251,191,36,0.12)]",  badge: "bg-amber-500/10 border-amber-500/20 text-amber-400"   },
  rose:    { ring: "border-rose-500/40",    dot: "bg-rose-400",    text: "text-rose-300",    glow: "shadow-[0_0_30px_rgba(251,113,133,0.12)]", badge: "bg-rose-500/10 border-rose-500/20 text-rose-400"     },
  red:     { ring: "border-red-500/40",     dot: "bg-red-400 animate-ping",text:"text-red-300", glow:"shadow-[0_0_30px_rgba(248,113,113,0.25)]", badge:"bg-red-500/10 border-red-500/20 text-red-400"       },
  sky:     { ring: "border-sky-500/40",     dot: "bg-sky-400",     text: "text-sky-300",     glow: "shadow-[0_0_30px_rgba(56,189,248,0.12)]",  badge: "bg-sky-500/10 border-sky-500/20 text-sky-400"        },
  violet:  { ring: "border-violet-500/40",  dot: "bg-violet-400",  text: "text-violet-300",  glow: "shadow-[0_0_30px_rgba(167,139,250,0.12)]", badge: "bg-violet-500/10 border-violet-500/20 text-violet-400"},
  cyan:    { ring: "border-cyan-500/40",    dot: "bg-cyan-400",    text: "text-cyan-300",    glow: "shadow-[0_0_30px_rgba(34,211,238,0.12)]",  badge: "bg-cyan-500/10 border-cyan-500/20 text-cyan-400"     },
};

function StatCard({ label, value, sub, highlight = false, accentColor = "cyan" }) {
  const acc = {
    cyan:    "from-cyan-500/10",
    emerald: "from-emerald-500/10",
    amber:   "from-amber-500/10",
    rose:    "from-rose-500/10",
    red:     "from-red-500/10",
  }[accentColor] || "from-cyan-500/10";

  return (
    <div className={`glass-panel relative flex flex-col justify-between rounded-[2rem] p-6 border transition-all duration-500 hover:scale-[1.02] ${
      highlight ? "border-white/20 bg-slate-900/60" : "border-white/5 bg-slate-900/30"
    }`}>
      {highlight && <div className={`absolute inset-0 rounded-[2rem] bg-gradient-to-br ${acc} to-transparent opacity-60`} />}
      <div className="relative z-10">
        <p className="text-[10px] font-bold uppercase tracking-[0.25em] text-slate-500 mb-1">{label}</p>
        <p className="text-3xl font-bold tracking-tight text-white tabular-nums">{value}</p>
      </div>
      {sub && <p className="relative z-10 mt-3 text-[11px] font-semibold tracking-wide text-slate-400">{sub}</p>}
    </div>
  );
}

function SignalBadge({ label, state }) {
  const colors = {
    GREEN:  "bg-emerald-500 shadow-[0_0_8px_rgba(52,211,153,0.8)]",
    YELLOW: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.8)]",
    RED:    "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]",
  }[state] || "bg-slate-600";

  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/5 border border-white/10">
      <div className={`w-2.5 h-2.5 rounded-full ${colors}`} />
      <span className="text-[11px] font-bold text-slate-300 tracking-wide">{label}</span>
    </div>
  );
}

export default function SimulationTestingPage() {
  const { connectionState: wsState, dashboardSnapshot, send } = useRealtimeSimulation();
  const [syncHardware, setSyncHardware] = useState(false);

  const sendHardwareCommand = useCallback((command) => {
    if (!syncHardware || !send) return;
    send({ type: "set_hardware_state", command });
  }, [syncHardware, send]);

  const onSignalChange = useCallback((signal) => {
    sendHardwareCommand(signal.command);
  }, [sendHardwareCommand]);
  // Use refs to avoid React re-renders in the rAF loop — but useState for UI
  const [stats, setStats] = useState({
    phase: "LIGHT TRAFFIC",
    demoTime: 0,
    signals: { NORTH:"GREEN", SOUTH:"GREEN", EAST:"RED", WEST:"RED" },
    vehicles: 0,
    avgWait: 0,
    throughput: 0,
    queuePressure: 0,
    emergencyVehicles: 0,
    activeDirection: "NORTH/SOUTH",
  });

  // Throttle React state updates to ~15fps to avoid jank
  const updateCounterRef = useRef(0);
  const pendingStatsRef  = useRef(null);
  const rafPendingRef    = useRef(false);

  const onStatsUpdate = useCallback((newStats) => {
    pendingStatsRef.current = newStats;
    if (!rafPendingRef.current) {
      rafPendingRef.current = true;
      requestAnimationFrame(() => {
        if (pendingStatsRef.current) {
          setStats(pendingStatsRef.current);
        }
        rafPendingRef.current = false;
      });
    }
  }, []);

  const curPhase = DEMO_TIMELINE.find(p => p.label === stats.phase) || DEMO_TIMELINE[0];
  const theme    = PHASE_COLORS[curPhase.color] || PHASE_COLORS.cyan;

  const progressPct = Math.min(100, (stats.demoTime / 62) * 100);

  return (
    <div className="flex flex-col gap-8 pb-16">

      {/* ── Header ── */}
      <div className="flex flex-col lg:flex-row gap-6 items-start lg:items-center justify-between">
        <div className="relative">
          <div className="absolute -left-6 top-1/2 -translate-y-1/2 w-1.5 h-12 bg-cyan-400 rounded-full blur-[2px]" />
          <h1 className="text-4xl font-bold tracking-tight text-white">
            Simulation <span className="text-cyan-400">Testing</span>
          </h1>
          <p className="mt-2 text-slate-400 max-w-xl text-sm leading-relaxed">
            Deterministic 60-second demo — 60 FPS locked, frontend-only physics engine with zero backend dependency.
          </p>
        </div>

        <div className="flex gap-3 flex-wrap">
          <div className="glass-panel px-5 py-3 rounded-[1.5rem] border border-cyan-500/20 bg-cyan-500/5 text-center">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-400/70">Render Mode</p>
            <p className="text-sm font-bold text-white mt-1">60 FPS LOCKED</p>
          </div>
          <div className="glass-panel px-5 py-3 rounded-[1.5rem] border border-white/10 text-center">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">Engine</p>
            <p className="text-sm font-bold text-white mt-1">Frontend Physics</p>
          </div>
        </div>
      </div>

      {/* ── Scenario Phase Bar ── */}
      <div className={`glass-panel relative overflow-hidden flex flex-col lg:flex-row items-start lg:items-center gap-4 px-8 py-5 rounded-[2rem] border ${theme.ring} bg-slate-900/40 ${theme.glow}`}>
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className={`w-3 h-3 rounded-full ${theme.dot}`} />
          <span className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">Active Scenario</span>
        </div>
        <div className="h-4 w-px bg-white/10 hidden lg:block" />
        <h2 className={`text-2xl font-black tracking-widest uppercase italic ${theme.text}`}>
          {stats.phase}
        </h2>

        {stats.emergencyVehicles > 0 && (
          <span className="px-3 py-1 rounded-full bg-red-500/20 border border-red-500/30 text-red-300 text-[10px] font-black uppercase tracking-widest animate-pulse">
            🚨 Emergency Active
          </span>
        )}

        <div className="lg:ml-auto flex items-center gap-3">
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest hidden sm:block">Progress</span>
          <div className="flex items-center gap-2">
            <div className="w-32 h-1.5 bg-white/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-cyan-400 rounded-full transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <span className="text-xs font-mono text-cyan-400 w-16 text-right">
              {Math.floor(stats.demoTime)}s / 60s
            </span>
          </div>
        </div>
        <div className="absolute right-0 top-0 w-1/3 h-full bg-gradient-to-l from-white/5 to-transparent pointer-events-none" />
      </div>

      {/* ── Main Layout: Canvas + Panels ── */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-8">

        {/* Canvas */}
        <div className="xl:col-span-3 rounded-[2rem] overflow-hidden border border-white/5 shadow-2xl" style={{ height: "680px" }}>
          <DemoCanvas onStatsUpdate={onStatsUpdate} onSignalChange={onSignalChange} className="rounded-[2rem]" />
        </div>

        {/* Side Panels */}
        <aside className="flex flex-col gap-5">

          {/* Signal Status */}
          <div className="glass-panel p-5 rounded-[2rem] border border-white/5 bg-slate-900/30">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500 mb-4">Signal Status</p>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(stats.signals).map(([dir, state]) => (
                <SignalBadge key={dir} label={dir} state={state} />
              ))}
            </div>
            <div className="mt-4 pt-4 border-t border-white/5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] uppercase font-bold text-slate-500 tracking-widest">Active Green</p>
                  <p className="text-lg font-bold text-emerald-300 mt-1">{stats.activeDirection}</p>
                </div>
                <button
                  onClick={() => setSyncHardware(!syncHardware)}
                  className={`px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all duration-300 border ${
                    syncHardware ? "bg-cyan-500 border-cyan-400 text-white shadow-[0_0_15px_rgba(6,182,212,0.4)]" : "bg-white/5 border-white/10 text-slate-500"
                  }`}
                >
                  {syncHardware ? "HW Sync: ON" : "HW Sync: OFF"}
                </button>
              </div>
              <div className="mt-2 text-[9px] text-slate-600 font-mono">
                {syncHardware ? `Command: ${stats.signalPhase || "AWAITING"}` : "Hardware idle"}
              </div>
            </div>
          </div>

          {/* Scenario Timeline */}
          <div className="glass-panel p-5 rounded-[2rem] border border-white/5 bg-slate-900/30">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500 mb-4">Demo Sequence</p>
            <div className="space-y-2">
              {DEMO_TIMELINE.map((p, i) => {
                const isActive = p.label === stats.phase;
                const isPast   = stats.demoTime > p.time;
                return (
                  <div
                    key={i}
                    className={`flex items-center gap-2 px-3 py-2 rounded-xl transition-all duration-300 ${
                      isActive ? `${PHASE_COLORS[p.color].badge} border font-bold` : isPast ? "opacity-40" : "opacity-60"
                    }`}
                  >
                    <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${isActive ? PHASE_COLORS[p.color].dot.replace("animate-ping","") : "bg-slate-600"}`} />
                    <span className="text-[10px] tracking-wide uppercase">{p.label}</span>
                    <span className="ml-auto text-[9px] text-slate-500">{p.time}s</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Live Stats */}
          <div className="glass-panel p-5 rounded-[2rem] border border-white/5 bg-slate-900/30">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500 mb-4">Live Metrics</p>
            <div className="space-y-3">
              {[
                { label: "Active Vehicles", value: stats.vehicles, total: 50, color: "bg-cyan-400" },
                { label: "Queue Pressure", value: Math.round(stats.queuePressure * 100), total: 100, color: "bg-amber-400", suffix: "%" },
                { label: "Avg Wait", value: stats.avgWait.toFixed(1), raw: true, suffix: "s", sub: "seconds per vehicle" },
                { label: "Throughput", value: stats.throughput, raw: true, suffix: "/s", sub: "vehicles cleared / sec" },
              ].map((m, i) => (
                <div key={i}>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wide">{m.label}</span>
                    <span className="text-sm font-bold text-white tabular-nums">{m.value}{m.suffix||""}</span>
                  </div>
                  {!m.raw && (
                    <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${m.color} transition-all duration-500`}
                        style={{ width: `${(m.value / m.total) * 100}%` }}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>

      {/* ── Stats Grid ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-5">
        <StatCard
          label="Active Vehicles"
          value={stats.vehicles}
          sub={`of ${50} max capacity`}
          highlight={stats.vehicles > 30}
          accentColor="cyan"
        />
        <StatCard
          label="Avg Wait Time"
          value={`${stats.avgWait.toFixed(1)}s`}
          sub="Per vehicle"
          highlight={stats.avgWait > 8}
          accentColor={stats.avgWait > 8 ? "rose" : "cyan"}
        />
        <StatCard
          label="Throughput"
          value={`${stats.throughput}`}
          sub="Vehicles / second"
          accentColor="emerald"
        />
        <StatCard
          label="Queue Pressure"
          value={`${Math.round(stats.queuePressure * 100)}%`}
          sub="Intersection load"
          highlight={stats.queuePressure > 0.6}
          accentColor={stats.queuePressure > 0.6 ? "amber" : "cyan"}
        />
        <StatCard
          label="Emergencies"
          value={stats.emergencyVehicles}
          sub={stats.emergencyVehicles > 0 ? "🚨 Active in field" : "None active"}
          highlight={stats.emergencyVehicles > 0}
          accentColor="red"
        />
        <StatCard
          label="Active Direction"
          value={stats.activeDirection}
          sub="Signal priority"
          accentColor="cyan"
        />
      </div>

    </div>
  );
}
