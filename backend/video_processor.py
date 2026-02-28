"""
backend/video_processor.py — Video Processing Pipeline
=======================================================
Orchestrates the full AI pipeline per frame:
  Camera → Detect → Track → Lane → Analyze → Optimize

Runs in a background thread and pushes state to subscribers.
"""

import cv2
import numpy as np
import threading
import time
import base64
import json
import os
import sys
from typing import Callable, Optional, Dict, List

# Path resolution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from core.detector   import Detector
from core.tracker    import CentroidTracker
from core.lane_manager  import LaneManager
from core.traffic_analyzer import TrafficAnalyzer
from core.signal_optimizer import SignalOptimizer


class VideoProcessor:
    """
    Full AI traffic analysis pipeline.
    
    Usage:
        vp = VideoProcessor(video_path="traffic.mp4")
        vp.start(on_frame=callback)
    """
    
    def __init__(self, video_path=None, frame_width=None, frame_height=None):
        self.video_path   = self._resolve_video(video_path)
        self.frame_width  = frame_width  or config.FRAME_WIDTH
        self.frame_height = frame_height or config.FRAME_HEIGHT
        
        print(f"[VideoProcessor] Video source: {self.video_path}")
        
        # AI components
        self.detector  = Detector()
        self.tracker   = CentroidTracker(max_disappeared=8, max_distance=100)
        self.lane_mgr  = LaneManager(self.frame_width, self.frame_height)
        self.analyzer  = TrafficAnalyzer()
        self.optimizer = SignalOptimizer()
        
        # State
        self.is_running = False
        self._capture_thread_obj: Optional[threading.Thread] = None
        self._inference_thread_obj: Optional[threading.Thread] = None
        self._frame_count = 0
        
        # Concurrency & Shared AI State
        self.state_lock = threading.Lock()
        self.raw_frame: Optional[np.ndarray] = None
        self.shared_detections: List = []
        self.shared_tracks: List = []
        self.shared_lane_stats: Dict = {}
        
        # Shared state (thread-safe via GIL for simple reads, but lock for structure)
        self.latest_frame:   Optional[np.ndarray] = None
        self.latest_metrics: Dict = {}
        self.latest_alerts:  List = []
        self.latest_signals: Dict = {}
        
        # Callbacks (called from processing thread)
        self._on_state: Optional[Callable] = None
    
    def _resolve_video(self, path=None) -> str:
        """Find a valid video file from config or fallbacks."""
        candidates = [path, config.VIDEO_PATH] + config.FALLBACK_VIDEO_PATHS
        for c in candidates:
            if c is None:
                continue
            if c == 0:
                return 0  # Webcam
            if os.path.isfile(str(c)):
                return c
        print("[VideoProcessor] WARNING: No video found. Defaulting to webcam (0).")
        return 0
    
    def start(self, on_state: Optional[Callable] = None):
        """Start processing in background threads."""
        self._on_state = on_state
        self.is_running = True
        
        self._capture_thread_obj = threading.Thread(target=self._capture_thread, daemon=True)
        self._inference_thread_obj = threading.Thread(target=self._inference_thread, daemon=True)
        
        self._capture_thread_obj.start()
        self._inference_thread_obj.start()
        print("[VideoProcessor] Capture and Inference threads started.")
    
    def stop(self):
        """Stop processing."""
        self.is_running = False
        if self._capture_thread_obj:
            self._capture_thread_obj.join(timeout=3.0)
        if self._inference_thread_obj:
            self._inference_thread_obj.join(timeout=3.0)
    
    def _capture_thread(self):
        """Reads frames and annotates them asynchronously for smooth playback."""
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print(f"[VideoProcessor] ERROR: Cannot open: {self.video_path}")
            return
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        
        target_fps = config.TARGET_FPS
        frame_delay = 1.0 / target_fps
        
        print(f"[VideoProcessor] Stream opened at "
              f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
              f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ {target_fps} FPS")
        
        while self.is_running:
            start_time = time.time()
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            
            frame = cv2.resize(frame, (self.frame_width, self.frame_height))
            
            with self.state_lock:
                self.raw_frame = frame.copy()
                current_detections = list(self.shared_detections)
                current_tracks = list(self.shared_tracks)
                current_lane_stats = dict(self.shared_lane_stats)
                
                self.latest_metrics = self.analyzer.metrics
                self.latest_alerts  = [a.to_dict() for a in self.analyzer.alerts[-5:]]
                self.latest_signals = self.optimizer.get_metrics()
            
            annotated = frame.copy()
            self.lane_mgr.draw_lanes(annotated)
            
            if current_detections:
                self.detector.draw(annotated, current_detections)
            if current_tracks:
                self.tracker.draw_tracks(annotated, current_tracks)
                
            self.optimizer.draw_signal_panel(annotated, x=10, y=10)
            self.analyzer.draw_overlay(annotated, current_lane_stats)
            
            self.latest_frame = annotated
            
            if self._on_state:
                try:
                    self._on_state({
                        "metrics": self.latest_metrics,
                        "alerts":  self.latest_alerts,
                        "signals": self.latest_signals,
                        "chart":   self.analyzer.get_chart_data(),
                    })
                except Exception:
                    pass
            
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_delay - elapsed)
            time.sleep(sleep_time)
            
        cap.release()
        print("[VideoProcessor] Capture thread closed.")

    def _inference_thread(self):
        """Runs YOLO and intersection logic continuously on the latest frame."""
        while self.is_running:
            with self.state_lock:
                frame_to_process = self.raw_frame
            
            if frame_to_process is None:
                time.sleep(0.01)
                continue
            
            # Since AI processes as fast as it can, run pipeline continuously
            detections = self.detector.detect(frame_to_process)
            tracks     = self.tracker.update(detections)
            lane_stats = self.lane_mgr.update(tracks)
            
            self.optimizer.update_phase_duration(lane_stats)
            _ = self.optimizer.update(lane_stats)
            
            _ = self.analyzer.update(tracks, lane_stats, list(detections))
            
            with self.state_lock:
                self.shared_detections = detections
                self.shared_tracks = tracks
                self.shared_lane_stats = lane_stats
            
            time.sleep(0.01)  # small buffer
    
    def get_jpeg_frame(self, quality: int = None) -> Optional[bytes]:
        """Return latest annotated frame as JPEG bytes."""
        if self.latest_frame is None:
            return None
        q = quality or config.STREAM_JPEG_QUALITY
        _, buf = cv2.imencode(".jpg", self.latest_frame, [cv2.IMWRITE_JPEG_QUALITY, q])
        return buf.tobytes()
    
    def get_b64_frame(self) -> Optional[str]:
        """Return latest frame as base64-encoded JPEG string."""
        jpg = self.get_jpeg_frame()
        if jpg is None:
            return None
        return base64.b64encode(jpg).decode("utf-8")
    
    def get_state(self) -> Dict:
        """Return current full system state as serializable dict."""
        return {
            "metrics": self.latest_metrics,
            "alerts":  self.latest_alerts,
            "signals": self.latest_signals,
            "chart":   self.analyzer.get_chart_data(),
            "frame_b64": self.get_b64_frame(),
        }
