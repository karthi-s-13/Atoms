import cv2
import json
import torch
import numpy as np
from ultralytics import YOLO, RTDETR
from typing import List, Dict, Any, Optional

# Modular OCR engine (Tesseract-based)
from vision_module.ocr_engine import detect_ambulance_text

from vision_module.config import (
    YOLO_MODEL_PATH, RTDETR_MODEL_PATH,
    VEHICLE_DETECTION_THRESHOLD, AMBULANCE_REFINEMENT_THRESHOLD,
    OCR_CONFIDENCE_THRESHOLD, ROI_PADDING, AMBULANCE_KEYWORDS, FRAME_SKIP
)
from vision_module.utils import crop_roi, detect_emergency_lights

class AmbulanceDetector:
    """
    Hybrid Ambulance Detection System using YOLOv8, RT-DETR, and OCR.
    """
    
    def __init__(self, device: str = "cuda" if torch.cuda.is_available() else "cpu"):
        self.device = device
        print(f"[Vision] Initializing models on {self.device}...")
        
        # Step 1: YOLOv8s for initial vehicle detection
        self.yolo_proposer = YOLO(YOLO_MODEL_PATH).to(self.device)
        
        # Step 2: RT-DETR for fine-grained refinement
        self.rtdetr_verifier = RTDETR(RTDETR_MODEL_PATH).to(self.device)
        
    def _perform_ocr(self, roi: np.ndarray) -> Dict[str, Any]:
        """Runs Tesseract OCR on the ROI using the modular engine."""
        return detect_ambulance_text(roi)

    def _validate_ambulance_text(self, text: str) -> bool:
        """Checks if any ambulance-related keywords exist in the text."""
        for keyword in AMBULANCE_KEYWORDS:
            if keyword in text:
                return True
        return False

    def refine_crop(self, crop: np.ndarray) -> Dict[str, Any]:
        """
        Refines a single vehicle crop using RT-DETR, OCR, and light detection.
        Returns a dictionary with detection results and evidence.
        """
        if crop is None or crop.size == 0:
            return {
                "ambulance_detected": False,
                "confidence": 0.0,
                "evidence": {"ocr_text": "", "light_detected": False, "model_agreement": False}
            }

        # 1. RT-DETR Refinement on ROI
        # Confirms vehicle characteristics with high-precision model
        refinements = self.rtdetr_verifier.predict(
            crop, 
            conf=AMBULANCE_REFINEMENT_THRESHOLD,
            verbose=False
        )
        model_agreement = len(refinements[0].boxes) > 0
        
        # 2. Evidence Gathering
        ocr_result = self._perform_ocr(crop) # Use 'crop' as per original logic
        has_text = ocr_result["text_detected"]
        has_lights = detect_emergency_lights(crop)
        
        # 3. Hybrid Fusion Logic
        # STRICT RULE: Must have (OCR or LIGHTS) + Model Agreement
        is_ambulance = False
        if model_agreement and (has_text or has_lights):
            is_ambulance = True
            
        return {
            "ambulance_detected": is_ambulance,
            "evidence": {
                "ocr_text": ocr_result["ocr_text"],
                "confidence_hint": ocr_result["confidence_hint"],
                "light_detected": has_lights,
                "model_agreement": model_agreement
            }
        }

    def detect_frame(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Runs the full hybrid detection pipeline on a single frame.
        """
        final_results = []
        
        # 1. Initial Detection (All Vehicles)
        proposals = self.yolo_proposer.predict(
            frame, 
            conf=VEHICLE_DETECTION_THRESHOLD, 
            classes=[2, 3, 5, 7],
            verbose=False
        )
        
        for proposal in proposals:
            for box in proposal.boxes:
                bbox = box.xyxy[0].tolist() # [x1, y1, x2, y2]
                
                # 2. Crop ROI for refinement
                roi = crop_roi(frame, bbox, padding=ROI_PADDING)
                
                # 3. Use refine_crop for detailed analysis
                refinement = self.refine_crop(roi)
                
                # 4. Merge results
                result = {
                    "ambulance_detected": refinement["ambulance_detected"],
                    "confidence": float(box.conf[0]),
                    "bounding_box": bbox,
                    "evidence": refinement["evidence"]
                }
                final_results.append(result)
        
        return final_results

    def log_false_positive(self, result: Dict[str, Any], frame: np.ndarray):
        """Logs cases where the model was uncertain or had conflicting evidence."""
        log_file = "vision_module/false_positives.log"
        with open(log_file, "a") as f:
            f.write(json.dumps(result) + "\n")
        # Optionally save the frame
        # cv2.imwrite(f"vision_module/fp_{result['confidence']:.2f}.jpg", frame)

    def process_stream(self, video_path: str, output_path: Optional[str] = None):
        """Processes a video file/stream and optionally saves debug output."""
        cap = cv2.VideoCapture(video_path)
        frame_count = 0
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_count += 1
            if frame_count % (FRAME_SKIP + 1) != 0:
                continue
                
            results = self.detect_frame(frame)
            
            # Print structured JSON as requested
            for res in results:
                if res["ambulance_detected"]:
                    print(json.dumps(res, indent=2))
                    
        cap.release()
