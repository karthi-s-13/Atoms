import cv2
import json
from vision_module.detector import AmbulanceDetector
from vision_module.utils import draw_debug_info

def main():
    # Initialize the high-precision detector
    detector = AmbulanceDetector()
    
    # Path to sample video or image
    # video_path = "path/to/traffic_feed.mp4"
    image_path = r"C:\Users\karth\.gemini\antigravity\brain\61ed87d7-0b43-4c36-a77a-12bb390403a3\test_ambulance_1_1774538406579.png"
    
    # Load sample image
    image = cv2.imread(image_path)
    if image is None:
        print(f"Error: Could not load {image_path}. Please provide a valid path.")
        return

    # Run detection
    results = detector.detect_frame(image)
    
    # Print structured output
    print(json.dumps(results, indent=2))
    
    # Draw debug overlay
    for res in results:
        if res["ambulance_detected"]:
            debug_frame = draw_debug_info(image, res)
            cv2.imshow("Ambulance Detection Debug", debug_frame)
            cv2.waitKey(0)

if __name__ == "__main__":
    main()
