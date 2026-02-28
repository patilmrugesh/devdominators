export default function Header({ metrics, uptime, isConnected, currentView, setCurrentView }) {
    const fps = parseFloat(metrics?.fps || metrics?.current_fps || 0).toFixed(1);
    const veh = metrics?.total_vehicles || metrics?.vehicle_count || 0;

    return (
        <header>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '24px' }}>🚦</span>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontWeight: '700', fontSize: '15px', letterSpacing: '0.5px' }}>
                        AI Traffic Control System
                    </span>
                    <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
                        YOLOv8 Detection &bull; Adaptive Signal Control
                    </span>
                </div>
            </div>

            <div style={{ display: 'flex', gap: '8px', background: 'rgba(255,255,255,0.05)', padding: '4px', borderRadius: '12px' }}>
                <button
                    onClick={() => setCurrentView('dashboard')}
                    style={{
                        background: currentView === 'dashboard' ? 'var(--blue)' : 'transparent',
                        color: currentView === 'dashboard' ? '#fff' : 'var(--muted)',
                        border: 'none', padding: '8px 16px', borderRadius: '8px',
                        fontSize: '13px', fontWeight: '600', cursor: 'pointer',
                        transition: 'all 0.2s'
                    }}>
                    🚦 Live Dashboard
                </button>
                <button
                    onClick={() => setCurrentView('incidents')}
                    style={{
                        background: currentView === 'incidents' ? 'var(--red)' : 'transparent',
                        color: currentView === 'incidents' ? '#fff' : 'var(--muted)',
                        border: 'none', padding: '8px 16px', borderRadius: '8px',
                        fontSize: '13px', fontWeight: '600', cursor: 'pointer',
                        transition: 'all 0.2s'
                    }}>
                    ⚠️ Incident Feed
                </button>
            </div>

            <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                    <div className="mono" style={{ color: 'var(--green)', fontSize: '18px', fontWeight: '700' }}>
                        {fps}
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--muted)', textTransform: 'uppercase' }}>FPS</div>
                </div>

                <div style={{ textAlign: 'center' }}>
                    <div className="mono" style={{ color: 'var(--blue)', fontSize: '18px', fontWeight: '700' }}>
                        {veh}
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--muted)', textTransform: 'uppercase' }}>Vehicles</div>
                </div>

                <div style={{ textAlign: 'center' }}>
                    <div className="mono" style={{ color: 'var(--purple)', fontSize: '18px', fontWeight: '700' }}>
                        {uptime}
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--muted)', textTransform: 'uppercase' }}>Uptime</div>
                </div>

                <div
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        background: isConnected ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                        border: isConnected ? '1px solid rgba(16, 185, 129, 0.3)' : '1px solid rgba(239, 68, 68, 0.3)',
                        padding: '6px 12px',
                        borderRadius: '20px',
                        fontSize: '11px',
                        fontWeight: '600'
                    }}
                >
                    {isConnected && <div className="live-pulse" />}
                    {isConnected ? 'LIVE' : 'DISCONNECTED'}
                </div>
            </div>
        </header>
    );
}
