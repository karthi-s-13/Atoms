import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import { useRealtimeSimulation } from "./hooks/useRealtimeSimulation";

const HomePage = lazy(() => import("./pages/HomePage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ImpactPage = lazy(() => import("./pages/ImpactPage"));
const LiveCvPage = lazy(() => import("./pages/LiveCvPage"));
const MapPage = lazy(() => import("./pages/MapPage"));
const SimulationTestingPage = lazy(() => import("./pages/SimulationTestingPage"));

export default function App() {
  const {
    connectionState,
    dashboardSnapshot,
    history,
    controls,
  } = useRealtimeSimulation();

  return (
    <AppShell connectionState={connectionState} controls={controls}>
      <Suspense fallback={<div className="glass-panel rounded-[2rem] p-8 text-sm text-slate-300">Loading command surface...</div>}>
        <Routes>
          <Route path="/" element={<HomePage snapshot={dashboardSnapshot} connectionState={connectionState} />} />
          <Route path="/dashboard" element={<DashboardPage snapshot={dashboardSnapshot} history={history} />} />
          <Route path="/impact" element={<ImpactPage snapshot={dashboardSnapshot} />} />
          <Route path="/live-cv" element={<LiveCvPage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/simulation-testing" element={<SimulationTestingPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}

