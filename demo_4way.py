"""
demo_4way.py — 4-Way Split Screen AI Traffic Demo
===================================================
Composites 4 separate video feeds (North, South, East, West) into a single 
2x2 grid screen and runs the AI Traffic De-Congestion System on it.

Usage:
  python demo_4way.py --v_north north.mp4 --v_south south.mp4 --v_east east.mp4 --v_west west.mp4
  # If you provide fewer videos, it will duplicate them to fill the 4 quadrants.
"""

import cv2
import sys
import os
import argparse
import time
import numpy as np

# ── Setup paths ─────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

from core.detector        import Detector
from core.tracker         import CentroidTracker
from core.lane_manager    import LaneManager
from core.traffic_analyzer import TrafficAnalyzer
from core.signal_optimizer import SignalOptimizer

# Custom 4-way polygons (normalized for the 2x2 composite)
# Top-Left: North, Top-Right: South, Bottom-Left: East, Bottom-Right: West
LANE_POLYGONS_4WAY = {
    "North": [(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)],
    "South": [(0.5, 0.0), (1.0, 0.0), (1.0, 0.5), (0.5, 0.5)],
    "East":  [(0.0, 0.5), (0.5, 0.5), (0.5, 1.0), (0.0, 1.0)],
    "West":  [(0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.5, 1.0)],
}

def parse_args():
    p = argparse.ArgumentParser(description="AI Traffic De-Congestion — 4-Way Demo")
    p.add_argument("--v_north", type=str, default="north.mp4", help="Video for North lane")
    p.add_argument("--v_south", type=str, default="south.mp4", help="Video for South lane")
    p.add_argument("--v_east",  type=str, default="east.mp4", help="Video for East lane")
    p.add_argument("--v_west",  type=str, default="west.mp4", help="Video for West lane")
    p.add_argument("--width",   type=int, default=1280, help="Total Width")
    p.add_argument("--height",  type=int, default=720,  help="Total Height")
    p.add_argument("--model",   type=str, default=config.MODEL_NAME)
    p.add_argument("--conf",    type=float, default=config.CONFIDENCE_THRESHOLD)
    return p.parse_args()


def resolve_videos(args):
    """Fallback to provided or default videos if some are missing."""
    provided = [v for v in [args.v_north, args.v_south, args.v_east, args.v_west] if v and os.path.isfile(v)]
    
    default_vid = provided[0] if provided else config.VIDEO_PATH
    if not os.path.isfile(str(default_vid)):
        for c in config.FALLBACK_VIDEO_PATHS:
            if c != 0 and os.path.isfile(str(c)):
                default_vid = c
                break
    
    if not isinstance(default_vid, str) or not os.path.isfile(default_vid):
        print("[Demo 4-Way] ERROR: No valid fallback video found. Provide at least one valid video file.")
        sys.exit(1)
        
    v_north = args.v_north if args.v_north and os.path.isfile(args.v_north) else default_vid
    v_south = args.v_south if args.v_south and os.path.isfile(args.v_south) else default_vid
    v_east  = args.v_east  if args.v_east  and os.path.isfile(args.v_east)  else default_vid
    v_west  = args.v_west  if args.v_west  and os.path.isfile(args.v_west)  else default_vid
    
    return [v_north, v_south, v_east, v_west]


def draw_hud(frame, analyzer, optimizer, frame_count, t_start):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 40), (10, 15, 25), -1)
    
    fps_text = f"FPS: {analyzer.current_fps:.1f}"
    cv2.putText(frame, "AI TRAFFIC DE-CONGESTION SYSTEM - 4-WAY SPLIT SCREEN", (10, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, fps_text, (w - 120, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 255, 150), 1, cv2.LINE_AA)
    cv2.line(frame, (0, 40), (w, 40), (30, 40, 60), 1)
    
    # Grid lines to separate quadrants clearly
    cv2.line(frame, (w//2, 40), (w//2, h), (100, 100, 100), 2)
    cv2.line(frame, (0, h//2 + 20), (w, h//2 + 20), (100, 100, 100), 2)
    
    # Emergency indicator
    if optimizer.emergency_active:
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
    h, w = frame.shape[:2]
    sidebar_w = 230
    x0 = w - sidebar_w - 5
    y0 = 48
    
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (w - 5, h - 60), (8, 12, 20), -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
    cv2.rectangle(frame, (x0, y0), (w - 5, h - 60), (30, 40, 60), 1)
    
    y = y0 + 15
    cv2.putText(frame, "SIGNAL STATUS", (x0 + 8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 150, 220), 1)
    y += 5
    cv2.line(frame, (x0+8, y), (w-13, y), (30, 40, 60), 1)
    y += 14
    
    STATE_COLORS = {"green": (0,220,100), "yellow": (0,200,255), "red": (80,80,80)}
    for lane_name, sig in signals.items():
        color = STATE_COLORS.get(sig.value, (80,80,80))
        cv2.circle(frame, (x0+16, y+1), 5, color, -1)
        count = lane_stats.get(lane_name)
        count_txt = f"{count.vehicle_count}v" if count else "0v"
        
        time_txt = ""
        if sig.value in ("green", "yellow"):
            tl = signals.get("_times", {}).get(lane_name, 0)
            time_txt = f" {tl:.0f}s"
        
        txt = f"{lane_name}: {sig.value.upper()}{time_txt}  [{count_txt}]"
        cv2.putText(frame, txt, (x0+28, y+5), cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)
        y += 18
    
    y += 8
    cv2.line(frame, (x0+8, y), (w-13, y), (30, 40, 60), 1)
    y += 14
    
    cv2.putText(frame, "LANE ANALYTICS", (x0 + 8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 150, 220), 1)
    y += 5
    cv2.line(frame, (x0+8, y), (w-13, y), (30, 40, 60), 1)
    y += 14
    
    lane_colors = {"North":(255,100,100),"South":(100,255,100), "East":(100,100,255),"West":(255,255,100)}
    for ln, stats in lane_stats.items():
        c = lane_colors.get(ln, (180,180,180))
        cv2.putText(frame, f"{ln}:", (x0+8, y+5), cv2.FONT_HERSHEY_SIMPLEX, 0.38, c, 1)
        
        bar_x, bar_w, bar_h_px = x0 + 65, sidebar_w - 80, 7
        density = min(1.0, stats.density_ratio)
        cv2.rectangle(frame, (bar_x, y-2), (bar_x+bar_w, y-2+bar_h_px), (30,40,60), -1)
        
        fill_color = (0,100,250) if density < 0.4 else (0,200,200) if density < 0.7 else (20,50,220)
        cv2.rectangle(frame, (bar_x, y-2), (bar_x + int(bar_w * density), y-2+bar_h_px), fill_color, -1)
        
        cv2.putText(frame, f"{stats.vehicle_count}v {density*100:.0f}%", (x0 + 155, y+5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160,160,160), 1)
        y += 20
    return frame

def draw_quadrant_signals(frame, optimizer_signals, qw, qh):
    """Draw signal lights in each of the 4 quadrants."""
    positions = {
        "North": (20, 60),
        "South": (qw + 20, 60),
        "East":  (20, qh + 40),
        "West":  (qw + 20, qh + 40),
    }
    
    STATE_COLORS = {"green": (0,220,100), "yellow": (0,200,255), "red": (80,80,80)}
    
    for lane_name, pos in positions.items():
        if lane_name not in optimizer_signals:
            continue
            
        sig = optimizer_signals[lane_name]
        state_str = sig.state.value
        color = STATE_COLORS.get(state_str, (80,80,80))
        
        x, y = pos
        cv2.rectangle(frame, (x-10, y-20), (x+130, y+20), (20,20,20), -1)
        cv2.rectangle(frame, (x-10, y-20), (x+130, y+20), (80,80,80), 1)
        
        cv2.circle(frame, (x+12, y), 10, color, -1)
        
        time_txt = ""
        if state_str in ("green", "yellow"):
            time_txt = f" {sig.time_left:.0f}s"
            
        txt = f"{state_str.upper()}{time_txt}"
        cv2.putText(frame, txt, (x+30, y+6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

def main():
    args = parse_args()
    v_paths = resolve_videos(args)
    
    print("=" * 60)
    print("  AI Traffic De-Congestion System — 4-Way Demo Mode")
    print("=" * 60)
    print(f"  North : {v_paths[0]}")
    print(f"  South : {v_paths[1]}")
    print(f"  East  : {v_paths[2]}")
    print(f"  West  : {v_paths[3]}")
    print()
    print("  Controls: Q = Quit, SPACE = Pause/Resume, A = Ambulance")
    print("=" * 60)
    
    # ── Initialize pipeline ──
    detector  = Detector(model_name=args.model, conf=args.conf)
    tracker   = CentroidTracker(max_disappeared=8, max_distance=100)
    # Inject our 4-quadrant custom layout
    lane_mgr  = LaneManager(args.width, args.height, polygons=LANE_POLYGONS_4WAY)
    analyzer  = TrafficAnalyzer()
    optimizer = SignalOptimizer()
    
    caps = [cv2.VideoCapture(v) for v in v_paths]
    for i, c in enumerate(caps):
        if not c.isOpened():
            print(f"[Demo] ERROR: Cannot open video source: {v_paths[i]}")
            sys.exit(1)
            
    print("[Demo] Stream opened. Press Q to quit.")
    
    qw, qh = args.width // 2, args.height // 2  # Quadrant dimensions
    
    process_every = config.PROCESS_EVERY_N_FRAMES
    frame_count   = 0
    paused        = False
    simulate_amb  = False
    t_start       = time.time()
    
    lane_stats = {}
    tracks     = []
    detections = []
    
    cv2.namedWindow("AI Traffic System 4-Way", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("AI Traffic System 4-Way", args.width, args.height)
    
    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): break
        elif key == ord(' '): paused = not paused
        elif key == ord('a'): simulate_amb = not simulate_amb
        
        if paused: continue
        
        frames = []
        for c in caps:
            ret, f = c.read()
            if not ret:
                c.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, f = c.read()
            frames.append(cv2.resize(f, (qw, qh)))
            
        # Stitch frames into 2x2 grid
        top_row = np.hstack((frames[0], frames[1]))
        bot_row = np.hstack((frames[2], frames[3]))
        composite_frame = np.vstack((top_row, bot_row))
        
        frame_count += 1
        
        if frame_count % process_every == 0:
            detections = detector.detect(composite_frame)
            if simulate_amb and detections:
                detections[0].is_ambulance = True
                detections[0].label = "ambulance"
            
            tracks     = tracker.update(detections)
            lane_stats = lane_mgr.update(tracks)
            
            optimizer.update_phase_duration(lane_stats)
            signal_states = optimizer.update(lane_stats)
            analyzer.update(tracks, lane_stats, detections)
            
        # Annotate
        annotated = composite_frame.copy()
        lane_mgr.draw_lanes(annotated)
        detector.draw(annotated, detections)
        tracker.draw_tracks(annotated, tracks)
        optimizer.draw_signal_panel(annotated, x=10, y=48)
        analyzer.draw_overlay(annotated, lane_stats)
        
        draw_hud(annotated, analyzer, optimizer, frame_count, t_start)
        sig_states = {n: s.state for n,s in optimizer.signals.items()}
        draw_metrics_sidebar(annotated, lane_stats, sig_states, analyzer)
        draw_quadrant_signals(annotated, optimizer.signals, qw, qh)
        
        cv2.putText(annotated, "YOLOv8n + Advanced Centroid Matrix",
                    (10, annotated.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (80, 80, 100), 1)
        
        cv2.imshow("AI Traffic System 4-Way", annotated)
        
    for c in caps: c.release()
    cv2.destroyAllWindows()
    print("[Demo] Exited cleanly.")

if __name__ == "__main__":
    main()
