"""
core/detector.py — YOLOv8 Object Detection Engine
===================================================
Handles vehicle, pedestrian, and ambulance detection.
"""

import cv2
import numpy as np
from ultralytics import YOLO
from typing import List, Dict, Tuple, Optional
import sys
import os

# Add parent to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class Detection:
    """Represents a single object detection result."""
    
    def __init__(self, box: Tuple[int,int,int,int], label: str, confidence: float,
                 class_id: int, is_vehicle: bool, is_person: bool, is_ambulance: bool):
        self.x1, self.y1, self.x2, self.y2 = box
        self.label     = label
        self.confidence = confidence
        self.class_id  = class_id
        self.is_vehicle    = is_vehicle
        self.is_person     = is_person
        self.is_ambulance  = is_ambulance
        
        # Centroid
        self.cx = (self.x1 + self.x2) // 2
        self.cy = (self.y1 + self.y2) // 2
        
        # Width / Height
        self.w = self.x2 - self.x1
        self.h = self.y2 - self.y1
    
    @property
    def box(self):
        return (self.x1, self.y1, self.x2, self.y2)
    
    @property
    def centroid(self):
        return (self.cx, self.cy)
    
    def __repr__(self):
        return f"Detection({self.label} {self.confidence:.2f} @ ({self.cx},{self.cy}))"


class Detector:
    """
    YOLOv8-based multi-class object detector.
    
    Detects vehicles (car, motorcycle, bus, truck), pedestrians,
    and ambulances in each video frame.
    """
    
    # Color palette per class
    COLORS = {
        "car":        (0,   220, 100),
        "motorcycle": (255, 165, 0  ),
        "bus":        (0,   100, 255),
        "truck":      (128, 0,   255),
        "person":     (255, 255, 0  ),
        "ambulance":  (255, 0,   0  ),
        "default":    (200, 200, 200),
    }
    
    def __init__(self, model_name: str = None, conf: float = None):
        model_name = model_name or config.MODEL_NAME
        conf       = conf       or config.CONFIDENCE_THRESHOLD
        
        print(f"[Detector] Loading model: {model_name}")
        self.model = YOLO(model_name)
        self.conf  = conf
        self.names = self.model.names   # {id: name}
        
        # Precompute valid vehicle class IDs
        self._vehicle_ids = set(config.VEHICLE_CLASSES.keys())
        
        print(f"[Detector] Ready. Classes available: {len(self.names)}")
    
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run detection on a single BGR frame.
        Returns a list of Detection objects.
        """
        results = self.model(frame, conf=self.conf, verbose=False)
        detections: List[Detection] = []
        
        if not results:
            return detections
        
        r = results[0]
        if r.boxes is None:
            return detections
        
        h, w = frame.shape[:2]
        
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
            # Clamp to frame
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            label = self.names.get(cls_id, "unknown")
            
            # Classify detection type
            is_vehicle   = cls_id in self._vehicle_ids and cls_id != 0
            is_person    = cls_id == 0
            is_ambulance = any(kw in label.lower() for kw in config.AMBULANCE_CLASS_KEYWORDS)
            
            # ── Hackathon Ambulance Override Heuristic ──
            # YOLOv8n struggles with ambulances. If it's a large vehicle, scan its pixels.
            if is_vehicle and not is_ambulance and label in ["truck", "bus", "car"]:
                box_width = x2 - x1
                box_height = y2 - y1
                frame_area = w * h
                box_area = box_width * box_height
                
                # Check for "truck/bus in size" -> either labeled as such, or big enough area
                is_truck_bus_size = label in ["truck", "bus"] or box_area > (frame_area * 0.05)
                
                if is_truck_bus_size:
                    # Crop the bounding box from the frame
                    crop = frame[y1:y2, x1:x2]
                    if crop.size > 0:
                        # Convert to HSV to look for bright white bodies & intense red/blue lights
                        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                        
                        # White mask (low saturation, high value)
                        lower_white = np.array([0, 0, 200])
                        upper_white = np.array([180, 40, 255])
                        mask_white = cv2.inRange(hsv, lower_white, upper_white)
                        
                        # Red mask (flashing lights usually stand out in hue 0-10 or 160-180 with high saturation/value)
                        mask_red1 = cv2.inRange(hsv, np.array([0, 150, 150]), np.array([10, 255, 255]))
                        mask_red2 = cv2.inRange(hsv, np.array([160, 150, 150]), np.array([180, 255, 255]))
                        mask_red = cv2.bitwise_or(mask_red1, mask_red2)
                        
                        # Blue mask (flashing lights usually stand out in hue 100-140)
                        lower_blue = np.array([100, 150, 150])
                        upper_blue = np.array([140, 255, 255])
                        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
                        
                        crop_area = crop.shape[0] * crop.shape[1]
                        white_ratio = cv2.countNonZero(mask_white) / crop_area
                        red_ratio = cv2.countNonZero(mask_red) / crop_area
                        blue_ratio = cv2.countNonZero(mask_blue) / crop_area
                        
                        # If it's predominantly white (>15%) and has EITHER red (>0.2%) OR blue peaks (>0.2%), override it!
                        if white_ratio > 0.15 and (red_ratio > 0.002 or blue_ratio > 0.002):
                            is_ambulance = True
                            label = "ambulance"
                        
            # ──────────────────────────────────────────────
            
            # Filter: only keep relevant classes
            if not (is_vehicle or is_person or is_ambulance):
                continue
            
            det = Detection(
                box=(x1, y1, x2, y2),
                label=label,
                confidence=conf,
                class_id=cls_id,
                is_vehicle=is_vehicle,
                is_person=is_person,
                is_ambulance=is_ambulance,
            )
            detections.append(det)
        
        return detections
    
    def draw(self, frame: np.ndarray, detections: List[Detection],
             show_labels: bool = True) -> np.ndarray:
        """Draw bounding boxes and labels on frame (in-place)."""
        for det in detections:
            color = self.COLORS.get(det.label, self.COLORS["default"])
            
            # Thicker box for ambulance
            thickness = 4 if det.is_ambulance else 2
            
            # Draw box
            cv2.rectangle(frame, (det.x1, det.y1), (det.x2, det.y2), color, thickness)
            
            if show_labels:
                text = f"{det.label} {det.confidence:.2f}"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                
                # Label background
                cv2.rectangle(frame,
                              (det.x1, det.y1 - th - 8),
                              (det.x1 + tw + 4, det.y1),
                              color, -1)
                cv2.putText(frame, text,
                            (det.x1 + 2, det.y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1,
                            cv2.LINE_AA)
            
            # Draw centroid dot
            cv2.circle(frame, det.centroid, 3, color, -1)
            
            # Special ambulance indicator
            if det.is_ambulance:
                cv2.putText(frame, "🚑 AMBULANCE DETECTED",
                            (det.x1, det.y1 - 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2,
                            cv2.LINE_AA)
        
        return frame
    
    def get_vehicle_count(self, detections: List[Detection]) -> int:
        return sum(1 for d in detections if d.is_vehicle)
    
    def has_ambulance(self, detections: List[Detection]) -> bool:
        return any(d.is_ambulance for d in detections)
    
    def has_person(self, detections: List[Detection]) -> bool:
        return any(d.is_person for d in detections)