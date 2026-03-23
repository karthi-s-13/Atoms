"""Lightweight wrapper around the simplified single intersection engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from shared.contracts import Point2D
from simulation_engine.engine import CompletedVehicleTransfer, TrafficSimulationEngine


@dataclass(frozen=True)
class IntersectionLayout:
    id: str
    label: str
    offset: Point2D


class Intersection:
    """Own one local engine plus lightweight network metadata."""

    def __init__(self, layout: IntersectionLayout) -> None:
        self.layout = layout
        self.engine = TrafficSimulationEngine()
        self.last_snapshot = self.engine.snapshot().to_dict()
        self.last_snapshot["intersection_id"] = self.layout.id
        self.last_network_context: Dict[str, Any] = {}
        self.congestion_level = 0.0
        self.outgoing_flow_rate = 0.0
        self.incoming_estimate = 0.0

    @property
    def id(self) -> str:
        return self.layout.id

    @property
    def label(self) -> str:
        return self.layout.label

    @property
    def offset(self) -> Point2D:
        return self.layout.offset

    @property
    def time(self) -> float:
        return self.engine.time

    @property
    def config(self):
        return self.engine.config

    def reset(self) -> None:
        self.engine.reset()
        self.last_network_context = {}
        self.congestion_level = 0.0
        self.outgoing_flow_rate = 0.0
        self.incoming_estimate = 0.0
        self.last_snapshot = self.engine.snapshot().to_dict()
        self.last_snapshot["intersection_id"] = self.layout.id

    def update_config(self, values: Dict[str, object]):
        return self.engine.update_config(values)

    def tick(self, dt: float, network_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        self.last_network_context = dict(network_context or {})
        self.engine.set_network_phase_context(self.last_network_context)
        snapshot = self.engine.tick(dt)
        snapshot["intersection_id"] = self.layout.id
        self.last_snapshot = snapshot
        self.congestion_level = self._congestion_level(snapshot)
        return snapshot

    def refresh_snapshot(self) -> Dict[str, Any]:
        snapshot = self.engine.snapshot().to_dict()
        snapshot["intersection_id"] = self.layout.id
        self.last_snapshot = snapshot
        self.congestion_level = self._congestion_level(snapshot)
        return snapshot

    def drain_completed_vehicle_transfers(self) -> List[CompletedVehicleTransfer]:
        return self.engine.drain_completed_vehicle_transfers()

    def inject_transfer_vehicle(self, **payload: Any) -> bool:
        accepted = self.engine.inject_transferred_vehicle(**payload)
        if accepted:
            self.refresh_snapshot()
        return accepted

    def summary(self) -> Dict[str, Any]:
        snapshot = self.last_snapshot
        metrics = snapshot.get("metrics", {})
        return {
            "id": self.layout.id,
            "label": self.layout.label,
            "offset": {"x": self.layout.offset.x, "y": self.layout.offset.y},
            "active_phase": snapshot.get("current_state", "NORTH"),
            "controller_phase": snapshot.get("controller_phase", "PHASE_GREEN"),
            "congestion_level": round(self.congestion_level, 3),
            "outgoing_flow_rate": round(self.outgoing_flow_rate, 3),
            "incoming_estimate": round(self.incoming_estimate, 3),
            "queued_vehicles": int(metrics.get("queued_vehicles", 0)),
            "vehicle_count": int(metrics.get("active_vehicles", 0)),
            "signals": dict(snapshot.get("signals", {})),
            "metrics": metrics,
            "traffic_brain": dict(snapshot.get("traffic_brain", {})),
        }

    def _congestion_level(self, snapshot: Dict[str, Any]) -> float:
        metrics = snapshot.get("metrics", {})
        queue_pressure = float(metrics.get("queue_pressure", 0.0))
        avg_wait_time = float(metrics.get("avg_wait_time", 0.0))
        alerts = len(snapshot.get("traffic_brain", {}).get("congestion_alerts", []))
        return min(1.0, (queue_pressure * 0.65) + min(avg_wait_time / 12.0, 0.25) + (alerts * 0.08))
