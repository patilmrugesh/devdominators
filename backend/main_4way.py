"""
backend/main_4way.py — FastAPI Server with 4-Way WebSocket Dashboard
"""
import asyncio
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
from backend.video_processor_4way import VideoProcessor4Way

app = FastAPI(title="AI Traffic 4-Way Dashboard", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

processor: VideoProcessor4Way = None
active_websockets: Set[WebSocket] = set()
main_event_loop: asyncio.AbstractEventLoop = None

def init_processor(v_north, v_south, v_east, v_west):
    global processor
    processor = VideoProcessor4Way(v_north, v_south, v_east, v_west)

@app.on_event("startup")
async def startup():
    global main_event_loop
    main_event_loop = asyncio.get_event_loop()
    def on_state(state: dict):
        if main_event_loop and main_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(state), main_event_loop)
    if processor:
        processor.start(on_state=on_state)

@app.on_event("shutdown")
async def shutdown():
    if processor: processor.stop()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_websockets.add(ws)
    try:
        while True:
            await asyncio.sleep(0.033)
            if processor and processor.latest_metrics:
                try: await ws.send_json(processor.get_state())
                except Exception: break
    except WebSocketDisconnect: pass
    finally: active_websockets.discard(ws)

async def broadcast(state: dict):
    dead = set()
    for ws in list(active_websockets):
        try: await ws.send_json(state)
        except Exception: dead.add(ws)
    active_websockets -= dead

assets_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web-dashboard", "dist", "assets")
if os.path.exists(assets_path): app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

@app.get("/")
async def index():
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web-dashboard", "dist", "index.html")
    if os.path.exists(frontend_path): return FileResponse(frontend_path)
    return HTMLResponse("<h1>React Dashboard not built yet.</h1>", status_code=404)

@app.get("/api/frame")
async def api_frame():
    from fastapi.responses import Response
    if processor:
        jpg = processor.get_jpeg_frame()
        if jpg: return Response(content=jpg, media_type="image/jpeg")
    return Response(status_code=204)
@app.get("/api/incidents")
async def api_incidents():
    """Returns the latest captured incident snapshots (Crowd, Ambulance, Accident, Parking)."""
    if processor:
        return JSONResponse(processor.get_incident_history())
    return JSONResponse([])
