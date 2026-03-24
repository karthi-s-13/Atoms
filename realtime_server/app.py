"""FastAPI + WebSocket bridge for the production traffic engine."""

from __future__ import annotations

import asyncio
import json
import heapq
import math
import os
import re
import tempfile
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Set

import cv2
import numpy as np
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

from realtime_server.emergency_routing import GoogleEmergencyRouter, decode_polyline_points
from realtime_server.traffic_platform import MapStreamHub, TrafficPlatformService
from simulation_engine import FRAME_DT, TrafficNetwork

JUNCTION_REGISTRY_PATH = Path(__file__).resolve().parent / "junction_registry.json"
AMBULANCE_CLASSIFIER_PATH = PROJECT_ROOT / "models" / "ambulance_yolo_cls.pt"
BASE_DETECTOR_MODEL_PATH = PROJECT_ROOT / "yolov8n.pt"
VEHICLE_CLASS_IDS = {1, 2, 3, 5, 7}
VEHICLE_LABELS = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}
POSITION_BUCKETS = ("left", "center", "right")
JUNCTION_DIRECTIONS = ("north", "south", "east", "west")
ACCIDENT_LABELS = {"car", "motorcycle", "bus", "truck", "ambulance"}
ACCIDENT_IOU_THRESHOLD = 0.16
ACCIDENT_CENTER_DISTANCE_FACTOR = 0.55
EXTERNAL_EVENT_LIMIT = 20
ALERT_COOLDOWN_SECONDS = 8.0
VIDEO_TARGET_PROCESSED_FPS = 5.0
VIDEO_MAX_PROCESSED_FRAMES = 96
VIDEO_TRACK_IMGSZ = 736
TRACK_CONFIDENCE = 0.22
TRACK_IOU = 0.5
LOW_LIGHT_MEAN_THRESHOLD = 82.0
LOW_LIGHT_STD_THRESHOLD = 58.0
AMBULANCE_TEXT_VARIANTS = ("AMBULANCE", "ECNALUBMA")
AMBULANCE_TEXT_MATCH_THRESHOLD = 0.38
RED_CROSS_RED_RATIO_THRESHOLD = 0.03
EMERGENCY_LIGHT_RATIO_THRESHOLD = 0.012
TRACK_HISTORY_LIMIT = 12
TRACK_MAX_STALE_FRAMES = 30
TRACK_OCCLUSION_MEMORY_FRAMES = 4
DEFAULT_TRACK_FPS = 1.0
STOPPED_SPEED_THRESHOLD = 5.0
SLOW_SPEED_THRESHOLD = 18.0
QUEUE_STATIONARY_FRAME_THRESHOLD = 2
MAX_TRACK_MODELS = 8
OVERSPEED_KMPH_THRESHOLD = 45.0
ACCIDENT_STATIONARY_FRAME_THRESHOLD = 6
ACCIDENT_SUDDEN_STOP_THRESHOLD = 14.0
ACCIDENT_OVERLAP_THRESHOLD = 0.22
ACCIDENT_CENTER_RISK_THRESHOLD = 0.3
EMERGENCY_LOCK_TIMEOUT_SECONDS = 10.0
EMERGENCY_TRACK_MISSING_TIMEOUT_SECONDS = 2.5
MAX_HISTORY = 20
PREDICTION_LOOKBACK = 5
PREDICTION_WEIGHT = 0.9
MAP_ROUTE_LOCK_SECONDS_PER_JUNCTION = 15.0
MAP_ROUTE_MAX_LOCK_SECONDS = 90.0
DEFAULT_GREEN_WAVE_SPEED_KMPH = 32.0


class AmbulanceYoloClassifier:
    """Optional YOLO classifier for ambulance-vs-nonambulance crops."""

    def __init__(self) -> None:
        self._model: YOLO | None = None
        self._lock = asyncio.Lock()

    async def predict(self, crop: np.ndarray) -> tuple[bool, float]:
        model = await self._get_model()
        return self._predict_with_model(model, crop)

    async def _get_model(self) -> YOLO | None:
        if self._model is not None:
            return self._model
        if not AMBULANCE_CLASSIFIER_PATH.exists():
            return None

        async with self._lock:
            if self._model is None and AMBULANCE_CLASSIFIER_PATH.exists():
                self._model = await asyncio.to_thread(YOLO, str(AMBULANCE_CLASSIFIER_PATH))
        return self._model

    def predict_sync(self, crop: np.ndarray) -> tuple[bool, float]:
        return self._predict_with_model(self._model, crop)

    def _predict_with_model(self, model: YOLO | None, crop: np.ndarray) -> tuple[bool, float]:
        if model is None or crop.size == 0:
            return False, 0.0

        results = model.predict(crop, verbose=False, imgsz=224)
        probs = results[0].probs
        if probs is None:
            return False, 0.0

        top_index = int(probs.top1)
        confidence = float(probs.top1conf.item())
        class_name = str(results[0].names.get(top_index, "")).strip().lower()
        return class_name == "ambulance" and confidence >= 0.65, round(confidence, 3)


class VehicleDetector:
    """Lazy-load YOLO and return only supported vehicle detections."""

    def __init__(self) -> None:
        self._model: YOLO | None = None
        self._tracking_models: Dict[str, YOLO] = {}
        self.tracking_state: Dict[str, Dict[int, Dict[str, Any]]] = {}
        self._tracking_context: Dict[str, Dict[str, Any]] = {}
        self._tracking_last_used: Dict[str, float] = {}
        self._calibration_state: Dict[str, Dict[str, Any]] = {}
        self._emergency_lock: Dict[str, Any] = {
            "active": False,
            "direction": None,
            "track_id": None,
            "stream_key": None,
            "start_time": 0.0,
            "locked": False,
        }
        self._lock = asyncio.Lock()
        self._ambulance_classifier = AmbulanceYoloClassifier()

    def _resolve_stream_key(self, source_type: str, stream_id: str | None, filename: str | None = None) -> str:
        raw = (stream_id or Path(filename or "").stem or source_type).strip().lower()
        safe = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-") or source_type
        if source_type == "image" and stream_id is None and "frame" not in safe:
            safe = f"upload-{safe}-{int(time.time() * 1000)}"
        return safe

    def _parse_point_payload(self, raw_points: str | None, *, name: str) -> list[list[float]] | None:
        if not raw_points:
            return None
        try:
            parsed = json.loads(raw_points)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid {name} JSON payload.") from exc
        if not isinstance(parsed, list) or len(parsed) != 4:
            raise HTTPException(status_code=400, detail=f"{name} must contain exactly 4 points.")
        points: list[list[float]] = []
        for point in parsed:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise HTTPException(status_code=400, detail=f"Each point in {name} must contain 2 numeric values.")
            points.append([float(point[0]), float(point[1])])
        return points

    def _set_homography_calibration(
        self,
        stream_key: str,
        image_points: list[list[float]] | None,
        real_points: list[list[float]] | None,
    ) -> None:
        if image_points is None or real_points is None:
            return
        image_array = np.array(image_points, dtype=np.float32)
        real_array = np.array(real_points, dtype=np.float32)
        matrix, _ = cv2.findHomography(image_array, real_array)
        if matrix is None:
            raise HTTPException(status_code=400, detail="Could not compute homography from the provided calibration points.")
        self._calibration_state[stream_key] = {
            "image_points": image_points,
            "real_points": real_points,
            "matrix": matrix,
            "updated_at": round(time.time(), 6),
        }

    def _transform_world_point(self, stream_key: str, point: tuple[float, float]) -> tuple[float, float] | None:
        calibration = self._calibration_state.get(stream_key)
        matrix = calibration.get("matrix") if calibration else None
        if matrix is None:
            return None
        source = np.array([[[float(point[0]), float(point[1])]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(source, matrix)
        return float(transformed[0][0][0]), float(transformed[0][0][1])

    def _resolve_approach_direction(self, stream_key: str, fallback: str | None = None) -> str | None:
        lowered = stream_key.lower()
        for direction in JUNCTION_DIRECTIONS:
            if direction in lowered:
                return direction
        return fallback

    def get_emergency_lock_state(self) -> Dict[str, Any]:
        return {
            "active": bool(self._emergency_lock.get("active")),
            "direction": self._emergency_lock.get("direction"),
            "locked": bool(self._emergency_lock.get("locked")),
            "track_id": self._emergency_lock.get("track_id"),
            "start_time": float(self._emergency_lock.get("start_time") or 0.0),
        }

    async def detect(
        self,
        image_bytes: bytes,
        *,
        stream_id: str | None = None,
        filename: str | None = None,
        image_points: str | None = None,
        real_points: str | None = None,
    ) -> Dict[str, Any]:
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Image payload is empty.")

        frame = self._decode_image(image_bytes)
        stream_key = self._resolve_stream_key("image", stream_id, filename)
        self._set_homography_calibration(
            stream_key,
            self._parse_point_payload(image_points, name="image_points"),
            self._parse_point_payload(real_points, name="real_points"),
        )
        return await self._analyze_frame(frame, source_type="image", stream_key=stream_key, fps=DEFAULT_TRACK_FPS)

    async def detect_upload(
        self,
        file_bytes: bytes,
        content_type: str,
        filename: str | None = None,
        *,
        stream_id: str | None = None,
        fps: float | None = None,
        image_points: str | None = None,
        real_points: str | None = None,
    ) -> Dict[str, Any]:
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        if content_type.startswith("image/"):
            return await self.detect(
                file_bytes,
                stream_id=stream_id,
                filename=filename,
                image_points=image_points,
                real_points=real_points,
            )
        if content_type.startswith("video/"):
            await self._get_model()
            await self._ambulance_classifier._get_model()
            stream_key = self._resolve_stream_key("video", stream_id, filename)
            self._set_homography_calibration(
                stream_key,
                self._parse_point_payload(image_points, name="image_points"),
                self._parse_point_payload(real_points, name="real_points"),
            )
            return await asyncio.to_thread(self._analyze_video_bytes, file_bytes, filename, stream_key, fps)
        raise HTTPException(status_code=400, detail="Expected an image or video upload.")

    async def _analyze_frame(self, frame: np.ndarray, *, source_type: str, stream_key: str, fps: float) -> Dict[str, Any]:
        model = await self._get_tracking_model(stream_key)
        results = await asyncio.to_thread(self._track_frame, model, frame, video_mode=source_type == "video")
        detections, uncertain_detections = await self._build_detection_lists_async(frame, results[0].boxes, results[0].names)
        tracking_metrics = self._update_tracking_metrics(
            stream_key=stream_key,
            detections=detections,
            image_width=frame.shape[1],
            image_height=frame.shape[0],
            fps=fps,
        )
        accident_alert = self._detect_accident(tracking_metrics["scene_tracks"], image_height=frame.shape[0])
        traffic_metrics = self._summarize_traffic(
            tracking_metrics["scene_tracks"],
            frame.shape[1],
            frame.shape[0],
            accident_alert,
            fallback_detections=detections,
        )
        emergency_count = len(tracking_metrics["emergency_labels"])
        if tracking_metrics["tracked_emergency_ids"]:
            traffic_metrics["signal_priority_value"] = max(int(traffic_metrics["signal_priority_value"]), 95)
            tracked_directions = sorted({item["direction"] for item in tracking_metrics["vehicles"] if item["id"] in tracking_metrics["tracked_emergency_ids"] and item["direction"] != "unknown"})
            if tracked_directions:
                traffic_metrics["signal_priority_reason"] = f"Emergency vehicle tracked moving {', '.join(tracked_directions)}. Favor immediate green priority."

        return {
            "detections": detections,
            "uncertain_detections": uncertain_detections,
            "vehicles": tracking_metrics["vehicles"],
            "source_type": source_type,
            "image": {"width": int(frame.shape[1]), "height": int(frame.shape[0])},
            "model": "yolov8n + bytetrack + ambulance yolo classifier",
            "vehicle_count": tracking_metrics["active_vehicle_count"],
            "tracked_vehicle_count": tracking_metrics["tracked_vehicle_count"],
            "uncertain_count": len(uncertain_detections),
            "emergency_count": emergency_count,
            "vehicle_types": traffic_metrics["vehicle_types"],
            "queue_length": traffic_metrics["queue_length"],
            "flow_count": tracking_metrics["flow_count"],
            "flow_by_direction": tracking_metrics["flow_by_direction"],
            "average_speed": tracking_metrics["average_speed"],
            "average_speed_kmph": tracking_metrics["average_speed_kmph"],
            "turn_analysis": tracking_metrics["turn_analysis"],
            "entry_counts": tracking_metrics["entry_counts"],
            "exit_counts": tracking_metrics["exit_counts"],
            "density_percent": traffic_metrics["density_percent"],
            "density_level": traffic_metrics["density_level"],
            "emergency_detected": traffic_metrics["emergency_detected"],
            "emergency_labels": traffic_metrics["emergency_labels"],
            "emergency": tracking_metrics["emergency"],
            "emergency_active": tracking_metrics["emergency"]["active"],
            "locked_direction": tracking_metrics["emergency"]["direction"] if tracking_metrics["emergency"]["locked"] else None,
            "signal_priority_value": traffic_metrics["signal_priority_value"],
            "signal_priority_reason": traffic_metrics["signal_priority_reason"],
            "accident_detected": accident_alert["detected"],
            "accident_confidence": accident_alert["confidence"],
            "accident_message": accident_alert["message"],
            "calibration_active": stream_key in self._calibration_state,
            "breakdown": {"ambulance": emergency_count, "fire_engine": 0},
            "processed_at": round(time.time(), 6),
        }

    def _analyze_video_bytes(
        self,
        file_bytes: bytes,
        filename: str | None = None,
        stream_key: str | None = None,
        fps_override: float | None = None,
    ) -> Dict[str, Any]:
        suffix = Path(filename or "upload.mp4").suffix or ".mp4"
        temp_path: str | None = None
        active_stream_key = stream_key or self._resolve_stream_key("video", None, filename)
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(file_bytes)
                temp_path = temp_file.name

            capture = cv2.VideoCapture(temp_path)
            if not capture.isOpened():
                raise HTTPException(status_code=400, detail="Could not read the uploaded video.")

            self._reset_tracking_stream(active_stream_key)
            frame_count = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
            video_fps = _coerce_float(capture.get(cv2.CAP_PROP_FPS)) or 12.0
            frame_stride = self._video_frame_stride(frame_count, video_fps)
            effective_fps = max((fps_override or video_fps) / frame_stride, 0.5)

            sampled_results: list[Dict[str, Any]] = []
            frame_index = 0
            while True:
                success, frame = capture.read()
                if not success or frame is None:
                    break
                if frame_index % frame_stride == 0:
                    processed_frame = self._enhance_video_frame(frame)
                    sampled_results.append(
                        self._analyze_frame_sync(
                            processed_frame,
                            source_type="video",
                            stream_key=active_stream_key,
                            fps=effective_fps,
                        )
                    )
                frame_index += 1
            capture.release()

            if not sampled_results:
                raise HTTPException(status_code=400, detail="No readable frames were found in the uploaded video.")

            representative = max(
                sampled_results,
                key=lambda item: (
                    bool(item.get("emergency_detected")),
                    float(item.get("tracked_vehicle_count", 0)),
                    float(item.get("flow_count", 0)),
                    float(item.get("signal_priority_value", 0)),
                    float(item.get("vehicle_count", 0)),
                    float(item.get("density_percent", 0)),
                ),
            )
            richest_frame = max(
                sampled_results,
                key=lambda item: (
                    float(item.get("tracked_vehicle_count", 0)),
                    float(item.get("vehicle_count", 0)),
                    float(item.get("flow_count", 0)),
                    -float(item.get("uncertain_count", 0)),
                ),
            )
            average_count = sum(float(item.get("vehicle_count", 0)) for item in sampled_results) / len(sampled_results)
            average_tracked_count = sum(float(item.get("tracked_vehicle_count", 0)) for item in sampled_results) / len(sampled_results)
            peak_queue = max(int(item.get("queue_length", 0)) for item in sampled_results)
            peak_density = max(float(item.get("density_percent", 0)) for item in sampled_results)
            peak_flow = max(int(item.get("flow_count", 0)) for item in sampled_results)

            merged = dict(representative)
            merged["source_type"] = "video"
            merged["sampled_frames"] = len(sampled_results)
            merged["frame_stride"] = frame_stride
            merged["processed_fps"] = round(effective_fps, 2)
            merged["tracked_vehicle_count"] = max(int(item.get("tracked_vehicle_count", 0)) for item in sampled_results)
            merged["flow_count"] = peak_flow
            merged["flow_by_direction"] = {
                direction: max(int(item.get("flow_by_direction", {}).get(direction, 0)) for item in sampled_results)
                for direction in JUNCTION_DIRECTIONS
            }
            merged["average_speed"] = round(
                sum(float(item.get("average_speed", 0.0)) for item in sampled_results) / len(sampled_results),
                2,
            )
            merged["average_speed_kmph"] = round(
                sum(float(item.get("average_speed_kmph", 0.0)) for item in sampled_results) / len(sampled_results),
                2,
            )
            merged["vehicles"] = richest_frame.get("vehicles", merged.get("vehicles", []))
            merged["turn_analysis"] = richest_frame.get("turn_analysis", {})
            merged["entry_counts"] = richest_frame.get("entry_counts", {})
            merged["exit_counts"] = richest_frame.get("exit_counts", {})
            merged["emergency"] = sampled_results[-1].get("emergency", {"active": False, "direction": None, "locked": False})
            merged["emergency_active"] = bool(merged["emergency"].get("active"))
            merged["locked_direction"] = merged["emergency"].get("direction") if merged["emergency"].get("locked") else None
            merged["video_summary"] = {
                "average_vehicle_count": round(average_count, 2),
                "average_tracked_vehicle_count": round(average_tracked_count, 2),
                "peak_vehicle_count": max(int(item.get("vehicle_count", 0)) for item in sampled_results),
                "peak_queue_length": peak_queue,
                "peak_density_percent": peak_density,
                "emergency_detected": any(bool(item.get("emergency_detected")) for item in sampled_results),
                "accident_detected": any(bool(item.get("accident_detected")) for item in sampled_results),
                "tracked_vehicle_count": max(int(item.get("tracked_vehicle_count", 0)) for item in sampled_results),
                "flow_count": peak_flow,
                "average_speed": round(
                    sum(float(item.get("average_speed", 0.0)) for item in sampled_results) / len(sampled_results),
                    2,
                ),
                "average_speed_kmph": round(
                    sum(float(item.get("average_speed_kmph", 0.0)) for item in sampled_results) / len(sampled_results),
                    2,
                ),
                "frame_stride": frame_stride,
                "processed_fps": round(effective_fps, 2),
            }
            return merged
        finally:
            self._reset_tracking_stream(active_stream_key)
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def _analyze_frame_sync(self, frame: np.ndarray, *, source_type: str, stream_key: str, fps: float) -> Dict[str, Any]:
        model = self._get_tracking_model_sync(stream_key)
        results = self._track_frame(model, frame, video_mode=source_type == "video")
        detections, uncertain_detections = self._build_detection_lists_sync(frame, results[0].boxes, results[0].names)
        tracking_metrics = self._update_tracking_metrics(
            stream_key=stream_key,
            detections=detections,
            image_width=frame.shape[1],
            image_height=frame.shape[0],
            fps=fps,
        )
        accident_alert = self._detect_accident(tracking_metrics["scene_tracks"], image_height=frame.shape[0])
        traffic_metrics = self._summarize_traffic(
            tracking_metrics["scene_tracks"],
            frame.shape[1],
            frame.shape[0],
            accident_alert,
            fallback_detections=detections,
        )
        emergency_count = len(tracking_metrics["emergency_labels"])
        if tracking_metrics["tracked_emergency_ids"]:
            traffic_metrics["signal_priority_value"] = max(int(traffic_metrics["signal_priority_value"]), 95)
            tracked_directions = sorted({item["direction"] for item in tracking_metrics["vehicles"] if item["id"] in tracking_metrics["tracked_emergency_ids"] and item["direction"] != "unknown"})
            if tracked_directions:
                traffic_metrics["signal_priority_reason"] = f"Emergency vehicle tracked moving {', '.join(tracked_directions)}. Favor immediate green priority."
        return {
            "detections": detections,
            "uncertain_detections": uncertain_detections,
            "vehicles": tracking_metrics["vehicles"],
            "source_type": source_type,
            "image": {"width": int(frame.shape[1]), "height": int(frame.shape[0])},
            "model": "yolov8n + bytetrack + ambulance yolo classifier",
            "vehicle_count": tracking_metrics["active_vehicle_count"],
            "tracked_vehicle_count": tracking_metrics["tracked_vehicle_count"],
            "uncertain_count": len(uncertain_detections),
            "emergency_count": emergency_count,
            "vehicle_types": traffic_metrics["vehicle_types"],
            "queue_length": traffic_metrics["queue_length"],
            "flow_count": tracking_metrics["flow_count"],
            "flow_by_direction": tracking_metrics["flow_by_direction"],
            "average_speed": tracking_metrics["average_speed"],
            "average_speed_kmph": tracking_metrics["average_speed_kmph"],
            "turn_analysis": tracking_metrics["turn_analysis"],
            "entry_counts": tracking_metrics["entry_counts"],
            "exit_counts": tracking_metrics["exit_counts"],
            "density_percent": traffic_metrics["density_percent"],
            "density_level": traffic_metrics["density_level"],
            "emergency_detected": traffic_metrics["emergency_detected"],
            "emergency_labels": traffic_metrics["emergency_labels"],
            "emergency": tracking_metrics["emergency"],
            "emergency_active": tracking_metrics["emergency"]["active"],
            "locked_direction": tracking_metrics["emergency"]["direction"] if tracking_metrics["emergency"]["locked"] else None,
            "signal_priority_value": traffic_metrics["signal_priority_value"],
            "signal_priority_reason": traffic_metrics["signal_priority_reason"],
            "accident_detected": accident_alert["detected"],
            "accident_confidence": accident_alert["confidence"],
            "accident_message": accident_alert["message"],
            "calibration_active": stream_key in self._calibration_state,
            "breakdown": {"ambulance": emergency_count, "fire_engine": 0},
            "processed_at": round(time.time(), 6),
        }

    def _decode_image(self, image_bytes: bytes) -> np.ndarray:
        encoded = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None:
            raise HTTPException(status_code=400, detail="Could not decode the uploaded image.")
        return frame

    async def _get_model(self) -> YOLO:
        if self._model is not None:
            return self._model

        async with self._lock:
            if self._model is None:
                model_source = str(BASE_DETECTOR_MODEL_PATH if BASE_DETECTOR_MODEL_PATH.exists() else "yolov8n.pt")
                self._model = await asyncio.to_thread(YOLO, model_source)
        return self._model

    async def _get_tracking_model(self, stream_key: str) -> YOLO:
        existing = self._tracking_models.get(stream_key)
        if existing is not None:
            self._tracking_last_used[stream_key] = time.time()
            return existing

        async with self._lock:
            if stream_key not in self._tracking_models:
                self._cleanup_tracking_models()
                self._tracking_models[stream_key] = await asyncio.to_thread(YOLO, "yolov8n.pt")
            self._tracking_last_used[stream_key] = time.time()
            return self._tracking_models[stream_key]

    def _get_tracking_model_sync(self, stream_key: str) -> YOLO:
        model = self._tracking_models.get(stream_key)
        if model is None:
            self._cleanup_tracking_models()
            model = YOLO("yolov8n.pt")
            self._tracking_models[stream_key] = model
        self._tracking_last_used[stream_key] = time.time()
        return model

    def _cleanup_tracking_models(self) -> None:
        while len(self._tracking_models) >= MAX_TRACK_MODELS:
            oldest_key = min(self._tracking_last_used, key=self._tracking_last_used.get)
            self._tracking_models.pop(oldest_key, None)
            self.tracking_state.pop(oldest_key, None)
            self._tracking_context.pop(oldest_key, None)
            self._tracking_last_used.pop(oldest_key, None)

    def _reset_tracking_stream(self, stream_key: str) -> None:
        model = self._tracking_models.get(stream_key)
        predictor = getattr(model, "predictor", None)
        if predictor is not None and hasattr(predictor, "trackers"):
            predictor.trackers = None
        self.tracking_state.pop(stream_key, None)
        self._tracking_context.pop(stream_key, None)
        if stream_key in self._tracking_last_used:
            self._tracking_last_used[stream_key] = time.time()

    def _track_frame(self, model: YOLO, frame: np.ndarray, *, video_mode: bool) -> Any:
        return model.track(
            frame,
            verbose=False,
            imgsz=VIDEO_TRACK_IMGSZ if video_mode else 640,
            tracker="bytetrack.yaml",
            persist=True,
            conf=TRACK_CONFIDENCE,
            iou=TRACK_IOU,
            classes=sorted(VEHICLE_CLASS_IDS),
        )

    def _enhance_video_frame(self, frame: np.ndarray) -> np.ndarray:
        grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(grayscale))
        contrast = float(np.std(grayscale))
        if brightness >= LOW_LIGHT_MEAN_THRESHOLD and contrast >= LOW_LIGHT_STD_THRESHOLD:
            return frame

        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
        enhanced_l = clahe.apply(l_channel)
        enhanced = cv2.merge((enhanced_l, a_channel, b_channel))
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def _video_frame_stride(self, frame_count: int, video_fps: float) -> int:
        target_fps = min(max(video_fps, 1.0), VIDEO_TARGET_PROCESSED_FPS)
        stride = max(1, int(round(video_fps / target_fps)))
        if frame_count > 0:
            stride = max(stride, int(math.ceil(frame_count / VIDEO_MAX_PROCESSED_FRAMES)))
        return stride

    async def _classify_ambulance(
        self,
        frame: np.ndarray,
        base_label: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> tuple[list[str], bool, float]:
        if base_label not in {"car", "bus", "truck"}:
            return [], False, 0.0

        crop = self._crop_roi(frame, x1, y1, x2, y2)
        if crop is None:
            return [], False, 0.0
        cues = self._collect_ambulance_cues(crop)
        classifier_match, confidence = await self._ambulance_classifier.predict(crop)
        return cues, self._resolve_ambulance_decision(base_label, cues, classifier_match, confidence), confidence

    def _classify_ambulance_sync(
        self,
        frame: np.ndarray,
        base_label: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> tuple[list[str], bool, float]:
        if base_label not in {"car", "bus", "truck"}:
            return [], False, 0.0

        crop = self._crop_roi(frame, x1, y1, x2, y2)
        if crop is None:
            return [], False, 0.0
        cues = self._collect_ambulance_cues(crop)
        classifier_match, confidence = self._ambulance_classifier.predict_sync(crop)
        return cues, self._resolve_ambulance_decision(base_label, cues, classifier_match, confidence), confidence

    def _resolve_ambulance_decision(
        self,
        base_label: str,
        cues: list[str],
        classifier_match: bool,
        classifier_confidence: float,
    ) -> bool:
        if base_label not in {"car", "bus", "truck"}:
            return False

        cue_set = set(cues)
        strong_visual_match = len(cue_set) >= 2 or {"ambulance_text", "emergency_lights"}.issubset(cue_set)
        if classifier_match and cue_set:
            return True
        if strong_visual_match and classifier_confidence >= 0.45:
            return True
        return False

    async def _build_detection_lists_async(
        self,
        frame: np.ndarray,
        boxes: Any,
        names: Dict[int, str],
    ) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
        detections: list[Dict[str, Any]] = []
        uncertain_detections: list[Dict[str, Any]] = []
        if boxes is None:
            return detections, uncertain_detections

        for box in boxes:
            class_id = int(box.cls[0].item())
            if class_id not in VEHICLE_CLASS_IDS:
                continue

            track_id = int(box.id[0].item()) if getattr(box, "id", None) is not None else None
            x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
            confidence = float(box.conf[0].item())
            base_label = VEHICLE_LABELS.get(class_id, names.get(class_id, "vehicle"))
            ambulance_cues, is_ambulance, ambulance_confidence = await self._classify_ambulance(frame, base_label, x1, y1, x2, y2)
            detections, uncertain_detections = self._append_detection(
                frame=frame,
                detections=detections,
                uncertain_detections=uncertain_detections,
                class_id=class_id,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                track_id=track_id,
                base_label=base_label,
                confidence=confidence,
                ambulance_confidence=ambulance_confidence,
                ambulance_cues=ambulance_cues,
                is_ambulance=is_ambulance,
            )
        return detections, uncertain_detections

    def _build_detection_lists_sync(
        self,
        frame: np.ndarray,
        boxes: Any,
        names: Dict[int, str],
    ) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
        detections: list[Dict[str, Any]] = []
        uncertain_detections: list[Dict[str, Any]] = []
        if boxes is None:
            return detections, uncertain_detections

        for box in boxes:
            class_id = int(box.cls[0].item())
            if class_id not in VEHICLE_CLASS_IDS:
                continue

            track_id = int(box.id[0].item()) if getattr(box, "id", None) is not None else None
            x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
            confidence = float(box.conf[0].item())
            base_label = VEHICLE_LABELS.get(class_id, names.get(class_id, "vehicle"))
            ambulance_cues, is_ambulance, ambulance_confidence = self._classify_ambulance_sync(frame, base_label, x1, y1, x2, y2)
            detections, uncertain_detections = self._append_detection(
                frame=frame,
                detections=detections,
                uncertain_detections=uncertain_detections,
                class_id=class_id,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                track_id=track_id,
                base_label=base_label,
                confidence=confidence,
                ambulance_confidence=ambulance_confidence,
                ambulance_cues=ambulance_cues,
                is_ambulance=is_ambulance,
            )
        return detections, uncertain_detections

    def _append_detection(
        self,
        *,
        frame: np.ndarray,
        detections: list[Dict[str, Any]],
        uncertain_detections: list[Dict[str, Any]],
        class_id: int,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        track_id: int | None,
        base_label: str,
        confidence: float,
        ambulance_confidence: float,
        ambulance_cues: list[str],
        is_ambulance: bool,
    ) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
        crop = self._crop_roi(frame, x1, y1, x2, y2)
        if crop is None:
            return detections, uncertain_detections

        final_confidence = round(max(confidence, ambulance_confidence), 3)
        resolved_label = "ambulance" if is_ambulance else base_label
        box_payload = {
            "x": round(x1, 1),
            "y": round(y1, 1),
            "width": round(max(0.0, x2 - x1), 1),
            "height": round(max(0.0, y2 - y1), 1),
        }
        centroid = {
            "x": round(box_payload["x"] + (box_payload["width"] / 2.0), 1),
            "y": round(box_payload["y"] + (box_payload["height"] / 2.0), 1),
        }
        front_features = self._front_view_features(crop, box_payload, frame.shape[1], frame.shape[0])
        vehicle_type = self._resolve_front_vehicle_type(resolved_label, box_payload, front_features, is_ambulance)
        payload = {
            "label": vehicle_type,
            "vehicle_type": vehicle_type,
            "base_vehicle_type": base_label,
            "track_id": track_id,
            "confidence": final_confidence,
            "confidence_level": self._front_confidence_level(final_confidence, front_features),
            "class_id": class_id,
            "is_emergency": is_ambulance,
            "ambulance_cues": ambulance_cues,
            "box": box_payload,
            "centroid": centroid,
            "position": self._position_label(box_payload, frame.shape[1]),
            "clue": self._front_vehicle_clue(vehicle_type, front_features, ambulance_cues),
            "front_view_clear": front_features["clear_front_view"],
            "front_view_score": front_features["clarity_score"],
            "uncertain_reason": front_features["uncertain_reason"],
        }
        detections.append(payload)
        if not front_features["clear_front_view"]:
            uncertain_detections.append(payload)
        return detections, uncertain_detections

    def _crop_roi(self, frame: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> np.ndarray | None:
        height, width = frame.shape[:2]
        left = max(0, min(width - 1, int(x1)))
        top = max(0, min(height - 1, int(y1)))
        right = max(left + 1, min(width, int(x2)))
        bottom = max(top + 1, min(height, int(y2)))
        crop = frame[top:bottom, left:right]
        if crop.size == 0:
            return None
        return crop

    def _collect_ambulance_cues(self, crop: np.ndarray) -> list[str]:
        cues: list[str] = []
        if self._has_ambulance_text_cue(crop):
            cues.append("ambulance_text")
        if self._has_red_cross_symbol(crop):
            cues.append("red_cross")
        if self._has_emergency_lights(crop):
            cues.append("emergency_lights")
        return cues

    def _has_ambulance_text_cue(self, crop: np.ndarray) -> bool:
        if crop.size == 0:
            return False

        processed = self._prepare_text_candidate(crop)
        if processed is None:
            return False

        best_score = 0.0
        for word in AMBULANCE_TEXT_VARIANTS:
            score = self._match_rendered_word(processed, word)
            if score > best_score:
                best_score = score
        return best_score >= AMBULANCE_TEXT_MATCH_THRESHOLD

    def _prepare_text_candidate(self, crop: np.ndarray) -> np.ndarray | None:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        enlarged = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        filtered = cv2.bilateralFilter(enlarged, 7, 50, 50)
        _, binary = cv2.threshold(filtered, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        inverted = cv2.bitwise_not(binary)

        candidates = [binary, inverted]
        best: np.ndarray | None = None
        best_width = 0

        for image in candidates:
            contours, _ = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue

            boxes: list[tuple[int, int, int, int]] = []
            image_h, image_w = image.shape[:2]
            min_area = max(40, int(image_h * image_w * 0.0008))
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = w * h
                if area < min_area:
                    continue
                if h < image_h * 0.08:
                    continue
                if w / max(h, 1) > 4.5:
                    boxes.append((x, y, w, h))

            if not boxes:
                continue

            left = min(box[0] for box in boxes)
            top = min(box[1] for box in boxes)
            right = max(box[0] + box[2] for box in boxes)
            bottom = max(box[1] + box[3] for box in boxes)
            roi = image[max(0, top - 8) : min(image_h, bottom + 8), max(0, left - 8) : min(image_w, right + 8)]
            if roi.size == 0:
                continue
            if roi.shape[1] > best_width:
                best = roi
                best_width = roi.shape[1]

        return best

    def _match_rendered_word(self, candidate: np.ndarray, word: str) -> float:
        if candidate.size == 0:
            return 0.0

        candidate_h, candidate_w = candidate.shape[:2]
        candidate_prepped = cv2.resize(candidate, (max(candidate_w, 120), 80), interpolation=cv2.INTER_AREA if candidate_w > 120 else cv2.INTER_CUBIC)
        candidate_prepped = cv2.GaussianBlur(candidate_prepped, (3, 3), 0)

        fonts = [
            cv2.FONT_HERSHEY_SIMPLEX,
            cv2.FONT_HERSHEY_DUPLEX,
            cv2.FONT_HERSHEY_TRIPLEX,
            cv2.FONT_HERSHEY_COMPLEX,
        ]
        best = 0.0
        for font in fonts:
            template = np.zeros((80, 240), dtype=np.uint8)
            cv2.putText(template, word, (6, 56), font, 1.0, 255, 2, cv2.LINE_AA)
            template = cv2.GaussianBlur(template, (3, 3), 0)
            resized_candidate = cv2.resize(candidate_prepped, (template.shape[1], template.shape[0]), interpolation=cv2.INTER_CUBIC)
            score = float(cv2.matchTemplate(resized_candidate, template, cv2.TM_CCOEFF_NORMED)[0][0])
            best = max(best, score)
        return best

    def _has_red_cross_symbol(self, crop: np.ndarray) -> bool:
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        lower_red_a = np.array([0, 90, 70], dtype=np.uint8)
        upper_red_a = np.array([12, 255, 255], dtype=np.uint8)
        lower_red_b = np.array([168, 90, 70], dtype=np.uint8)
        upper_red_b = np.array([180, 255, 255], dtype=np.uint8)
        red_mask = cv2.inRange(hsv, lower_red_a, upper_red_a) | cv2.inRange(hsv, lower_red_b, upper_red_b)
        kernel = np.ones((3, 3), np.uint8)
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
        red_ratio = float(np.count_nonzero(red_mask)) / float(red_mask.size or 1)
        if red_ratio < RED_CROSS_RED_RATIO_THRESHOLD:
            return False

        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        crop_h, crop_w = red_mask.shape[:2]
        min_area = max(35, int(crop_h * crop_w * 0.004))
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            aspect = w / max(h, 1)
            if aspect < 0.65 or aspect > 1.35:
                continue
            roi = red_mask[y : y + h, x : x + w]
            vertical = roi[:, max(0, int(w * 0.35)) : min(w, int(w * 0.65))]
            horizontal = roi[max(0, int(h * 0.35)) : min(h, int(h * 0.65)), :]
            if vertical.size == 0 or horizontal.size == 0:
                continue
            vertical_ratio = float(np.count_nonzero(vertical)) / float(vertical.size)
            horizontal_ratio = float(np.count_nonzero(horizontal)) / float(horizontal.size)
            if vertical_ratio >= 0.38 and horizontal_ratio >= 0.38:
                return True
        return False

    def _has_emergency_lights(self, crop: np.ndarray) -> bool:
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        upper_band = hsv[: max(1, int(hsv.shape[0] * 0.35)), :]
        if upper_band.size == 0:
            return False

        lower_blue = np.array([95, 110, 120], dtype=np.uint8)
        upper_blue = np.array([130, 255, 255], dtype=np.uint8)
        lower_red_a = np.array([0, 120, 140], dtype=np.uint8)
        upper_red_a = np.array([12, 255, 255], dtype=np.uint8)
        lower_red_b = np.array([168, 120, 140], dtype=np.uint8)
        upper_red_b = np.array([180, 255, 255], dtype=np.uint8)

        blue_mask = cv2.inRange(upper_band, lower_blue, upper_blue)
        red_mask = cv2.inRange(upper_band, lower_red_a, upper_red_a) | cv2.inRange(upper_band, lower_red_b, upper_red_b)
        light_mask = blue_mask | red_mask
        light_ratio = float(np.count_nonzero(light_mask)) / float(light_mask.size or 1)
        if light_ratio < EMERGENCY_LIGHT_RATIO_THRESHOLD:
            return False

        contours, _ = cv2.findContours(light_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        bright_blobs = 0
        min_area = max(6, int(upper_band.shape[0] * upper_band.shape[1] * 0.0007))
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= min_area:
                bright_blobs += 1
        return bright_blobs >= 2

    def _front_view_features(
        self,
        crop: np.ndarray,
        box: Dict[str, float],
        image_width: int,
        image_height: int,
    ) -> Dict[str, Any]:
        if crop.size == 0:
            return {
                "clear_front_view": False,
                "clarity_score": 0.0,
                "symmetry_score": 0.0,
                "shape": "unknown",
                "uncertain_reason": "front view crop is empty",
            }

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (72, 72), interpolation=cv2.INTER_AREA)
        left_half = resized[:, :36]
        right_half = cv2.flip(resized[:, 36:], 1)
        symmetry_score = float(1.0 - (np.mean(np.abs(left_half.astype(np.float32) - right_half.astype(np.float32))) / 255.0))

        area_ratio = (float(box["width"]) * float(box["height"])) / max(float(image_width * image_height), 1.0)
        border_touch = (
            box["x"] <= image_width * 0.02
            or box["y"] <= image_height * 0.02
            or (box["x"] + box["width"]) >= image_width * 0.98
            or (box["y"] + box["height"]) >= image_height * 0.98
        )
        aspect = float(box["width"]) / max(float(box["height"]), 1.0)
        shape = "wide" if aspect >= 1.35 else "narrow" if aspect <= 0.78 else "balanced"

        clarity_score = max(
            0.0,
            min(
                1.0,
                (symmetry_score * 0.55)
                + min(area_ratio * 42.0, 0.3)
                + (0.15 if not border_touch else 0.0),
            ),
        )

        unclear_reasons: list[str] = []
        if border_touch:
            unclear_reasons.append("partial vehicle near image edge")
        if area_ratio < 0.0035:
            unclear_reasons.append("front view is too small")
        if symmetry_score < 0.42:
            unclear_reasons.append("front view is unclear or not frontal")

        clear_front_view = clarity_score >= 0.5 and symmetry_score >= 0.42 and area_ratio >= 0.0035 and not border_touch
        uncertain_reason = "" if clear_front_view else ", ".join(unclear_reasons) or "front view is unclear"
        return {
            "clear_front_view": clear_front_view,
            "clarity_score": round(clarity_score, 3),
            "symmetry_score": round(symmetry_score, 3),
            "shape": shape,
            "aspect": round(aspect, 3),
            "area_ratio": round(area_ratio, 5),
            "uncertain_reason": uncertain_reason,
        }

    def _resolve_front_vehicle_type(
        self,
        label: str,
        box: Dict[str, float],
        front_features: Dict[str, Any],
        is_emergency: bool,
    ) -> str:
        if is_emergency or label == "ambulance":
            return "ambulance"
        if label in {"car", "motorcycle"}:
            aspect = float(front_features.get("aspect", 1.0))
            width = float(box["width"])
            height = float(box["height"])
            if 0.8 <= aspect <= 1.2 and width >= 36 and height >= 40 and front_features.get("shape") == "balanced":
                return "auto_rickshaw"
        return label

    def _front_confidence_level(self, confidence: float, front_features: Dict[str, Any]) -> str:
        blended = (confidence * 0.6) + (float(front_features.get("clarity_score", 0.0)) * 0.4)
        if blended >= 0.75 and front_features.get("clear_front_view"):
            return "high"
        if blended >= 0.52:
            return "medium"
        return "low"

    def _front_vehicle_clue(self, label: str, front_features: Dict[str, Any], ambulance_cues: list[str]) -> str:
        if label == "ambulance":
            cue_text = ", ".join(cue.replace("_", " ") for cue in ambulance_cues) if ambulance_cues else "front emergency markers"
            return f"Front emergency cues detected: {cue_text}"
        if label == "car":
            return "Two headlights, front grille, wide windshield"
        if label == "motorcycle":
            return "Single headlight area, visible handlebar, narrow body"
        if label == "bus":
            return "Large flat front, wide windshield, tall rectangular face"
        if label == "truck":
            return "Tall front cabin, large bumper, heavy front structure"
        if label == "bicycle":
            return "Thin front fork, no engine body, narrow frame"
        if label == "auto_rickshaw":
            return "Compact front cabin, small windshield, narrow 3-wheel structure"
        return f"Front-facing vehicle with {front_features.get('shape', 'balanced')} front structure"

    def _confidence_level(self, confidence: float) -> str:
        if confidence >= 0.75:
            return "high"
        if confidence >= 0.5:
            return "medium"
        return "low"

    def _position_label(self, box: Dict[str, float], image_width: int) -> str:
        center_x = float(box["x"]) + (float(box["width"]) / 2.0)
        section = max(float(image_width), 1.0) / 3.0
        if center_x < section:
            return "left"
        if center_x < section * 2.0:
            return "center"
        return "right"

    def _detect_accident(
        self,
        active_tracks: list[Dict[str, Any]],
        *,
        image_height: int,
    ) -> Dict[str, Any]:
        if any(bool(item.get("is_emergency")) for item in active_tracks):
            return {
                "detected": False,
                "confidence": 0.0,
                "message": "",
            }

        candidates = [
            item
            for item in active_tracks
            if (
                item["label"] in ACCIDENT_LABELS
                and bool(item.get("stopped"))
                and int(item.get("stopped_frames", 0)) >= ACCIDENT_STATIONARY_FRAME_THRESHOLD
                and bool(item.get("sudden_stop"))
            )
        ]
        best_score = 0.0
        best_pair: tuple[str, str] | None = None

        for candidate in candidates:
            box = candidate["box"]
            center_x = float(box["x"]) + (float(box["width"]) / 2.0)
            center_y = float(box["y"]) + (float(box["height"]) / 2.0)
            abnormal_position = (
                candidate.get("current_zone") == "intersection_center"
                or not self._is_queue_zone((center_x, center_y), image_height)
                or "illegal_stop" in candidate.get("flags", [])
            )
            overlap_partner: Dict[str, Any] | None = None
            overlap_score = 0.0

            for other in active_tracks:
                if other["id"] == candidate["id"] or other["label"] not in ACCIDENT_LABELS:
                    continue
                overlap = self._intersection_over_union(candidate["box"], other["box"])
                if overlap > overlap_score:
                    overlap_score = overlap
                    overlap_partner = other

            if not abnormal_position and overlap_score < ACCIDENT_OVERLAP_THRESHOLD:
                continue

            sudden_stop_score = min(
                0.35,
                max(float(candidate.get("recent_peak_speed", 0.0)) - float(candidate.get("speed", 0.0)), 0.0)
                / max(ACCIDENT_SUDDEN_STOP_THRESHOLD * 1.2, 1.0),
            )
            stationary_score = min(0.3, float(candidate.get("stopped_frames", 0)) / 18.0)
            overlap_component = min(0.35, overlap_score) if overlap_score >= ACCIDENT_OVERLAP_THRESHOLD else 0.0
            abnormal_component = ACCIDENT_CENTER_RISK_THRESHOLD if abnormal_position else 0.0
            score = round(min(0.99, sudden_stop_score + stationary_score + overlap_component + abnormal_component), 3)
            if score > best_score:
                best_score = score
                if overlap_partner is not None:
                    best_pair = (candidate["label"], overlap_partner["label"])
                else:
                    best_pair = (candidate["label"], candidate["label"])

        detected = best_pair is not None and best_score >= 0.58
        message = ""
        if detected and best_pair is not None:
            if best_pair[0] == best_pair[1]:
                message = f"Possible road accident detected involving a stopped {best_pair[0]}."
            else:
                message = f"Possible road accident detected between {best_pair[0]} and {best_pair[1]}."

        return {
            "detected": detected,
            "confidence": best_score if detected else 0.0,
            "message": message,
        }

    def _intersection_over_union(self, first: Dict[str, float], second: Dict[str, float]) -> float:
        left = max(first["x"], second["x"])
        top = max(first["y"], second["y"])
        right = min(first["x"] + first["width"], second["x"] + second["width"])
        bottom = min(first["y"] + first["height"], second["y"] + second["height"])
        intersection_width = max(0.0, right - left)
        intersection_height = max(0.0, bottom - top)
        intersection = intersection_width * intersection_height
        if intersection <= 0.0:
            return 0.0

        first_area = max(1.0, first["width"] * first["height"])
        second_area = max(1.0, second["width"] * second["height"])
        union = first_area + second_area - intersection
        return intersection / max(union, 1.0)

    def _center_distance(self, first: Dict[str, float], second: Dict[str, float]) -> float:
        first_center_x = first["x"] + (first["width"] / 2.0)
        first_center_y = first["y"] + (first["height"] / 2.0)
        second_center_x = second["x"] + (second["width"] / 2.0)
        second_center_y = second["y"] + (second["height"] / 2.0)
        return float(np.hypot(second_center_x - first_center_x, second_center_y - first_center_y))

    def _track_is_stopped(self, track_data: Dict[str, Any]) -> bool:
        speed_kmph = float(track_data.get("speed_kmph") or 0.0)
        if speed_kmph > 0.0:
            return speed_kmph < 5.0
        return float(track_data.get("speed") or 0.0) < STOPPED_SPEED_THRESHOLD

    def _active_scene_tracks(self, state: Dict[int, Dict[str, Any]], frame_index: int) -> list[Dict[str, Any]]:
        active_tracks: list[Dict[str, Any]] = []
        for track_id, track_data in state.items():
            age_frames = frame_index - int(track_data.get("last_seen_frame", frame_index))
            if age_frames > TRACK_OCCLUSION_MEMORY_FRAMES:
                continue

            box = track_data.get("last_box")
            if not isinstance(box, dict):
                continue

            stopped = self._track_is_stopped(track_data)
            speed = float(track_data.get("speed") or 0.0)
            speed_kmph = float(track_data.get("speed_kmph") or 0.0)
            active_tracks.append(
                {
                    "id": int(track_id),
                    "label": str(track_data.get("class") or "vehicle"),
                    "vehicle_type": str(track_data.get("class") or "vehicle"),
                    "box": dict(box),
                    "position": str(track_data.get("position") or "center"),
                    "confidence": round(float(track_data.get("confidence") or 0.0), 3),
                    "direction": str(track_data.get("direction") or "unknown"),
                    "movement": str(track_data.get("movement") or "entry"),
                    "speed": round(speed, 2),
                    "speed_kmph": round(speed_kmph, 2),
                    "speed_category": self._speed_category(speed),
                    "speed_category_kmph": self._speed_category_kmph(speed_kmph) if speed_kmph > 0.0 else "uncalibrated",
                    "flags": list(track_data.get("flags", [])),
                    "is_emergency": bool(track_data.get("is_emergency")),
                    "ambulance_cues": list(track_data.get("ambulance_cues", [])),
                    "front_view_clear": bool(track_data.get("front_view_clear")),
                    "stopped": stopped,
                    "stopped_frames": int(track_data.get("stopped_frames") or 0),
                    "sudden_stop": bool(track_data.get("sudden_stop")),
                    "recent_peak_speed": round(float(track_data.get("recent_peak_speed") or 0.0), 2),
                    "current_zone": track_data.get("current_zone"),
                    "visible": age_frames == 0,
                    "occluded_frames": max(age_frames, 0),
                }
            )

        active_tracks.sort(key=lambda item: (item["occluded_frames"], item["id"]))
        return active_tracks

    def _update_tracking_metrics(
        self,
        *,
        stream_key: str,
        detections: list[Dict[str, Any]],
        image_width: int,
        image_height: int,
        fps: float,
    ) -> Dict[str, Any]:
        state = self.tracking_state.setdefault(stream_key, {})
        context = self._tracking_context.setdefault(
            stream_key,
            {
                "frame_index": 0,
                "unique_ids": set(),
                "flow_count": 0,
                "flow_by_direction": {direction: 0 for direction in JUNCTION_DIRECTIONS},
                "emergency_track_ids": set(),
                "turn_stats": {direction: {"straight": 0, "left": 0, "right": 0} for direction in JUNCTION_DIRECTIONS},
                "entry_counts": {direction: 0 for direction in JUNCTION_DIRECTIONS},
                "exit_counts": {direction: 0 for direction in JUNCTION_DIRECTIONS},
            },
        )
        context["frame_index"] += 1
        frame_index = int(context["frame_index"])
        vehicles: list[Dict[str, Any]] = []
        tracked_emergency_ids: set[int] = set()

        for item in detections:
            track_id = item.get("track_id")
            if track_id is None:
                continue

            centroid = item.get("centroid", {})
            centroid_x = float(centroid.get("x", 0.0))
            centroid_y = float(centroid.get("y", 0.0))
            previous_state = state.get(track_id)
            previous_position = previous_state["positions"][-1] if previous_state and previous_state.get("positions") else None
            previous_world_position = previous_state["world_positions"][-1] if previous_state and previous_state.get("world_positions") else None
            speed = 0.0
            speed_kmph = 0.0
            direction = "unknown"
            crossed_line = False
            flags: list[str] = list(previous_state.get("flags", [])) if previous_state else []
            world_point = self._transform_world_point(stream_key, (centroid_x, centroid_y))

            if previous_position is not None:
                dx = centroid_x - float(previous_position[0])
                dy = centroid_y - float(previous_position[1])
                speed = round(float(np.hypot(dx, dy)) * max(fps, 0.1), 2)
                direction = self._movement_direction(dx, dy)
                crossed_line = self._crossed_virtual_line(previous_position, (centroid_x, centroid_y), image_width, image_height)
            if previous_world_position is not None and world_point is not None:
                speed_kmph = round(float(np.hypot(world_point[0] - previous_world_position[0], world_point[1] - previous_world_position[1])) * max(fps, 0.1) * 3.6, 2)
            speed_category = self._speed_category(speed)
            has_calibrated_speed = previous_world_position is not None and world_point is not None
            speed_category_kmph = self._speed_category_kmph(speed_kmph) if has_calibrated_speed else "uncalibrated"
            stopped_now = speed_kmph < 5.0 if has_calibrated_speed else speed < STOPPED_SPEED_THRESHOLD

            if previous_state is None:
                previous_state = {
                    "positions": [],
                    "world_positions": [],
                    "last_seen": time.time(),
                    "last_seen_frame": frame_index,
                    "class": str(item["label"]),
                    "speed": 0.0,
                    "speed_kmph": 0.0,
                    "direction": "unknown",
                    "crossed": False,
                    "start_zone": None,
                    "end_zone": None,
                    "current_zone": None,
                    "visited_center": False,
                    "movement": None,
                    "movement_counted": False,
                    "entry_counted": False,
                    "exit_counted": False,
                    "flags": [],
                    "recent_speeds": [],
                    "stopped_frames": 0,
                    "sudden_stop": False,
                    "recent_peak_speed": 0.0,
                    "last_box": {},
                    "position": "center",
                    "confidence": 0.0,
                    "ambulance_cues": [],
                    "is_emergency": False,
                    "front_view_clear": False,
                }

            previous_state["positions"] = [*previous_state.get("positions", []), (round(centroid_x, 1), round(centroid_y, 1))][
                -TRACK_HISTORY_LIMIT:
            ]
            if world_point is not None:
                previous_state["world_positions"] = [*previous_state.get("world_positions", []), (round(world_point[0], 3), round(world_point[1], 3))][
                    -TRACK_HISTORY_LIMIT:
                ]
            previous_state["last_seen"] = round(time.time(), 6)
            previous_state["last_seen_frame"] = frame_index
            previous_state["class"] = str(item["label"])
            previous_state["speed"] = speed
            previous_state["speed_kmph"] = speed_kmph
            previous_state["direction"] = direction
            recent_speeds = [*previous_state.get("recent_speeds", []), speed][-TRACK_HISTORY_LIMIT:]
            previous_state["recent_speeds"] = recent_speeds
            previous_state["recent_peak_speed"] = round(max(recent_speeds[:-1], default=0.0), 2)
            previous_state["stopped_frames"] = int(previous_state.get("stopped_frames", 0)) + 1 if stopped_now else 0
            previous_state["sudden_stop"] = bool(
                previous_state["recent_peak_speed"] >= ACCIDENT_SUDDEN_STOP_THRESHOLD and previous_state["stopped_frames"] >= 1
            )
            previous_state["last_box"] = dict(item.get("box", {}))
            previous_state["position"] = str(item.get("position", "center"))
            previous_state["confidence"] = round(float(item.get("confidence", 0.0)), 3)
            previous_state["ambulance_cues"] = list(item.get("ambulance_cues", []))
            previous_state["is_emergency"] = bool(item.get("is_emergency"))
            previous_state["front_view_clear"] = bool(item.get("front_view_clear"))
            current_zone = self._zone_name_for_point((centroid_x, centroid_y), image_width, image_height)
            previous_state["current_zone"] = current_zone
            if current_zone == "intersection_center":
                previous_state["visited_center"] = True

            edge_zone = current_zone if current_zone in JUNCTION_DIRECTIONS else None
            if edge_zone and previous_state.get("start_zone") is None:
                previous_state["start_zone"] = edge_zone
                if not previous_state.get("entry_counted"):
                    context["entry_counts"][edge_zone] += 1
                    previous_state["entry_counted"] = True

            if previous_state.get("start_zone") and edge_zone and edge_zone != previous_state.get("start_zone") and previous_state.get("visited_center"):
                previous_state["end_zone"] = edge_zone
                if not previous_state.get("exit_counted"):
                    context["exit_counts"][edge_zone] += 1
                    previous_state["exit_counted"] = True
                if not previous_state.get("movement_counted"):
                    movement = self._classify_turn_movement(previous_state.get("start_zone"), edge_zone)
                    previous_state["movement"] = movement
                    if movement in {"straight", "left", "right"}:
                        context["turn_stats"][previous_state["start_zone"]][movement] += 1
                        previous_state["movement_counted"] = True

            flags = []
            queue_zone = self._is_queue_zone((centroid_x, centroid_y), image_height)
            if has_calibrated_speed and speed_kmph > OVERSPEED_KMPH_THRESHOLD:
                flags.append("overspeeding")
            if stopped_now and not queue_zone:
                flags.append("illegal_stop")
            previous_state["flags"] = flags
            state[track_id] = previous_state

            context["unique_ids"].add(track_id)
            if item.get("is_emergency"):
                context["emergency_track_ids"].add(track_id)
                tracked_emergency_ids.add(track_id)

            if crossed_line and not previous_state.get("crossed"):
                previous_state["crossed"] = True
                context["flow_count"] += 1
                if direction in context["flow_by_direction"]:
                    context["flow_by_direction"][direction] += 1
            item["track_id"] = track_id
            item["speed"] = speed
            item["speed_kmph"] = speed_kmph
            item["speed_category"] = speed_category
            item["speed_category_kmph"] = speed_category_kmph
            item["direction"] = direction
            item["movement"] = previous_state.get("movement") or "entry"
            item["flags"] = flags
            vehicles.append(
                {
                    "id": track_id,
                    "type": item.get("vehicle_type", item.get("label")),
                    "speed": speed,
                    "speed_kmph": speed_kmph,
                    "speed_category": speed_category,
                    "speed_category_kmph": speed_category_kmph,
                    "movement": previous_state.get("movement") or "entry",
                    "direction": direction,
                    "position": item.get("position", "center"),
                    "class": item.get("label"),
                    "flags": flags,
                }
            )

        stale_ids = [
            track_id
            for track_id, track_data in state.items()
            if frame_index - int(track_data.get("last_seen_frame", frame_index)) > TRACK_MAX_STALE_FRAMES
        ]
        for stale_track_id in stale_ids:
            state.pop(stale_track_id, None)

        scene_tracks = self._active_scene_tracks(state, frame_index)
        tracked_emergency_ids = {int(item["id"]) for item in scene_tracks if item.get("is_emergency")}
        vehicle_types: Dict[str, int] = {}
        ambulance_cue_counts: Dict[str, int] = {}
        positions_breakdown: Dict[str, int] = {bucket: 0 for bucket in POSITION_BUCKETS}
        total_area = 0.0
        for scene_track in scene_tracks:
            label = str(scene_track["label"])
            vehicle_types[label] = vehicle_types.get(label, 0) + 1
            position = str(scene_track.get("position", "center"))
            if position in positions_breakdown:
                positions_breakdown[position] += 1
            box = scene_track["box"]
            total_area += float(box.get("width", 0.0)) * float(box.get("height", 0.0))
            for cue in scene_track.get("ambulance_cues", []):
                ambulance_cue_counts[cue] = ambulance_cue_counts.get(cue, 0) + 1

        vehicles = [
            {
                "id": item["id"],
                "type": item["vehicle_type"],
                "speed": item["speed"],
                "speed_kmph": item["speed_kmph"],
                "speed_category": item["speed_category"],
                "speed_category_kmph": item["speed_category_kmph"],
                "movement": item["movement"],
                "direction": item["direction"],
                "position": item["position"],
                "class": item["label"],
                "flags": list(item.get("flags", [])),
                "visible": bool(item.get("visible")),
                "front_view_clear": bool(item.get("front_view_clear")),
            }
            for item in scene_tracks
        ]
        queue_count = sum(
            1
            for item in scene_tracks
            if bool(item.get("stopped")) and int(item.get("stopped_frames", 0)) >= QUEUE_STATIONARY_FRAME_THRESHOLD
        )
        active_speed_values = [float(item["speed"]) for item in scene_tracks if float(item.get("speed", 0.0)) > 0.0]
        active_speed_kmph_values = [float(item["speed_kmph"]) for item in scene_tracks if float(item.get("speed_kmph", 0.0)) > 0.0]
        average_speed = round(sum(active_speed_values) / len(active_speed_values), 2) if active_speed_values else 0.0
        average_speed_kmph = round(sum(active_speed_kmph_values) / len(active_speed_kmph_values), 2) if active_speed_kmph_values else 0.0
        emergency = self._update_emergency_lock(
            stream_key=stream_key,
            active_emergency_ids=tracked_emergency_ids,
            frame_index=frame_index,
        )
        return {
            "active_vehicle_count": len(scene_tracks),
            "tracked_vehicle_count": len(context["unique_ids"]),
            "queue_count": queue_count,
            "flow_count": int(context["flow_count"]),
            "flow_by_direction": dict(context["flow_by_direction"]),
            "average_speed": average_speed,
            "average_speed_kmph": average_speed_kmph,
            "vehicles": vehicles,
            "scene_tracks": scene_tracks,
            "vehicle_types": vehicle_types,
            "ambulance_cue_counts": ambulance_cue_counts,
            "positions_breakdown": positions_breakdown,
            "density_area": round(total_area, 2),
            "emergency_labels": sorted({item["label"] for item in scene_tracks if item.get("is_emergency")}),
            "tracked_emergency_ids": sorted(int(track_id) for track_id in tracked_emergency_ids),
            "turn_analysis": {
                direction: dict(counts) for direction, counts in context["turn_stats"].items()
            },
            "entry_counts": dict(context["entry_counts"]),
            "exit_counts": dict(context["exit_counts"]),
            "emergency": emergency,
        }

    def _movement_direction(self, dx: float, dy: float) -> str:
        if abs(dx) < 1.0 and abs(dy) < 1.0:
            return "unknown"
        if abs(dx) >= abs(dy):
            return "east" if dx > 0 else "west"
        return "south" if dy > 0 else "north"

    def _crossed_virtual_line(
        self,
        previous_position: tuple[float, float],
        current_position: tuple[float, float],
        image_width: int,
        image_height: int,
    ) -> bool:
        dx = current_position[0] - previous_position[0]
        dy = current_position[1] - previous_position[1]
        if abs(dx) >= abs(dy):
            line_x = image_width * 0.5
            return (previous_position[0] < line_x <= current_position[0]) or (previous_position[0] > line_x >= current_position[0])
        line_y = image_height * 0.5
        return (previous_position[1] < line_y <= current_position[1]) or (previous_position[1] > line_y >= current_position[1])

    def _speed_category(self, speed: float) -> str:
        if speed < STOPPED_SPEED_THRESHOLD:
            return "stopped"
        if speed < SLOW_SPEED_THRESHOLD:
            return "slow"
        return "moving"

    def _speed_category_kmph(self, speed_kmph: float) -> str:
        if speed_kmph < 5.0:
            return "stopped"
        if speed_kmph <= 20.0:
            return "slow"
        if speed_kmph > OVERSPEED_KMPH_THRESHOLD:
            return "overspeed"
        return "normal"

    def _zone_name_for_point(self, point: tuple[float, float], image_width: int, image_height: int) -> str:
        x, y = point
        center_left = image_width * 0.35
        center_right = image_width * 0.65
        center_top = image_height * 0.35
        center_bottom = image_height * 0.65
        if center_left <= x <= center_right and center_top <= y <= center_bottom:
            return "intersection_center"
        if y <= image_height * 0.2:
            return "north"
        if y >= image_height * 0.8:
            return "south"
        if x <= image_width * 0.2:
            return "west"
        if x >= image_width * 0.8:
            return "east"
        return "approach"

    def _is_queue_zone(self, point: tuple[float, float], image_height: int) -> bool:
        return float(point[1]) >= image_height * 0.58

    def _classify_turn_movement(self, start_zone: str | None, end_zone: str | None) -> str:
        if not start_zone or not end_zone:
            return "entry"
        if start_zone == end_zone:
            return "entry"
        straight_pairs = {
            ("north", "south"),
            ("south", "north"),
            ("east", "west"),
            ("west", "east"),
        }
        left_pairs = {
            ("north", "west"),
            ("west", "south"),
            ("south", "east"),
            ("east", "north"),
        }
        right_pairs = {
            ("north", "east"),
            ("east", "south"),
            ("south", "west"),
            ("west", "north"),
        }
        if (start_zone, end_zone) in straight_pairs:
            return "straight"
        if (start_zone, end_zone) in left_pairs:
            return "left"
        if (start_zone, end_zone) in right_pairs:
            return "right"
        return "exit"

    def _update_emergency_lock(
        self,
        *,
        stream_key: str,
        active_emergency_ids: set[int],
        frame_index: int,
    ) -> Dict[str, Any]:
        now = time.time()
        lock = self._emergency_lock
        if lock.get("active"):
            lock_stream = str(lock.get("stream_key") or "")
            lock_track_id = lock.get("track_id")
            track_data = self.tracking_state.get(lock_stream, {}).get(lock_track_id)
            timed_out = (now - float(lock.get("start_time") or 0.0)) > EMERGENCY_LOCK_TIMEOUT_SECONDS
            missing = (
                track_data is None
                or (now - float(track_data.get("last_seen") or 0.0)) > EMERGENCY_TRACK_MISSING_TIMEOUT_SECONDS
            )
            exited = bool(track_data and track_data.get("exit_counted"))
            if timed_out or missing or exited:
                self._emergency_lock = {
                    "active": False,
                    "direction": None,
                    "track_id": None,
                    "stream_key": None,
                    "start_time": 0.0,
                    "locked": False,
                }
                lock = self._emergency_lock

        if active_emergency_ids:
            track_id = next(iter(sorted(active_emergency_ids)))
            track_data = self.tracking_state.get(stream_key, {}).get(track_id, {})
            direction = (
                self._resolve_approach_direction(stream_key)
                or track_data.get("start_zone")
                or track_data.get("direction")
                or "unknown"
            )
            if not lock.get("active") or lock.get("track_id") != track_id:
                self._emergency_lock = {
                    "active": True,
                    "direction": direction,
                    "track_id": track_id,
                    "stream_key": stream_key,
                    "start_time": now,
                    "locked": direction in JUNCTION_DIRECTIONS,
                    "frame_index": frame_index,
                }
            else:
                self._emergency_lock["direction"] = direction
                self._emergency_lock["locked"] = direction in JUNCTION_DIRECTIONS
                self._emergency_lock["frame_index"] = frame_index

        return {
            "active": bool(self._emergency_lock.get("active")),
            "direction": self._emergency_lock.get("direction"),
            "locked": bool(self._emergency_lock.get("locked")),
            "track_id": self._emergency_lock.get("track_id"),
            "started_at": round(float(self._emergency_lock.get("start_time") or 0.0), 6) if self._emergency_lock.get("active") else 0.0,
        }

    def _summarize_traffic(
        self,
        active_tracks: list[Dict[str, Any]],
        image_width: int,
        image_height: int,
        accident_alert: Dict[str, Any],
        fallback_detections: list[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        vehicle_types: Dict[str, int] = {}
        ambulance_cue_counts: Dict[str, int] = {}
        positions_breakdown: Dict[str, int] = {bucket: 0 for bucket in POSITION_BUCKETS}
        queue_length = 0
        total_area = 0.0
        emergency_labels: list[str] = []

        summary_source = active_tracks or (fallback_detections or [])
        for item in summary_source:
            label = str(item["label"])
            vehicle_types[label] = vehicle_types.get(label, 0) + 1
            position = str(item.get("position", "center"))
            if position in positions_breakdown:
                positions_breakdown[position] += 1
            box = item["box"]
            total_area += float(box["width"]) * float(box["height"])
            if active_tracks:
                if bool(item.get("stopped")) and int(item.get("stopped_frames", 0)) >= QUEUE_STATIONARY_FRAME_THRESHOLD:
                    queue_length += 1
            else:
                center_y = float(box["y"]) + (float(box["height"]) / 2.0)
                tall_enough = float(box["height"]) >= image_height * 0.08
                if center_y >= image_height * 0.58 and tall_enough:
                    queue_length += 1

            if item.get("is_emergency"):
                emergency_labels.append(label)
            for cue in item.get("ambulance_cues", []):
                ambulance_cue_counts[cue] = ambulance_cue_counts.get(cue, 0) + 1

        image_area = max(float(image_width * image_height), 1.0)
        density_percent = round(min(100.0, (total_area / image_area) * 100.0), 2)
        if density_percent >= 28:
            density_level = "high"
        elif density_percent >= 12:
            density_level = "medium"
        else:
            density_level = "low"

        emergency_detected = bool(emergency_labels)
        priority_value = min(
            100,
            int(
                12
                + min(queue_length * 8, 28)
                + min(int(density_percent * 0.6), 25)
                + (32 if emergency_detected else 0)
                + (18 if accident_alert.get("detected") else 0)
            ),
        )
        if emergency_detected:
            priority_reason = "Emergency vehicle detected. Favor immediate green priority."
        elif accident_alert.get("detected"):
            priority_reason = "Possible accident detected. Raise operator attention and phase priority."
        elif queue_length >= 4 or density_level == "high":
            priority_reason = "Heavy queue buildup detected. Increase this lane's signal priority."
        else:
            priority_reason = "Normal flow. Standard adaptive timing is sufficient."

        return {
            "vehicle_types": vehicle_types,
            "ambulance_cue_counts": ambulance_cue_counts,
            "positions_breakdown": positions_breakdown,
            "queue_length": queue_length,
            "density_percent": density_percent,
            "density_level": density_level,
            "emergency_detected": emergency_detected,
            "emergency_labels": sorted(set(emergency_labels)),
            "signal_priority_value": priority_value,
            "signal_priority_reason": priority_reason,
        }


class SimulationRuntime:
    """Own the authoritative simulation clock and websocket fanout."""

    def __init__(self) -> None:
        self.engine = TrafficNetwork()
        self.connections: Set[WebSocket] = set()
        self.lock = asyncio.Lock()
        self.running = False
        self.frame_task: asyncio.Task[None] | None = None
        self.external_events = deque(maxlen=EXTERNAL_EVENT_LIMIT)
        self.last_alert_at: Dict[str, float] = {}
        self.latest_snapshot = self.engine.tick(FRAME_DT)
        self.latest_snapshot = self._merge_external_events(self.latest_snapshot)

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.frame_task = asyncio.create_task(self._frame_loop(), name="traffic-runtime-loop")

    async def stop(self) -> None:
        self.running = False
        if self.frame_task is not None:
            self.frame_task.cancel()
            try:
                await self.frame_task
            except asyncio.CancelledError:
                pass
        self.frame_task = None

    async def _frame_loop(self) -> None:
        while self.running:
            started = time.perf_counter()
            async with self.lock:
                self.latest_snapshot = self._merge_external_events(self.engine.tick(FRAME_DT))
                payload = {
                    "type": "snapshot",
                    "snapshot": self.latest_snapshot,
                    "sent_at": round(time.time(), 6),
                }
            await self._broadcast(payload)
            elapsed = time.perf_counter() - started
            await asyncio.sleep(max(0.0, FRAME_DT - elapsed))

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for connection in list(self.connections):
            try:
                await connection.send_json(payload)
            except Exception:
                stale.append(connection)
        for connection in stale:
            self.connections.discard(connection)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)
        await websocket.send_json(
            {
                "type": "hello",
                "snapshot": self.latest_snapshot,
                "frame_dt": FRAME_DT,
                "sent_at": round(time.time(), 6),
            }
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def record_external_event(self, *, level: str, message: str, dedupe_key: str) -> bool:
        async with self.lock:
            now = self.engine.time
            last_seen = self.last_alert_at.get(dedupe_key, -ALERT_COOLDOWN_SECONDS)
            if now - last_seen < ALERT_COOLDOWN_SECONDS:
                return False

            self.last_alert_at[dedupe_key] = now
            event = {
                "timestamp": round(now, 3),
                "level": level,
                "message": message,
            }
            self.external_events.appendleft(event)
            self.latest_snapshot = self._merge_external_events(self._snapshot_dict(self.engine.snapshot()))
            payload = {
                "type": "snapshot",
                "snapshot": self.latest_snapshot,
                "sent_at": round(time.time(), 6),
            }
        await self._broadcast(payload)
        return True

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any] | None:
        message_type = str(message.get("type", "")).strip().lower()
        async with self.lock:
            if message_type == "set_config":
                config = message.get("config", {})
                if isinstance(config, dict):
                    self.engine.update_config(config)
            elif message_type == "pause":
                self.engine.update_config({"paused": True})
            elif message_type == "play":
                self.engine.update_config({"paused": False})
            elif message_type == "reset":
                config = message.get("config")
                self.engine.reset(config if isinstance(config, dict) else None)
            elif message_type == "ping":
                return {"type": "pong", "sent_at": round(time.time(), 6)}
            else:
                return {"type": "error", "message": f"Unknown message type: {message_type or 'empty'}"}

            self.latest_snapshot = self._merge_external_events(self._snapshot_dict(self.engine.snapshot()))
            return {"type": "ack", "action": message_type, "snapshot": self.latest_snapshot, "sent_at": round(time.time(), 6)}

    def _merge_external_events(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        merged_snapshot = dict(snapshot)
        engine_events = list(snapshot.get("events", []))
        merged_events = [*list(self.external_events), *engine_events][:40]
        merged_snapshot["events"] = merged_events
        metrics = dict(snapshot.get("metrics", {}))
        metrics["detections"] = len(merged_events)
        merged_snapshot["metrics"] = metrics
        return merged_snapshot

    def _snapshot_dict(self, snapshot: Any) -> Dict[str, Any]:
        if isinstance(snapshot, dict):
            return snapshot
        if hasattr(snapshot, "to_dict"):
            return snapshot.to_dict()
        return {}


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class JunctionPriorityController:
    """Keep simple controller memory so the junction behaves more like a field deployment."""

    def __init__(self) -> None:
        self.last_green_direction: str | None = None
        self.last_switch_at = time.time()
        self.wait_cycles = {direction: 0 for direction in JUNCTION_DIRECTIONS}
        self.traffic_history = {direction: [] for direction in JUNCTION_DIRECTIONS}

    def _append_history(self, direction: str, vehicle_count: int) -> None:
        history = [*self.traffic_history.get(direction, []), int(max(vehicle_count, 0))]
        self.traffic_history[direction] = history[-MAX_HISTORY:]

    def _moving_average(self, values: list[int]) -> float:
        if not values:
            return 0.0
        window = values[-PREDICTION_LOOKBACK:]
        return float(sum(window)) / float(max(len(window), 1))

    def _trend_prediction(self, values: list[int]) -> float:
        if len(values) < 3:
            return float(values[-1]) if values else 0.0
        x = np.arange(len(values), dtype=np.float32)
        y = np.array(values, dtype=np.float32)
        slope, intercept = np.polyfit(x, y, 1)
        return float((slope * (len(values) + 1)) + intercept)

    def _predict_incoming(self, direction: str) -> Dict[str, float]:
        history = self.traffic_history.get(direction, [])
        moving_avg = self._moving_average(history)
        trend = self._trend_prediction(history)
        predicted_incoming = max(0.0, round((moving_avg * 0.45) + (trend * 0.55), 2))
        return {
            "history": history[-MAX_HISTORY:],
            "moving_average": round(moving_avg, 2),
            "trend_prediction": round(trend, 2),
            "predicted_incoming": predicted_incoming,
        }

    def compute(self, approaches: Dict[str, Any], emergency_override: Dict[str, Any] | None = None) -> Dict[str, Any]:
        now = time.time()
        normalized: Dict[str, Dict[str, Any]] = {}
        active_directions: list[str] = []

        for direction in JUNCTION_DIRECTIONS:
            raw = approaches.get(direction, {}) if isinstance(approaches, dict) else {}
            vehicle_count = _coerce_int(raw.get("vehicle_count"))
            queue_length = _coerce_int(raw.get("queue_length"))
            flow_count = _coerce_int(raw.get("flow_count"))
            density_percent = _coerce_float(raw.get("density_percent"))
            signal_priority_value = _coerce_int(raw.get("signal_priority_value"))
            uncertain_count = _coerce_int(raw.get("uncertain_count"))
            emergency_detected = bool(raw.get("emergency_detected"))
            accident_detected = bool(raw.get("accident_detected"))
            density_level = str(raw.get("density_level") or "low")
            self._append_history(direction, vehicle_count)
            prediction = self._predict_incoming(direction)
            predicted_incoming = float(prediction["predicted_incoming"])
            predicted_load = round(max(queue_length, 0) + predicted_incoming, 2)
            analyzed = any(
                [
                    vehicle_count > 0,
                    queue_length > 0,
                    flow_count > 0,
                    density_percent > 0.0,
                    signal_priority_value > 0,
                    emergency_detected,
                    accident_detected,
                    uncertain_count > 0,
                ]
            )

            model_score = min(int(signal_priority_value * 0.45), 45)
            vehicle_score = min(vehicle_count * 3, 18)
            queue_score = min(queue_length * 7, 28)
            flow_score = min(flow_count * 4, 20)
            density_score = min(int(density_percent * 0.22), 22)
            prediction_score = min(int(predicted_load * PREDICTION_WEIGHT * 2.0), 24)
            fairness_score = min(self.wait_cycles.get(direction, 0) * 6, 18)
            incident_score = (70 if emergency_detected else 0) + (18 if accident_detected else 0)
            uncertainty_penalty = min(uncertain_count * 3, 12)

            effective_priority = max(
                0,
                min(
                    100,
                    model_score
                    + vehicle_score
                    + queue_score
                    + flow_score
                    + density_score
                    + prediction_score
                    + fairness_score
                    + incident_score
                    - uncertainty_penalty,
                ),
            )

            normalized[direction] = {
                "direction": direction,
                "vehicle_count": vehicle_count,
                "queue_length": queue_length,
                "flow_count": flow_count,
                "density_percent": round(density_percent, 2),
                "density_level": density_level,
                "signal_priority_value": signal_priority_value,
                "effective_priority": effective_priority if analyzed else 0,
                "emergency_detected": emergency_detected,
                "accident_detected": accident_detected,
                "uncertain_count": uncertain_count,
                "model_score": model_score,
                "vehicle_score": vehicle_score,
                "queue_score": queue_score,
                "flow_score": flow_score,
                "density_score": density_score,
                "prediction_score": prediction_score,
                "fairness_score": fairness_score,
                "incident_score": incident_score,
                "uncertainty_penalty": uncertainty_penalty,
                "predicted_incoming": predicted_incoming,
                "predicted_load": predicted_load,
                "prediction": prediction,
                "status": "ready" if analyzed else "waiting",
            }
            if analyzed:
                active_directions.append(direction)
            else:
                self.wait_cycles[direction] = 0

        if not active_directions:
            return {
                "ready": False,
                "recommended_green_direction": None,
                "recommended_next_signal": None,
                "predicted_winner": None,
                "prediction": {direction: 0.0 for direction in JUNCTION_DIRECTIONS},
                "signal_states": {direction: "red" for direction in JUNCTION_DIRECTIONS},
                "cycle_plan": {"green_duration_sec": 0, "amber_duration_sec": 0, "all_red_duration_sec": 0},
                "rationale": "Analyze at least one direction to recommend a safe junction phase plan.",
                "controller": {
                    "phase_action": "idle",
                    "last_green_direction": self.last_green_direction,
                    "elapsed_green_sec": round(now - self.last_switch_at, 1),
                    "fairness_cycles": dict(self.wait_cycles),
                    "starvation_watch": [],
                },
                "emergency_lock": {"active": False, "locked_direction": None, "track_id": None},
                "approaches": normalized,
            }

        predicted_winner = max(
            active_directions,
            key=lambda direction: (
                normalized[direction]["predicted_load"],
                normalized[direction]["flow_count"],
                normalized[direction]["queue_length"],
            ),
        )
        prediction_summary = {
            direction: round(float(normalized[direction]["predicted_load"]), 2) for direction in JUNCTION_DIRECTIONS
        }

        override_direction = str((emergency_override or {}).get("direction") or "").lower()
        emergency_lock_active = bool((emergency_override or {}).get("active")) and bool((emergency_override or {}).get("locked")) and override_direction in JUNCTION_DIRECTIONS
        if emergency_lock_active:
            winner = override_direction
            if winner not in normalized:
                winner = active_directions[0]
            self.last_green_direction = winner
            self.last_switch_at = now
            for direction in JUNCTION_DIRECTIONS:
                if direction == winner:
                    self.wait_cycles[direction] = 0
                elif direction in active_directions:
                    self.wait_cycles[direction] = min(self.wait_cycles.get(direction, 0) + 1, 5)
            winner_data = normalized[winner]
            return {
                "ready": True,
                "recommended_green_direction": winner,
                "recommended_next_signal": winner,
                "predicted_winner": predicted_winner,
                "prediction": prediction_summary,
                "signal_states": {direction: ("green" if direction == winner else "red") for direction in JUNCTION_DIRECTIONS},
                "cycle_plan": {
                    "green_duration_sec": min(65, max(20, 22 + min(winner_data["queue_length"] * 3, 16))),
                    "amber_duration_sec": 4,
                    "all_red_duration_sec": 2,
                },
                "rationale": f"Emergency route lock is active for {winner.title()}, so the controller holds that approach green until the ambulance clears or the lock times out.",
                "controller": {
                    "phase_action": "emergency_lock",
                    "last_green_direction": self.last_green_direction,
                    "elapsed_green_sec": 0.0,
                    "fairness_cycles": dict(self.wait_cycles),
                    "starvation_watch": [
                        direction.title()
                        for direction in active_directions
                        if direction != winner and self.wait_cycles.get(direction, 0) >= 3
                    ],
                },
                "emergency_lock": {
                    "active": True,
                    "locked_direction": winner,
                    "track_id": (emergency_override or {}).get("track_id"),
                },
                "approaches": normalized,
            }

        top_candidate = max(
            active_directions,
            key=lambda direction: (
                normalized[direction]["effective_priority"],
                normalized[direction]["emergency_detected"],
                normalized[direction]["queue_length"],
                normalized[direction]["vehicle_count"],
            ),
        )
        elapsed_green_sec = now - self.last_switch_at
        winner = top_candidate
        phase_action = "switch_green"
        hold_reason = ""

        if self.last_green_direction in active_directions:
            current_green = self.last_green_direction
            current_data = normalized[current_green]
            challenger_data = normalized[top_candidate]
            emergency_elsewhere = top_candidate != current_green and challenger_data["emergency_detected"]
            should_hold = (
                top_candidate == current_green
                or (
                    not emergency_elsewhere
                    and elapsed_green_sec < 18.0
                    and challenger_data["effective_priority"] < current_data["effective_priority"] + 10
                )
            )
            if should_hold:
                winner = current_green
                phase_action = "hold_green"
                hold_reason = f"Holding {current_green.title()} green to avoid rapid phase changes and to respect minimum green time."

        if winner != self.last_green_direction:
            self.last_green_direction = winner
            self.last_switch_at = now
            elapsed_green_sec = 0.0

        for direction in JUNCTION_DIRECTIONS:
            if direction == winner:
                self.wait_cycles[direction] = 0
            elif direction in active_directions:
                self.wait_cycles[direction] = min(self.wait_cycles.get(direction, 0) + 1, 5)

        winner_data = normalized[winner]
        green_duration_sec = min(
            65,
            max(
                18,
                18
                + min(winner_data["queue_length"] * 3, 18)
                + min(int(winner_data["flow_count"] * 1.5), 10)
                + min(int(winner_data["density_percent"] * 0.16), 12)
                + min(int(winner_data["predicted_load"] * 0.8), 16)
                + min(winner_data["vehicle_count"] * 2, 10)
                + (18 if winner_data["emergency_detected"] else 0),
            ),
        )
        amber_duration_sec = 4 if winner_data["density_level"] in {"medium", "high"} or winner_data["vehicle_count"] >= 6 else 3
        all_red_duration_sec = 2
        starvation_watch = [
            direction.title()
            for direction in active_directions
            if direction != winner and self.wait_cycles.get(direction, 0) >= 3
        ]

        if winner_data["emergency_detected"]:
            rationale = f"{winner.title()} has an emergency vehicle, so it receives immediate override and green priority."
        elif winner_data["accident_detected"]:
            rationale = f"{winner.title()} shows incident risk, so the controller clears that approach first while holding the others red."
        elif starvation_watch:
            rationale = f"{winner.title()} wins now, but the controller is also watching {', '.join(starvation_watch)} so those legs do not starve in later cycles."
        elif hold_reason:
            rationale = hold_reason
        elif winner_data["predicted_load"] >= 10:
            rationale = f"{winner.title()} is expected to receive the heaviest near-future load, so the controller pre-allocates green time before congestion builds."
        elif winner_data["queue_length"] >= 4 or winner_data["density_level"] == "high":
            rationale = f"{winner.title()} has the strongest queue pressure and congestion, so it should receive the next green phase."
        else:
            rationale = f"{winner.title()} currently has the strongest balanced demand after queue, flow, prediction, density, vehicle load, and fairness are combined."

        return {
            "ready": True,
            "recommended_green_direction": winner,
            "recommended_next_signal": winner,
            "predicted_winner": predicted_winner,
            "prediction": prediction_summary,
            "signal_states": {direction: ("green" if direction == winner else "red") for direction in JUNCTION_DIRECTIONS},
            "cycle_plan": {
                "green_duration_sec": green_duration_sec,
                "amber_duration_sec": amber_duration_sec,
                "all_red_duration_sec": all_red_duration_sec,
            },
            "rationale": rationale,
            "controller": {
                "phase_action": phase_action,
                "last_green_direction": self.last_green_direction,
                "elapsed_green_sec": round(elapsed_green_sec, 1),
                "fairness_cycles": dict(self.wait_cycles),
                "starvation_watch": starvation_watch,
            },
            "emergency_lock": {"active": False, "locked_direction": None, "track_id": None},
            "approaches": normalized,
        }


runtime = SimulationRuntime()
vehicle_detector = VehicleDetector()
junction_priority_controller = JunctionPriorityController()
traffic_platform = TrafficPlatformService(JUNCTION_REGISTRY_PATH)
map_stream_hub = MapStreamHub(traffic_platform, vehicle_detector.get_emergency_lock_state)
emergency_router = GoogleEmergencyRouter()

class EmergencyRouteRequest(BaseModel):
    source: tuple[float, float]
    destination: tuple[float, float]


class EmergencySimulationStartRequest(BaseModel):
    start_point_id: str | None = None
    start_junction_id: str | None = None
    start: tuple[float, float] | None = None
    speed_multiplier: float = 1.0


class EmergencySpeedRequest(BaseModel):
    speed_multiplier: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    await runtime.start()
    await map_stream_hub.start()
    try:
        yield
    finally:
        await map_stream_hub.stop()
        await runtime.stop()


app = FastAPI(title="Traffic Digital Twin Realtime Server", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "running": runtime.running,
        "frame_dt": FRAME_DT,
        "connections": len(runtime.connections),
        "snapshot": runtime.latest_snapshot,
    }


@app.post("/api/live-cv/detect")
async def detect_vehicles(
    media: UploadFile = File(...),
    stream_id: str | None = Form(default=None),
    fps: float | None = Form(default=None),
    image_points: str | None = Form(default=None),
    real_points: str | None = Form(default=None),
) -> Dict[str, Any]:
    if not media.content_type:
        raise HTTPException(status_code=400, detail="Expected an image or video upload.")

    file_bytes = await media.read()
    result = await vehicle_detector.detect_upload(
        file_bytes,
        media.content_type,
        media.filename,
        stream_id=stream_id,
        fps=fps,
        image_points=image_points,
        real_points=real_points,
    )
    if result.get("accident_detected") and result.get("accident_message"):
        confidence = float(result.get("accident_confidence") or 0.0)
        message = f"{result['accident_message']} Confidence {confidence:.2f}."
        await runtime.record_external_event(level="CRITICAL", message=message, dedupe_key="cv-accident")
    if result.get("emergency_detected"):
        emergency_labels = ", ".join(result.get("emergency_labels", [])) or "emergency vehicle"
        await runtime.record_external_event(
            level="WARN",
            message=f"Emergency traffic detected in Live CV: {emergency_labels}. Recommended signal priority {int(result.get('signal_priority_value', 0))}.",
            dedupe_key="cv-emergency",
        )
    return result


@app.post("/api/live-cv/junction/priority")
async def compute_live_cv_junction_priority(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    approaches = payload.get("approaches", {}) if isinstance(payload, dict) else {}
    return junction_priority_controller.compute(
        approaches if isinstance(approaches, dict) else {},
        emergency_override=vehicle_detector.get_emergency_lock_state(),
    )


@app.get("/api/map/junctions")
async def get_map_junctions() -> list[Dict[str, Any]]:
    snapshot = traffic_platform.build_snapshot(emergency_override=vehicle_detector.get_emergency_lock_state())
    return snapshot["junctions"]


@app.get("/api/map/predictions")
async def get_map_predictions() -> list[Dict[str, Any]]:
    snapshot = traffic_platform.build_snapshot(emergency_override=vehicle_detector.get_emergency_lock_state())
    return snapshot["predictions"]


@app.get("/api/map/status")
async def get_map_status() -> Dict[str, Any]:
    snapshot = traffic_platform.build_snapshot(emergency_override=vehicle_detector.get_emergency_lock_state())
    return snapshot["global_status"]


@app.get("/api/map/junction-registry")
async def get_junction_registry() -> list[Dict[str, Any]]:
    return traffic_platform.list_registry()


@app.get("/api/emergency/config")
async def get_emergency_demo_config() -> Dict[str, Any]:
    return traffic_platform.get_demo_config()


@app.get("/api/emergency/status")
async def get_emergency_demo_status() -> Dict[str, Any]:
    return traffic_platform.get_emergency_state()


@app.post("/api/emergency/start")
async def start_emergency_demo(payload: EmergencySimulationStartRequest) -> Dict[str, Any]:
    if payload.start_point_id:
        emergency_state = traffic_platform.start_emergency_demo(payload.start_point_id)
        starting_point = emergency_state.get("starting_point") or {}
        activation_junction_id = str(emergency_state.get("activation_junction_id") or "")
        activation_junction = next((item for item in traffic_platform.list_registry() if item["junction_id"] == activation_junction_id), None)
        google_route: Dict[str, Any] = {}
        approach_route: Dict[str, Any] = {}
        emergency_route: Dict[str, Any] = {}
        google_route_available = False
        google_route_error = None
        if starting_point and emergency_state.get("hospital") and activation_junction:
            try:
                google_route = emergency_router.start_emergency(
                    (float(starting_point["lat"]), float(starting_point["lng"])),
                    hospital=emergency_state.get("hospital"),
                )
                approach_route = emergency_router.get_route(
                    (float(starting_point["lat"]), float(starting_point["lng"])),
                    (float(activation_junction["lat"]), float(activation_junction["lng"])),
                )
                emergency_route = emergency_router.get_route(
                    (float(activation_junction["lat"]), float(activation_junction["lng"])),
                    (
                        float(emergency_state["hospital"]["lat"]),
                        float(emergency_state["hospital"]["lng"]),
                    ),
                )
                approach_duration_sec = max(float(approach_route["duration_s"]) / 8.0, 6.0)
                emergency_duration_sec = max(float(emergency_route["duration_in_traffic_s"]) / 8.0, 12.0)
                approach_path_coords = [
                    {"lat": round(lat, 6), "lng": round(lng, 6)}
                    for lat, lng in decode_polyline_points(str(approach_route["polyline"]))
                ]
                emergency_path_coords = [
                    {"lat": round(lat, 6), "lng": round(lng, 6)}
                    for lat, lng in decode_polyline_points(str(emergency_route["polyline"]))
                ]
                approach_eta_min = float(approach_route["duration_in_traffic_s"]) / 60.0
                emergency_normal_eta_min = float(emergency_route["duration_in_traffic_s"]) / 60.0
                optimized_eta_min = round(approach_eta_min + max(emergency_normal_eta_min * 0.5, 0.5), 1)
                normal_eta_min = round(approach_eta_min + emergency_normal_eta_min, 1)
                time_saved_min = round(max(normal_eta_min - optimized_eta_min, 0.1), 1)
                time_saved_percent = round((time_saved_min / max(normal_eta_min, 0.1)) * 100.0, 1)
                emergency_state = traffic_platform.apply_structured_demo_google_paths(
                    approach_path_coords=approach_path_coords,
                    emergency_path_coords=emergency_path_coords,
                    approach_duration_sec=approach_duration_sec,
                    emergency_duration_sec=emergency_duration_sec,
                    route_distance_km=round((float(approach_route["distance_m"]) + float(emergency_route["distance_m"])) / 1000.0, 3),
                    normal_eta_min=normal_eta_min,
                    optimized_eta_min=optimized_eta_min,
                    time_saved_min=time_saved_min,
                    time_saved_percent=time_saved_percent,
                )
                google_route_available = True
            except HTTPException as exc:
                google_route_error = exc.detail

        emergency_state = traffic_platform.update_emergency_speed(payload.speed_multiplier)

        merged_directions = []
        for step in approach_route.get("steps", []):
            merged_directions.append({**step, "phase": "approach"})
        for step in emergency_route.get("steps", []):
            merged_directions.append({**step, "phase": "emergency"})

        return {
            "mode": "structured_demo",
            "start_point_id": payload.start_point_id,
            "starting_point": starting_point,
            "hospital": google_route.get("hospital") or emergency_state.get("hospital"),
            "normal_eta": google_route.get("normal_eta", emergency_state.get("normal_eta")),
            "optimized_eta": google_route.get("optimized_eta", emergency_state.get("optimized_eta")),
            "time_saved": google_route.get("time_saved", emergency_state.get("time_saved")),
            "time_saved_percent": google_route.get("time_saved_percent", emergency_state.get("time_saved_percent")),
            "route_distance_km": (
                round(float(google_route.get("distance_m", 0)) / 1000.0, 3)
                if google_route.get("distance_m") is not None
                else emergency_state.get("route_distance_km")
            ),
            "polyline": google_route.get("polyline"),
            "distance_m": google_route.get("distance_m"),
            "duration_s": google_route.get("duration_s"),
            "duration_in_traffic_s": google_route.get("duration_in_traffic_s"),
            "approach_polyline": approach_route.get("polyline"),
            "emergency_polyline": emergency_route.get("polyline"),
            "directions": merged_directions,
            "google_maps_url": google_route.get("google_maps_url"),
            "google_route_available": google_route_available,
            "google_route_error": google_route_error,
            "approach_route_coords": emergency_state.get("approach_route_coords"),
            "emergency_route_coords": emergency_state.get("emergency_route_coords"),
            "full_route_coords": emergency_state.get("full_route_coords"),
            "activation_junction_id": emergency_state.get("activation_junction_id"),
            "planned_route_nodes": emergency_state.get("planned_route_nodes"),
            "emergency_state": emergency_state,
        }

    if payload.start is not None:
        start = (float(payload.start[0]), float(payload.start[1]))
        start_junction_id = payload.start_junction_id
    elif payload.start_junction_id:
        junction = next((item for item in traffic_platform.list_registry() if item["junction_id"] == payload.start_junction_id), None)
        if junction is None:
            raise HTTPException(status_code=404, detail=f"Unknown start junction: {payload.start_junction_id}")
        start = (float(junction["lat"]), float(junction["lng"]))
        start_junction_id = payload.start_junction_id
    else:
        raise HTTPException(status_code=400, detail="Either start_junction_id or start must be provided.")

    route_data = emergency_router.start_emergency(start)
    traffic_platform.activate_emergency_route(start, (route_data["hospital"]["lat"], route_data["hospital"]["lng"]))
    emergency_state = traffic_platform.get_emergency_state()
    return {
        "start_junction_id": start_junction_id,
        "start": {"lat": round(start[0], 6), "lng": round(start[1], 6)},
        "polyline": route_data["polyline"],
        "hospital": route_data["hospital"],
        "distance_m": route_data["distance_m"],
        "duration_s": route_data["duration_s"],
        "duration_in_traffic_s": route_data["duration_in_traffic_s"],
        "normal_eta": route_data["normal_eta"],
        "optimized_eta": route_data["optimized_eta"],
        "time_saved": route_data["time_saved"],
        "time_saved_percent": route_data["time_saved_percent"],
        "emergency_state": emergency_state,
    }


@app.post("/api/emergency/clear")
async def clear_emergency_demo() -> Dict[str, Any]:
    return {
        "status": "cleared",
        "emergency_state": traffic_platform.clear_emergency_route(),
    }


@app.post("/api/emergency/speed")
async def update_emergency_speed(payload: EmergencySpeedRequest) -> Dict[str, Any]:
    emergency_state = traffic_platform.update_emergency_speed(payload.speed_multiplier)
    return {
        "status": "updated",
        "speed_multiplier": emergency_state.get("speed_multiplier", 1.0),
        "emergency_state": emergency_state,
    }


@app.put("/api/map/junctions/{junction_id}")
async def upsert_map_junction(junction_id: str, payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    record = dict(payload) if isinstance(payload, dict) else {}
    record["junction_id"] = junction_id
    junction = traffic_platform.upsert_junction(record)
    return {"status": "upserted", "junction": junction}


@app.delete("/api/map/junctions/{junction_id}")
async def delete_map_junction(junction_id: str) -> Dict[str, Any]:
    traffic_platform.remove_junction(junction_id)
    return {"status": "removed", "junction_id": junction_id}


@app.post("/api/map/junctions/{junction_id}/heartbeat")
async def update_camera_heartbeat(junction_id: str) -> Dict[str, Any]:
    return traffic_platform.touch_camera_heartbeat(junction_id)


@app.post("/api/map/emergency-route")
async def activate_map_emergency_route(payload: EmergencyRouteRequest) -> Dict[str, Any]:
    emergency_state = traffic_platform.activate_emergency_route(payload.source, payload.destination)
    return {
        "status": "activated",
        "route": [{"junction_id": junction_id} for junction_id in emergency_state["route"]],
        "emergency_state": emergency_state,
    }


@app.post("/api/map/emergency-route/clear")
async def clear_map_emergency_route() -> Dict[str, Any]:
    return {
        "status": "cleared",
        "emergency_state": traffic_platform.clear_emergency_route(),
    }


@app.get("/api/map/signal-coordination")
async def get_signal_coordination() -> Dict[str, Any]:
    snapshot = traffic_platform.build_snapshot(emergency_override=vehicle_detector.get_emergency_lock_state())
    return snapshot["coordination"]


@app.websocket("/ws/map-stream")
async def map_stream_endpoint(websocket: WebSocket) -> None:
    await map_stream_hub.connect(websocket)
    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and str(message.get("type", "")).lower() == "ping":
                await websocket.send_json({"type": "pong", "sent_at": round(time.time(), 6)})
    except WebSocketDisconnect:
        await map_stream_hub.disconnect(websocket)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await runtime.connect(websocket)
    try:
        while True:
            message = await websocket.receive_json()
            response = await runtime.handle_message(message if isinstance(message, dict) else {})
            if response is not None:
                await websocket.send_json(response)
    except WebSocketDisconnect:
        await runtime.disconnect(websocket)
