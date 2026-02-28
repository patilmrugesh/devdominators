import React, { useState, useEffect } from 'react';

export default function IncidentMonitor() {
    const [incidents, setIncidents] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchIncidents = async () => {
            try {
                const res = await fetch(`http://${window.location.hostname}:8000/api/incidents`);
                if (res.ok) {
                    const data = await res.json();
                    setIncidents(data);
                }
            } catch (err) {
                console.error("Failed to fetch incidents", err);
            } finally {
                setLoading(false);
            }
        };

        fetchIncidents();
        const interval = setInterval(fetchIncidents, 2000);
        return () => clearInterval(interval);
    }, []);

    const getTypeColor = (type) => {
        switch (type) {
            case 'crowd': return 'var(--blue)';
            case 'ambulance': return 'var(--purple)';
            case 'accident': return 'var(--red)';
            case 'parking': return 'var(--orange)';
            default: return 'var(--muted)';
        }
    };

    const getIcon = (type) => {
        switch (type) {
            case 'crowd': return '👥';
            case 'ambulance': return '🚑';
            case 'accident': return '💥';
            case 'parking': return '🛑';
            default: return '⚠️';
        }
    };

    return (
        <div style={{ padding: '24px', flex: 1, overflowY: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                <div className="section-dot" style={{ background: 'var(--red)', width: '12px', height: '12px' }} />
                <h2 style={{ fontSize: '20px', fontWeight: '700', letterSpacing: '0.5px' }}>Live Security Feed</h2>
                <div style={{ marginLeft: 'auto', background: 'var(--card-bg)', padding: '6px 12px', borderRadius: '20px', fontSize: '12px' }}>
                    Tracking <span style={{ color: 'var(--red)', fontWeight: 'bold' }}>{incidents.length}</span> Recent Anomalies
                </div>
            </div>

            {loading && incidents.length === 0 ? (
                <div style={{ textAlign: 'center', color: 'var(--muted)', marginTop: '40px' }}>Loading incident data...</div>
            ) : incidents.length === 0 ? (
                <div style={{
                    textAlign: 'center', padding: '60px', background: 'var(--card-bg)',
                    borderRadius: '16px', border: '1px solid var(--border)'
                }}>
                    <div style={{ fontSize: '48px', marginBottom: '16px' }}>🛡️</div>
                    <h3 style={{ color: 'var(--green)', fontSize: '18px', marginBottom: '8px' }}>Intersection Secure</h3>
                    <p style={{ color: 'var(--muted)', fontSize: '14px' }}>No severe incidents, crowds, or accidents detected recently.</p>
                </div>
            ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '20px' }}>
                    {incidents.map((incident, idx) => (
                        <div key={idx} className="glass-panel" style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                            <div style={{ position: 'relative', height: '200px', background: '#000' }}>
                                {incident.frame_b64 ? (
                                    <img
                                        src={`data:image/jpeg;base64,${incident.frame_b64}`}
                                        alt="Incident Snapshot"
                                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                    />
                                ) : (
                                    <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)' }}>
                                        No Image Provided
                                    </div>
                                )}
                                <div style={{
                                    position: 'absolute', top: '12px', right: '12px',
                                    background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
                                    padding: '4px 10px', borderRadius: '12px',
                                    border: `1px solid ${getTypeColor(incident.type)}`,
                                    display: 'flex', alignItems: 'center', gap: '6px',
                                    fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase',
                                    color: getTypeColor(incident.type)
                                }}>
                                    <span>{getIcon(incident.type)}</span>
                                    {incident.type}
                                </div>
                            </div>
                            <div style={{ padding: '16px', flex: 1, backgroundColor: 'rgba(10, 15, 25, 0.4)' }}>
                                <div className="mono" style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '8px' }}>
                                    {new Date(incident.timestamp * 1000).toLocaleString()}
                                </div>
                                <div style={{ fontSize: '14px', lineHeight: '1.5', color: 'var(--text)' }}>
                                    {incident.description}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
