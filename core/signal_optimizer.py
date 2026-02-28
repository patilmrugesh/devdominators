"""
core/signal_optimizer.py — Adaptive Traffic Signal Optimizer
=============================================================
Implements adaptive signal timing with:
  - Weighted rule-based timing (base + per-vehicle seconds)
  - Fairness enforcement (no lane waits > threshold)
  - Emergency vehicle preemption
  - 4-phase cycle: North → South → East → West

State machine:
  GREEN (active) → YELLOW (transitioning) → RED → wait for next turn
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from enum import Enum
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class SignalState(str, Enum):
    GREEN  = "green"
    YELLOW = "yellow"
    RED    = "red"


@dataclass
class LaneSignal:
    """Current signal state and timing for one lane."""
    name:        str
    state:       SignalState = SignalState.RED
    time_left:   float       = 0.0     # Seconds remaining
    last_green:  float       = 0.0     # Timestamp of last green
    total_green: float       = 0.0     # Cumulative green time
    total_wait:  float       = 0.0     # Cumulative wait time


class SignalOptimizer:
    """
    Adaptive Traffic Signal Optimizer.
    
    Algorithm:
      1. Evaluate all lanes by priority score
      2. Compute green time: BASE + count × WEIGHT (capped at MAX)
      3. If any lane waited > MAX_WAIT_TIME → force it green next
      4. Ambulance detected → immediate preemption override
    
    Trade-offs documented:
      Rule-based: Simple, predictable, fast. No training needed.
      RL-based: More adaptive but needs simulation environment + training.
      → Hackathon choice: Rule-based with ML-ready interface.
    """
    
    PHASE_ORDER = ["North", "South", "East", "West"]
    
    def __init__(self):
        now = time.time()
        self.signals: Dict[str, LaneSignal] = {
            name: LaneSignal(name=name, last_green=now) for name in self.PHASE_ORDER
        }
        
        # Current phase
        self._phase_idx     = 0
        self._phase_start   = time.time()
        self._phase_duration = config.MIN_GREEN_TIME    # Will be updated
        self._in_yellow     = False
        self._yellow_start  = 0.0
        
        # Emergency
        self.emergency_lane:   Optional[str] = None
        self.emergency_active: bool = False
        self.emergency_start:  float = 0.0
        
        # Metrics
        self.total_cycles    = 0
        self.last_update     = time.time()
        self.phase_history:  List[Dict] = []   # For analytics
        
        # Initialize first green
        self._activate_phase(self._phase_idx)
    
    @property
    def current_lane(self) -> str:
        return self.PHASE_ORDER[self._phase_idx]
    
    @property
    def current_state(self) -> SignalState:
        return self.signals[self.current_lane].state
    
    def compute_green_time(self, stats) -> float:
        """
        Compute adaptive green time based on physics density & queue length.
        
        Formula: 
          - Calculate a density multiplier (0.0 to 1.0)
          - Scale BASE_GREEN to MAX_GREEN via multiplier
          - Add minor buffer for large stopped queues
        """
        if not stats:
            return config.MIN_GREEN_TIME
            
        ratio = getattr(stats, 'density_ratio', 0.0)
        queue = getattr(stats, 'queue_length', 0)
        
        # Scale between base and max using density (clamp ratio up to 0.8 as 'fully dense')
        effective_density_ratio = min(1.0, ratio / 0.8) if ratio > 0 else 0.0
        green_time = config.BASE_GREEN_TIME + ((config.MAX_GREEN_TIME - config.BASE_GREEN_TIME) * effective_density_ratio)
        
        # Minor bump for long queues to assist clearing
        if queue > 4:
            green_time += (queue - 4) * 1.5
            
        return max(config.MIN_GREEN_TIME, min(config.MAX_GREEN_TIME, green_time))
    
    def update(self, lane_stats: Dict) -> Dict[str, SignalState]:
        """
        Main update tick — call once per frame.
        
        Args:
            lane_stats: Dict[lane_name → LaneStats] from LaneManager
        
        Returns:
            Dict[lane_name → SignalState] for all lanes
        """
        now = time.time()
        elapsed = now - self._phase_start
        
        # ── Emergency Override ──────────────────────────────────────────────
        ambulance_lanes = [
            name for name, stats in lane_stats.items()
            if getattr(stats, 'ambulance_present', False)
        ]
        
        if ambulance_lanes and config.AMBULANCE_OVERRIDE:
            target = ambulance_lanes[0]
            if not self.emergency_active or self.emergency_lane != target:
                self._trigger_emergency(target)
        elif self.emergency_active:
            # Emergency over if ambulance gone for 5+ seconds
            if time.time() - self.emergency_start > 5.0 and not ambulance_lanes:
                self._clear_emergency()
        
        if self.emergency_active:
            return self._get_signal_states()
        
        # ── Yellow Phase ─────────────────────────────────────────────────────
        if self._in_yellow:
            yellow_elapsed = now - self._yellow_start
            self.signals[self.current_lane].time_left = (
                config.YELLOW_DURATION - yellow_elapsed
            )
            
            if yellow_elapsed >= config.YELLOW_DURATION:
                self._in_yellow = False
                self.signals[self.current_lane].state = SignalState.RED
                self._advance_phase(lane_stats)
            
            return self._get_signal_states()
        
        # ── Active Green Phase ───────────────────────────────────────────────
        time_left = self._phase_duration - elapsed
        self.signals[self.current_lane].time_left = max(0, time_left)
        
        if elapsed >= self._phase_duration:
            # Transition to yellow
            self._in_yellow = True
            self._yellow_start = now
            self.signals[self.current_lane].state = SignalState.YELLOW
            self.signals[self.current_lane].time_left = config.YELLOW_DURATION
        
        return self._get_signal_states()
    
    def _advance_phase(self, lane_stats: Dict):
        """Choose the next phase, respecting fairness and priority."""
        # ── Fairness check ───────────────────────────────────────────────────
        now = time.time()
        fairness_candidate = None
        longest_wait = 0.0
        
        for name, sig in self.signals.items():
            if name == self.current_lane:
                continue
            wait = now - sig.last_green
            if wait > config.MAX_WAIT_TIME and wait > longest_wait:
                fairness_candidate = name
                longest_wait = wait
        
        if fairness_candidate:
            # Forced green for fairness
            next_lane = fairness_candidate
            self._phase_idx = self.PHASE_ORDER.index(next_lane)
        else:
            # Priority-based selection: pick highest score from remaining
            remaining = [n for n in self.PHASE_ORDER if n != self.current_lane]
            
            def priority(name):
                s = lane_stats.get(name)
                if s is None:
                    return 0
                return s.priority_score if hasattr(s, 'priority_score') else 0
            
            # Sort remaining lanes by priority descending and select the highest one
            best_lane = max(remaining, key=priority)
            self._phase_idx = self.PHASE_ORDER.index(best_lane)
        
        self._activate_phase(self._phase_idx)
        self.total_cycles += 1
    
    def _activate_phase(self, idx: int):
        """Set a phase as active (green)."""
        lane = self.PHASE_ORDER[idx]
        
        # Set all to red first
        for name, sig in self.signals.items():
            sig.state = SignalState.RED
            sig.time_left = 0.0
        
        # Activate chosen lane
        self.signals[lane].state      = SignalState.GREEN
        self.signals[lane].last_green = time.time()
        self._phase_start             = time.time()
        
        # Default duration until update() sets it properly
        self._phase_duration = config.BASE_GREEN_TIME
        
        # Log phase change
        self.phase_history.append({
            "lane": lane, "time": time.time(), "duration": self._phase_duration
        })
        if len(self.phase_history) > 100:
            self.phase_history.pop(0)
    
    def update_phase_duration(self, lane_stats: Dict):
        """Update the green duration for the current active phase."""
        stats = lane_stats.get(self.current_lane)
        if stats:
            self._phase_duration = self.compute_green_time(stats)
    
    def _trigger_emergency(self, lane: str):
        """Immediately switch to emergency lane (green)."""
        self.emergency_active = True
        self.emergency_lane   = lane
        self.emergency_start  = time.time()
        
        # Set all red, emergency lane green
        for name, sig in self.signals.items():
            sig.state = SignalState.RED
            sig.time_left = 0.0
        
        self.signals[lane].state      = SignalState.GREEN
        self.signals[lane].time_left  = 30.0  # 30 second emergency window
        self.signals[lane].last_green = time.time()
    
    def _clear_emergency(self):
        """Resume normal operation after emergency."""
        self.emergency_active = False
        self.emergency_lane   = None
        # Resume from current phase index
        self._activate_phase(self._phase_idx)
    
    def _get_signal_states(self) -> Dict[str, SignalState]:
        return {name: sig.state for name, sig in self.signals.items()}
    
    def draw_signal_panel(self, frame, x: int = 10, y: int = 10) -> None:
        """Draw a compact signal status panel on the frame."""
        import cv2
        
        COLORS = {
            SignalState.GREEN:  (0, 255, 0),
            SignalState.YELLOW: (0, 200, 255),
            SignalState.RED:    (0, 0, 255),
        }
        
        panel_w, panel_h = 200, 140
        # Background
        cv2.rectangle(frame,
                      (x, y), (x + panel_w, y + panel_h),
                      (20, 20, 20), -1)
        cv2.rectangle(frame,
                      (x, y), (x + panel_w, y + panel_h),
                      (80, 80, 80), 1)
        
        cv2.putText(frame, "SIGNAL STATUS",
                    (x + 10, y + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        
        for i, (name, sig) in enumerate(self.signals.items()):
            row_y = y + 32 + i * 26
            color = COLORS[sig.state]
            
            # Signal circle
            cv2.circle(frame, (x + 16, row_y), 8, color, -1)
            
            # Lane name
            cv2.putText(frame, f"{name}:",
                        (x + 30, row_y + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
            
            # State + time
            state_text = sig.state.value.upper()
            if sig.state in (SignalState.GREEN, SignalState.YELLOW):
                state_text += f" {sig.time_left:.0f}s"
            
            cv2.putText(frame, state_text,
                        (x + 80, row_y + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
        # Emergency banner
        if self.emergency_active:
            cv2.rectangle(frame,
                          (x, y + panel_h + 2), (x + panel_w, y + panel_h + 24),
                          (0, 0, 200), -1)
            cv2.putText(frame, f"🚑 EMERGENCY: {self.emergency_lane}",
                        (x + 4, y + panel_h + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    
    def get_metrics(self) -> Dict:
        """Return serializable signal metrics for dashboard."""
        return {
            "signals": {
                name: {
                    "state":     sig.state.value,
                    "time_left": round(sig.time_left, 1),
                    "last_green": sig.last_green,
                }
                for name, sig in self.signals.items()
            },
            "current_lane":    self.current_lane,
            "total_cycles":    self.total_cycles,
            "emergency_active": self.emergency_active,
            "emergency_lane":  self.emergency_lane,
        }
