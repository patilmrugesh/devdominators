export default function DetectionStats({ vehicleTypes = {} }) {
    const stats = [
        { label: 'Cars', key: 'car', color: 'var(--green)', icon: '🟢' },
        { label: 'Trucks', key: 'truck', color: 'var(--purple)', icon: '🟣' },
        { label: 'Motorcycles', key: 'motorcycle', color: 'var(--orange)', icon: '🟠' },
        { label: 'Buses', key: 'bus', color: 'var(--blue)', icon: '🔵' }
    ];

    return (
        <div className="glass-panel" style={{ padding: '16px' }}>
            <div className="section-title">
                <div className="section-dot" style={{ background: 'var(--blue)' }} />
                Detection Stats
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '12px' }}>
                {stats.map(item => (
                    <div key={item.key} style={{
                        background: 'rgba(9, 17, 30, 0.8)',
                        border: '1px solid var(--border)',
                        borderRadius: '10px',
                        padding: '12px'
                    }}>
                        <div className="mono" style={{ fontSize: '20px', fontWeight: '700', color: item.color }}>
                            {vehicleTypes[item.key] || 0}
                        </div>
                        <div style={{ fontSize: '10px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginTop: '4px' }}>
                            {item.icon} {item.label}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
