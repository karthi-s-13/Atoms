"""Production-oriented city traffic state, analytics, and map streaming."""

from __future__ import annotations

import asyncio
import copy
import heapq
import json
import math
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import HTTPException, WebSocket

DEFAULT_GREEN_WAVE_SPEED_KMPH = 32.0
MAP_ROUTE_LOCK_SECONDS_PER_JUNCTION = 15.0
MAP_ROUTE_MAX_LOCK_SECONDS = 90.0
HEARTBEAT_STALE_SECONDS = 20.0
HISTORY_LIMIT = 60
PREDICTION_LOOKBACK = 5
STREAM_INTERVAL_SECONDS = 1.0
NORMAL_SPEED_KMPH = 25.0
IMPROVED_SPEED_KMPH = 40.0
SIGNAL_DELAY_SECONDS = 120.0
TRAFFIC_DELAY_SECONDS = 90.0
MINIMAL_DELAY_SECONDS = 15.0
DEMO_MIN_TRAVEL_SECONDS = 18.0
DEMO_MAX_TRAVEL_SECONDS = 54.0
YELLOW_DURATION_SECONDS = 1.5
ALL_RED_BUFFER_SECONDS = 1.0
GREEN_MIN_SECONDS = 5.0

METRIC_ALPHA = {
    "density": 0.3,
    "queue_length": 0.5,
    "vehicle_count": 0.4,
    "flow_count": 0.35,
    "average_speed_kmph": 0.25,
}
SIGNIFICANT_CHANGE_THRESHOLD = {
    "density": 0.05,
    "queue_length": 2.0,
    "vehicle_count": 3.0,
    "flow_count": 2.0,
    "predicted_load": 3.0,
    "average_speed_kmph": 3.0,
    "confidence": 0.08,
    "status": 1.0,
    "signal": 1.0,
    "signal_locked": 1.0,
    "anomaly": 1.0,
    "incident": 1.0,
}
STATUS_RANK = {"stable": 0, "uncertain": 1, "degraded": 2}
SIGNAL_DIRECTIONS = ("N", "S", "E", "W")
SIGNAL_DIRECTION_ORDER = ("N", "S", "E", "W")
LONG_TO_SHORT_DIRECTION = {"north": "N", "south": "S", "east": "E", "west": "W"}
SHORT_TO_LONG_DIRECTION = {"N": "north", "S": "south", "E": "east", "W": "west"}
METRIC_BOUNDS = {
    "vehicle_count": (0.0, 180.0),
    "queue_length": (0.0, 120.0),
    "density": (0.0, 1.0),
    "flow_count": (0.0, 80.0),
    "average_speed_kmph": (0.0, 90.0),
    "predicted_load": (0.0, 180.0),
}
DEMO_JUNCTIONS = {
    "J1": {"id": "J1", "name": "Central Station", "lat": 13.0827, "lng": 80.2707, "neighbors": ["J2", "J3"]},
    "J2": {"id": "J2", "name": "Harbor North", "lat": 13.0674, "lng": 80.2376, "neighbors": ["J1", "J3", "J4"]},
    "J3": {"id": "J3", "name": "South Market", "lat": 13.0569, "lng": 80.2425, "neighbors": ["J1", "J2", "J4", "J5"]},
    "J4": {"id": "J4", "name": "IT Corridor", "lat": 13.0455, "lng": 80.2341, "neighbors": ["J2", "J3", "J5"]},
    "J5": {"id": "J5", "name": "Medical Link", "lat": 13.0392, "lng": 80.2298, "neighbors": ["J3", "J4"]},
}
DEMO_HOSPITALS = [
    {"id": "H1", "name": "Apollo Specialty Center", "lat": 13.0368, "lng": 80.2258},
    {"id": "H2", "name": "MIOT Care Annex", "lat": 13.0311, "lng": 80.2142},
    {"id": "H3", "name": "City Medical Center", "lat": 13.0424, "lng": 80.2318},
    {"id": "H4", "name": "Riverside General", "lat": 13.0488, "lng": 80.2192},
]
DEMO_START_POINTS = [
    {
        "id": "S1",
        "name": "North Wharf Standby",
        "lat": 13.0898,
        "lng": 80.2790,
        "nearby_junctions": ["J1", "J2"],
        "activation_junction_id": "J1",
        "pre_detection_junctions": ["J1", "J2"],
        "emergency_route_nodes": ["J1", "J2", "J3", "J4"],
        "hospital_id": "H4",
        "dispatch_note": "J1 handles first detection, then the corridor rolls south through J2, J3, and J4.",
    },
    {
        "id": "S2",
        "name": "Civic Rescue Bay",
        "lat": 13.0708,
        "lng": 80.2448,
        "nearby_junctions": ["J2", "J3"],
        "activation_junction_id": "J2",
        "pre_detection_junctions": ["J2", "J3"],
        "emergency_route_nodes": ["J2", "J3", "J4", "J5"],
        "hospital_id": "H1",
        "dispatch_note": "The approach arms J2 first, then hands the green corridor through J3, J4, and J5.",
    },
    {
        "id": "S3",
        "name": "Metro Command Point",
        "lat": 13.0608,
        "lng": 80.2446,
        "nearby_junctions": ["J3", "J2"],
        "activation_junction_id": "J3",
        "pre_detection_junctions": ["J3", "J2"],
        "emergency_route_nodes": ["J3", "J2", "J4", "J5"],
        "hospital_id": "H2",
        "dispatch_note": "J3 opens the route from the command point, then J2, J4, and J5 sequence naturally toward the medical zone.",
    },
    {
        "id": "S4",
        "name": "Riverfront Dispatch",
        "lat": 13.0762,
        "lng": 80.2669,
        "nearby_junctions": ["J1", "J3"],
        "activation_junction_id": "J1",
        "pre_detection_junctions": ["J1", "J3"],
        "emergency_route_nodes": ["J1", "J3", "J4", "J5"],
        "hospital_id": "H3",
        "dispatch_note": "This riverfront preset cuts directly through J1, J3, J4, and J5 for a tighter emergency corridor.",
    },
]
DEFAULT_DEMO_START_POINT = DEMO_START_POINTS[0]
DEMO_TRIGGER_DISTANCE_METERS = 10.0
DEMO_APPROACH_JUNCTION_ID = str(DEFAULT_DEMO_START_POINT["activation_junction_id"])
DEMO_PRE_DETECTION_JUNCTIONS = tuple(DEFAULT_DEMO_START_POINT["pre_detection_junctions"])
DEMO_EMERGENCY_ROUTE_NODES = tuple(DEFAULT_DEMO_START_POINT["emergency_route_nodes"])
DEMO_APPROACH_SPEED_KMPH = 28.0
DEMO_ROUTE_SPEED_KMPH = 42.0
DEMO_APPROACH_SECONDS_RANGE = (10.0, 18.0)
DEMO_EMERGENCY_SECONDS_RANGE = (24.0, 42.0)
EMERGENCY_ALERT_LIMIT = 8


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _sanitize_metric(metric: str, value: Any, *, default: float = 0.0) -> float:
    fallback = float(default) if math.isfinite(float(default)) else 0.0
    numeric = _coerce_float(value, default=fallback)
    if not math.isfinite(numeric):
        numeric = fallback
    lower, upper = METRIC_BOUNDS.get(metric, (-1_000_000_000.0, 1_000_000_000.0))
    return _clip(numeric, lower, upper)


def _finite_series(values: list[float]) -> list[float]:
    finite: list[float] = []
    for value in values:
        numeric = _coerce_float(value, default=0.0)
        if math.isfinite(numeric):
            finite.append(float(numeric))
    return finite


def _haversine_distance_m(lat_a: float, lng_a: float, lat_b: float, lng_b: float) -> float:
    radius_m = 6_371_000.0
    lat1 = math.radians(lat_a)
    lat2 = math.radians(lat_b)
    delta_lat = math.radians(lat_b - lat_a)
    delta_lng = math.radians(lng_b - lng_a)
    chord = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * (math.sin(delta_lng / 2.0) ** 2)
    )
    return 2.0 * radius_m * math.atan2(math.sqrt(chord), math.sqrt(max(1e-12, 1.0 - chord)))


def _direction_between(source: dict[str, Any], target: dict[str, Any]) -> str:
    lat_delta = float(target["lat"]) - float(source["lat"])
    lng_delta = float(target["lng"]) - float(source["lng"])
    if abs(lat_delta) >= abs(lng_delta):
        return "north" if lat_delta >= 0 else "south"
    return "east" if lng_delta >= 0 else "west"


class JunctionRegistry:
    """Load, validate, and mutate the multi-city junction registry."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._junctions: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not self.config_path.exists():
            raise RuntimeError(f"Missing junction registry config: {self.config_path}")
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        items = payload.get("junctions", []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            raise RuntimeError("Junction registry config is invalid.")
        self._junctions = {}
        for item in items:
            normalized = self.validate_junction(item)
            self._junctions[normalized["junction_id"]] = normalized

    def _save(self) -> None:
        payload = {"junctions": list(self._junctions.values())}
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._junctions)

    def ids(self) -> list[str]:
        return sorted(self._junctions)

    def get(self, junction_id: str) -> dict[str, Any]:
        junction = self._junctions.get(junction_id)
        if not junction:
            raise HTTPException(status_code=404, detail=f"Unknown junction: {junction_id}")
        return copy.deepcopy(junction)

    def validate_junction(self, payload: dict[str, Any]) -> dict[str, Any]:
        junction_id = str(payload.get("junction_id", "")).strip()
        if not junction_id:
            raise HTTPException(status_code=400, detail="junction_id is required.")
        lat = _coerce_float(payload.get("lat"))
        lng = _coerce_float(payload.get("lng"))
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            raise HTTPException(status_code=400, detail=f"Invalid coordinates for junction {junction_id}.")
        status = str(payload.get("status", "active")).strip().lower()
        if status not in {"active", "inactive"}:
            raise HTTPException(status_code=400, detail="status must be 'active' or 'inactive'.")
        camera_id = str(payload.get("camera_id", "")).strip()
        if not camera_id:
            raise HTTPException(status_code=400, detail=f"camera_id is required for junction {junction_id}.")
        base_metrics = payload.get("base_metrics", {}) if isinstance(payload.get("base_metrics"), dict) else {}
        return {
            "junction_id": junction_id,
            "name": str(payload.get("name") or junction_id),
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "camera_id": camera_id,
            "region": str(payload.get("region", "default")).strip() or "default",
            "status": status,
            "neighbors": [str(item).strip() for item in payload.get("neighbors", []) if str(item).strip()],
            "base_metrics": {
                "vehicle_count": max(_coerce_int(base_metrics.get("vehicle_count")), 0),
                "queue": max(_coerce_int(base_metrics.get("queue")), 0),
                "density": _clip(_coerce_float(base_metrics.get("density")), 0.0, 1.0),
                "flow_count": max(_coerce_int(base_metrics.get("flow_count")), 0),
                "accident": bool(base_metrics.get("accident", False)),
                "average_speed_kmph": max(_coerce_float(base_metrics.get("average_speed_kmph"), default=24.0), 0.0),
            },
        }

    def upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self.validate_junction(payload)
        self._junctions[normalized["junction_id"]] = normalized
        self._save()
        return copy.deepcopy(normalized)

    def remove(self, junction_id: str) -> None:
        if junction_id not in self._junctions:
            raise HTTPException(status_code=404, detail=f"Unknown junction: {junction_id}")
        del self._junctions[junction_id]
        self._save()


class TrafficPlatformService:
    """Central state store for visibility, intelligence, and control layers."""

    def __init__(self, config_path: Path) -> None:
        self.registry = JunctionRegistry(config_path)
        self.state: dict[str, dict[str, Any]] = {}
        self.signal_states: dict[str, dict[str, Any]] = {}
        self.history: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self.camera_health: dict[str, dict[str, Any]] = {}
        self.incident_memory: dict[str, dict[str, Any]] = {}
        self.emergency_state: dict[str, Any] = self._empty_emergency_state()
        for junction_id in self.registry.ids():
            self._ensure_junction_state(junction_id)

    def _empty_emergency_state(self) -> dict[str, Any]:
        return {
            "active": False,
            "completed": False,
            "mode": "idle",
            "stage": "idle",
            "emergency_active": False,
            "route": [],
            "route_nodes": [],
            "display_route": [],
            "current_junction": None,
            "current_index": 0,
            "next_target": None,
            "distance_to_next_m": 0.0,
            "eta_to_next_sec": 0.0,
            "active_signal_direction": None,
            "source": None,
            "starting_point": None,
            "destination": None,
            "hospital": None,
            "ambulance_position": None,
            "normal_eta_min": 0.0,
            "optimized_eta_min": 0.0,
            "time_saved_min": 0.0,
            "time_saved_percent": 0.0,
            "route_distance_km": 0.0,
            "remaining_eta_sec": 0.0,
            "demo_duration_sec": 0.0,
            "start_time": 0.0,
            "expires_at": 0.0,
            "lock_duration_sec": 0.0,
            "speed_multiplier": 1.0,
            "max_lock_time_sec": MAP_ROUTE_MAX_LOCK_SECONDS,
            "activation_junction_id": DEMO_APPROACH_JUNCTION_ID,
            "approach_route_coords": [],
            "approach_path_coords": [],
            "approach_duration_sec": 0.0,
            "approach_started_at": 0.0,
            "approach_elapsed_offset_sec": 0.0,
            "emergency_route_coords": [],
            "emergency_path_coords": [],
            "emergency_started_at": 0.0,
            "emergency_duration_sec": 0.0,
            "emergency_elapsed_offset_sec": 0.0,
            "full_route_coords": [],
            "full_path_coords": [],
            "pre_detection_junctions": list(DEMO_PRE_DETECTION_JUNCTIONS),
            "planned_route_nodes": list(DEMO_EMERGENCY_ROUTE_NODES),
            "alerts": [],
            "last_progress_index": -1,
            "detection_triggered_at": 0.0,
        }

    def _ensure_junction_state(self, junction_id: str) -> None:
        if junction_id in self.state:
            return
        now = time.time()
        self.state[junction_id] = {
            "metrics": {},
            "prediction": {},
            "signal": {"signal": "RED", "signal_locked": False},
            "status": "stable",
            "confidence": 1.0,
            "last_snapshot": None,
            "updated_at": 0.0,
        }
        self.camera_health[junction_id] = {
            "healthy": True,
            "last_seen_at": time.time(),
            "failure_count": 0,
        }
        self.incident_memory[junction_id] = {
            "active_frames": 0,
            "last_confirmed_at": 0.0,
        }
        self.signal_states[junction_id] = {
            "active_direction": "N",
            "phase": "GREEN",
            "signals": {"N": "GREEN", "S": "RED", "E": "RED", "W": "RED"},
            "pending_direction": None,
            "phase_started_at": now,
            "green_started_at": now,
            "alert": "Normal cycle on N",
            "reason": "Normal traffic progression.",
            "emergency_hold": False,
        }

    def upsert_junction(self, payload: dict[str, Any]) -> dict[str, Any]:
        junction = self.registry.upsert(payload)
        self._ensure_junction_state(junction["junction_id"])
        return junction

    def remove_junction(self, junction_id: str) -> None:
        self.registry.remove(junction_id)
        self.state.pop(junction_id, None)
        self.signal_states.pop(junction_id, None)
        self.history.pop(junction_id, None)
        self.camera_health.pop(junction_id, None)
        self.incident_memory.pop(junction_id, None)

    def touch_camera_heartbeat(self, junction_id: str) -> dict[str, Any]:
        self.registry.get(junction_id)
        health = self.camera_health.setdefault(
            junction_id,
            {"healthy": True, "last_seen_at": time.time(), "failure_count": 0},
        )
        health["healthy"] = True
        health["last_seen_at"] = time.time()
        return {"junction_id": junction_id, "healthy": True, "last_seen_at": round(health["last_seen_at"], 6)}

    def list_registry(self) -> list[dict[str, Any]]:
        return list(self.registry.list().values())

    def _append_history(self, junction_id: str, metric: str, value: float) -> list[float]:
        series = self.history[junction_id][metric]
        fallback = series[-1] if series else 0.0
        series.append(_sanitize_metric(metric, value, default=fallback))
        if len(series) > HISTORY_LIMIT:
            del series[:-HISTORY_LIMIT]
        return series

    def _moving_average(self, values: list[float]) -> float:
        window = _finite_series(values[-PREDICTION_LOOKBACK:])
        if not window:
            return 0.0
        return float(sum(window)) / float(max(len(window), 1))

    def _trend_prediction(self, values: list[float]) -> float:
        series = _finite_series(values)
        if len(series) < 3:
            return float(series[-1]) if series else 0.0
        x_mean = (len(series) - 1) / 2.0
        y_mean = float(sum(series)) / float(len(series))
        numerator = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(series))
        denominator = sum((index - x_mean) ** 2 for index in range(len(series)))
        if denominator <= 1e-9:
            return float(series[-1])
        slope = numerator / denominator
        projected = y_mean + (slope * (len(series) - x_mean))
        return float(projected) if math.isfinite(projected) else float(series[-1])

    def _recent_delta(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        return float(values[-1] - values[-2])

    def _health_status(self, junction: dict[str, Any]) -> tuple[bool, str]:
        health = self.camera_health.setdefault(
            junction["junction_id"],
            {"healthy": True, "last_seen_at": time.time(), "failure_count": 0},
        )
        if junction["status"] != "active":
            return False, "degraded"
        if time.time() - float(health["last_seen_at"]) > HEARTBEAT_STALE_SECONDS:
            health["healthy"] = False
            health["failure_count"] += 1
            return False, "degraded"
        return True, "stable"

    def _simulated_metrics(self, junction: dict[str, Any]) -> dict[str, float]:
        base = junction["base_metrics"]
        tick = time.time() / 8.0
        phase = (sum(ord(char) for char in junction["junction_id"]) % 13) / 5.0
        vehicle_count = max(base["vehicle_count"] + round(math.sin(tick + phase) * 6), 0)
        queue_length = max(base["queue"] + round(math.cos((tick * 1.4) + phase) * 4), 0)
        density = _clip(base["density"] + (math.sin((tick * 0.85) + phase) * 0.12), 0.02, 0.98)
        flow_count = max(base["flow_count"] + round(math.sin((tick * 1.2) + phase) * 3), 0)
        speed_drop = density * 12.0 + (queue_length / max(vehicle_count, 1)) * 10.0
        average_speed_kmph = max(base["average_speed_kmph"] - speed_drop + (math.cos(tick + phase) * 3.0), 4.0)
        return {
            "vehicle_count": float(vehicle_count),
            "queue_length": float(queue_length),
            "density": float(density),
            "flow_count": float(flow_count),
            "average_speed_kmph": float(average_speed_kmph),
        }

    def _neighbor_average(self, junction_id: str, metric: str, junction_map: dict[str, dict[str, Any]]) -> float:
        neighbors = junction_map[junction_id].get("neighbors", [])
        values: list[float] = []
        for neighbor_id in neighbors:
            neighbor_state = self.state.get(neighbor_id, {})
            metrics = neighbor_state.get("metrics", {})
            if metric in metrics:
                values.append(float(metrics[metric]))
        return float(sum(values)) / float(len(values)) if values else 0.0

    def _smooth_metric(self, junction_id: str, metric: str, current: float, junction_map: dict[str, dict[str, Any]]) -> float:
        previous = _sanitize_metric(metric, self.state[junction_id]["metrics"].get(metric), default=current)
        current_value = _sanitize_metric(metric, current, default=previous)
        alpha = METRIC_ALPHA.get(metric, 0.3)
        temporal = ((1.0 - alpha) * previous) + (alpha * current_value)
        neighbor_avg = self._neighbor_average(junction_id, metric, junction_map)
        if neighbor_avg > 0.0:
            neighbor_weight = 0.12 if metric == "density" else 0.18
            temporal = ((1.0 - neighbor_weight) * temporal) + (
                neighbor_weight * _sanitize_metric(metric, neighbor_avg, default=current_value)
            )
        if metric == "density":
            return round(_sanitize_metric(metric, temporal, default=current_value), 3)
        return round(_sanitize_metric(metric, temporal, default=current_value), 2)

    def _metric_confidence(self, raw: dict[str, float], smoothed: dict[str, float], healthy: bool) -> dict[str, float]:
        confidence_floor = 0.58 if healthy else 0.28
        confidence_cap = 0.98 if healthy else 0.62
        confidence: dict[str, float] = {}
        for metric, value in smoothed.items():
            raw_value = _coerce_float(raw.get(metric), default=value)
            variance = abs(raw_value - value)
            normalized_variance = min(variance / max(abs(value), 1.0), 1.0)
            score = confidence_cap - (normalized_variance * 0.35)
            confidence[metric] = round(_clip(score, confidence_floor, confidence_cap), 3)
        return confidence

    def _derive_overall_status(self, confidence: float, health_status: str) -> str:
        if health_status == "degraded":
            return "degraded"
        if confidence < 0.68:
            return "uncertain"
        return "stable"

    def _incident_state(
        self,
        junction_id: str,
        metrics: dict[str, float],
        confidence: dict[str, float],
        base_accident: bool,
    ) -> dict[str, Any]:
        memory = self.incident_memory[junction_id]
        speed_drop = max(0.0, 35.0 - float(metrics["average_speed_kmph"]))
        incident_candidate = base_accident or (
            float(metrics["queue_length"]) >= 14.0
            and float(metrics["density"]) >= 0.72
            and speed_drop >= 10.0
        )
        if incident_candidate:
            memory["active_frames"] += 1
        else:
            memory["active_frames"] = max(memory["active_frames"] - 1, 0)
        confirmed = memory["active_frames"] >= 3 and float(confidence["density"]) >= 0.6
        if confirmed:
            memory["last_confirmed_at"] = time.time()
        severity = min(
            1.0,
            (float(metrics["queue_length"]) / 24.0) * 0.45
            + (speed_drop / 30.0) * 0.3
            + float(metrics["density"]) * 0.25,
        )
        return {
            "active": confirmed,
            "detected_for": int(memory["active_frames"]),
            "confidence": round(float(confidence["density"]), 3),
            "severity": round(severity, 3),
        }

    def _prediction(self, junction_id: str, metrics: dict[str, float], confidence: dict[str, float]) -> dict[str, Any]:
        vehicle_history = self._append_history(junction_id, "vehicle_count", metrics["vehicle_count"])
        trend = _sanitize_metric("vehicle_count", self._trend_prediction(vehicle_history), default=vehicle_history[-1])
        moving_avg = _sanitize_metric("vehicle_count", self._moving_average(vehicle_history), default=vehicle_history[-1])
        recent_delta = self._recent_delta(vehicle_history)
        if not math.isfinite(recent_delta):
            recent_delta = 0.0
        predicted = _sanitize_metric(
            "predicted_load",
            (0.45 * trend) + (0.35 * moving_avg) + (0.20 * (vehicle_history[-1] + recent_delta)),
            default=moving_avg,
        )
        previous_prediction = _sanitize_metric(
            "predicted_load",
            self.state[junction_id]["prediction"].get("predicted_load"),
            default=predicted,
        )
        smoothed_prediction = _sanitize_metric(
            "predicted_load",
            (0.7 * previous_prediction) + (0.3 * predicted),
            default=predicted,
        )
        max_prediction = min(
            max(max(vehicle_history) * 1.35, float(metrics["vehicle_count"]) * 1.25, 20.0),
            METRIC_BOUNDS["predicted_load"][1],
        )
        clipped = round(_clip(smoothed_prediction, 0.0, max_prediction), 2)
        pred_confidence = round(
            _clip(
                (confidence["vehicle_count"] * 0.45)
                + (confidence["density"] * 0.35)
                + (confidence["flow_count"] * 0.20),
                0.25,
                0.98,
            ),
            3,
        )
        return {
            "trend": round(trend, 2),
            "moving_avg": round(moving_avg, 2),
            "recent_delta": round(recent_delta, 2),
            "predicted_load": clipped,
            "confidence": pred_confidence,
        }

    def _anomaly_state(self, junction_id: str, metrics: dict[str, float]) -> dict[str, Any]:
        queue_history = self._append_history(junction_id, "queue_length", metrics["queue_length"])
        speed_history = self._append_history(junction_id, "average_speed_kmph", metrics["average_speed_kmph"])
        rolling_queue_mean = self._moving_average(queue_history[-10:]) if queue_history else 0.0
        rolling_speed_mean = self._moving_average(speed_history[-10:]) if speed_history else 0.0
        queue_spike = rolling_queue_mean > 0 and metrics["queue_length"] > (1.8 * rolling_queue_mean)
        speed_drop = rolling_speed_mean > 0 and metrics["average_speed_kmph"] < (0.65 * rolling_speed_mean)
        score = 0.0
        if rolling_queue_mean > 0:
            score += min(metrics["queue_length"] / rolling_queue_mean, 3.0) * 0.35
        if rolling_speed_mean > 0:
            score += min(rolling_speed_mean / max(metrics["average_speed_kmph"], 1.0), 3.0) * 0.25
        score += metrics["density"] * 0.25
        score += min(metrics["flow_count"] / max(metrics["vehicle_count"], 1.0), 1.0) * 0.15
        return {
            "active": bool(queue_spike or speed_drop),
            "score": round(min(score / 2.2, 1.0), 3),
            "rolling_mean": round(rolling_queue_mean, 2),
        }

    def _next_cycle_direction(self, current_direction: str | None) -> str:
        current = current_direction if current_direction in SIGNAL_DIRECTION_ORDER else SIGNAL_DIRECTION_ORDER[0]
        index = SIGNAL_DIRECTION_ORDER.index(current)
        return SIGNAL_DIRECTION_ORDER[(index + 1) % len(SIGNAL_DIRECTION_ORDER)]

    def _approach_direction(self, ambulance_position: dict[str, Any] | None, junction: dict[str, Any]) -> str:
        if not ambulance_position:
            return "N"
        lat_delta = float(ambulance_position["lat"]) - float(junction["lat"])
        lng_delta = float(ambulance_position["lng"]) - float(junction["lng"])
        if abs(lat_delta) >= abs(lng_delta):
            return "S" if lat_delta < 0 else "N"
        return "W" if lng_delta < 0 else "E"

    def _eta_to_junction_seconds(self, emergency_state: dict[str, Any], junction_id: str) -> float | None:
        route_nodes = list(emergency_state.get("route_nodes") or [])
        if junction_id not in route_nodes:
            return None
        if not emergency_state.get("active") or emergency_state.get("completed"):
            return None
        current_index = int(emergency_state.get("current_index") or 0)
        target_index = route_nodes.index(junction_id)
        remaining_route = max(len(route_nodes) - current_index, 1)
        seconds_per_hop = float(emergency_state.get("remaining_eta_sec") or 0.0) / remaining_route
        return max((target_index - current_index) * seconds_per_hop, 0.0)

    def _advance_signal_state(self, junction_id: str, now: float) -> None:
        state = self.signal_states[junction_id]
        while True:
            elapsed = now - float(state["phase_started_at"])
            if state["phase"] == "YELLOW" and elapsed >= YELLOW_DURATION_SECONDS:
                state["phase"] = "RED"
                state["signals"] = {direction: "RED" for direction in SIGNAL_DIRECTIONS}
                state["phase_started_at"] = float(state["phase_started_at"]) + YELLOW_DURATION_SECONDS
                continue
            if state["phase"] == "RED" and state.get("pending_direction") and elapsed >= ALL_RED_BUFFER_SECONDS:
                target = state["pending_direction"]
                state["phase"] = "GREEN"
                state["active_direction"] = target
                state["signals"] = {direction: ("GREEN" if direction == target else "RED") for direction in SIGNAL_DIRECTIONS}
                state["pending_direction"] = None
                state["phase_started_at"] = float(state["phase_started_at"]) + ALL_RED_BUFFER_SECONDS
                state["green_started_at"] = state["phase_started_at"]
                continue
            break

    def _begin_transition(self, junction_id: str, target_direction: str, *, alert: str, reason: str, now: float) -> None:
        state = self.signal_states[junction_id]
        current_direction = state["active_direction"] if state["active_direction"] in SIGNAL_DIRECTIONS else "N"
        state["pending_direction"] = target_direction
        state["phase"] = "YELLOW"
        state["signals"] = {direction: ("YELLOW" if direction == current_direction else "RED") for direction in SIGNAL_DIRECTIONS}
        state["phase_started_at"] = now
        state["alert"] = alert
        state["reason"] = reason

    def _update_signal_controller(
        self,
        junction_id: str,
        junction: dict[str, Any],
        emergency_state: dict[str, Any],
        *,
        target_direction: str,
        forced_green: bool,
        now: float,
    ) -> dict[str, Any]:
        state = self.signal_states[junction_id]
        self._advance_signal_state(junction_id, now)
        state = self.signal_states[junction_id]
        eta_to_junction = self._eta_to_junction_seconds(emergency_state, junction_id)
        emergency_active = bool(forced_green) and eta_to_junction is not None and eta_to_junction < 5.0

        if emergency_active:
            if state["phase"] == "GREEN" and state["active_direction"] == target_direction:
                state["alert"] = f"Junction {junction_id} already GREEN for ambulance approach."
                state["reason"] = "Ambulance is approaching and the required movement is already green."
            elif state["phase"] == "GREEN" and state["active_direction"] != target_direction:
                self._begin_transition(
                    junction_id,
                    target_direction,
                    alert=f"{junction_id} preparing signal for ambulance in {eta_to_junction:.1f}s.",
                    reason="Emergency preemption requested. Current green is moving through yellow before safe handoff.",
                    now=now,
                )
                self._advance_signal_state(junction_id, now)
                state = self.signal_states[junction_id]
            elif state["phase"] == "RED" and state.get("pending_direction") == target_direction:
                state["alert"] = f"{junction_id} all-red safety buffer active before emergency green."
                state["reason"] = "Emergency transition is in the all-red clearance window."
            state["emergency_hold"] = True
        else:
            state["emergency_hold"] = False
            if state["phase"] == "GREEN" and (now - float(state["green_started_at"])) >= GREEN_MIN_SECONDS:
                next_direction = self._next_cycle_direction(state["active_direction"])
                self._begin_transition(
                    junction_id,
                    next_direction,
                    alert=f"{junction_id} normal cycle: {state['active_direction']} to {next_direction}.",
                    reason="Minimum green time elapsed, continuing the normal 4-way cycle.",
                    now=now,
                )
                self._advance_signal_state(junction_id, now)
                state = self.signal_states[junction_id]
            elif state["phase"] == "GREEN":
                state["alert"] = f"{junction_id} holding {state['active_direction']} green."
                state["reason"] = "Normal traffic cycle is serving the current movement."

        ambulance_direction = self._approach_direction(emergency_state.get("ambulance_position"), junction)
        return {
            "signals": dict(state["signals"]),
            "active_direction": state["active_direction"],
            "phase": state["phase"],
            "pending_direction": state.get("pending_direction"),
            "alert": state["alert"],
            "reason": state["reason"],
            "eta_to_junction_sec": round(float(eta_to_junction), 1) if eta_to_junction is not None else None,
            "ambulance_direction": ambulance_direction,
        }

    def _nearest_junction_id(self, point: tuple[float, float]) -> str:
        lat, lng = float(point[0]), float(point[1])
        junctions = self.registry.list()
        return min(
            junctions,
            key=lambda junction_id: _haversine_distance_m(
                lat,
                lng,
                float(junctions[junction_id]["lat"]),
                float(junctions[junction_id]["lng"]),
            ),
        )

    def _shortest_path(self, start_id: str, end_id: str) -> list[str]:
        junctions = self.registry.list()
        queue: list[tuple[float, str, list[str]]] = [(0.0, start_id, [start_id])]
        visited: dict[str, float] = {}
        while queue:
            cost, current_id, path = heapq.heappop(queue)
            if current_id == end_id:
                return path
            if current_id in visited and visited[current_id] <= cost:
                continue
            visited[current_id] = cost
            current = junctions[current_id]
            for neighbor_id in current.get("neighbors", []):
                if neighbor_id not in junctions or neighbor_id in path:
                    continue
                neighbor = junctions[neighbor_id]
                edge_cost = _haversine_distance_m(
                    float(current["lat"]),
                    float(current["lng"]),
                    float(neighbor["lat"]),
                    float(neighbor["lng"]),
                )
                heapq.heappush(queue, (cost + edge_cost, neighbor_id, [*path, neighbor_id]))
        raise HTTPException(status_code=404, detail="No route could be computed across the configured junction graph.")

    def get_demo_config(self) -> dict[str, Any]:
        demo_junctions = []
        junction_map = self.registry.list()
        for junction_id in DEMO_JUNCTIONS:
            if junction_id in junction_map:
                junction = junction_map[junction_id]
                demo_junctions.append(
                    {
                        "id": junction["junction_id"],
                        "name": junction["name"],
                        "lat": float(junction["lat"]),
                        "lng": float(junction["lng"]),
                        "neighbors": list(junction.get("neighbors", [])),
                    }
                )
        default_profile = self._demo_route_profile()
        return {
            "junctions": demo_junctions,
            "starting_points": [dict(item) for item in DEMO_START_POINTS],
            "hospitals": [dict(item) for item in DEMO_HOSPITALS],
            "activation_junction_id": default_profile["activation_junction_id"],
            "pre_detection_junctions": list(default_profile["pre_detection_junctions"]),
            "emergency_route_nodes": list(default_profile["emergency_route_nodes"]),
        }

    def _demo_start_point(self, start_point_id: str) -> dict[str, Any]:
        start_point = next((item for item in DEMO_START_POINTS if item["id"] == start_point_id), None)
        if not start_point:
            raise HTTPException(status_code=404, detail=f"Unknown demo starting point: {start_point_id}")
        return dict(start_point)

    def _default_demo_start_point(self) -> dict[str, Any]:
        return dict(DEFAULT_DEMO_START_POINT)

    def _demo_route_profile(self, start_point: dict[str, Any] | None = None) -> dict[str, Any]:
        selected_start = dict(start_point) if start_point else self._default_demo_start_point()
        activation_junction_id = str(selected_start.get("activation_junction_id") or DEMO_APPROACH_JUNCTION_ID)
        route_nodes = [str(node_id) for node_id in selected_start.get("emergency_route_nodes") or DEMO_EMERGENCY_ROUTE_NODES]
        ordered_route_nodes = [activation_junction_id, *[node_id for node_id in route_nodes if node_id != activation_junction_id]]
        pre_detection = [str(node_id) for node_id in selected_start.get("pre_detection_junctions") or [activation_junction_id]]
        hospital_id = selected_start.get("hospital_id")
        hospital = next((dict(item) for item in DEMO_HOSPITALS if item["id"] == hospital_id), None) if hospital_id else None
        if not hospital:
            terminal_junction = self._demo_junction(ordered_route_nodes[-1] if ordered_route_nodes else activation_junction_id)
            hospital = dict(self._find_nearest_hospital(terminal_junction["lat"], terminal_junction["lng"]))
        return {
            "start_point": selected_start,
            "activation_junction_id": activation_junction_id,
            "pre_detection_junctions": pre_detection,
            "emergency_route_nodes": ordered_route_nodes,
            "hospital": hospital,
        }

    def _demo_junction(self, junction_id: str) -> dict[str, Any]:
        junction = self.registry.list().get(junction_id)
        if not junction:
            raise HTTPException(status_code=404, detail=f"Unknown demo junction: {junction_id}")
        return {
            "id": junction["junction_id"],
            "name": junction["name"],
            "lat": float(junction["lat"]),
            "lng": float(junction["lng"]),
            "neighbors": list(junction.get("neighbors", [])),
        }

    def _find_nearest_hospital(self, lat: float, lng: float) -> dict[str, Any]:
        return min(
            DEMO_HOSPITALS,
            key=lambda hospital: _haversine_distance_m(lat, lng, hospital["lat"], hospital["lng"]),
        )

    def _coord_record(self, *, identifier: str, name: str, lat: float, lng: float, kind: str) -> dict[str, Any]:
        return {
            "id": identifier,
            "name": name,
            "lat": round(float(lat), 6),
            "lng": round(float(lng), 6),
            "kind": kind,
        }

    def _route_nodes_to_coords(self, route_nodes: list[str], *, hospital: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        coords = []
        for node_id in route_nodes:
            junction = self._demo_junction(node_id)
            coords.append(
                self._coord_record(
                    identifier=junction["id"],
                    name=junction["name"],
                    lat=junction["lat"],
                    lng=junction["lng"],
                    kind="junction",
                )
            )
        if hospital:
            coords.append(
                self._coord_record(
                    identifier=str(hospital["id"]),
                    name=str(hospital["name"]),
                    lat=float(hospital["lat"]),
                    lng=float(hospital["lng"]),
                    kind="hospital",
                )
            )
        return coords

    def _route_distance_coords(self, coords: list[dict[str, Any]]) -> float:
        distance_m = 0.0
        for left, right in zip(coords, coords[1:]):
            distance_m += _haversine_distance_m(float(left["lat"]), float(left["lng"]), float(right["lat"]), float(right["lng"]))
        return round(distance_m / 1000.0, 3)

    def _distance_coords_m(self, coords: list[dict[str, Any]]) -> float:
        distance_m = 0.0
        for left, right in zip(coords, coords[1:]):
            distance_m += _haversine_distance_m(float(left["lat"]), float(left["lng"]), float(right["lat"]), float(right["lng"]))
        return round(distance_m, 2)

    def _estimate_demo_duration_seconds(self, distance_m: float, speed_kmph: float, minimum: float, maximum: float) -> float:
        if speed_kmph <= 0:
            return minimum
        travel_seconds = distance_m / max((speed_kmph * 1000.0) / 3600.0, 0.1)
        return round(_clip(travel_seconds / 5.0, minimum, maximum), 1)

    def _interpolate_position(self, coords: list[dict[str, Any]], progress: float) -> dict[str, float] | None:
        if not coords:
            return None
        if len(coords) == 1:
            return {"lat": round(float(coords[0]["lat"]), 6), "lng": round(float(coords[0]["lng"]), 6)}
        total_segments = len(coords) - 1
        scaled = _clip(progress, 0.0, 1.0) * total_segments
        index = min(int(math.floor(scaled)), total_segments - 1)
        local = scaled - index
        start = coords[index]
        end = coords[index + 1]
        return {
            "lat": round(float(start["lat"]) + ((float(end["lat"]) - float(start["lat"])) * local), 6),
            "lng": round(float(start["lng"]) + ((float(end["lng"]) - float(start["lng"])) * local), 6),
        }

    def _append_emergency_alert(self, message: str, *, stage: str) -> None:
        alerts = list(self.emergency_state.get("alerts") or [])
        alerts.append({"message": message, "stage": stage, "timestamp": round(time.time(), 3)})
        self.emergency_state["alerts"] = alerts[-EMERGENCY_ALERT_LIMIT:]

    def _speed_multiplier(self) -> float:
        return _clip(_coerce_float(self.emergency_state.get("speed_multiplier"), default=1.0), 0.5, 2.5)

    def _scaled_stage_elapsed(self, stage: str, now: float) -> float:
        speed_multiplier = self._speed_multiplier()
        if stage == "approach":
            started_at = float(self.emergency_state.get("approach_started_at") or self.emergency_state.get("start_time") or now)
            offset = max(float(self.emergency_state.get("approach_elapsed_offset_sec") or 0.0), 0.0)
            return max(offset + ((now - started_at) * speed_multiplier), 0.0)
        if stage == "emergency":
            started_at = float(self.emergency_state.get("emergency_started_at") or now)
            offset = max(float(self.emergency_state.get("emergency_elapsed_offset_sec") or 0.0), 0.0)
            return max(offset + ((now - started_at) * speed_multiplier), 0.0)
        return 0.0

    def start_emergency_demo(self, start_point_id: str) -> dict[str, Any]:
        start_point = self._demo_start_point(start_point_id)
        route_profile = self._demo_route_profile(start_point)
        activation_junction = self._demo_junction(str(route_profile["activation_junction_id"]))
        hospital = dict(route_profile["hospital"])
        approach_route_coords = [
            self._coord_record(
                identifier=start_point["id"],
                name=start_point["name"],
                lat=float(start_point["lat"]),
                lng=float(start_point["lng"]),
                kind="start",
            ),
            self._coord_record(
                identifier=activation_junction["id"],
                name=activation_junction["name"],
                lat=float(activation_junction["lat"]),
                lng=float(activation_junction["lng"]),
                kind="junction",
            ),
        ]
        emergency_route_nodes = list(route_profile["emergency_route_nodes"])
        emergency_route_coords = self._route_nodes_to_coords(emergency_route_nodes, hospital=hospital)
        full_route_coords = [*approach_route_coords, *emergency_route_coords[1:]]

        approach_distance_m = self._distance_coords_m(approach_route_coords)
        emergency_distance_m = self._distance_coords_m(emergency_route_coords)
        route_distance_km = round((approach_distance_m + emergency_distance_m) / 1000.0, 3)
        normal_eta_min = round(((route_distance_km / NORMAL_SPEED_KMPH) * 60.0) + ((SIGNAL_DELAY_SECONDS + TRAFFIC_DELAY_SECONDS) / 60.0), 1)
        optimized_eta_min = round(((route_distance_km / IMPROVED_SPEED_KMPH) * 60.0) + (MINIMAL_DELAY_SECONDS / 60.0), 1)
        time_saved_min = round(max(normal_eta_min - optimized_eta_min, 0.1), 1)
        time_saved_percent = round((time_saved_min / max(normal_eta_min, 0.1)) * 100.0, 1)
        approach_duration_sec = self._estimate_demo_duration_seconds(
            approach_distance_m,
            DEMO_APPROACH_SPEED_KMPH,
            DEMO_APPROACH_SECONDS_RANGE[0],
            DEMO_APPROACH_SECONDS_RANGE[1],
        )
        emergency_duration_sec = self._estimate_demo_duration_seconds(
            emergency_distance_m,
            DEMO_ROUTE_SPEED_KMPH,
            DEMO_EMERGENCY_SECONDS_RANGE[0],
            DEMO_EMERGENCY_SECONDS_RANGE[1],
        )
        now = time.time()

        self.emergency_state = {
            **self._empty_emergency_state(),
            "active": True,
            "completed": False,
            "mode": "structured_demo",
            "stage": "approach",
            "emergency_active": False,
            "display_route": [item["id"] for item in full_route_coords],
            "source": {"lat": round(float(start_point["lat"]), 6), "lng": round(float(start_point["lng"]), 6)},
            "starting_point": dict(start_point),
            "destination": {"lat": round(float(hospital["lat"]), 6), "lng": round(float(hospital["lng"]), 6)},
            "hospital": dict(hospital),
            "ambulance_position": {"lat": round(float(start_point["lat"]), 6), "lng": round(float(start_point["lng"]), 6)},
            "normal_eta_min": normal_eta_min,
            "optimized_eta_min": optimized_eta_min,
            "time_saved_min": time_saved_min,
            "time_saved_percent": time_saved_percent,
            "route_distance_km": route_distance_km,
            "remaining_eta_sec": round(approach_duration_sec + emergency_duration_sec, 1),
            "demo_duration_sec": round(approach_duration_sec + emergency_duration_sec, 1),
            "start_time": now,
            "expires_at": now + approach_duration_sec + emergency_duration_sec,
            "lock_duration_sec": round(emergency_duration_sec, 1),
            "max_lock_time_sec": MAP_ROUTE_MAX_LOCK_SECONDS,
            "activation_junction_id": activation_junction["id"],
            "approach_route_coords": approach_route_coords,
            "approach_path_coords": list(approach_route_coords),
            "approach_duration_sec": approach_duration_sec,
            "approach_started_at": now,
            "approach_elapsed_offset_sec": 0.0,
            "emergency_route_coords": emergency_route_coords,
            "emergency_path_coords": list(emergency_route_coords),
            "emergency_started_at": 0.0,
            "emergency_duration_sec": emergency_duration_sec,
            "emergency_elapsed_offset_sec": 0.0,
            "full_route_coords": full_route_coords,
            "full_path_coords": list(full_route_coords),
            "pre_detection_junctions": list(route_profile["pre_detection_junctions"]),
            "planned_route_nodes": emergency_route_nodes,
            "alerts": [],
            "current_junction": None,
            "current_index": 0,
            "next_target": activation_junction["id"],
            "distance_to_next_m": approach_distance_m,
            "eta_to_next_sec": approach_duration_sec,
            "active_signal_direction": None,
            "speed_multiplier": 1.0,
        }
        self._append_emergency_alert(
            f"Ambulance dispatched from {start_point['id']} and moving toward {activation_junction['id']} to arm the preset corridor.",
            stage="approach",
        )
        return self.get_emergency_state()

    def activate_emergency_route(self, source: tuple[float, float], destination: tuple[float, float]) -> dict[str, Any]:
        start_id = self._nearest_junction_id(source)
        end_id = self._nearest_junction_id(destination)
        route = self._shortest_path(start_id, end_id)
        now = time.time()
        lock_duration = min(
            MAP_ROUTE_MAX_LOCK_SECONDS,
            max(float(len(route)) * MAP_ROUTE_LOCK_SECONDS_PER_JUNCTION, MAP_ROUTE_LOCK_SECONDS_PER_JUNCTION),
        )
        self.emergency_state = {
            "active": True,
            "completed": False,
            "mode": "manual",
            "route": route,
            "route_nodes": route,
            "current_junction": route[0],
            "current_index": 0,
            "source": {"lat": round(float(source[0]), 6), "lng": round(float(source[1]), 6), "junction_id": start_id},
            "destination": {"lat": round(float(destination[0]), 6), "lng": round(float(destination[1]), 6), "junction_id": end_id},
            "hospital": None,
            "ambulance_position": {"lat": round(float(source[0]), 6), "lng": round(float(source[1]), 6)},
            "normal_eta_min": 0.0,
            "optimized_eta_min": 0.0,
            "time_saved_min": 0.0,
            "time_saved_percent": 0.0,
            "stage": "emergency",
            "emergency_active": True,
            "route_distance_km": round(self._route_distance(route, self.registry.list()) / 1000.0, 3),
            "remaining_eta_sec": lock_duration,
            "demo_duration_sec": lock_duration,
            "start_time": now,
            "expires_at": now + lock_duration,
            "lock_duration_sec": round(lock_duration, 1),
            "max_lock_time_sec": MAP_ROUTE_MAX_LOCK_SECONDS,
            "display_route": list(route),
            "approach_route_coords": [],
            "approach_path_coords": [],
            "approach_elapsed_offset_sec": 0.0,
            "emergency_route_coords": self._route_nodes_to_coords(route),
            "emergency_path_coords": self._route_nodes_to_coords(route),
            "full_route_coords": self._route_nodes_to_coords(route),
            "full_path_coords": self._route_nodes_to_coords(route),
            "emergency_started_at": now,
            "emergency_duration_sec": round(lock_duration, 1),
            "emergency_elapsed_offset_sec": 0.0,
            "alerts": [],
            "speed_multiplier": 1.0,
        }
        return self.get_emergency_state()

    def apply_structured_demo_google_paths(
        self,
        *,
        approach_path_coords: list[dict[str, Any]] | None = None,
        emergency_path_coords: list[dict[str, Any]] | None = None,
        approach_duration_sec: float | None = None,
        emergency_duration_sec: float | None = None,
        route_distance_km: float | None = None,
        normal_eta_min: float | None = None,
        optimized_eta_min: float | None = None,
        time_saved_min: float | None = None,
        time_saved_percent: float | None = None,
    ) -> dict[str, Any]:
        if str(self.emergency_state.get("mode") or "") != "structured_demo":
            return self.get_emergency_state()

        if approach_path_coords:
            self.emergency_state["approach_path_coords"] = list(approach_path_coords)
        if emergency_path_coords:
            self.emergency_state["emergency_path_coords"] = list(emergency_path_coords)

        approach_path = list(self.emergency_state.get("approach_path_coords") or self.emergency_state.get("approach_route_coords") or [])
        emergency_path = list(self.emergency_state.get("emergency_path_coords") or self.emergency_state.get("emergency_route_coords") or [])
        full_path = [*approach_path, *(emergency_path[1:] if len(emergency_path) > 1 else emergency_path)]
        self.emergency_state["full_path_coords"] = full_path

        if approach_duration_sec is not None:
            self.emergency_state["approach_duration_sec"] = round(max(float(approach_duration_sec), 1.0), 1)
        if emergency_duration_sec is not None:
            self.emergency_state["emergency_duration_sec"] = round(max(float(emergency_duration_sec), 1.0), 1)
            self.emergency_state["lock_duration_sec"] = round(max(float(emergency_duration_sec), 1.0), 1)
        if route_distance_km is not None:
            self.emergency_state["route_distance_km"] = round(float(route_distance_km), 3)
        if normal_eta_min is not None:
            self.emergency_state["normal_eta_min"] = round(float(normal_eta_min), 1)
        if optimized_eta_min is not None:
            self.emergency_state["optimized_eta_min"] = round(float(optimized_eta_min), 1)
        if time_saved_min is not None:
            self.emergency_state["time_saved_min"] = round(float(time_saved_min), 1)
        if time_saved_percent is not None:
            self.emergency_state["time_saved_percent"] = round(float(time_saved_percent), 1)

        total_duration = float(self.emergency_state.get("approach_duration_sec") or 0.0) + float(self.emergency_state.get("emergency_duration_sec") or 0.0)
        self.emergency_state["demo_duration_sec"] = round(total_duration, 1)
        stage = str(self.emergency_state.get("stage") or "approach")
        if stage == "approach":
            self.emergency_state["remaining_eta_sec"] = round(total_duration, 1)
            self.emergency_state["expires_at"] = float(self.emergency_state.get("approach_started_at") or time.time()) + total_duration
        elif stage == "emergency":
            emergency_started_at = float(self.emergency_state.get("emergency_started_at") or time.time())
            self.emergency_state["remaining_eta_sec"] = round(float(self.emergency_state.get("emergency_duration_sec") or 0.0), 1)
            self.emergency_state["expires_at"] = emergency_started_at + float(self.emergency_state.get("emergency_duration_sec") or 0.0)
        return self.get_emergency_state()

    def update_emergency_speed(self, speed_multiplier: float) -> dict[str, Any]:
        next_multiplier = round(_clip(_coerce_float(speed_multiplier, default=1.0), 0.5, 2.5), 2)
        if str(self.emergency_state.get("mode") or "idle") == "idle":
            self.emergency_state["speed_multiplier"] = next_multiplier
            return self.get_emergency_state()

        now = time.time()
        current_stage = str(self.emergency_state.get("stage") or "idle")
        if current_stage == "approach":
            elapsed = min(
                self._scaled_stage_elapsed("approach", now),
                float(self.emergency_state.get("approach_duration_sec") or 0.0),
            )
            self.emergency_state["approach_elapsed_offset_sec"] = round(elapsed, 3)
            self.emergency_state["approach_started_at"] = now
        elif current_stage == "emergency":
            elapsed = min(
                self._scaled_stage_elapsed("emergency", now),
                float(self.emergency_state.get("emergency_duration_sec") or 0.0),
            )
            self.emergency_state["emergency_elapsed_offset_sec"] = round(elapsed, 3)
            self.emergency_state["emergency_started_at"] = now
        elif self.emergency_state.get("active"):
            remaining = max(float(self.emergency_state.get("remaining_eta_sec") or 0.0), 0.0)
            elapsed = max(float(self.emergency_state.get("demo_duration_sec") or 0.0) - remaining, 0.0)
            self.emergency_state["start_time"] = now - (elapsed / max(next_multiplier, 0.1))

        self.emergency_state["speed_multiplier"] = next_multiplier
        stage_label = current_stage if current_stage not in {"idle", "complete"} else "control"
        self._append_emergency_alert(
            f"Ambulance speed updated to {next_multiplier:.2f}x for the {stage_label} stage.",
            stage=stage_label,
        )
        return self.get_emergency_state()

    def _activate_structured_emergency(self, now: float) -> None:
        activation_junction_id = str(self.emergency_state.get("activation_junction_id") or DEMO_APPROACH_JUNCTION_ID)
        activation_junction = self._demo_junction(activation_junction_id)
        planned_route_nodes = list(self.emergency_state.get("planned_route_nodes") or DEMO_EMERGENCY_ROUTE_NODES)
        self.emergency_state["stage"] = "emergency"
        self.emergency_state["emergency_active"] = True
        self.emergency_state["route_nodes"] = planned_route_nodes
        self.emergency_state["route"] = [*planned_route_nodes, str(self.emergency_state.get("hospital", {}).get("name") or "Hospital")]
        self.emergency_state["current_junction"] = activation_junction_id
        self.emergency_state["current_index"] = 0
        self.emergency_state["last_progress_index"] = 0
        self.emergency_state["next_target"] = planned_route_nodes[1] if len(planned_route_nodes) > 1 else self.emergency_state.get("hospital", {}).get("id")
        self.emergency_state["ambulance_position"] = {
            "lat": round(float(activation_junction["lat"]), 6),
            "lng": round(float(activation_junction["lng"]), 6),
        }
        self.emergency_state["emergency_started_at"] = now
        self.emergency_state["emergency_elapsed_offset_sec"] = 0.0
        self.emergency_state["detection_triggered_at"] = now
        self.emergency_state["expires_at"] = now + float(self.emergency_state.get("emergency_duration_sec") or 0.0)
        self._append_emergency_alert(f"Ambulance detected at {activation_junction_id}. Identifying nearest hospital.", stage="emergency")
        hospital_name = str(self.emergency_state.get("hospital", {}).get("name") or "nearest hospital")
        self._append_emergency_alert(f"Emergency mode activated. Routing corridor toward {hospital_name}.", stage="emergency")
        next_junction = planned_route_nodes[1] if len(planned_route_nodes) > 1 else None
        if next_junction:
            self._append_emergency_alert(f"{activation_junction_id} passed. Alert sent to {next_junction}.", stage="emergency")

    def _segment_state(
        self,
        coords: list[dict[str, Any]],
        progress: float,
    ) -> tuple[dict[str, float] | None, int, dict[str, Any] | None, dict[str, Any] | None]:
        if not coords:
            return None, 0, None, None
        if len(coords) == 1:
            position = {"lat": round(float(coords[0]["lat"]), 6), "lng": round(float(coords[0]["lng"]), 6)}
            return position, 0, coords[0], None
        progress = _clip(progress, 0.0, 1.0)
        segment_count = len(coords) - 1
        scaled = progress * segment_count
        index = min(int(math.floor(scaled)), segment_count - 1)
        position = self._interpolate_position(coords, progress)
        current = coords[index]
        next_target = coords[index + 1] if index + 1 < len(coords) else None
        return position, index, current, next_target

    def _advance_structured_demo_state(self) -> None:
        if not self.emergency_state.get("active"):
            return
        now = time.time()
        stage = str(self.emergency_state.get("stage") or "idle")
        if stage == "approach":
            approach_duration = float(self.emergency_state.get("approach_duration_sec") or 0.0)
            elapsed = self._scaled_stage_elapsed("approach", now)
            progress = _clip((elapsed / approach_duration) if approach_duration else 1.0, 0.0, 1.0)
            path_coords = list(self.emergency_state.get("approach_path_coords") or self.emergency_state.get("approach_route_coords") or [])
            ambulance_position = self._interpolate_position(path_coords, progress) if path_coords else None
            activation_junction = self._demo_junction(str(self.emergency_state.get("activation_junction_id") or DEMO_APPROACH_JUNCTION_ID))
            next_target = {
                "id": activation_junction["id"],
                "lat": activation_junction["lat"],
                "lng": activation_junction["lng"],
            }
            self.emergency_state["ambulance_position"] = ambulance_position
            if next_target and ambulance_position:
                distance_to_next = _haversine_distance_m(
                    float(ambulance_position["lat"]),
                    float(ambulance_position["lng"]),
                    float(next_target["lat"]),
                    float(next_target["lng"]),
                )
                self.emergency_state["next_target"] = next_target["id"]
                self.emergency_state["distance_to_next_m"] = round(distance_to_next, 1)
                self.emergency_state["eta_to_next_sec"] = round(max(approach_duration - elapsed, 0.0), 1)
                self.emergency_state["active_signal_direction"] = SHORT_TO_LONG_DIRECTION.get(
                    self._approach_direction(ambulance_position, self._demo_junction(next_target["id"])),
                    None,
                )
                if distance_to_next <= DEMO_TRIGGER_DISTANCE_METERS or progress >= 1.0:
                    self._activate_structured_emergency(now)
                    self._advance_structured_demo_state()
                    return
            self.emergency_state["remaining_eta_sec"] = round(
                max((approach_duration - elapsed) + float(self.emergency_state.get("emergency_duration_sec") or 0.0), 0.0),
                1,
            )
            return

        if stage != "emergency":
            return

        route_nodes = list(self.emergency_state.get("route_nodes") or [])
        emergency_duration = float(self.emergency_state.get("emergency_duration_sec") or 0.0)
        elapsed = self._scaled_stage_elapsed("emergency", now)
        progress = _clip((elapsed / emergency_duration) if emergency_duration else 1.0, 0.0, 1.0)
        path_coords = list(self.emergency_state.get("emergency_path_coords") or self.emergency_state.get("emergency_route_coords") or [])
        ambulance_position = self._interpolate_position(path_coords, progress) if path_coords else None
        completed = progress >= 1.0
        current_index = min(int(progress * max(len(route_nodes), 1)), max(len(route_nodes) - 1, 0)) if route_nodes else 0
        current_node = self._demo_junction(route_nodes[current_index]) if route_nodes else None
        next_target_id = route_nodes[current_index + 1] if current_index + 1 < len(route_nodes) else self.emergency_state.get("hospital", {}).get("id")
        if next_target_id in {item["id"] for item in DEMO_HOSPITALS}:
            next_target = next((dict(item) for item in DEMO_HOSPITALS if item["id"] == next_target_id), None)
        elif next_target_id:
            junction = self._demo_junction(str(next_target_id))
            next_target = {"id": junction["id"], "lat": junction["lat"], "lng": junction["lng"]}
        else:
            next_target = None
        self.emergency_state["ambulance_position"] = ambulance_position
        self.emergency_state["current_index"] = current_index
        self.emergency_state["current_junction"] = current_node["id"] if current_node else None
        self.emergency_state["next_target"] = next_target["id"] if next_target else None
        if next_target and ambulance_position:
            distance_to_next = _haversine_distance_m(
                float(ambulance_position["lat"]),
                float(ambulance_position["lng"]),
                float(next_target["lat"]),
                float(next_target["lng"]),
            )
            segment_remaining = max(len(route_nodes) - 1 - current_index, 1)
            eta_to_next = max(float(self.emergency_state.get("remaining_eta_sec") or 0.0) / segment_remaining, 0.0)
            self.emergency_state["distance_to_next_m"] = round(distance_to_next, 1)
            self.emergency_state["eta_to_next_sec"] = round(min(eta_to_next, max(emergency_duration - elapsed, 0.0)), 1)
            if current_node:
                self.emergency_state["active_signal_direction"] = _direction_between(
                    {"lat": ambulance_position["lat"], "lng": ambulance_position["lng"]},
                    {"lat": current_node["lat"], "lng": current_node["lng"]},
                )
        else:
            self.emergency_state["distance_to_next_m"] = 0.0
            self.emergency_state["eta_to_next_sec"] = 0.0
            self.emergency_state["active_signal_direction"] = None

        last_progress_index = int(self.emergency_state["last_progress_index"]) if self.emergency_state.get("last_progress_index") is not None else -1
        if current_index > last_progress_index and current_index < len(route_nodes):
            current_junction_id = route_nodes[current_index]
            next_junction_id = route_nodes[current_index + 1] if current_index + 1 < len(route_nodes) else None
            if next_junction_id:
                self._append_emergency_alert(
                    f"{current_junction_id} switching corridor. Alert sent to {next_junction_id}.",
                    stage="emergency",
                )
            self.emergency_state["last_progress_index"] = current_index

        self.emergency_state["remaining_eta_sec"] = round(max(emergency_duration - elapsed, 0.0), 1)
        self.emergency_state["completed"] = completed
        self.emergency_state["active"] = not completed
        if completed:
            self.emergency_state["emergency_active"] = False
            self.emergency_state["stage"] = "complete"
            self.emergency_state["route_nodes"] = []
            self.emergency_state["route"] = []
            self.emergency_state["current_junction"] = None
            self.emergency_state["next_target"] = self.emergency_state.get("hospital", {}).get("id")
            self._append_emergency_alert(
                f"Ambulance reached {self.emergency_state.get('hospital', {}).get('name', 'the hospital')}. Corridor released.",
                stage="complete",
            )

    def clear_emergency_route(self) -> dict[str, Any]:
        self.emergency_state = self._empty_emergency_state()
        return self.get_emergency_state()

    def get_emergency_state(self) -> dict[str, Any]:
        mode = str(self.emergency_state.get("mode") or "idle")
        if mode == "structured_demo":
            self._advance_structured_demo_state()
        elif bool(self.emergency_state.get("active")):
            now = time.time()
            route = list(self.emergency_state.get("route_nodes") or self.emergency_state.get("route") or [])
            if route:
                elapsed = max(0.0, now - float(self.emergency_state.get("start_time") or now))
                duration = float(self.emergency_state.get("demo_duration_sec") or 0.0)
                current_index = min(int(elapsed // MAP_ROUTE_LOCK_SECONDS_PER_JUNCTION), len(route) - 1)
                self.emergency_state["current_index"] = current_index
                self.emergency_state["current_junction"] = route[current_index]
                self.emergency_state["completed"] = duration > 0 and elapsed >= duration
                self.emergency_state["active"] = not self.emergency_state["completed"]
                self.emergency_state["remaining_eta_sec"] = round(max(duration - elapsed, 0.0), 1)

        now = time.time()
        route = list(self.emergency_state.get("route") or [])
        route_nodes = list(self.emergency_state.get("route_nodes") or [])
        display_route = list(self.emergency_state.get("display_route") or route)
        full_route_coords = list(self.emergency_state.get("full_path_coords") or self.emergency_state.get("full_route_coords") or self.emergency_state.get("emergency_route_coords") or [])
        emergency_route_coords = list(self.emergency_state.get("emergency_path_coords") or self.emergency_state.get("emergency_route_coords") or [])
        approach_route_coords = list(self.emergency_state.get("approach_path_coords") or self.emergency_state.get("approach_route_coords") or [])
        remaining_sec = max(0.0, float(self.emergency_state.get("remaining_eta_sec") or 0.0))
        current_index = int(self.emergency_state.get("current_index") or 0)
        locked = [] if self.emergency_state.get("completed") else route_nodes[current_index:]
        unlocked = route_nodes[:current_index]
        return {
            "active": bool(self.emergency_state.get("active")),
            "completed": bool(self.emergency_state.get("completed")),
            "mode": self.emergency_state.get("mode", "idle"),
            "stage": self.emergency_state.get("stage", "idle"),
            "emergency_active": bool(self.emergency_state.get("emergency_active")),
            "route": route,
            "display_route": display_route,
            "route_coords": full_route_coords,
            "full_route_coords": full_route_coords,
            "approach_route_coords": approach_route_coords,
            "emergency_route_coords": emergency_route_coords,
            "route_nodes": route_nodes,
            "current_junction": self.emergency_state.get("current_junction"),
            "current_index": current_index,
            "remaining_lock_sec": round(remaining_sec, 1),
            "lock_duration_sec": float(self.emergency_state.get("lock_duration_sec") or 0.0),
            "source": self.emergency_state.get("source"),
            "starting_point": self.emergency_state.get("starting_point"),
            "destination": self.emergency_state.get("destination"),
            "hospital": self.emergency_state.get("hospital"),
            "ambulance_position": self.emergency_state.get("ambulance_position"),
            "normal_eta": float(self.emergency_state.get("normal_eta_min") or 0.0),
            "optimized_eta": float(self.emergency_state.get("optimized_eta_min") or 0.0),
            "time_saved": float(self.emergency_state.get("time_saved_min") or 0.0),
            "time_saved_percent": float(self.emergency_state.get("time_saved_percent") or 0.0),
            "route_distance_km": float(self.emergency_state.get("route_distance_km") or 0.0),
            "remaining_eta_sec": round(remaining_sec, 1),
            "demo_duration_sec": float(self.emergency_state.get("demo_duration_sec") or 0.0),
            "speed_multiplier": self._speed_multiplier(),
            "progress": round(
                1.0 - (remaining_sec / max(float(self.emergency_state.get("demo_duration_sec") or 1.0), 1.0)),
                3,
            ),
            "released_junctions": unlocked,
            "locked_junctions": locked,
            "max_lock_time_sec": MAP_ROUTE_MAX_LOCK_SECONDS,
            "next_target": self.emergency_state.get("next_target"),
            "distance_to_next_m": float(self.emergency_state.get("distance_to_next_m") or 0.0),
            "eta_to_next_sec": float(self.emergency_state.get("eta_to_next_sec") or 0.0),
            "active_signal_direction": self.emergency_state.get("active_signal_direction"),
            "activation_junction_id": self.emergency_state.get("activation_junction_id"),
            "pre_detection_junctions": list(self.emergency_state.get("pre_detection_junctions") or []),
            "planned_route_nodes": list(self.emergency_state.get("planned_route_nodes") or []),
            "alerts": list(self.emergency_state.get("alerts") or []),
        }

    def _route_distance(self, route: list[str], junction_map: dict[str, dict[str, Any]]) -> float:
        distance_m = 0.0
        for source_id, target_id in zip(route, route[1:]):
            source = junction_map[source_id]
            target = junction_map[target_id]
            distance_m += _haversine_distance_m(source["lat"], source["lng"], target["lat"], target["lng"])
        return round(distance_m, 2)

    def _global_status(self, junctions: list[dict[str, Any]]) -> dict[str, Any]:
        if not junctions:
            return {
                "congestion_index": 0.0,
                "active_emergencies": 0,
                "system_health": "degraded",
                "active_cameras": 0,
                "degraded_cameras": 0,
                "uncertain_junctions": 0,
            }
        congestion_index = sum(float(item["density"]) for item in junctions) / len(junctions)
        active_emergencies = sum(1 for item in junctions if item["incident"]["active"])
        degraded_cameras = sum(1 for item in junctions if item["status"] == "degraded")
        uncertain_junctions = sum(1 for item in junctions if item["status"] == "uncertain")
        active_cameras = sum(1 for item in junctions if item["camera_health"]["healthy"])
        if degraded_cameras:
            system_health = "degraded"
        elif uncertain_junctions:
            system_health = "uncertain"
        else:
            system_health = "stable"
        return {
            "congestion_index": round(congestion_index, 3),
            "active_emergencies": active_emergencies,
            "system_health": system_health,
            "active_cameras": active_cameras,
            "degraded_cameras": degraded_cameras,
            "uncertain_junctions": uncertain_junctions,
        }

    def _fallback_metrics(self, junction_id: str, junction_map: dict[str, dict[str, Any]]) -> dict[str, float]:
        junction = junction_map[junction_id]
        neighbor_ids = junction.get("neighbors", [])
        neighbor_values: dict[str, list[float]] = defaultdict(list)
        for neighbor_id in neighbor_ids:
            metrics = self.state.get(neighbor_id, {}).get("metrics", {})
            for key in ("vehicle_count", "queue_length", "density", "flow_count", "average_speed_kmph"):
                if key in metrics:
                    neighbor_values[key].append(float(metrics[key]))
        fallback: dict[str, float] = {}
        base = junction["base_metrics"]

        def _blended_fallback(metric: str, base_value: float, *, neighbor_weight: float = 0.65) -> float:
            values = _finite_series(neighbor_values[metric])
            if not values:
                return _sanitize_metric(metric, base_value, default=base_value)
            neighbor_average = float(sum(values)) / float(len(values))
            blended = (neighbor_weight * neighbor_average) + ((1.0 - neighbor_weight) * base_value)
            return _sanitize_metric(metric, blended, default=base_value)

        fallback["vehicle_count"] = _blended_fallback("vehicle_count", float(base["vehicle_count"]))
        fallback["queue_length"] = _blended_fallback("queue_length", float(base["queue"]))
        fallback["density"] = _blended_fallback("density", float(base["density"]), neighbor_weight=0.55)
        fallback["flow_count"] = _blended_fallback("flow_count", float(base["flow_count"]))
        fallback["average_speed_kmph"] = _blended_fallback("average_speed_kmph", float(base["average_speed_kmph"]), neighbor_weight=0.5)
        return fallback

    def build_snapshot(self, emergency_override: dict[str, Any] | None = None) -> dict[str, Any]:
        junction_map = self.registry.list()
        for junction_id in junction_map:
            self._ensure_junction_state(junction_id)
        emergency_state = self.get_emergency_state()
        junctions: list[dict[str, Any]] = []
        predictions: list[dict[str, Any]] = []

        for junction_id, junction in junction_map.items():
            healthy, health_status = self._health_status(junction)
            raw_metrics = self._simulated_metrics(junction)
            if not healthy:
                raw_metrics = self._fallback_metrics(junction_id, junction_map)
            smoothed_metrics = {
                metric: self._smooth_metric(junction_id, metric, value, junction_map)
                for metric, value in raw_metrics.items()
            }
            metric_confidence = self._metric_confidence(raw_metrics, smoothed_metrics, healthy)
            overall_confidence = round(sum(metric_confidence.values()) / max(len(metric_confidence), 1), 3)
            incident = self._incident_state(
                junction_id,
                smoothed_metrics,
                metric_confidence,
                bool(junction["base_metrics"].get("accident")),
            )
            anomaly = self._anomaly_state(junction_id, smoothed_metrics)
            prediction = self._prediction(junction_id, smoothed_metrics, metric_confidence)
            status = self._derive_overall_status(overall_confidence, health_status)
            self.state[junction_id]["metrics"] = {**smoothed_metrics, "confidence": metric_confidence}
            self.state[junction_id]["prediction"] = prediction
            self.state[junction_id]["status"] = status
            self.state[junction_id]["confidence"] = overall_confidence
            self.state[junction_id]["updated_at"] = round(time.time(), 6)

            junction_snapshot = {
                "junction_id": junction_id,
                "name": junction["name"],
                "lat": float(junction["lat"]),
                "lng": float(junction["lng"]),
                "camera_id": junction["camera_id"],
                "region": junction["region"],
                "neighbors": list(junction.get("neighbors", [])),
                "vehicle_count": int(round(smoothed_metrics["vehicle_count"])),
                "queue": int(round(smoothed_metrics["queue_length"])),
                "queue_length": int(round(smoothed_metrics["queue_length"])),
                "density": float(smoothed_metrics["density"]),
                "flow_count": int(round(smoothed_metrics["flow_count"])),
                "average_speed_kmph": round(float(smoothed_metrics["average_speed_kmph"]), 2),
                "predicted_load": float(prediction["predicted_load"]),
                "prediction_confidence": float(prediction["confidence"]),
                "confidence": overall_confidence,
                "status": status,
                "camera_health": {
                    "healthy": healthy,
                    "status": health_status,
                    "last_seen_at": round(float(self.camera_health[junction_id]["last_seen_at"]), 6),
                },
                "metric_confidence": metric_confidence,
                "incident": incident,
                "anomaly": anomaly,
                "emergency": junction_id in emergency_state["locked_junctions"],
                "accident": bool(incident["active"]),
                "signal": "RED",
                "signals": {direction: "RED" for direction in SIGNAL_DIRECTIONS},
                "active_direction": None,
                "phase": "RED",
                "signal_locked": False,
                "recommended_signal": None,
                "coordination_priority": 0.0,
                "green_wave_eta_sec": None,
                "green_wave_active": False,
                "signal_alert": None,
                "updated_at": round(time.time(), 6),
            }
            junctions.append(junction_snapshot)
            predictions.append(
                {
                    "junction_id": junction_id,
                    "predicted_load": float(prediction["predicted_load"]),
                    "confidence": float(prediction["confidence"]),
                }
            )

        coordination = self.compute_signal_coordination(junctions, emergency_override=emergency_override)
        green_wave_timings = {item["junction_id"]: item for item in coordination["green_wave"].get("timings", [])}
        coordination_map = coordination["coordination"]
        for junction in junctions:
            control = coordination_map.get(junction["junction_id"], {})
            junction["recommended_signal"] = control.get("next_signal")
            junction["signal"] = str(control.get("signal_state", "RED")).upper()
            junction["signals"] = dict(control.get("signals") or junction["signals"])
            junction["active_direction"] = control.get("active_direction")
            junction["phase"] = str(control.get("phase", "RED")).upper()
            junction["signal_locked"] = bool(control.get("forced_green"))
            junction["coordination_priority"] = round(float(control.get("priority_score") or 0.0), 2)
            junction["green_wave_eta_sec"] = green_wave_timings.get(junction["junction_id"], {}).get("next_green_in_sec")
            junction["green_wave_active"] = junction["junction_id"] in coordination["green_wave"].get("path", [])
            junction["signal_alert"] = control.get("alert")
            self.state[junction["junction_id"]]["signal"] = {
                "signal": junction["signal"],
                "signals": junction["signals"],
                "phase": junction["phase"],
                "active_direction": junction["active_direction"],
                "signal_locked": junction["signal_locked"],
                "recommended_signal": junction["recommended_signal"],
                "alert": junction["signal_alert"],
            }
            self.state[junction["junction_id"]]["last_snapshot"] = junction

        return {
            "updated_at": round(time.time(), 6),
            "junctions": junctions,
            "predictions": predictions,
            "coordination": coordination,
            "global_status": self._global_status(junctions),
        }

    def compute_signal_coordination(
        self,
        junctions: list[dict[str, Any]],
        *,
        emergency_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        emergency_state = self.get_emergency_state()
        route_ids = list(emergency_state.get("locked_junctions") or emergency_state.get("route_nodes") or [])
        external_lock_active = bool((emergency_override or {}).get("active")) and bool((emergency_override or {}).get("locked"))
        junction_map = {item["junction_id"]: item for item in junctions}
        coordination: dict[str, dict[str, Any]] = {}
        now = time.time()

        for junction_id, junction in junction_map.items():
            neighbor_scores: list[tuple[float, str]] = []
            fairness_boost = min(float(self._moving_average(self.history[junction_id]["queue_length"][-6:])) * 0.15, 8.0)

            for neighbor_id in junction.get("neighbors", []):
                neighbor = junction_map.get(neighbor_id)
                if not neighbor:
                    continue
                outbound_boost = round(float(junction.get("flow_count", 0)) * 0.35, 2)
                neighbor_priority = (
                    float(neighbor.get("queue_length", 0))
                    + float(neighbor.get("predicted_load", 0))
                    + outbound_boost
                    + (float(neighbor.get("density", 0)) * 10.0)
                )
                neighbor_scores.append((neighbor_priority, _direction_between(junction, neighbor)))

            local_decision = (
                float(junction.get("queue_length", 0))
                + min(float(junction.get("density", 0.0)) * 22.0, 22.0)
                + float(junction.get("flow_count", 0)) * 0.5
            )
            global_hint = float(junction.get("predicted_load", 0.0)) + fairness_boost
            emergency_override_score = 100.0 if junction_id in route_ids else 0.0
            priority_score = round(local_decision + global_hint + emergency_override_score, 2)
            forced_green = emergency_override_score > 0.0
            if forced_green:
                next_signal = SHORT_TO_LONG_DIRECTION.get(
                    self._approach_direction(emergency_state.get("ambulance_position"), junction),
                    "north",
                )
            elif neighbor_scores:
                next_signal = max(neighbor_scores, key=lambda item: item[0])[1]
            else:
                next_signal = "north"
            signal_update = self._update_signal_controller(
                junction_id,
                junction,
                emergency_state,
                target_direction=LONG_TO_SHORT_DIRECTION.get(next_signal, "N"),
                forced_green=forced_green,
                now=now,
            )
            signal_state = "green" if signal_update["phase"] == "GREEN" else ("yellow" if signal_update["phase"] == "YELLOW" else "red")
            coordination[junction_id] = {
                "junction_id": junction_id,
                "next_signal": next_signal,
                "priority_score": priority_score,
                "local_decision": round(local_decision, 2),
                "global_hint": round(global_hint, 2),
                "emergency_override": emergency_override_score > 0.0,
                "forced_green": forced_green,
                "signal_state": signal_state,
                "signals": signal_update["signals"],
                "active_direction": signal_update["active_direction"],
                "phase": signal_update["phase"],
                "pending_direction": signal_update["pending_direction"],
                "route_locked": forced_green,
                "eta_to_junction_sec": signal_update["eta_to_junction_sec"],
                "ambulance_direction": signal_update["ambulance_direction"],
                "reason": signal_update["reason"],
                "alert": signal_update["alert"],
            }

        green_wave = self.compute_green_wave(junction_map, coordination, emergency_override=emergency_override)
        if external_lock_active:
            green_wave["external_emergency_lock"] = dict(emergency_override or {})
        return {
            "updated_at": round(time.time(), 6),
            "emergency": emergency_state,
            "coordination": coordination,
            "green_wave": green_wave,
        }

    def compute_green_wave(
        self,
        junction_map: dict[str, dict[str, Any]],
        coordination: dict[str, dict[str, Any]],
        *,
        emergency_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        emergency_state = self.get_emergency_state()
        route = list(emergency_state.get("locked_junctions") or emergency_state.get("route") or [])
        if not route:
            ranked = sorted(
                junction_map.values(),
                key=lambda item: (
                    float(item.get("predicted_load", 0.0)) + float(item.get("queue_length", 0)),
                    float(item.get("flow_count", 0)),
                ),
                reverse=True,
            )
            route = [item["junction_id"] for item in ranked[: min(4, len(ranked))]]
        if len(route) < 2:
            return {
                "active": False,
                "path": route,
                "path_coords": [
                    [round(float(junction_map[junction_id]["lat"]), 6), round(float(junction_map[junction_id]["lng"]), 6)]
                    for junction_id in route
                    if junction_id in junction_map
                ],
                "avg_speed_kmph": DEFAULT_GREEN_WAVE_SPEED_KMPH,
                "timings": [],
            }

        route_junctions = [junction_map[junction_id] for junction_id in route if junction_id in junction_map]
        avg_speed = max(
            10.0,
            round(sum(float(item.get("average_speed_kmph", 0.0)) for item in route_junctions) / len(route_junctions), 2),
        )
        speed_mps = max(avg_speed / 3.6, 1.0)
        timings: list[dict[str, Any]] = []
        cumulative_distance = 0.0
        for index, junction in enumerate(route_junctions):
            if index > 0:
                previous = route_junctions[index - 1]
                cumulative_distance += _haversine_distance_m(
                    float(previous["lat"]),
                    float(previous["lng"]),
                    float(junction["lat"]),
                    float(junction["lng"]),
                )
            timings.append(
                {
                    "junction_id": junction["junction_id"],
                    "next_signal": coordination.get(junction["junction_id"], {}).get("next_signal"),
                    "distance_m": round(cumulative_distance, 2),
                    "next_green_in_sec": round(cumulative_distance / speed_mps, 1),
                }
            )
        return {
            "active": bool(emergency_state.get("active")) or bool((emergency_override or {}).get("active")),
            "path": [junction["junction_id"] for junction in route_junctions],
            "path_coords": [
                [round(float(junction["lat"]), 6), round(float(junction["lng"]), 6)] for junction in route_junctions
            ],
            "avg_speed_kmph": avg_speed,
            "route_distance_m": self._route_distance([junction["junction_id"] for junction in route_junctions], junction_map),
            "timings": timings,
        }


class MapStreamHub:
    """Push delta updates only when city map state changes materially."""

    def __init__(self, platform: TrafficPlatformService, emergency_provider) -> None:
        self.platform = platform
        self.emergency_provider = emergency_provider
        self.connections: set[WebSocket] = set()
        self.running = False
        self.task: asyncio.Task[None] | None = None
        self.last_snapshot: dict[str, Any] | None = None

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._loop(), name="map-stream-loop")

    async def stop(self) -> None:
        self.running = False
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)
        snapshot = self.platform.build_snapshot(emergency_override=self.emergency_provider())
        if self.last_snapshot is None:
            self.last_snapshot = snapshot
        await websocket.send_json({"type": "snapshot", "snapshot": snapshot, "sent_at": round(time.time(), 6)})

    async def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def _loop(self) -> None:
        while self.running:
            snapshot = self.platform.build_snapshot(emergency_override=self.emergency_provider())
            payload = self._build_delta_payload(snapshot)
            if payload is not None:
                await self._broadcast(payload)
            await asyncio.sleep(STREAM_INTERVAL_SECONDS)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for connection in list(self.connections):
            try:
                await connection.send_json(payload)
            except Exception:
                stale.append(connection)
        for connection in stale:
            self.connections.discard(connection)

    def _build_delta_payload(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        previous = self.last_snapshot
        self.last_snapshot = snapshot
        if previous is None:
            return {"type": "snapshot", "snapshot": snapshot, "sent_at": round(time.time(), 6)}

        previous_junctions = {item["junction_id"]: item for item in previous.get("junctions", [])}
        current_junctions = {item["junction_id"]: item for item in snapshot.get("junctions", [])}
        deltas: list[dict[str, Any]] = []
        removed = sorted(set(previous_junctions) - set(current_junctions))

        for junction_id, current in current_junctions.items():
            prior = previous_junctions.get(junction_id)
            if prior is None:
                deltas.append({"junction_id": junction_id, "updates": current})
                continue
            updates = self._junction_delta(prior, current)
            if updates:
                deltas.append({"junction_id": junction_id, "updates": updates})

        coordination_changed = previous.get("coordination") != snapshot.get("coordination")
        status_changed = previous.get("global_status") != snapshot.get("global_status")
        if not deltas and not removed and not coordination_changed and not status_changed:
            return None
        return {
            "type": "delta",
            "updates": deltas,
            "removed_junction_ids": removed,
            "coordination": snapshot["coordination"] if coordination_changed else None,
            "global_status": snapshot["global_status"] if status_changed else None,
            "sent_at": round(time.time(), 6),
        }

    def _junction_delta(self, previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        for key, value in current.items():
            prior = previous.get(key)
            if isinstance(value, dict):
                if prior != value:
                    updates[key] = value
                continue
            if isinstance(value, list):
                if prior != value:
                    updates[key] = value
                continue
            threshold = SIGNIFICANT_CHANGE_THRESHOLD.get(key)
            if threshold is None:
                if prior != value:
                    updates[key] = value
                continue
            if isinstance(value, (int, float)) and isinstance(prior, (int, float)):
                if abs(float(value) - float(prior)) >= threshold:
                    updates[key] = value
            elif key == "status":
                if STATUS_RANK.get(str(value), 0) != STATUS_RANK.get(str(prior), 0):
                    updates[key] = value
            elif prior != value:
                updates[key] = value
        return updates
