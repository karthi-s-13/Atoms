"""FastAPI + WebSocket bridge for the production traffic engine."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Set

import cv2
import numpy as np
from fastapi import Body, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ultralytics import YOLO

from simulation_engine import FRAME_DT, TrafficSimulationEngine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AMBULANCE_CLASSIFIER_PATH = PROJECT_ROOT / "models" / "ambulance_yolo_cls.pt"
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
VIDEO_SAMPLE_FRAMES = 8
AMBULANCE_TEXT_VARIANTS = ("AMBULANCE", "ECNALUBMA")
AMBULANCE_TEXT_MATCH_THRESHOLD = 0.38
RED_CROSS_RED_RATIO_THRESHOLD = 0.03
EMERGENCY_LIGHT_RATIO_THRESHOLD = 0.012


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
        self._lock = asyncio.Lock()
        self._ambulance_classifier = AmbulanceYoloClassifier()

    async def detect(self, image_bytes: bytes) -> Dict[str, Any]:
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Image payload is empty.")

        frame = self._decode_image(image_bytes)
        return await self._analyze_frame(frame, source_type="image")

    async def detect_upload(self, file_bytes: bytes, content_type: str, filename: str | None = None) -> Dict[str, Any]:
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        if content_type.startswith("image/"):
            return await self.detect(file_bytes)
        if content_type.startswith("video/"):
            await self._get_model()
            await self._ambulance_classifier._get_model()
            return await asyncio.to_thread(self._analyze_video_bytes, file_bytes, filename)
        raise HTTPException(status_code=400, detail="Expected an image or video upload.")

    async def _analyze_frame(self, frame: np.ndarray, *, source_type: str) -> Dict[str, Any]:
        model = await self._get_model()
        results = await asyncio.to_thread(model.predict, frame, verbose=False, imgsz=640)
        detections, uncertain_detections = await self._build_detection_lists_async(frame, results[0].boxes, results[0].names)
        emergency_count = sum(1 for item in detections if item.get("is_emergency"))

        accident_alert = self._detect_accident(detections)
        traffic_metrics = self._summarize_traffic(detections, frame.shape[1], frame.shape[0], accident_alert)

        return {
            "detections": detections,
            "uncertain_detections": uncertain_detections,
            "source_type": source_type,
            "image": {"width": int(frame.shape[1]), "height": int(frame.shape[0])},
            "model": "yolov8n + ambulance yolo classifier",
            "vehicle_count": len(detections),
            "uncertain_count": len(uncertain_detections),
            "emergency_count": emergency_count,
            "vehicle_types": traffic_metrics["vehicle_types"],
            "queue_length": traffic_metrics["queue_length"],
            "density_percent": traffic_metrics["density_percent"],
            "density_level": traffic_metrics["density_level"],
            "emergency_detected": traffic_metrics["emergency_detected"],
            "emergency_labels": traffic_metrics["emergency_labels"],
            "signal_priority_value": traffic_metrics["signal_priority_value"],
            "signal_priority_reason": traffic_metrics["signal_priority_reason"],
            "accident_detected": accident_alert["detected"],
            "accident_confidence": accident_alert["confidence"],
            "accident_message": accident_alert["message"],
            "breakdown": {"ambulance": emergency_count, "fire_engine": 0},
            "processed_at": round(time.time(), 6),
        }

    def _analyze_video_bytes(self, file_bytes: bytes, filename: str | None = None) -> Dict[str, Any]:
        suffix = Path(filename or "upload.mp4").suffix or ".mp4"
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(file_bytes)
                temp_path = temp_file.name

            capture = cv2.VideoCapture(temp_path)
            if not capture.isOpened():
                raise HTTPException(status_code=400, detail="Could not read the uploaded video.")

            frame_count = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
            sample_count = min(VIDEO_SAMPLE_FRAMES, frame_count)
            sample_indices = sorted({int(round(index)) for index in np.linspace(0, frame_count - 1, num=sample_count)})

            sampled_results: list[Dict[str, Any]] = []
            for frame_index in sample_indices:
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                success, frame = capture.read()
                if not success or frame is None:
                    continue
                sampled_results.append(self._analyze_frame_sync(frame, source_type="video"))
            capture.release()

            if not sampled_results:
                raise HTTPException(status_code=400, detail="No readable frames were found in the uploaded video.")

            representative = max(
                sampled_results,
                key=lambda item: (
                    float(item.get("signal_priority_value", 0)),
                    float(item.get("vehicle_count", 0)),
                    float(item.get("density_percent", 0)),
                ),
            )
            average_count = sum(float(item.get("vehicle_count", 0)) for item in sampled_results) / len(sampled_results)
            peak_queue = max(int(item.get("queue_length", 0)) for item in sampled_results)
            peak_density = max(float(item.get("density_percent", 0)) for item in sampled_results)

            merged = dict(representative)
            merged["source_type"] = "video"
            merged["sampled_frames"] = len(sampled_results)
            merged["video_summary"] = {
                "average_vehicle_count": round(average_count, 2),
                "peak_vehicle_count": max(int(item.get("vehicle_count", 0)) for item in sampled_results),
                "peak_queue_length": peak_queue,
                "peak_density_percent": peak_density,
                "emergency_detected": any(bool(item.get("emergency_detected")) for item in sampled_results),
                "accident_detected": any(bool(item.get("accident_detected")) for item in sampled_results),
            }
            return merged
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def _analyze_frame_sync(self, frame: np.ndarray, *, source_type: str) -> Dict[str, Any]:
        if self._model is None:
            raise HTTPException(status_code=500, detail="Detection model is not loaded.")

        results = self._model.predict(frame, verbose=False, imgsz=640)
        detections, uncertain_detections = self._build_detection_lists_sync(frame, results[0].boxes, results[0].names)
        emergency_count = sum(1 for item in detections if item.get("is_emergency"))

        accident_alert = self._detect_accident(detections)
        traffic_metrics = self._summarize_traffic(detections, frame.shape[1], frame.shape[0], accident_alert)
        return {
            "detections": detections,
            "uncertain_detections": uncertain_detections,
            "source_type": source_type,
            "image": {"width": int(frame.shape[1]), "height": int(frame.shape[0])},
            "model": "yolov8n + ambulance yolo classifier",
            "vehicle_count": len(detections),
            "uncertain_count": len(uncertain_detections),
            "emergency_count": emergency_count,
            "vehicle_types": traffic_metrics["vehicle_types"],
            "queue_length": traffic_metrics["queue_length"],
            "density_percent": traffic_metrics["density_percent"],
            "density_level": traffic_metrics["density_level"],
            "emergency_detected": traffic_metrics["emergency_detected"],
            "emergency_labels": traffic_metrics["emergency_labels"],
            "signal_priority_value": traffic_metrics["signal_priority_value"],
            "signal_priority_reason": traffic_metrics["signal_priority_reason"],
            "accident_detected": accident_alert["detected"],
            "accident_confidence": accident_alert["confidence"],
            "accident_message": accident_alert["message"],
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
                self._model = await asyncio.to_thread(YOLO, "yolov8n.pt")
        return self._model

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
        is_ambulance, confidence = await self._ambulance_classifier.predict(crop)
        if not is_ambulance:
            return cues, False, confidence
        return cues, bool(cues), confidence

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
        is_ambulance, confidence = self._ambulance_classifier.predict_sync(crop)
        if not is_ambulance:
            return cues, False, confidence
        return cues, bool(cues), confidence

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
        front_features = self._front_view_features(crop, box_payload, frame.shape[1], frame.shape[0])
        vehicle_type = self._resolve_front_vehicle_type(resolved_label, box_payload, front_features, is_ambulance)
        payload = {
            "label": vehicle_type,
            "vehicle_type": vehicle_type,
            "base_vehicle_type": resolved_label,
            "confidence": final_confidence,
            "confidence_level": self._front_confidence_level(final_confidence, front_features),
            "class_id": class_id,
            "is_emergency": is_ambulance,
            "ambulance_cues": ambulance_cues,
            "box": box_payload,
            "position": self._position_label(box_payload, frame.shape[1]),
            "clue": self._front_vehicle_clue(vehicle_type, front_features, ambulance_cues),
            "front_view_clear": front_features["clear_front_view"],
            "front_view_score": front_features["clarity_score"],
            "uncertain_reason": front_features["uncertain_reason"],
        }
        if front_features["clear_front_view"]:
            detections.append(payload)
        else:
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

    def _detect_accident(self, detections: list[Dict[str, Any]]) -> Dict[str, Any]:
        candidates = [item for item in detections if item["label"] in ACCIDENT_LABELS]
        best_score = 0.0
        best_pair: tuple[str, str] | None = None

        for index, first in enumerate(candidates):
            for second in candidates[index + 1 :]:
                overlap = self._intersection_over_union(first["box"], second["box"])
                if overlap < ACCIDENT_IOU_THRESHOLD:
                    continue

                center_distance = self._center_distance(first["box"], second["box"])
                size_scale = max(
                    min(first["box"]["width"], first["box"]["height"]),
                    min(second["box"]["width"], second["box"]["height"]),
                    1.0,
                )
                closeness = max(0.0, 1.0 - (center_distance / (size_scale / ACCIDENT_CENTER_DISTANCE_FACTOR)))
                score = round(min(0.99, (overlap * 0.7) + (closeness * 0.3)), 3)
                if score > best_score:
                    best_score = score
                    best_pair = (first["label"], second["label"])

        detected = best_pair is not None
        message = ""
        if detected and best_pair is not None:
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

    def _summarize_traffic(
        self,
        detections: list[Dict[str, Any]],
        image_width: int,
        image_height: int,
        accident_alert: Dict[str, Any],
    ) -> Dict[str, Any]:
        vehicle_types: Dict[str, int] = {}
        ambulance_cue_counts: Dict[str, int] = {}
        positions_breakdown: Dict[str, int] = {bucket: 0 for bucket in POSITION_BUCKETS}
        queue_length = 0
        total_area = 0.0
        emergency_labels: list[str] = []

        for item in detections:
            label = str(item["label"])
            vehicle_types[label] = vehicle_types.get(label, 0) + 1
            position = str(item.get("position", "center"))
            if position in positions_breakdown:
                positions_breakdown[position] += 1
            box = item["box"]
            total_area += float(box["width"]) * float(box["height"])

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
        self.engine = TrafficSimulationEngine()
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
            self.latest_snapshot = self._merge_external_events(self.engine.snapshot().to_dict())
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
                self.engine.reset()
            elif message_type == "ping":
                return {"type": "pong", "sent_at": round(time.time(), 6)}
            else:
                return {"type": "error", "message": f"Unknown message type: {message_type or 'empty'}"}

            self.latest_snapshot = self._merge_external_events(self.engine.snapshot().to_dict())
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


def _compute_junction_priority(approaches: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Dict[str, Any]] = {}
    active_directions: list[str] = []

    for direction in JUNCTION_DIRECTIONS:
        raw = approaches.get(direction, {}) if isinstance(approaches, dict) else {}
        vehicle_count = _coerce_int(raw.get("vehicle_count"))
        queue_length = _coerce_int(raw.get("queue_length"))
        density_percent = _coerce_float(raw.get("density_percent"))
        signal_priority_value = _coerce_int(raw.get("signal_priority_value"))
        uncertain_count = _coerce_int(raw.get("uncertain_count"))
        emergency_detected = bool(raw.get("emergency_detected"))
        accident_detected = bool(raw.get("accident_detected"))
        density_level = str(raw.get("density_level") or "low")

        analyzed = any(
            [
                vehicle_count > 0,
                queue_length > 0,
                density_percent > 0.0,
                signal_priority_value > 0,
                emergency_detected,
                accident_detected,
                uncertain_count > 0,
            ]
        )
        effective_priority = max(
            0,
            min(
                100,
                signal_priority_value
                + (36 if emergency_detected else 0)
                + (14 if accident_detected else 0)
                + min(queue_length * 3, 18)
                + min(int(density_percent * 0.18), 12)
                - min(uncertain_count * 2, 10),
            ),
        )

        normalized[direction] = {
            "direction": direction,
            "vehicle_count": vehicle_count,
            "queue_length": queue_length,
            "density_percent": round(density_percent, 2),
            "density_level": density_level,
            "signal_priority_value": signal_priority_value,
            "effective_priority": effective_priority if analyzed else 0,
            "emergency_detected": emergency_detected,
            "accident_detected": accident_detected,
            "uncertain_count": uncertain_count,
            "status": "ready" if analyzed else "waiting",
        }
        if analyzed:
            active_directions.append(direction)

    if not active_directions:
        return {
            "ready": False,
            "recommended_green_direction": None,
            "signal_states": {direction: "red" for direction in JUNCTION_DIRECTIONS},
            "cycle_plan": {"green_duration_sec": 0, "amber_duration_sec": 0, "all_red_duration_sec": 0},
            "rationale": "Analyze at least one direction to recommend a safe junction phase plan.",
            "approaches": normalized,
        }

    winner = max(
        active_directions,
        key=lambda direction: (
            normalized[direction]["effective_priority"],
            normalized[direction]["emergency_detected"],
            normalized[direction]["queue_length"],
            normalized[direction]["vehicle_count"],
        ),
    )
    winner_data = normalized[winner]
    green_duration_sec = min(
        70,
        max(
            18,
            18
            + min(winner_data["queue_length"] * 4, 20)
            + min(int(winner_data["density_percent"] * 0.22), 18)
            + (14 if winner_data["emergency_detected"] else 0),
        ),
    )
    amber_duration_sec = 4 if winner_data["density_level"] in {"medium", "high"} or winner_data["vehicle_count"] >= 6 else 3
    all_red_duration_sec = 2

    if winner_data["emergency_detected"]:
        rationale = f"{winner.title()} approach has an emergency vehicle, so it should receive immediate green priority."
    elif winner_data["accident_detected"]:
        rationale = f"{winner.title()} approach shows accident risk, so traffic should clear that leg first while the other signals stay red."
    elif winner_data["queue_length"] >= 4 or winner_data["density_level"] == "high":
        rationale = f"{winner.title()} approach has the strongest queue pressure and density, so it should receive the next green phase."
    else:
        rationale = f"{winner.title()} approach currently has the highest balanced traffic demand and should receive green in the next cycle."

    return {
        "ready": True,
        "recommended_green_direction": winner,
        "signal_states": {direction: ("green" if direction == winner else "red") for direction in JUNCTION_DIRECTIONS},
        "cycle_plan": {
            "green_duration_sec": green_duration_sec,
            "amber_duration_sec": amber_duration_sec,
            "all_red_duration_sec": all_red_duration_sec,
        },
        "rationale": rationale,
        "approaches": normalized,
    }


runtime = SimulationRuntime()
vehicle_detector = VehicleDetector()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await runtime.start()
    try:
        yield
    finally:
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
async def detect_vehicles(media: UploadFile = File(...)) -> Dict[str, Any]:
    if not media.content_type:
        raise HTTPException(status_code=400, detail="Expected an image or video upload.")

    file_bytes = await media.read()
    result = await vehicle_detector.detect_upload(file_bytes, media.content_type, media.filename)
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
    return _compute_junction_priority(approaches if isinstance(approaches, dict) else {})


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
