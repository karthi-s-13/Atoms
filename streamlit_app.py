"""Minimal Streamlit runner with a persistent simulation engine."""

from __future__ import annotations

import time
from typing import Dict, List

import plotly.graph_objects as go
import streamlit as st

from simulation_engine import FRAME_DT, TrafficSimulationEngine


REFRESH_INTERVAL_MS = 50


st.set_page_config(page_title="Traffic Simulation Monitor", layout="wide")


def get_engine() -> TrafficSimulationEngine:
    if "engine" not in st.session_state:
        st.session_state["engine"] = TrafficSimulationEngine()
    return st.session_state["engine"]


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
        if not engine.config.paused:
            assert len(engine.vehicles) > 0, "Simulation stalled: no vehicles remain in the engine."
        st.session_state["snapshot"] = snapshot
        st.session_state["last_valid_snapshot"] = snapshot
        st.session_state["sim_error"] = None
        return snapshot
    except Exception as exc:  # pragma: no cover - UI safety path
        st.session_state["sim_error"] = str(exc)
        return st.session_state.get("last_valid_snapshot", engine.get_state())


def _positions(items: List[Dict[str, object]], color: str, name: str) -> go.Scatter:
    return go.Scatter(
        x=[item["x"] for item in items],
        y=[item["y"] for item in items],
        mode="markers",
        name=name,
        marker={"size": 10 if name == "Vehicles" else 8, "color": color},
        hovertext=[item["id"] for item in items],
        hoverinfo="text",
    )


def render(snapshot: Dict[str, object]) -> None:
    st.title("Traffic Simulation Monitor")

    error_message = st.session_state.get("sim_error")
    if error_message:
        st.warning(f"Simulation recovered from an error and is rendering the last valid snapshot: {error_message}")

    metrics = snapshot["metrics"]
    top = st.columns(5)
    top[0].metric("Frame", snapshot["frame"])
    top[1].metric("Active Flow", snapshot["active_direction"] or "ALL RED")
    top[2].metric("Vehicles", metrics["active_vehicles"])
    top[3].metric("Pedestrians", metrics["active_pedestrians"])
    top[4].metric("Avg Wait", f"{metrics['avg_wait_time']:.2f}s")

    chart_col, detail_col = st.columns([1.7, 1.0])
    with chart_col:
        fig = go.Figure()
        fig.add_trace(_positions(snapshot["vehicles"], "#38bdf8", "Vehicles"))
        fig.add_trace(_positions(snapshot["pedestrians"], "#f97316", "Pedestrians"))
        fig.update_layout(
            height=520,
            margin={"l": 20, "r": 20, "t": 20, "b": 20},
            paper_bgcolor="#0f172a",
            plot_bgcolor="#0f172a",
            font={"color": "#e2e8f0"},
            xaxis={"range": [-80, 80], "title": "X"},
            yaxis={"range": [-80, 80], "title": "Y", "scaleanchor": "x", "scaleratio": 1},
            legend={"orientation": "h", "y": 1.02, "x": 0},
        )
        st.plotly_chart(fig, use_container_width=True)

    with detail_col:
        st.subheader("Signals")
        st.json(snapshot["signals"])
        st.subheader("Recent Events")
        st.dataframe(snapshot["events"][:8], use_container_width=True, hide_index=True)

    st.subheader("Live Actors")
    actor_col, ped_col = st.columns(2)
    with actor_col:
        st.caption("Vehicles")
        st.dataframe(snapshot["vehicles"][:12], use_container_width=True, hide_index=True)
    with ped_col:
        st.caption("Pedestrians")
        st.dataframe(snapshot["pedestrians"][:12], use_container_width=True, hide_index=True)


def run_frame(engine: TrafficSimulationEngine) -> None:
    snapshot = advance_engine(engine)
    st.session_state["snapshot"] = snapshot
    render(snapshot)

engine = get_engine()
update_controls(engine)

if hasattr(st, "autorefresh"):
    st.autorefresh(interval=REFRESH_INTERVAL_MS, key="sim_loop")
    run_frame(engine)
else:
    @st.fragment(run_every=REFRESH_INTERVAL_MS / 1000)
    def live_fragment() -> None:
        run_frame(engine)

    live_fragment()
