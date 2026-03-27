import cv2
import numpy as np
from typing import List, Tuple

def crop_roi(image: np.ndarray, bbox: List[float], padding: int = 20) -> np.ndarray:
    """
    Crops an ROI from the image with optional padding.
    bbox: [x1, y1, x2, y2]
    """
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox
    
    # Apply padding
    x1 = max(0, int(x1 - padding))
    y1 = max(0, int(y1 - padding))
    x2 = min(w, int(x2 + padding))
    y2 = min(h, int(y2 + padding))
    
    return image[y1:y2, x1:x2]

def detect_emergency_lights(roi: np.ndarray) -> bool:
    """
    Heuristic-based emergency light detection.
    Looks for red/blue saturated regions in the upper part of the vehicle.
    """
    if roi.size == 0:
        return False
        
    # Focus on the top 40% of the vehicle (where light bars usually are)
    h, w = roi.shape[:2]
    top_roi = roi[0:int(h*0.4), :]
    
    hsv = cv2.cvtColor(top_roi, cv2.COLOR_BGR2HSV)
    
    # Red ranges
    lower_red1 = np.array([0, 150, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 150, 100])
    upper_red2 = np.array([180, 255, 255])
    
    mask_red = cv2.bitwise_or(cv2.inRange(hsv, lower_red1, upper_red1),
                               cv2.inRange(hsv, lower_red2, upper_red2))
    
    # Blue ranges
    lower_blue = np.array([100, 150, 100])
    upper_blue = np.array([130, 255, 255])
    mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
    
    # Light structure detection (high value, low saturation - white lights/reflections)
    lower_white = np.array([0, 0, 200])
    upper_white = np.array([180, 50, 255])
    mask_white = cv2.inRange(hsv, lower_white, upper_white)
    
    red_ratio = np.sum(mask_red > 0) / (h * w)
    blue_ratio = np.sum(mask_blue > 0) / (h * w)
    white_ratio = np.sum(mask_white > 0) / (h * w)
    
    # Heuristic: Presence of both red/blue or significant red/blue in a small area
    # Or a dense white/reflective strip in the center top
    if (red_ratio > 0.005 and blue_ratio > 0.005) or (red_ratio > 0.015) or (blue_ratio > 0.015):
        return True
        
    return False

def draw_debug_info(image: np.ndarray, result: dict) -> np.ndarray:
    """Draws bounding boxes and metadata on the frame."""
    draw = image.copy()
    if not result.get("ambulance_detected"):
        return draw
        
    x1, y1, x2, y2 = map(int, result["bounding_box"])
    conf = result["confidence"]
    evidence = result["evidence"]
    
    color = (0, 0, 255) # Red for ambulance
    cv2.rectangle(draw, (x1, y1), (x2, y2), color, 3)
    
    label = f"AMBULANCE {conf:.2f}"
    cv2.putText(draw, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    
    # Draw evidence summary
    y_off = y2 + 20
    text = f"OCR: {evidence['ocr_text']} | Light: {evidence['light_detected']}"
    cv2.putText(draw, text, (x1, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    return draw
