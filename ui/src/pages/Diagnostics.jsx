import React, { useEffect, useState } from 'react'
import LineChart from '../components/LineChart'
import { Stethoscope, Cpu, Monitor } from 'lucide-react'

function InfoRow({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.3rem 0', fontSize: '0.85rem' }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontFamily: 'monospace' }}>{value}</span>
    </div>
  )
}

export default function Diagnostics() {
  const [diag, setDiag] = useState(null)

  useEffect(() => {
    const fetchDiag = async () => {
      try { setDiag(await window.api.diagnostics.get()) } catch (e) { /* service offline */ }
    }
    fetchDiag()
    const timer = setInterval(fetchDiag, 2000)
    return () => clearInterval(timer)
  }, [])

  if (!diag) {
    return <section className="glass-panel"><p style={{ color: 'var(--text-muted)' }}>Waiting for diagnostics…</p></section>
  }

  const history = diag.history || []
  const fpsSeries = history.map((p) => p.fps)
  const latSeries = history.map((p) => p.latency_ms)

  return (
    <section className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', overflowY: 'auto' }}>
      <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Stethoscope size={20} /> Diagnostics</h3>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        <LineChart data={fpsSeries} color="#10b981" label="FPS (60 s)" unit="fps" />
        <LineChart data={latSeries} color="#8b5cf6" label="Latency (60 s)" unit="ms" />
      </div>

      <div className="metric-card">
        <h4 style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}><Cpu size={16} /> System</h4>
        <InfoRow label="Platform" value={diag.platform} />
        <InfoRow label="Python" value={diag.python} />
        <InfoRow label="GPU" value={`${diag.gpu?.prefer} (${diag.gpu?.enabled ? 'on' : 'off'})`} />
        <InfoRow label="Capture method" value={diag.capture_method} />
        <InfoRow label="Pipeline" value={`${diag.pipeline?.running ? 'running' : 'stopped'} · restarts ${diag.pipeline?.restarts ?? 0}`} />
      </div>

      <div className="metric-card">
        <h4 style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}><Monitor size={16} /> Device & Displays</h4>
        <InfoRow label="Device IP" value={diag.device?.ip} />
        <InfoRow label="Device MAC" value={diag.device?.mac || 'unknown'} />
        <InfoRow label="LED count" value={diag.device?.led_count} />
        <InfoRow label="Monitors" value={(diag.monitors || []).map((m) => `${m.width}×${m.height}`).join(', ') || 'none'} />
      </div>
    </section>
  )
}
