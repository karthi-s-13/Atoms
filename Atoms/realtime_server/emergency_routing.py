"""Secure backend-only emergency routing via Google Directions API."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import HTTPException

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
ROUTE_CACHE_TTL_SECONDS = 300.0

CHENNAI_HOSPITALS = [
    {"id": "H1", "name": "Apollo Specialty Center", "lat": 13.0368, "lng": 80.2258},
    {"id": "H2", "name": "MIOT Care Annex", "lat": 13.0311, "lng": 80.2142},
    {"id": "H3", "name": "City Medical Center", "lat": 13.0424, "lng": 80.2318},
    {"id": "H4", "name": "Riverside General", "lat": 13.0488, "lng": 80.2192},
]


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").replace("&nbsp;", " ").strip()


def decode_polyline_points(encoded: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    index = 0
    latitude = 0
    longitude = 0
    while index < len(encoded):
        shift = 0
        result = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        latitude += ~(result >> 1) if (result & 1) else (result >> 1)

        shift = 0
        result = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        longitude += ~(result >> 1) if (result & 1) else (result >> 1)
        points.append((latitude / 1e5, longitude / 1e5))
    return points


def _haversine_distance_m(lat_a: float, lng_a: float, lat_b: float, lng_b: float) -> float:
    from math import atan2, cos, radians, sin, sqrt

    radius_m = 6_371_000.0
    lat1 = radians(lat_a)
    lat2 = radians(lat_b)
    delta_lat = radians(lat_b - lat_a)
    delta_lng = radians(lng_b - lng_a)
    chord = sin(delta_lat / 2.0) ** 2 + cos(lat1) * cos(lat2) * (sin(delta_lng / 2.0) ** 2)
    return 2.0 * radius_m * atan2(sqrt(chord), sqrt(max(1e-12, 1.0 - chord)))


class GoogleEmergencyRouter:
    """Resolve hospital routes securely and cache repeated direction lookups."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def get_hospitals(self) -> list[dict[str, Any]]:
        return [dict(item) for item in CHENNAI_HOSPITALS]

    def find_nearest_hospital(
        self,
        start: tuple[float, float],
        *,
        hospitals: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        pool = hospitals or CHENNAI_HOSPITALS
        return min(
            pool,
            key=lambda hospital: _haversine_distance_m(start[0], start[1], hospital["lat"], hospital["lng"]),
        )

    def _cache_key(self, origin: tuple[float, float], destination: tuple[float, float]) -> str:
        return f"{origin[0]:.6f},{origin[1]:.6f}->{destination[0]:.6f},{destination[1]:.6f}"

    def _get_cached(self, origin: tuple[float, float], destination: tuple[float, float]) -> dict[str, Any] | None:
        cached = self._cache.get(self._cache_key(origin, destination))
        if not cached:
            return None
        if time.time() - float(cached["stored_at"]) > ROUTE_CACHE_TTL_SECONDS:
            self._cache.pop(self._cache_key(origin, destination), None)
            return None
        return dict(cached["value"])

    def _set_cached(self, origin: tuple[float, float], destination: tuple[float, float], value: dict[str, Any]) -> None:
        self._cache[self._cache_key(origin, destination)] = {
            "stored_at": time.time(),
            "value": dict(value),
        }

    def get_route(self, origin: tuple[float, float], destination: tuple[float, float]) -> dict[str, Any]:
        cached = self._get_cached(origin, destination)
        if cached is not None:
            return cached

        api_key = os.getenv("GOOGLE_MAPS_API_KEY") or GOOGLE_MAPS_API_KEY
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="GOOGLE_MAPS_API_KEY is not configured on the backend.",
            )

        params = {
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
            "key": api_key,
            "mode": "driving",
            "traffic_model": "best_guess",
            "departure_time": "now",
        }

        request_url = f"{GOOGLE_DIRECTIONS_URL}?{urlencode(params)}"
        try:
            with urlopen(request_url, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Google Directions request failed with HTTP {exc.code}.") from exc
        except URLError as exc:
            raise HTTPException(status_code=502, detail="Google Directions request failed to reach the upstream service.") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Google Directions request failed unexpectedly.") from exc

        status = str(payload.get("status") or "UNKNOWN")
        routes = payload.get("routes") or []
        if status != "OK" or not routes:
            error_message = payload.get("error_message")
            detail = f"Google Directions returned {status}."
            if error_message:
                detail = f"{detail} {error_message}"
            raise HTTPException(status_code=502, detail=detail)

        leg = routes[0]["legs"][0]
        steps = []
        for index, step in enumerate(leg.get("steps") or []):
            steps.append(
                {
                    "index": index,
                    "instruction": _strip_html(str(step.get("html_instructions") or "")),
                    "distance_m": int((step.get("distance") or {}).get("value") or 0),
                    "duration_s": int((step.get("duration") or {}).get("value") or 0),
                    "start_location": {
                        "lat": float((step.get("start_location") or {}).get("lat") or 0.0),
                        "lng": float((step.get("start_location") or {}).get("lng") or 0.0),
                    },
                    "end_location": {
                        "lat": float((step.get("end_location") or {}).get("lat") or 0.0),
                        "lng": float((step.get("end_location") or {}).get("lng") or 0.0),
                    },
                    "maneuver": str(step.get("maneuver") or ""),
                }
            )
        result = {
            "polyline": routes[0]["overview_polyline"]["points"],
            "distance_m": int(leg["distance"]["value"]),
            "duration_s": int(leg["duration"]["value"]),
            "duration_in_traffic_s": int((leg.get("duration_in_traffic") or leg["duration"])["value"]),
            "steps": steps,
        }
        self._set_cached(origin, destination, result)
        return result

    def start_emergency(
        self,
        start: tuple[float, float],
        *,
        hospital: dict[str, Any] | None = None,
        hospitals: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        chosen_hospital = dict(hospital) if hospital else self.find_nearest_hospital(start, hospitals=hospitals)
        destination = (float(chosen_hospital["lat"]), float(chosen_hospital["lng"]))
        route_data = self.get_route(start, destination)
        normal_eta = round(float(route_data["duration_in_traffic_s"]) / 60.0, 1)
        optimized_eta = round(max(normal_eta * 0.5, 0.5), 1)
        time_saved = round(max(normal_eta - optimized_eta, 0.1), 1)
        return {
            "polyline": route_data["polyline"],
            "hospital": chosen_hospital,
            "distance_m": int(route_data["distance_m"]),
            "duration_s": int(route_data["duration_s"]),
            "duration_in_traffic_s": int(route_data["duration_in_traffic_s"]),
            "steps": list(route_data.get("steps") or []),
            "normal_eta": normal_eta,
            "optimized_eta": optimized_eta,
            "time_saved": time_saved,
            "time_saved_percent": round((time_saved / max(normal_eta, 0.1)) * 100.0, 1),
            "google_maps_url": (
                "https://www.google.com/maps/dir/?api=1"
                f"&origin={start[0]},{start[1]}"
                f"&destination={destination[0]},{destination[1]}"
                "&travelmode=driving"
            ),
        }
