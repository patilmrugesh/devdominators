"""
demo.py — Standalone OpenCV Demo (No Server Required)
======================================================
Perfect for live hackathon demonstration on a projector.
Shows an annotated OpenCV window with:
  - YOLOv8 vehicle detection (bounding boxes)
  - Virtual lane overlays
  - Per-lane vehicle count & density
  - Adaptive signal timing panel
  - Emergency detection alerts
  - Accident detection

Usage:
  python demo.py
  python demo.py --video path/to/video.mp4
  python demo.py --webcam
"""

import cv2
import sys
import os
import argparse
import time

# ── Setup paths ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

from core.detector        import Detector
from core.tracker         import CentroidTracker
from core.lane_manager    import LaneManager
from core.traffic_analyzer import TrafficAnalyzer
from core.signal_optimizer import SignalOptimizer


def parse_args():
    p = argparse.ArgumentParser(description="AI Traffic De-Congestion — Standalone Demo")
    p.add_argument("--video",  type=str, default=None, help="Path to video file")
    p.add_argument("--webcam", action="store_true",    help="Use webcam input")
    p.add_argument("--width",  type=int, default=config.FRAME_WIDTH)
    p.add_argument("--height", type=int, default=config.FRAME_HEIGHT)
    p.add_argument("--model",  type=str, default=config.MODEL_NAME)
    p.add_argument("--conf",   type=float, default=config.CONFIDENCE_THRESHOLD)
    return p.parse_args()


def find_video(args):
    """Resolve video source."""
    if args.webcam:
        return 0
    if args.video and os.path.isfile(args.video):
        return args.video
    
    # Try config paths
    candidates = [config.VIDEO_PATH] + config.FALLBACK_VIDEO_PATHS
    for c in candidates:
        if c == 0:
            return 0
        if c and os.path.isfile(str(c)):
            print(f"[Demo] Using video: {c}")
            return c
    
    print("[Demo] No video found. Trying webcam...")
    return 0


def draw_hud(frame, analyzer, optimizer, frame_count, t_start):
    """Draw heads-up display overlay."""
    h, w = frame.shape[:2]
    
    # Top HUD bar
    cv2.rectangle(frame, (0, 0), (w, 40), (10, 15, 25), -1)
    
    elapsed = time.time() - t_start
    fps_text = f"FPS: {analyzer.current_fps:.1f}"
    cv2.putText(frame, "AI TRAFFIC DE-CONGESTION SYSTEM", (10, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 255), 1, cv2.LINE_AA)
    
    cv2.putText(frame, fps_text, (w - 120, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 255, 150), 1, cv2.LINE_AA)
    
    # Separator line
    cv2.line(frame, (0, 40), (w, 40), (30, 40, 60), 1)
    
    # Emergency indicator
    if optimizer.emergency_active:
        # Flash effect
        t = time.time()
        alpha = 0.5 + 0.5 * abs(round((t % 0.8) / 0.4) - 1)
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 41), (w, 80), (0, 0, 180), -1)
        cv2.addWeighted(overlay, alpha * 0.7, frame, 1 - alpha * 0.7, 0, frame)
        cv2.putText(frame,
                    f"  AMBULANCE - EMERGENCY PREEMPTION: {optimizer.emergency_lane} LANE",
                    (10, 66),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 100), 2, cv2.LINE_AA)
    
    return frame


def draw_metrics_sidebar(frame, lane_stats, signals, analyzer):
    """Draw right sidebar with metrics."""
    h, w = frame.shape[:2]
    sidebar_w = 230
    x0 = w - sidebar_w - 5
    y0 = 48
    
    # Background
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (w - 5, h - 60), (8, 12, 20), -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
    cv2.rectangle(frame, (x0, y0), (w - 5, h - 60), (30, 40, 60), 1)
    
    y = y0 + 15
    
    # Title
    cv2.putText(frame, "SIGNAL STATUS", (x0 + 8, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 150, 220), 1)
    y += 5
    cv2.line(frame, (x0+8, y), (w-13, y), (30, 40, 60), 1)
    y += 14
    
    STATE_COLORS = {"green": (0,220,100), "yellow": (0,200,255), "red": (80,80,80)}
    
    for lane_name, sig in signals.items():
        color = STATE_COLORS.get(sig.value, (80,80,80))
        # Circle indicator
        cv2.circle(frame, (x0+16, y+1), 5, color, -1)
        
        count = lane_stats.get(lane_name)
        count_txt = f"{count.vehicle_count}v" if count else "0v"
        
        time_txt = ""
        if sig.value in ("green", "yellow"):
            from core.signal_optimizer import SignalOptimizer as SO
            tl = signals.get("_times", {}).get(lane_name, 0)
            time_txt = f" {tl:.0f}s"
        
        txt = f"{lane_name}: {sig.value.upper()}{time_txt}  [{count_txt}]"
        cv2.putText(frame, txt, (x0+28, y+5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)
        y += 18
    
    y += 8
    cv2.line(frame, (x0+8, y), (w-13, y), (30, 40, 60), 1)
    y += 14
    
    # Lane details
    cv2.putText(frame, "LANE ANALYTICS", (x0 + 8, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 150, 220), 1)
    y += 5
    cv2.line(frame, (x0+8, y), (w-13, y), (30, 40, 60), 1)
    y += 14
    
    lane_colors = {"North":(255,100,100),"South":(100,255,100),
                   "East":(100,100,255),"West":(255,255,100)}
    
    for ln, stats in lane_stats.items():
        c = lane_colors.get(ln, (180,180,180))
        
        # Lane label
        cv2.putText(frame, f"{ln}:", (x0+8, y+5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, c, 1)
        
        # Progress bar for density
        bar_x = x0 + 65
        bar_w = sidebar_w - 80
        bar_h_px = 7
        density = min(1.0, stats.density_ratio)
        cv2.rectangle(frame, (bar_x, y-2), (bar_x+bar_w, y-2+bar_h_px), (30,40,60), -1)
        
        fill_color = (0,100,250) if density < 0.4 else (0,200,200) if density < 0.7 else (20,50,220)
        cv2.rectangle(frame, (bar_x, y-2),
                      (bar_x + int(bar_w * density), y-2+bar_h_px), fill_color, -1)
        
        cv2.putText(frame, f"{stats.vehicle_count}v {density*100:.0f}%",
                    (x0 + 155, y+5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160,160,160), 1)
        y += 20
    
    return frame


def main():
    args = parse_args()
    video_src = find_video(args)
    
    print("=" * 55)
    print("  AI Traffic De-Congestion System — Demo Mode")
    print("=" * 55)
    print(f"  Video:  {video_src}")
    print(f"  Model:  {args.model}")
    print(f"  Conf:   {args.conf}")
    print(f"  Size:   {args.width}x{args.height}")
    print()
    print("  Controls:")
    print("    Q     — Quit")
    print("    SPACE — Pause/Resume")
    print("    R     — Reset (loop video)")
    print("    A     — Simulate Ambulance (toggle)")
    print("=" * 55)
    
    # ── Initialize pipeline ────────────────────────────────────────────────
    print("[Demo] Loading YOLOv8 model...")
    detector  = Detector(model_name=args.model, conf=args.conf)
    tracker   = CentroidTracker(max_disappeared=8, max_distance=100)
    lane_mgr  = LaneManager(args.width, args.height)
    analyzer  = TrafficAnalyzer()
    optimizer = SignalOptimizer()
    
    # ── Open video ─────────────────────────────────────────────────────────
    cap = cv2.VideoCapture(video_src)
    if not cap.isOpened():
        print(f"[Demo] ERROR: Cannot open video source: {video_src}")
        sys.exit(1)
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    
    print(f"[Demo] Stream opened. Press Q to quit.")
    
    process_every = config.PROCESS_EVERY_N_FRAMES
    frame_count   = 0
    paused        = False
    simulate_amb  = False
    t_start       = time.time()
    
    lane_stats  = {}
    tracks      = []
    detections  = []
    
    # Create window
    cv2.namedWindow("AI Traffic System", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("AI Traffic System", args.width, args.height)
    
    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord(' '):
            paused = not paused
            print(f"[Demo] {'Paused' if paused else 'Resumed'}")
        elif key == ord('r'):
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            print("[Demo] Video reset.")
        elif key == ord('a'):
            simulate_amb = not simulate_amb
            print(f"[Demo] Ambulance simulation: {'ON' if simulate_amb else 'OFF'}")
        
        if paused:
            continue
        
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        
        frame = cv2.resize(frame, (args.width, args.height))
        frame_count += 1
        
        # ── AI pipeline (every N frames) ────────────────────────────────
        if frame_count % process_every == 0:
            detections = detector.detect(frame)
            
            # Simulate ambulance for demo
            if simulate_amb and detections:
                detections[0].is_ambulance = True
                detections[0].label = "ambulance"
            
            tracks     = tracker.update(detections)
            lane_stats = lane_mgr.update(tracks)
            
            optimizer.update_phase_duration(lane_stats)
            signal_states = optimizer.update(lane_stats)
            
            analyzer.update(tracks, lane_stats, detections)
        
        # ── Annotate frame ───────────────────────────────────────────────
        annotated = frame.copy()
        
        lane_mgr.draw_lanes(annotated)
        detector.draw(annotated, detections)
        tracker.draw_tracks(annotated, tracks)
        optimizer.draw_signal_panel(annotated, x=10, y=48)
        analyzer.draw_overlay(annotated, lane_stats)
        draw_hud(annotated, analyzer, optimizer, frame_count, t_start)
        
        # ── Sidebar ──────────────────────────────────────────────────────
        sig_states = {n: s.state for n,s in optimizer.signals.items()}
        draw_metrics_sidebar(annotated, lane_stats, sig_states, analyzer)
        
        # ── System info watermark ─────────────────────────────────────────
        cv2.putText(annotated, "YOLOv8n + Centroid Tracker + Adaptive Signal Optimizer",
                    (10, annotated.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (80, 80, 100), 1)
        
        cv2.imshow("AI Traffic System", annotated)
    
    cap.release()
    cv2.destroyAllWindows()
    print("[Demo] Exited cleanly.")


if __name__ == "__main__":
    main()
