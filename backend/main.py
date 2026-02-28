"""
backend/main.py — FastAPI Server with WebSocket Dashboard
=========================================================
Serves real-time traffic data to the frontend via WebSocket.
REST endpoints for system configuration and status.
"""

import asyncio
import json
import time
import os
import sys
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from backend.video_processor import VideoProcessor

# ─── App Setup ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Traffic De-Congestion System",
    description="Real-time AI-powered traffic signal optimization",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Globals ──────────────────────────────────────────────────────────────────
processor: VideoProcessor = None
active_websockets: Set[WebSocket] = set()
latest_state: dict = {}
main_event_loop: asyncio.AbstractEventLoop = None # Store the main event loop

# ─── Startup / Shutdown ───────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    global processor, main_event_loop
    processor = VideoProcessor()
    main_event_loop = asyncio.get_event_loop() # Capture the main event loop
    
    def on_state(state: dict):
        global latest_state
        latest_state = state
        # Schedule broadcast (non-blocking)
        # Use the captured main_event_loop to safely schedule coroutine from another thread
        if main_event_loop and main_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(state), main_event_loop)
    
    processor.start(on_state=on_state)
    print("[Server] VideoProcessor started.")

@app.on_event("shutdown")
async def shutdown():
    if processor:
        processor.stop()

# ─── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_websockets.add(ws)
    print(f"[WS] Client connected. Total: {len(active_websockets)}")
    
    try:
        while True:
            # Keep alive + push state on demand
            await asyncio.sleep(0.033)  # ~30fps push
            if processor and processor.latest_metrics:
                state = processor.get_state()
                try:
                    await ws.send_json(state)
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        active_websockets.discard(ws)
        print(f"[WS] Client disconnected. Total: {len(active_websockets)}")

async def broadcast(state: dict):
    """Broadcast state to all connected WebSocket clients."""
    dead = set()
    for ws in list(active_websockets):
        try:
            await ws.send_json(state)
        except Exception:
            dead.add(ws)
    active_websockets -= dead

# ─── REST Endpoints ───────────────────────────────────────────────────────────
# Mount React assets
assets_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "web-dashboard", "dist", "assets"
)
if os.path.exists(assets_path):
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

@app.get("/")
async def index():
    """Serve the React dashboard HTML."""
    frontend_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "web-dashboard", "dist", "index.html"
    )
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return HTMLResponse("<h1>React Dashboard not built yet. Run 'npm run build' in web-dashboard folder.</h1>", status_code=404)

@app.get("/api/status")
async def api_status():
    """Current system status."""
    if processor:
        return JSONResponse({
            "status": "running",
            "metrics": processor.latest_metrics,
            "signals": processor.latest_signals,
            "alerts":  processor.latest_alerts,
        })
    return JSONResponse({"status": "not_started"})

@app.get("/api/metrics")
async def api_metrics():
    """Detailed metrics endpoint."""
    if processor:
        return JSONResponse(processor.latest_metrics)
    return JSONResponse({})

@app.get("/api/frame")
async def api_frame():
    """Latest annotated frame as JPEG (for polling fallback)."""
    from fastapi.responses import Response
    if processor:
        jpg = processor.get_jpeg_frame()
        if jpg:
            return Response(content=jpg, media_type="image/jpeg")
    return Response(status_code=204)

@app.get("/health")
async def health():
    return {"ok": True, "time": time.time()}

# ─── Run ──────────────────────────────────────────────────────────────────────
def run():
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")

if __name__ == "__main__":
    run()
