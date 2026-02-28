"""
run.py — Full System Launcher
==============================
Starts the FastAPI backend and opens the browser dashboard.

Usage:
  python run.py
  python run.py --video path/to/video.mp4
  python run.py --port 8080
"""

import subprocess
import sys
import os
import time
import argparse
import webbrowser
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def parse_args():
    p = argparse.ArgumentParser(description="AI Traffic De-Congestion System — Full Server")
    p.add_argument("--port",   type=int, default=8000)
    p.add_argument("--host",   type=str, default="0.0.0.0")
    p.add_argument("--video",  type=str, default=None, help="Override video path")
    p.add_argument("--no-browser", action="store_true", help="Don't open browser")
    return p.parse_args()


def open_browser(port: int, delay: float = 2.5):
    """Open dashboard in browser after delay."""
    def _open():
        time.sleep(delay)
        url = f"http://localhost:{port}"
        print(f"[Launcher] Opening dashboard: {url}")
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def check_deps():
    """Check that required packages are available."""
    missing = []
    packages = {
        "ultralytics": "ultralytics",
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "cv2": "opencv-python",
        "numpy": "numpy",
    }
    for module, pkg in packages.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print("\nWARNING: Missing packages. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
        print("DONE: Dependencies installed\n")


def main():
    args = parse_args()
    
    print("\n" + "="*60)
    print("   AI Traffic De-Congestion System v1.0")
    print("   Real-time YOLOv8 - Adaptive Signals - Dashboard")
    print("="*60)
    
    # Check dependencies
    check_deps()
    
    # Override video if specified
    if args.video:
        import config as cfg
        cfg.VIDEO_PATH = args.video
        print(f"[Launcher] Using video: {args.video}")
    
    # Open browser
    if not args.no_browser:
        open_browser(args.port)
    
    # Start the server
    import uvicorn
    from backend.main import app
    
    print(f"\n[Launcher] Dashboard: http://localhost:{args.port}")
    print("[Launcher] API Docs:  http://localhost:{args.port}/docs")
    print("[Launcher] Press Ctrl+C to stop\n")
    
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
