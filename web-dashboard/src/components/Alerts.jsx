export default function Alerts({ alerts = [] }) {
    return (
        <div className="glass-panel" style={{ padding: '16px', flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div className="section-title">
                <div className="section-dot" style={{ background: 'var(--red)' }} />
                Active Alerts
            </div>

            <div style={{ marginTop: '12px', flex: 1, overflowY: 'auto' }}>
                {alerts.length === 0 ? (
                    <div style={{
                        color: 'var(--muted)',
                        fontSize: '11px',
                        textAlign: 'center',
                        padding: '16px'
                    }}>
                        ✓ No active alerts
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {alerts.map((a, i) => {
                            let bg = 'rgba(59, 130, 246, 0.1)';
                            let border = 'var(--blue)';

                            if (a.severity === 'critical') {
                                bg = 'rgba(239, 68, 68, 0.15)';
                                border = 'var(--red)';
                            } else if (a.severity === 'high') {
                                bg = 'rgba(249, 115, 22, 0.15)';
                                border = 'var(--orange)';
                            } else if (a.severity === 'medium') {
                                bg = 'rgba(245, 158, 11, 0.15)';
                                border = 'var(--yellow)';
                            }

                            return (
                                <div key={i} style={{
                                    borderRadius: '8px',
                                    padding: '10px 12px',
                                    fontSize: '11px',
                                    display: 'flex',
                                    gap: '8px',
                                    alignItems: 'flex-start',
                                    background: bg,
                                    borderLeft: `3px solid ${border}`,
                                    animation: 'fadeIn 0.35s ease'
                                }}>
                                    <span>{a.emoji || '⚠'}</span>
                                    <span>{a.message || a.type}</span>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
        </div>
    );
}
