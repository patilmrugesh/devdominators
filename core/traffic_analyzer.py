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
    
    Accident Detection Strategy — Two-Phase Collision Confirmation:
      Phase 1: Detect collision event (IoU overlap + close centroids)
               → record as "pending collision" with timestamp.
      Phase 2: If BOTH vehicles remain stopped for COLLISION_CONFIRM_TIME
               seconds (default 8s), confirm as real accident.
               If either vehicle starts moving, discard the event.
      Additional: Person detected in vehicle lane → pedestrian accident.
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
        
        # Accident tracking — multi-heuristic collision confirmation
        self._pending_collisions: Dict = {}            # key → {"timestamp", "lane"}
        self._accident_cooldown: float = 0.0           # Prevent duplicate alerts
        
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
        """
        Multi-heuristic accident detection — aggressive for real crash scenes:
          1. Two-vehicle IoU overlap → confirm after stop time
          2. Bounding box edge proximity (near-collision / side impact)
          3. Stopped vehicle + persons gathering nearby (crash scene)
          4. Single vehicle stopped abnormally long (stall/crash)
          5. Pedestrian very close to vehicle (impact)
        """
        vehicle_tracks = [t for t in tracks if t.is_vehicle]
        person_dets = [d for d in detections if d.is_person]
        now = time.time()

        if not vehicle_tracks:
            self._pending_collisions.clear()
            return None

        track_map = {t.track_id: t for t in vehicle_tracks}

        # ── Heuristic 1 & 2: Vehicle-to-vehicle collision ─────────────────────
        for i, t1 in enumerate(vehicle_tracks):
            for t2 in vehicle_tracks[i+1:]:
                iou = self._compute_iou(
                    (t1.x1, t1.y1, t1.x2, t1.y2),
                    (t2.x1, t2.y1, t2.x2, t2.y2)
                )

                dx = t1.cx - t2.cx
                dy = t1.cy - t2.cy
                centroid_dist = (dx**2 + dy**2) ** 0.5

                # Edge proximity: how close the bounding box edges are
                gap_x = max(0, max(t1.x1, t2.x1) - min(t1.x2, t2.x2))
                gap_y = max(0, max(t1.y1, t2.y1) - min(t1.y2, t2.y2))
                edge_dist = (gap_x**2 + gap_y**2) ** 0.5

                # Collision: IoU overlap OR bounding boxes within 30px of each other
                is_collision = (iou > config.ACCIDENT_OVERLAP_IOU) or (edge_dist < 30 and centroid_dist < 100)

                if is_collision:
                    pair_key = (min(t1.track_id, t2.track_id),
                                max(t1.track_id, t2.track_id))
                    if pair_key not in self._pending_collisions:
                        self._pending_collisions[pair_key] = {
                            "timestamp": now,
                            "lane": t1.lane or t2.lane,
                            "type": "collision",
                        }

        # Check pending collisions for stop confirmation
        expired_keys = []
        for pair_key, info in list(self._pending_collisions.items()):
            if info.get("type") != "collision":
                continue
            if not isinstance(pair_key, tuple):
                continue
            tid1, tid2 = pair_key
            t1 = track_map.get(tid1)
            t2 = track_map.get(tid2)

            if t1 is None or t2 is None:
                expired_keys.append(pair_key)
                continue

            # Either or both stopped → potential crash aftermath
            both_stopped = t1.is_stopped and t2.is_stopped
            one_stopped = t1.is_stopped or t2.is_stopped

            elapsed = now - info["timestamp"]

            # Both stopped for CONFIRM_TIME → definite accident
            if both_stopped and elapsed >= config.COLLISION_CONFIRM_TIME:
                self.total_accidents += 1
                expired_keys.append(pair_key)
                return Alert(
                    alert_type="accident",
                    message=f"⚠ COLLISION CONFIRMED — Vehicle #{tid1} and #{tid2} stopped {elapsed:.0f}s after impact!",
                    lane=info["lane"],
                    severity="critical"
                )

            # One stopped for longer → likely crash (other might be pushed away)
            if one_stopped and elapsed >= config.COLLISION_CONFIRM_TIME * 1.5:
                self.total_accidents += 1
                expired_keys.append(pair_key)
                stopped_id = tid1 if (t1 and t1.is_stopped) else tid2
                return Alert(
                    alert_type="accident",
                    message=f"⚠ COLLISION — Vehicle #{stopped_id} stopped after impact with #{tid1 if stopped_id != tid1 else tid2}!",
                    lane=info["lane"],
                    severity="critical"
                )

            # Both moving after 15s → false alarm, discard
            if not one_stopped and elapsed > 15.0:
                expired_keys.append(pair_key)

        for key in expired_keys:
            self._pending_collisions.pop(key, None)

        # ── Heuristic 3: Stopped vehicle + persons gathering (crash scene) ────
        # Real accidents: wreckage not detected by YOLO, but persons gather.
        for track in vehicle_tracks:
            if not track.is_stopped or track.wait_time < 3.0:
                continue

            # Count persons within 150px of this stopped vehicle
            persons_nearby = 0
            for p in person_dets:
                if abs(p.cx - track.cx) < 150 and abs(p.cy - track.cy) < 150:
                    persons_nearby += 1

            # 2+ persons near a stopped vehicle → potential accident scene
            if persons_nearby >= 2:
                scene_key = f"scene_{track.track_id}"
                if scene_key not in self._pending_collisions:
                    self._pending_collisions[scene_key] = {
                        "timestamp": now,
                        "lane": track.lane,
                        "type": "scene",
                    }
                else:
                    elapsed = now - self._pending_collisions[scene_key]["timestamp"]
                    if elapsed >= config.COLLISION_CONFIRM_TIME:
                        self.total_accidents += 1
                        self._pending_collisions.pop(scene_key, None)
                        return Alert(
                            alert_type="accident",
                            message=f"⚠ ACCIDENT SCENE — Vehicle #{track.track_id} stopped, {persons_nearby} persons gathered!",
                            lane=track.lane,
                            severity="critical"
                        )

        # ── Heuristic 4: Single vehicle stopped abnormally long ───────────────
        for track in vehicle_tracks:
            if track.is_stopped and track.wait_time > 10.0:
                stall_key = f"stall_{track.track_id}"
                if stall_key not in self._pending_collisions:
                    self._pending_collisions[stall_key] = {
                        "timestamp": now,
                        "lane": track.lane,
                        "type": "stall",
                    }
                elif now - self._pending_collisions[stall_key]["timestamp"] >= config.COLLISION_CONFIRM_TIME:
                    self.total_accidents += 1
                    self._pending_collisions.pop(stall_key, None)
                    return Alert(
                        alert_type="accident",
                        message=f"⚠ Vehicle #{track.track_id} stopped for {track.wait_time:.0f}s — possible crash/stall!",
                        lane=track.lane,
                        severity="high"
                    )

        # ── Heuristic 5: Pedestrian very close to vehicle (impact) ────────────
        for det in person_dets:
            for track in vehicle_tracks:
                if abs(det.cx - track.cx) < 50 and abs(det.cy - track.cy) < 50:
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
                "congestion_index": round(s.congestion_index, 3),
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