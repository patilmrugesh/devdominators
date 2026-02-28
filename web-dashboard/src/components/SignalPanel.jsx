export default function SignalPanel({ signals, laneStats }) {
    const data = signals?.signals || {};
    const lanes = ['North', 'South'];

    return (
        <div className="glass-panel" style={{ padding: '16px' }}>
            <div className="section-title">
                <div className="section-dot" style={{ background: 'var(--green)' }} />
                Signal Control
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '12px' }}>
                {lanes.map((lane, index) => {
                    const s = data[lane] || { state: 'red', time_left: 0 };
                    const stats = laneStats?.[lane] || { vehicle_count: 0 };

                    let stColor = 'var(--muted)';
                    let maxTime = 5;

                    if (s.state === 'green') {
                        stColor = 'var(--green)';
                        maxTime = 45;
                    } else if (s.state === 'yellow') {
                        stColor = 'var(--yellow)';
                        maxTime = 3;
                    } else {
                        stColor = 'var(--red)';
                    }

                    const pct = Math.min(1, Math.max(0, s.time_left / maxTime));
                    const circ = 2 * Math.PI * 20;

                    return (
                        <div key={lane}>
                            <div style={{
                                background: 'rgba(9, 17, 30, 0.8)',
                                border: `1px solid ${s.state !== 'red' ? stColor : 'var(--border)'}`,
                                borderRadius: '12px',
                                padding: '12px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '16px',
                                boxShadow: s.state !== 'red' ? `0 0 16px ${stColor}20` : 'none',
                                transition: 'all 0.3s ease'
                            }}>
                                {/* Traffic Light Bulbs */}
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                    <div style={{ width: '14px', height: '14px', borderRadius: '50%', background: s.state === 'red' ? 'var(--red)' : '#3a1515', opacity: s.state === 'red' ? 1 : 0.3, boxShadow: s.state === 'red' ? '0 0 8px var(--red)' : 'none' }} />
                                    <div style={{ width: '14px', height: '14px', borderRadius: '50%', background: s.state === 'yellow' ? 'var(--yellow)' : '#3a3215', opacity: s.state === 'yellow' ? 1 : 0.3, boxShadow: s.state === 'yellow' ? '0 0 8px var(--yellow)' : 'none' }} />
                                    <div style={{ width: '14px', height: '14px', borderRadius: '50%', background: s.state === 'green' ? 'var(--green)' : '#0d2e1a', opacity: s.state === 'green' ? 1 : 0.3, boxShadow: s.state === 'green' ? '0 0 8px var(--green)' : 'none' }} />
                                </div>

                                {/* Countdown Ring */}
                                <div style={{ position: 'relative', width: '48px', height: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <svg style={{ position: 'absolute', transform: 'rotate(-90deg)' }} width="48" height="48" viewBox="0 0 48 48">
                                        <circle cx="24" cy="24" r="20" fill="none" stroke="var(--border)" strokeWidth="4" />
                                        <circle cx="24" cy="24" r="20" fill="none" stroke={stColor} strokeWidth="4" strokeLinecap="round"
                                            style={{
                                                strokeDasharray: circ,
                                                strokeDashoffset: circ * (1 - pct),
                                                transition: 'stroke-dashoffset 1s linear, stroke 0.3s'
                                            }}
                                        />
                                    </svg>
                                    <div style={{ textAlign: 'center', zIndex: 1 }}>
                                        <div className="mono" style={{ fontSize: '14px', fontWeight: '800', color: stColor, lineHeight: 1 }}>
                                            {s.time_left > 0 ? Math.ceil(s.time_left) : '--'}
                                        </div>
                                        <div style={{ fontSize: '8px', color: 'var(--muted)', marginTop: '2px' }}>sec</div>
                                    </div>
                                </div>

                                {/* Info block */}
                                <div style={{ flex: 1 }}>
                                    <div style={{ fontSize: '14px', fontWeight: '800', textTransform: 'uppercase', letterSpacing: '1px', color: `var(--${lane.toLowerCase()})` }}>
                                        {lane}
                                    </div>
                                    <div style={{ fontSize: '10px', fontWeight: '600', textTransform: 'uppercase', color: stColor }}>
                                        {s.state} ●
                                    </div>
                                    <div className="mono" style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px' }}>
                                        {stats.vehicle_count} vehicles
                                    </div>
                                </div>
                            </div>

                            {index === 0 && (
                                <div style={{ position: 'relative', textAlign: 'center', margin: '6px 0', color: 'var(--muted)', fontSize: '9px', letterSpacing: '2px' }}>
                                    <div style={{ position: 'absolute', top: '50%', left: 0, right: 0, height: '1px', background: 'var(--border)' }} />
                                    <span style={{ background: 'var(--card-bg)', padding: '0 8px', position: 'relative' }}>VS</span>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
