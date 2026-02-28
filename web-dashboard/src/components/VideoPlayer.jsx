import { useEffect, useRef } from 'react';

export default function VideoPlayer({ frameB64, fps }) {
    const imgRef = useRef(null);

    useEffect(() => {
        if (frameB64 && imgRef.current) {
            imgRef.current.src = `data:image/jpeg;base64,${frameB64}`;
        }
    }, [frameB64]);

    return (
        <div style={{ width: '100%', height: '100%', position: 'relative' }}>
            {!frameB64 ? (
                <div style={{
                    position: 'absolute', inset: 0, display: 'flex',
                    flexDirection: 'column', alignItems: 'center',
                    justifyContent: 'center', color: 'var(--muted)'
                }}>
                    <div style={{ fontSize: '48px', marginBottom: '16px' }}>📷</div>
                    <p style={{ fontSize: '14px' }}>Waiting for video stream...</p>
                </div>
            ) : (
                <img
                    ref={imgRef}
                    className="video-feed"
                    alt="Live Traffic Feed"
                />
            )}

            {/* Camera Badge Overlay */}
            <div className="glass-panel" style={{
                position: 'absolute', top: '16px', left: '16px',
                padding: '6px 12px', display: 'flex', gap: '8px',
                fontSize: '11px', color: 'var(--muted)', alignItems: 'center'
            }}>
                LIVE — CAMERA <span style={{ color: 'var(--border)' }}>|</span>
                <span className="mono" style={{ color: 'var(--green)', fontWeight: 'bold' }}>
                    {parseFloat(fps || 0).toFixed(1)} FPS
                </span>
            </div>

            {/* Legend Overlay */}
            <div className="glass-panel" style={{
                position: 'absolute', bottom: '16px', left: '16px',
                padding: '8px 16px', display: 'flex', gap: '16px', fontSize: '11px'
            }}>
                {[
                    { label: 'Car', color: 'var(--green)' },
                    { label: 'Motorcycle', color: 'var(--orange)' },
                    { label: 'Bus', color: 'var(--blue)' },
                    { label: 'Truck', color: 'var(--purple)' },
                    { label: 'Ambulance', color: 'var(--red)' }
                ].map(item => (
                    <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <div style={{ width: '10px', height: '10px', borderRadius: '2px', background: item.color }} />
                        {item.label}
                    </div>
                ))}
            </div>
        </div>
    );
}
