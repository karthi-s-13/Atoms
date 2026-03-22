import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import { useRealtimeSimulation } from "./hooks/useRealtimeSimulation";

const HomePage = lazy(() => import("./pages/HomePage"));
const SimulationPage = lazy(() => import("./pages/SimulationPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ImpactPage = lazy(() => import("./pages/ImpactPage"));
const LiveCvPage = lazy(() => import("./pages/LiveCvPage"));

export default function App() {
  const {
    connectionState,
    sceneSnapshot,
    dashboardSnapshot,
    sceneBufferRef,
    cameraStateRef,
    history,
    controls,
    updateConfig,
    play,
    pause,
    reset,
  } = useRealtimeSimulation();

  return (
    <AppShell connectionState={connectionState} snapshot={dashboardSnapshot}>
      <Suspense fallback={<div className="glass-panel rounded-[2rem] p-8 text-sm text-slate-300">Loading command surface...</div>}>
        <Routes>
          <Route path="/" element={<HomePage snapshot={dashboardSnapshot} connectionState={connectionState} />} />
          <Route
            path="/simulation"
            element={
              <SimulationPage
                sceneSnapshot={sceneSnapshot}
                dashboardSnapshot={dashboardSnapshot}
                sceneBufferRef={sceneBufferRef}
                cameraStateRef={cameraStateRef}
                controls={controls}
                updateConfig={updateConfig}
                play={play}
                pause={pause}
                reset={reset}
              />
            }
          />
          <Route path="/dashboard" element={<DashboardPage snapshot={dashboardSnapshot} history={history} />} />
          <Route path="/impact" element={<ImpactPage snapshot={dashboardSnapshot} />} />
          <Route path="/live-cv" element={<LiveCvPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
