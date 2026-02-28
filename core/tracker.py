"""
core/tracker.py — Centroid-Based Multi-Object Tracker
======================================================
Assigns persistent IDs to detected objects across frames.
Tracks: position, speed estimate, wait time, lane occupancy.

Design: Lightweight centroid matching (no heavy ByteTrack deps).
Trade-off: Less robust than DeepSORT but zero additional dependencies.
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
import time
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class Track:
    """Represents a tracked object with persistent identity."""
    track_id:    int
    label:       str
    cx:          int
    cy:          int
    x1:          int
    y1:          int
    x2:          int
    y2:          int
    is_vehicle:  bool
    is_person:   bool
    is_ambulance: bool
    
    # Temporal data
    created_at:      float = field(default_factory=time.time)
    last_seen:       float = field(default_factory=time.time)
    frames_tracked:  int   = 0
    frames_missing:  int   = 0
    
    # Motion
    prev_cx:    int = 0
    prev_cy:    int = 0
    speed_px:   float = 0.0   # pixels/frame
    
    # Lane
    lane: Optional[str] = None
    
    # Wait tracking (for congestion and fairness)
    wait_start:   Optional[float] = None
    total_wait:   float = 0.0
    is_stopped:   bool = False
    
    @property
    def w(self):
        return self.x2 - self.x1
    
    @property
    def h(self):
        return self.y2 - self.y1
    
    @property
    def centroid(self):
        return (self.cx, self.cy)
    
    @property
    def age(self) -> float:
        """Seconds since this track was first seen."""
        return time.time() - self.created_at
    
    @property
    def wait_time(self) -> float:
        """Current wait time in seconds (time stopped)."""
        if self.wait_start is not None:
            return time.time() - self.wait_start + self.total_wait
        return self.total_wait
    
    def update_motion(self):
        """Compute speed and stopped status from position delta."""
        dx = self.cx - self.prev_cx
        dy = self.cy - self.prev_cy
        self.speed_px = (dx**2 + dy**2) ** 0.5
        
        # Consider stopped if moving less than ~3 pixels/frame
        STOP_THRESHOLD = 3.0
        if self.speed_px < STOP_THRESHOLD:
            if not self.is_stopped:
                self.is_stopped = True
                self.wait_start = time.time()
        else:
            if self.is_stopped:
                self.is_stopped = False
                if self.wait_start:
                    self.total_wait += time.time() - self.wait_start
                    self.wait_start = None


class CentroidTracker:
    """
    Matches detections across frames using centroid distance.
    
    Maintains active tracks and removes stale ones.
    """
    
    def __init__(self, max_disappeared: int = 10, max_distance: int = 80):
        """
        Args:
            max_disappeared: Frames before a track is removed.
            max_distance: Maximum centroid distance for matching (pixels).
        """
        self.max_disappeared = max_disappeared
        self.max_distance    = max_distance
        
        self._next_id = 1
        self.tracks: Dict[int, Track] = {}   # track_id → Track
    
    def update(self, detections) -> List[Track]:
        """
        Update tracker with new detections.
        
        Args:
            detections: List of Detection objects from detector.py
        
        Returns:
            List of active Track objects.
        """
        # If no detections, age all tracks
        if not detections:
            missing_ids = []
            for tid, track in self.tracks.items():
                track.frames_missing += 1
                if track.frames_missing > self.max_disappeared:
                    missing_ids.append(tid)
            for tid in missing_ids:
                del self.tracks[tid]
            return list(self.tracks.values())
        
        # Build arrays for matching
        det_centroids = np.array([(d.cx, d.cy) for d in detections], dtype=float)
        
        if not self.tracks:
            # Register all as new
            for det in detections:
                self._register(det)
            return list(self.tracks.values())
        
        # ── Hungarian-style matching via distance matrix ───────────────────
        track_ids      = list(self.tracks.keys())
        track_centroids = np.array([(t.cx, t.cy) for t in self.tracks.values()], dtype=float)
        
        # Compute pairwise distances
        D = np.linalg.norm(
            track_centroids[:, np.newaxis, :] - det_centroids[np.newaxis, :, :],
            axis=2
        )  # shape: (num_tracks, num_dets)
        
        # Greedy matching: sort by distance
        matched_tracks = set()
        matched_dets   = set()
        
        # Get sorted indices of distances
        rows, cols = np.unravel_index(np.argsort(D, axis=None), D.shape)
        
        for r, c in zip(rows, cols):
            if r in matched_tracks or c in matched_dets:
                continue
            if D[r, c] > self.max_distance:
                break  # Remaining are all too far
            
            tid = track_ids[r]
            det = detections[c]
            
            track = self.tracks[tid]
            
            # Save prev position for motion
            track.prev_cx = track.cx
            track.prev_cy = track.cy
            
            # Update position
            track.cx = det.cx
            track.cy = det.cy
            track.x1, track.y1 = det.x1, det.y1
            track.x2, track.y2 = det.x2, det.y2
            track.label        = det.label
            track.is_ambulance = det.is_ambulance
            track.last_seen    = time.time()
            track.frames_tracked += 1
            track.frames_missing  = 0
            
            track.update_motion()
            
            matched_tracks.add(r)
            matched_dets.add(c)
        
        # Register unmatched detections as new tracks
        for i, det in enumerate(detections):
            if i not in matched_dets:
                self._register(det)
        
        # Age unmatched tracks
        missing_ids = []
        for i, tid in enumerate(track_ids):
            if i not in matched_tracks:
                track = self.tracks[tid]
                track.frames_missing += 1
                if track.frames_missing > self.max_disappeared:
                    missing_ids.append(tid)
        
        for tid in missing_ids:
            del self.tracks[tid]
        
        return list(self.tracks.values())
    
    def _register(self, det) -> Track:
        """Create a new track from a Detection."""
        track = Track(
            track_id=self._next_id,
            label=det.label,
            cx=det.cx, cy=det.cy,
            x1=det.x1, y1=det.y1,
            x2=det.x2, y2=det.y2,
            is_vehicle=det.is_vehicle,
            is_person=det.is_person,
            is_ambulance=det.is_ambulance,
        )
        track.prev_cx = det.cx
        track.prev_cy = det.cy
        self.tracks[self._next_id] = track
        self._next_id += 1
        return track
    
    def get_vehicle_tracks(self) -> List[Track]:
        return [t for t in self.tracks.values() if t.is_vehicle]
    
    def get_ambulance_tracks(self) -> List[Track]:
        return [t for t in self.tracks.values() if t.is_ambulance]
    
    def get_stopped_vehicles(self, min_wait: float = 3.0) -> List[Track]:
        """Return vehicles that have been stopped for at least min_wait seconds."""
        return [t for t in self.tracks.values()
                if t.is_vehicle and t.is_stopped and t.wait_time >= min_wait]
    
    @property
    def total_active(self) -> int:
        return len(self.tracks)
    
    def draw_tracks(self, frame, track_list: Optional[List[Track]] = None):
        """Draw track IDs and lanes on frame."""
        import cv2
        tracks = track_list or list(self.tracks.values())
        for track in tracks:
            label = f"ID:{track.track_id}"
            if track.lane:
                label += f" [{track.lane}]"
            cv2.putText(frame, label,
                        (track.cx - 20, track.cy + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 255, 200), 1,
                        cv2.LINE_AA)
        return frame
