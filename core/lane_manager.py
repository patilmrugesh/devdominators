"""
core/lane_manager.py — Virtual Lane Polygon Assignment
=======================================================
Defines virtual lane regions at an intersection and assigns
each tracked vehicle to the correct lane using polygon containment.

Design: Manual polygon approach (Approach A — best for hackathon).
Trade-off: Reliable and fast vs. AI lane detection which is error-prone.
"""

import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


@dataclass
class LaneStats:
    """Statistics for a single lane."""
    name:           str
    vehicle_count:  int   = 0
    person_count:   int   = 0
    ambulance_present: bool = False
    density_ratio:  float = 0.0     # 0.0–1.0 (area occupancy)
    avg_wait_time:  float = 0.0
    max_wait_time:  float = 0.0
    queue_length:   int   = 0       # Number of stopped vehicles
    flow_per_min:   float = 0.0     # Throughput
    
    @property
    def congestion_level(self) -> str:
        if self.vehicle_count == 0:
            return "free"
        elif self.vehicle_count <= 3:
            return "light"
        elif self.vehicle_count <= 8:
            return "moderate"
        else:
            return "heavy"
    
    @property
    def priority_score(self) -> float:
        """Score for signal priority — heavily weighted by physical density."""
        score = self.vehicle_count * 2.0
        score += self.density_ratio * 50.0  # Density drives phase decisions
        score += self.avg_wait_time * 0.5
        score += self.queue_length * 3.0
        if self.ambulance_present:
            score += 10000.0  # Ambulance always wins
        return score


class LaneManager:
    """
    Manages virtual lane polygons and assigns tracks to lanes.
    
    Polygon coordinates are normalized (0–1) relative to frame size
    and scaled to actual pixel coordinates at runtime.
    """
    
    # Draw colors per lane
    LANE_COLORS = {
        "North": (255, 100, 100),
        "South": (100, 255, 100),
        "East":  (100, 100, 255),
        "West":  (255, 255, 100),
    }
    
    def __init__(self, frame_width: int, frame_height: int,
                 polygons: Dict[str, List[Tuple[float,float]]] = None):
        self.fw = frame_width
        self.fy = frame_height
        
        raw = polygons or config.LANE_POLYGONS
        
        # Convert normalized polygons to pixel polygons
        self.lane_polys: Dict[str, np.ndarray] = {}
        for lane_name, norm_pts in raw.items():
            pts = [(int(x * frame_width), int(y * frame_height))
                   for x, y in norm_pts]
            self.lane_polys[lane_name] = np.array(pts, dtype=np.int32)
        
        self.lane_names = list(self.lane_polys.keys())
        
        # Lane area (pixels squared) for density calculation
        self.lane_areas: Dict[str, float] = {
            name: cv2.contourArea(poly)
            for name, poly in self.lane_polys.items()
        }
        
        # Stats per lane
        self.stats: Dict[str, LaneStats] = {
            name: LaneStats(name=name) for name in self.lane_names
        }
        
        # Throughput tracking
        self._flow_counter: Dict[str, int]  = {n: 0 for n in self.lane_names}
        self._flow_timer:   Dict[str, float] = {n: 0.0 for n in self.lane_names}
    
    def assign_lane(self, cx: int, cy: int) -> Optional[str]:
        """
        Assign a centroid (cx, cy) to a lane using polygon containment.
        Returns None if centroid is not in any lane polygon.
        """
        pt = (float(cx), float(cy))
        for name, poly in self.lane_polys.items():
            result = cv2.pointPolygonTest(poly, pt, measureDist=False)
            if result >= 0:
                return name
        return None
    
    def update(self, tracks) -> Dict[str, LaneStats]:
        """
        Assign tracks to lanes and recompute lane statistics.
        
        Args:
            tracks: List of Track objects from tracker.py
        
        Returns:
            Dict of lane_name → LaneStats
        """
        import time
        
        # Reset stats
        lane_vehicles:  Dict[str, List] = {n: [] for n in self.lane_names}
        lane_persons:   Dict[str, int]  = {n: 0  for n in self.lane_names}
        lane_ambul:     Dict[str, bool] = {n: False for n in self.lane_names}
        lane_stopped:   Dict[str, int]  = {n: 0  for n in self.lane_names}
        lane_wait:      Dict[str, List[float]] = {n: [] for n in self.lane_names}
        lane_bbox_area: Dict[str, float] = {n: 0.0 for n in self.lane_names}
        
        for track in tracks:
            lane = self.assign_lane(track.cx, track.cy)
            track.lane = lane  # Write back
            
            if lane is None:
                continue
            
            if track.is_vehicle:
                lane_vehicles[lane].append(track)
                bbox_area = track.w * track.h
                lane_bbox_area[lane] += bbox_area
                
                if track.is_stopped:
                    lane_stopped[lane] += 1
                lane_wait[lane].append(track.wait_time)
                
                if track.is_ambulance:
                    lane_ambul[lane] = True
            
            elif track.is_person:
                lane_persons[lane] += 1
        
        # Build LaneStats
        for name in self.lane_names:
            waits = lane_wait[name]
            area  = self.lane_areas[name]
            
            s = self.stats[name]
            s.vehicle_count     = len(lane_vehicles[name])
            s.person_count      = lane_persons[name]
            s.ambulance_present = lane_ambul[name]
            s.density_ratio     = min(1.0, lane_bbox_area[name] / max(area, 1))
            s.avg_wait_time     = sum(waits) / len(waits) if waits else 0.0
            s.max_wait_time     = max(waits) if waits else 0.0
            s.queue_length      = lane_stopped[name]
        
        return self.stats
    
    def draw_lanes(self, frame: np.ndarray, show_labels: bool = True) -> np.ndarray:
        """Draw lane polygon overlays on the frame."""
        overlay = frame.copy()
        
        for name, poly in self.lane_polys.items():
            color = self.LANE_COLORS.get(name, (200, 200, 200))
            stats = self.stats[name]
            
            # Filled polygon (semi-transparent)
            alpha = 0.15 if stats.vehicle_count == 0 else 0.25
            cv2.fillPoly(overlay, [poly], color)
            
            # Border
            cv2.polylines(frame, [poly], isClosed=True, color=color, thickness=2)
            
            if show_labels:
                # Lane label near centroid of polygon
                M = cv2.moments(poly)
                if M["m00"] != 0:
                    lx = int(M["m10"] / M["m00"])
                    ly = int(M["m01"] / M["m00"])
                else:
                    lx, ly = poly[0]
                
                text = f"{name}: {stats.vehicle_count}v"
                cv2.putText(frame, text, (lx - 30, ly),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            color, 2, cv2.LINE_AA)
                
                # Congestion level
                cong = stats.congestion_level.upper()
                cong_color = {
                    "FREE": (0, 255, 0),
                    "LIGHT": (0, 200, 150),
                    "MODERATE": (0, 165, 255),
                    "HEAVY": (0, 0, 255),
                }.get(cong, (255,255,255))
                cv2.putText(frame, cong, (lx - 30, ly + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                            cong_color, 1, cv2.LINE_AA)
        
        # Blend overlay
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
        return frame
    
    def get_priority_order(self) -> List[str]:
        """Return lanes sorted by priority score (highest first)."""
        return sorted(
            self.lane_names,
            key=lambda n: self.stats[n].priority_score,
            reverse=True
        )
    
    def get_max_wait_lane(self) -> Optional[Tuple[str, float]]:
        """Return (lane_name, wait_time) of the lane with highest max wait."""
        if not self.stats:
            return None
        best = max(self.stats.items(), key=lambda x: x[1].max_wait_time)
        return best[0], best[1].max_wait_time
