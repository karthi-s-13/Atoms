import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/", label: "Home" },
  { to: "/simulation", label: "Simulation" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/impact", label: "Impact" },
  { to: "/live-cv", label: "Live CV" },
];

export default function AppShell({ connectionState, snapshot, children }) {
  return (
    <div className="min-h-screen bg-hero-grid">
      <header className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-6 py-7 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.34em] text-cyan-300">Urban Mobility Digital Twin</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-white">Realtime Traffic Intelligence Platform</h1>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-300">
            Single-direction adaptive signal phases, emergency preemption, protected pedestrian crossings, and a buffered 3D
            render loop designed for smooth operator use.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-3xl border border-white/10 bg-white/5 px-4 py-3 backdrop-blur-xl">
            <p className="metric-label">Connection</p>
            <div className="mt-2 flex items-center gap-2">
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  connectionState === "live"
                    ? "bg-emerald-400"
                    : connectionState === "error"
                      ? "bg-rose-400"
                      : "bg-amber-400"
                }`}
              />
              <span className="text-sm font-medium text-white">{connectionState}</span>
            </div>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/5 px-4 py-3 backdrop-blur-xl">
            <p className="metric-label">Frame</p>
            <p className="mt-2 text-lg font-semibold text-white">{snapshot.frame}</p>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/5 px-4 py-3 backdrop-blur-xl">
            <p className="metric-label">Active Phase</p>
            <p className="mt-2 text-lg font-semibold text-white">{snapshot.active_direction ?? "PEDESTRIAN"}</p>
          </div>
        </div>
      </header>

      <nav className="mx-auto flex w-full max-w-7xl flex-wrap gap-3 px-6">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `rounded-full px-4 py-2 text-sm transition ${
                isActive
                  ? "accent-ring bg-cyan-400/10 text-white"
                  : "border border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <main className="mx-auto w-full max-w-7xl px-6 py-6">{children}</main>
    </div>
  );
}
