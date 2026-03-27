import os

# Model Paths
# YOLOv8s is the suggested base proposer
YOLO_MODEL_PATH = "yolov8s.pt"  
# RT-DETR-L for refinement
RTDETR_MODEL_PATH = "rtdetr-l.pt" 

# Confidence Thresholds
VEHICLE_DETECTION_THRESHOLD = 0.45
AMBULANCE_REFINEMENT_THRESHOLD = 0.65
OCR_CONFIDENCE_THRESHOLD = 0.80

# Processing Settings
FRAME_SKIP = 3  # Process every 4th frame for video streams
BATCH_SIZE = 4
USE_GPU = True

# ROI Expansion (to capture context/OCR)
ROI_PADDING = 20  # pixels

# OCR Settings (Tesseract)
TESSERACT_CONFIG = "--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ"
OCR_MIN_CHAR_COUNT = 4

# OCR Keywords for fuzzy matching
AMBULANCE_KEYWORDS = ["AMBULANCE", "AMBULAN", "AMBULANCEE", "MEDICAL", "RESCUE"]
