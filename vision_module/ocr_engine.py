import cv2
import pytesseract
import numpy as np
from typing import Dict, Any, Tuple
from vision_module.config import TESSERACT_CONFIG, AMBULANCE_KEYWORDS, OCR_MIN_CHAR_COUNT

def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Applies image preprocessing to improve Tesseract OCR accuracy.
    - Grayscale conversion
    - 2x Upscaling
    - Gaussian Blurring
    - OTSU Binary Thresholding
    """
    if image is None or image.size == 0:
        return None
        
    # 1. Grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # 2. Resize (2x scaling for better character recognition)
    resized = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    
    # 3. Gaussian Blur to reduce noise
    blurred = cv2.GaussianBlur(resized, (3, 3), 0)
    
    # 4. Binary Thresholding (Adaptive/Otsu)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 5. Optional: Sharpening
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(thresh, -1, kernel)
    
    return sharpened

def detect_ambulance_text(image: np.ndarray) -> Dict[str, Any]:
    """
    Detects "AMBULANCE" text from a vehicle crop using Tesseract OCR.
    """
    preprocessed = preprocess_for_ocr(image)
    if preprocessed is None:
        return {
            "text_detected": False,
            "ocr_text": "",
            "confidence_hint": "low"
        }
        
    # Run Tesseract with custom config
    # Note: Ensure tesseract binary is in system path or set pytesseract.pytesseract.tesseract_cmd
    try:
        raw_text = pytesseract.image_to_string(preprocessed, config=TESSERACT_CONFIG)
        detected_text = raw_text.strip().upper()
    except Exception as e:
        print(f"[OCR] Error running Tesseract: {e}")
        return {
            "text_detected": False,
            "ocr_text": f"Error: {str(e)}",
            "confidence_hint": "low"
        }
    
    # Detection Logic
    is_detected = False
    confidence_hint = "low"
    
    # Filter noisy/short strings
    if len(detected_text) >= OCR_MIN_CHAR_COUNT:
        for keyword in AMBULANCE_KEYWORDS:
            if keyword in detected_text:
                is_detected = True
                confidence_hint = "high"
                break
        
        # Fallback: fuzzy match for partial strings if long enough
        if not is_detected and len(detected_text) >= 5:
            # Simple heuristic: if at least 5 letters match 'AMBULANCE' sequentially
            if "AMBUL" in detected_text or "ULANC" in detected_text:
                is_detected = True
                confidence_hint = "medium"

    # Visualization (for debugging)
    # In a real pipeline, we'd log this or save to a debug dir
    if is_detected:
        print(f"[OCR] Positive Match: '{detected_text}' | Confidence: {confidence_hint}")

    return {
        "text_detected": is_detected,
        "ocr_text": detected_text,
        "confidence_hint": confidence_hint
    }
