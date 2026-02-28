"""
core/traffic_analyzer.py — Traffic Metrics & Accident Detection
===============================================================
Aggregates tracker + lane data into actionable metrics.
Detects accidents, anomalies, and generates alerts.
"""

import time
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


@dataclass
class Alert:
    """A system alert (accident, emergency, congestion)."""
    alert_type:  str          # "accident", "ambulance", "congestion", "info"
    message:     str
    lane:        Optional[str] = None
    severity:    str = "low"  # "low", "medium", "high", "critical"
    timestamp:   float = field(default_factory=time.time)
    acknowledged: bool = False
    
    @property
    def age(self) -> float:
        return time.time() - self.timestamp
    
    def to_dict(self) -> Dict:
        return {
            "type": self.alert_type,
            "message": self.message,
            "lane": self.lane,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "age": round(self.age, 1),
        }


class TrafficAnalyzer:
    """
    Analyzes traffic flow, detects accidents, and manages alert system.
    
    Accident Detection Strategy (Hackathon):
      Rule-based:
        1. Vehicle stopped for > STOP_THRESHOLD seconds (possible stall/accident)
        2. Bounding box overlap (IoU > threshold) between two vehicles (collision)
        3. Person detected in road lane (pedestrian accident)
    """
    
    MAX_ALERTS = 20
    ALERT_EXPIRY = 30.0  # Seconds before auto-clearing alerts
    
    def __init__(self):
        self.alerts:    List[Alert] = []
        self.metrics:   Dict = {}
        
        # History for charts
        self.count_history:   List[Dict] = []   # [{time, north, south, east, west}, ...]
        self.wait_history:    List[Dict] = []
        self.history_window   = 60  # seconds
        
        # Accident tracking
        self._stop_counters: Dict[int, float] = {}  # track_id → when_stopped
        self._accident_cooldown: float = 0.0         # Prevent duplicate alerts
        
        # Session stats
        self.session_start    = time.time()
        self.total_detected   = 0
        self.total_accidents  = 0
        self.total_emergency  = 0
        
        # FPS tracking
        self._fps_frames     = 0
        self._fps_start      = time.time()
        self.current_fps     = 0.0
    
    def update(self, tracks, lane_stats: Dict, detections) -> List[Alert]:
        """
        Main analysis tick.
        
        Args:
            tracks:      List[Track] from tracker
            lane_stats:  Dict[lane_name → LaneStats] from lane manager
            detections:  List[Detection] from detector
        
        Returns:
            New alerts generated this tick.
        """
        new_alerts: List[Alert] = []
        now = time.time()
        
        # ── FPS tracking ─────────────────────────────────────────────────────
        self._fps_frames += 1
        fps_elapsed = now - self._fps_start
        if fps_elapsed >= 1.0:
            self.current_fps  = self._fps_frames / fps_elapsed
            self._fps_frames  = 0
            self._fps_start   = now
        
        # ── Total detection count ─────────────────────────────────────────────
        vehicle_tracks = [t for t in tracks if t.is_vehicle]
        self.total_detected = max(self.total_detected, len(vehicle_tracks))
        
        # ── Ambulance alerts ─────────────────────────────────────────────────
        for track in tracks:
            if track.is_ambulance:
                if not any(a.alert_type == "ambulance" for a in self.alerts
                           if a.age < self.ALERT_EXPIRY):
                    alert = Alert(
                        alert_type="ambulance",
                        message=f"🚑 AMBULANCE detected in {track.lane or 'unknown'} lane!",
                        lane=track.lane,
                        severity="critical"
                    )
                    new_alerts.append(alert)
                    self.total_emergency += 1
        
        # ── Accident detection ────────────────────────────────────────────────
        if now > self._accident_cooldown:
            acc_alert = self._check_accidents(tracks, detections, lane_stats)
            if acc_alert:
                new_alerts.append(acc_alert)
                self._accident_cooldown = now + 10.0  # 10s cooldown
        
        # ── Heavy congestion alert ────────────────────────────────────────────
        for lane_name, stats in lane_stats.items():
            if stats.vehicle_count > 10:
                if not any(a.alert_type == "congestion" and a.lane == lane_name
                           for a in self.alerts if a.age < 15.0):
                    new_alerts.append(Alert(
                        alert_type="congestion",
                        message=f"Heavy congestion in {lane_name} lane ({stats.vehicle_count} vehicles)",
                        lane=lane_name,
                        severity="medium"
                    ))
        
        # ── Maintain alert list ───────────────────────────────────────────────
        self.alerts = [a for a in self.alerts if a.age < self.ALERT_EXPIRY]
        self.alerts.extend(new_alerts)
        if len(self.alerts) > self.MAX_ALERTS:
            self.alerts = self.alerts[-self.MAX_ALERTS:]
        
        # ── History recording ─────────────────────────────────────────────────
        entry = {"time": now}
        for name, stats in lane_stats.items():
            entry[name] = stats.vehicle_count
        
        self.count_history.append(entry)
        # Trim old history
        cutoff = now - self.history_window
        self.count_history = [e for e in self.count_history if e["time"] >= cutoff]
        
        # ── Build metrics dict ────────────────────────────────────────────────
        self.metrics = self._build_metrics(tracks, lane_stats, detections)
        
        return new_alerts
    
    def _check_accidents(self, tracks, detections, lane_stats) -> Optional[Alert]:
        """Rule-based accident detection."""
        vehicle_tracks = [t for t in tracks if t.is_vehicle]
        
        if not vehicle_tracks:
            return None
        
        # Check 1: Long-stopped vehicles (possible stall or accident)
        stopped = [t for t in vehicle_tracks
                   if t.is_stopped and t.wait_time > config.ACCIDENT_STOP_THRESHOLD * 2]
        
        # Check 2: Bounding box overlap (collision)
        for i, t1 in enumerate(vehicle_tracks):
            for t2 in vehicle_tracks[i+1:]:
                iou = self._compute_iou(
                    (t1.x1, t1.y1, t1.x2, t1.y2),
                    (t2.x1, t2.y1, t2.x2, t2.y2)
                )
                if iou > config.ACCIDENT_OVERLAP_IOU:
                    self.total_accidents += 1
                    return Alert(
                        alert_type="accident",
                        message=f"⚠ COLLISION detected between Vehicle #{t1.track_id} and #{t2.track_id}!",
                        lane=t1.lane,
                        severity="critical"
                    )
        
        # Check 3: Person in vehicle lane (potential pedestrian accident)
        for det in detections:
            if det.is_person:
                for track in vehicle_tracks:
                    if abs(det.cx - track.cx) < 40 and abs(det.cy - track.cy) < 40:
                        return Alert(
                            alert_type="accident",
                            message="⚠ PEDESTRIAN in vehicle lane — possible accident!",
                            lane=track.lane,
                            severity="high"
                        )
        
        return None
    
    def _compute_iou(self, box1: Tuple, box2: Tuple) -> float:
        """Compute Intersection-over-Union between two bounding boxes."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        if inter == 0:
            return 0.0
        
        area1 = (box1[2]-box1[0]) * (box1[3]-box1[1])
        area2 = (box2[2]-box2[0]) * (box2[3]-box2[1])
        union = area1 + area2 - inter
        
        return inter / max(union, 1)
    
    def _build_metrics(self, tracks, lane_stats: Dict, detections=None) -> Dict:
        """Build serializable metrics dict for dashboard."""
        vehicle_tracks = [t for t in tracks if t.is_vehicle]

        wait_times = [t.wait_time for t in vehicle_tracks]
        avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0.0

        # Vehicle type breakdown from detections
        vehicle_types = {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "person": 0}
        if detections:
            for d in detections:
                lbl = d.label.lower()
                if lbl in vehicle_types:
                    vehicle_types[lbl] += 1
                elif d.is_person:
                    vehicle_types["person"] += 1

        # Lane stats with dashboard-friendly field names
        lane_stats_out = {}
        for name, s in lane_stats.items():
            lane_stats_out[name] = {
                "vehicle_count":   s.vehicle_count,
                "density_ratio":   round(s.density_ratio, 3),
                "queue_length":    s.queue_length,
                "avg_wait_time":   round(s.avg_wait_time, 1),
                "congestion_level": s.congestion_level,
                "ambulance_present": s.ambulance_present,
            }

        return {
            "fps":              round(self.current_fps, 1),
            "current_fps":      round(self.current_fps, 1),
            "total_vehicles":   len(vehicle_tracks),
            "vehicle_count":    len(vehicle_tracks),
            "total_persons":    sum(1 for t in tracks if t.is_person),
            "ambulance_active": any(t.is_ambulance for t in tracks),
            "avg_wait_sec":     round(avg_wait, 1),
            "session_uptime":   round(time.time() - self.session_start, 0),
            "total_alerts":     len(self.alerts),
            "vehicle_types":    vehicle_types,
            "lane_stats":       lane_stats_out,
            "lanes": {
                name: {
                    "vehicles":   s.vehicle_count,
                    "density":    round(s.density_ratio * 100, 1),
                    "queue":      s.queue_length,
                    "avg_wait":   round(s.avg_wait_time, 1),
                    "congestion": s.congestion_level,
                    "ambulance":  s.ambulance_present,
                }
                for name, s in lane_stats.items()
            },
        }
    
    def draw_overlay(self, frame, lane_stats: Dict) -> None:
        """Draw analytics overlay — vehicle counts, wait times per lane."""
        import cv2
        h, w = frame.shape[:2]
        
        # Bottom bar
        bar_h = 50
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, h - bar_h), (w, h), (15, 15, 15), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        stats_items = list(lane_stats.items())
        col_w = w // max(len(stats_items), 1)
        
        for i, (name, stats) in enumerate(stats_items):
            x = i * col_w + 10
            y = h - bar_h + 16
            
            # Lane name
            color = {
                "free": (100, 255, 100),
                "light": (180, 255, 100),
                "moderate": (0, 200, 255),
                "heavy": (0, 50, 255),
            }.get(stats.congestion_level, (200, 200, 200))
            
            cv2.putText(frame, f"{name}: {stats.vehicle_count}v",
                        (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            cv2.putText(frame, f"Wait:{stats.avg_wait_time:.0f}s D:{stats.density_ratio*100:.0f}%",
                        (x, y + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 180, 180), 1)
        
        # FPS counter
        cv2.putText(frame, f"FPS: {self.current_fps:.1f}",
                    (w - 90, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 150), 1)
    
    def get_chart_data(self) -> Dict:
        """Return chart-ready time series data."""
        if not self.count_history:
            return {}
        
        now = time.time()
        labels = [round(now - e["time"], 1) for e in self.count_history]
        
        result = {"labels": labels}
        for lane in ["North", "South", "East", "West"]:
            result[lane] = [e.get(lane, 0) for e in self.count_history]
        
        return result
