"""Minimal Streamlit runner with a persistent simulation engine."""

from __future__ import annotations

import time
from typing import Any, Dict, List

import plotly.graph_objects as go
import streamlit as st

from hardware import SignalController
from simulation_engine import FRAME_DT, TrafficSimulationEngine


REFRESH_INTERVAL_MS = 50


st.set_page_config(page_title="Traffic Simulation Monitor", layout="wide")


def get_engine() -> TrafficSimulationEngine:
    if "engine" not in st.session_state:
        st.session_state["engine"] = TrafficSimulationEngine()
    if "hw" not in st.session_state:
        import os
        port = os.getenv("SERIAL_PORT", "COM5")
        st.session_state["hw"] = SignalController(port=port)
    return st.session_state["engine"], st.session_state["hw"]


def update_controls(engine: TrafficSimulationEngine) -> None:
    with st.sidebar:
        st.header("Simulation Controls")
        left, right = st.columns(2)
        if left.button("Play", use_container_width=True):
            engine.update_config({"paused": False})
        if right.button("Pause", use_container_width=True):
            engine.update_config({"paused": True})

        if st.button("Reset", use_container_width=True):
            engine.reset()
            st.session_state["last_tick_wallclock"] = time.perf_counter()
            snapshot = engine.get_state()
            st.session_state["snapshot"] = snapshot
            st.session_state["last_valid_snapshot"] = snapshot
            st.session_state["sim_error"] = None

        traffic_intensity = st.slider(
            "Traffic Intensity",
            min_value=0.0,
            max_value=1.0,
            value=float(engine.config.traffic_intensity),
            step=0.05,
        )
        max_vehicles = st.slider(
            "Max Vehicles",
            min_value=8,
            max_value=120,
            value=int(engine.config.max_vehicles),
            step=2,
        )
        engine.update_config(
            {
                "traffic_intensity": traffic_intensity,
                "max_vehicles": max_vehicles,
            }
        )


def advance_engine(engine: TrafficSimulationEngine) -> Dict[str, object]:
    now = time.perf_counter()
    last_tick = st.session_state.get("last_tick_wallclock", now - FRAME_DT)
    dt = max(FRAME_DT, min(0.1, now - last_tick))
    st.session_state["last_tick_wallclock"] = now

    try:
        engine.tick(dt)
        snapshot = engine.get_state()
        
        # Mirror the simulation state to the Arduino Hardware
        if "hw" in st.session_state:
            st.session_state["hw"].update(
                active_direction=snapshot.get("active_direction"),
                phase_state=engine.phase_state,
                pedestrian_active=snapshot.get("pedestrian_phase_active", False)
            )
        if not engine.config.paused:
            assert len(engine.vehicles) > 0, "Simulation stalled: no vehicles remain in the engine."
        st.session_state["snapshot"] = snapshot
        st.session_state["last_valid_snapshot"] = snapshot
        st.session_state["sim_error"] = None
        return snapshot
    except Exception as exc:  # pragma: no cover - UI safety path
        st.session_state["sim_error"] = str(exc)
        return st.session_state.get("last_valid_snapshot", engine.get_state())


def _positions(items: List[Dict[str, object]], color: str, name: str) -> List[go.Scatter]:
    # Separate emergency vehicles for highlighting
    standard = [v for v in items if not v.get("has_siren")]
    emergency = [v for v in items if v.get("has_siren")]
    
    scatters = []
    if standard:
        scatters.append(go.Scatter(
            x=[item["x"] for item in standard],
            y=[item["y"] for item in standard],
            mode="markers",
            name="Traffic",
            marker={"size": 10, "color": "#38bdf8", "opacity": 0.8},
            hovertext=[f"ID: {item['id']}<br>Speed: {item['speed']:.1f}m/s" for item in standard],
            hoverinfo="text",
        ))
    
    if emergency:
        scatters.append(go.Scatter(
            x=[item["x"] for item in emergency],
            y=[item["y"] for item in emergency],
            mode="markers+text",
            name="EMERGENCY",
            text=["🚨" for _ in emergency],
            textposition="top center",
            marker={"size": 14, "color": "#ef4444", "line": {"width": 2, "color": "white"}},
            hovertext=[f"ID: {item['id']}<br>PRIORITY: {item.get('priority', 'HIGH')}<br>Speed: {item['speed']:.1f}m/s" for item in emergency],
            hoverinfo="text",
        ))
    
    return scatters


def render(snapshot: Dict[str, Any]) -> None:
    st.title("Traffic Simulation Monitor")

    error_message = st.session_state.get("sim_error")
    if error_message:
        st.warning(f"Simulation recovered from an error and is rendering the last valid snapshot: {error_message}")

    metrics = snapshot["metrics"]
    top = st.columns(4)
    top[0].metric("Frame", snapshot["frame"])
    top[1].metric("Active Flow", snapshot["active_direction"] or "ALL RED")
    top[2].metric("Vehicles", metrics["active_vehicles"])
    top[3].metric("Avg Wait", f"{metrics['avg_wait_time']:.2f}s")

    chart_col, detail_col = st.columns([1.7, 1.0])
    with chart_col:
        # Check for active emergency in traffic_brain telemetry
        brain_info = snapshot.get("traffic_brain", {})
        emergency_info = brain_info.get("emergency", {})
        
        if emergency_info.get("active"):
            level = emergency_info.get("level", "DETECTED")
            eta = emergency_info.get("eta_seconds", 0) # ep.eta_seconds is the contract field
            direction = emergency_info.get("preferred_phase", "NONE") # ep.preferred_phase is the contract field
            
            if level == "CRITICAL":
                st.error(f"🚨 CRITICAL PREEMPTION: Emergency approaching {direction} in {eta}s!")
            elif level == "APPROACHING":
                st.warning(f"⚠️ EMERGENCY APPROACHING: Clearing path for {direction} (ETA: {eta}s)")
            else:
                st.info(f"ℹ️ EMERGENCY DETECTED: {direction} approach monitored (ETA: {eta}s)")

        fig = go.Figure()
        for trace in _positions(snapshot["vehicles"], "#38bdf8", "Vehicles"):
            fig.add_trace(trace)
            
        fig.update_layout(
            height=520,
            margin={"l": 20, "r": 20, "t": 20, "b": 20},
            paper_bgcolor="#0f172a",
            plot_bgcolor="#0f172a",
            font={"color": "#e2e8f0"},
            xaxis={"range": [-80, 80], "title": "X", "gridcolor": "#1e293b"},
            yaxis={"range": [-80, 80], "title": "Y", "scaleanchor": "x", "scaleratio": 1, "gridcolor": "#1e293b"},
            legend={"orientation": "h", "y": 1.02, "x": 0},
        )
        st.plotly_chart(fig, use_container_width=True)

    with detail_col:
        if emergency_info.get("active"):
            st.subheader("🚨 Emergency Telemetry")
            st.metric("Priority Score", f"{emergency_info.get('score', 0.0):.1f}")
            st.metric("Preemption Level", emergency_info.get("level", "NONE"))
            st.divider()

        st.subheader("Signals")
        st.json(snapshot["signals"])
        st.subheader("Recent Events")
        st.dataframe(snapshot["events"][:8], use_container_width=True, hide_index=True)

    st.subheader("Live Actors")
    st.caption("Vehicles")
    st.dataframe(snapshot["vehicles"][:12], use_container_width=True, hide_index=True)


def run_frame(engine: TrafficSimulationEngine, hw: SignalController) -> None:
    advance_engine(engine) # Advance the engine, which updates st.session_state["snapshot"]
    current_snapshot = st.session_state.get("snapshot")
    if current_snapshot:
        render(current_snapshot)

engine, hw = get_engine()
update_controls(engine)

if hasattr(st, "autorefresh"):
    st.autorefresh(interval=REFRESH_INTERVAL_MS, key="sim_loop")
    run_frame(engine, hw)
else:
    @st.fragment(run_every=REFRESH_INTERVAL_MS / 1000)
    def live_fragment() -> None:
        run_frame(engine, hw)

    live_fragment()
