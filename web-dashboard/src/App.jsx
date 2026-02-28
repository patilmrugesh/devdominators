import { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import VideoPlayer from './components/VideoPlayer';
import SignalPanel from './components/SignalPanel';
import DetectionStats from './components/DetectionStats';
import LaneAnalytics from './components/LaneAnalytics';
import Alerts from './components/Alerts';
import IncidentMonitor from './components/IncidentMonitor';

function App() {
  const [currentView, setCurrentView] = useState('dashboard');
  const [state, setState] = useState({
    metrics: {},
    signals: {},
    alerts: [],
    frame_b64: null,
  });

  const [isConnected, setIsConnected] = useState(false);
  const startTime = useRef(Date.now());
  const [uptime, setUptime] = useState('00:00');

  useEffect(() => {
    // Uptime timer
    const t = setInterval(() => {
      const sec = Math.floor((Date.now() - startTime.current) / 1000);
      setUptime(
        String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0')
      );
    }, 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let ws;
    let wsRetries = 0;

    function connectWS() {
      // Connect to the fastapi backend
      ws = new WebSocket(`ws://${window.location.hostname}:8000/ws`);

      ws.onopen = () => {
        setIsConnected(true);
        wsRetries = 0;
      };

      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          setState(data);
        } catch (e) {
          console.error("Failed to parse websocket message", e);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        setTimeout(connectWS, wsRetries++ < 5 ? 800 : 2500);
      };

      ws.onerror = () => ws.close();
    }

    connectWS();

    // Cleanup
    return () => {
      if (ws) ws.close();
    };
  }, []);

  return (
    <>
      <Header
        metrics={state.metrics}
        uptime={uptime}
        isConnected={isConnected}
        currentView={currentView}
        setCurrentView={setCurrentView}
      />

      <main className="main-container">
        {currentView === 'dashboard' ? (
          <>
            <section className="video-section">
              <VideoPlayer frameB64={state.frame_b64} fps={state.metrics?.current_fps} />
            </section>

            <aside className="sidebar">
              <SignalPanel signals={state.signals} laneStats={state.metrics?.lane_stats} />
              <DetectionStats vehicleTypes={state.metrics?.vehicle_types} />
              <LaneAnalytics laneStats={state.metrics?.lane_stats} />
              <Alerts alerts={state.alerts} />
            </aside>
          </>
        ) : (
          <IncidentMonitor />
        )}
      </main>
    </>
  );
}

export default App;
