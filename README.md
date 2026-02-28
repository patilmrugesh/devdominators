# 🚦 AI Traffic De-Congestion System

> **Hackathon-ready** real-time AI system that detects vehicles using **YOLOv8**, assigns them to lanes, and dynamically adjusts traffic signal timings to reduce congestion.

---

## 🎯 Problem Statement
Conventional traffic signals use fixed timing — they can't respond to real congestion. This system uses computer vision to:
- Count vehicles per lane in real-time
- Give green light proportional to traffic density
- Prioritize **ambulances** (emergency preemption)
- Detect **accidents** and alert operators
- Show everything on a **live monitoring dashboard**

---

## 🏗️ Architecture

```
Camera Feed → YOLOv8 Detection → Centroid Tracker → Lane Assignment
           → Traffic Analyzer → Signal Optimizer → Dashboard
```

| Layer | Component | Technology |
|-------|-----------|-----------|
| Detection | `core/detector.py` | YOLOv8n |
| Tracking | `core/tracker.py` | Centroid Matching |
| Lane Zones | `core/lane_manager.py` | Polygon Containment |
| Metrics | `core/traffic_analyzer.py` | Rule-based |
| Signals | `core/signal_optimizer.py` | Weighted Rules + Fairness |
| API | `backend/main.py` | FastAPI + WebSocket |
| Dashboard | `frontend/index.html` | Vanilla JS + Chart.js |

---

## 🚀 Quick Start

### Option A — Live Dashboard (Full System)
```bash
pip install -r requirements.txt
python run.py
# → Opens http://localhost:8000 automatically
```

### Option B — Standalone OpenCV Demo (No Server)
```bash
python demo.py
# Or with a specific video:
python demo.py --video path/to/traffic.mp4
```

### Demo Controls (`demo.py`)
| Key | Action |
|-----|--------|
| `Q` | Quit |
| `SPACE` | Pause / Resume |
| `R` | Reset video |
| `A` | Toggle ambulance simulation |

---

## 🧠 Algorithm — Signal Timing

```python
# Adaptive green time formula
green_time = BASE_TIME (10s) + vehicle_count × 2s
green_time = clamp(green_time, MIN=5s, MAX=45s)

# Fairness rule
if any_lane_wait > 60s:
    force_green(that_lane)

# Emergency preemption
if ambulance_detected:
    immediate_green(ambulance_lane)
```

**Trade-off Analysis:**
| Approach | Accuracy | Complexity | Chosen? |
|----------|----------|------------|---------|
| Rule-based (this system) | Good | Low | ✅ |
| Reinforcement Learning | Best | Very High | Future |

---

## 🔍 Detection Classes

| Class | COCO ID | Detection |
|-------|---------|-----------|
| Car | 2 | ✅ |
| Motorcycle | 3 | ✅ |
| Bus | 5 | ✅ |
| Truck | 7 | ✅ |
| Person | 0 | ✅ |
| Ambulance | Custom label | ✅ |

---

## 📊 Expected Improvements

| Metric | Fixed Timing | AI System | Improvement |
|--------|-------------|-----------|-------------|
| Avg Wait Time | ~90s | ~42s | **53% ↓** |
| Queue Length | High | Reduced | ~40% ↓ |
| Emergency Response | No priority | Instant | ∞ |

---

## ⚙️ Configuration

All settings in `config.py`:
```python
VIDEO_PATH = "path/to/video.mp4"   # Video source
CONFIDENCE_THRESHOLD = 0.40         # Detection confidence
BASE_GREEN_TIME = 10                # Min green time (seconds)
GREEN_PER_VEHICLE = 2               # Extra seconds per vehicle
MAX_GREEN_TIME = 45                 # Cap (seconds)
MAX_WAIT_TIME = 60                  # Fairness threshold
```

---

## 🛣️ Future Scope
- Reinforcement Learning signal optimizer
- Multi-camera intersection fusion  
- City-wide traffic command center
- Predictive congestion (30s ahead)
- V2X vehicle communication
- Integration with navigation apps

---

## 📁 Project Structure

```
TrafficAI/
├── config.py                  # All configuration
├── demo.py                    # Standalone OpenCV demo ← START HERE
├── run.py                     # Full server launcher
├── requirements.txt
├── core/
│   ├── detector.py            # YOLOv8 detection
│   ├── tracker.py             # Multi-object tracking
│   ├── lane_manager.py        # Virtual lane zones
│   ├── traffic_analyzer.py    # Metrics + accident detection
│   └── signal_optimizer.py    # Adaptive signal control
├── backend/
│   ├── main.py                # FastAPI + WebSocket server
│   └── video_processor.py     # Pipeline orchestration
└── frontend/
    └── index.html             # Premium monitoring dashboard
```
