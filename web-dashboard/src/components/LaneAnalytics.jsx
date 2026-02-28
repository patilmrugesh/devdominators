export default function LaneAnalytics({ laneStats = {} }) {
    const lanes = ['North', 'South'];

    return (
        <div className="glass-panel" style={{ padding: '16px' }}>
            <div className="section-title">
                <div className="section-dot" style={{ background: 'var(--purple)' }} />
                Lane Analytics
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '12px' }}>
                {lanes.map(lane => {
                    const stats = laneStats[lane] || {};
                    const count = stats.vehicle_count || 0;
                    const density = Math.round((stats.density_ratio || 0) * 100);
                    const queue = stats.queue_length || 0;
                    const wait = Math.round(stats.avg_wait_time || 0);

                    let barColor = 'var(--green)';
                    if (density >= 40) barColor = 'var(--yellow)';
                    if (density >= 75) barColor = 'var(--red)';

                    const nameColor = `var(--${lane.toLowerCase()})`;

                    return (
                        <div key={lane}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', fontWeight: '600' }}>
                                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: nameColor }} />
                                    <span style={{ color: nameColor }}>{lane}</span>
                                </div>
                                <div className="mono" style={{ fontSize: '12px' }}>{count} veh</div>
                            </div>

                            {/* Progress Bar Background */}
                            <div style={{ background: 'var(--border)', borderRadius: '6px', height: '6px', overflow: 'hidden' }}>
                                {/* Progress Bar Fill */}
                                <div style={{
                                    height: '100%',
                                    background: barColor,
                                    width: `${Math.min(density, 100)}%`,
                                    transition: 'width 0.5s ease, background 0.5s ease',
                                    borderRadius: '6px'
                                }} />
                            </div>

                            <div className="mono" style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                marginTop: '6px',
                                fontSize: '10px',
                                color: 'var(--muted)'
                            }}>
                                <span>Density: {density}%</span>
                                <span>Queue: {queue}</span>
                                <span>Wait: {wait}s</span>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
