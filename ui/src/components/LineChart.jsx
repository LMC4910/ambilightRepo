import React from 'react'

/**
 * Minimal dependency-free SVG line chart for time-series metrics.
 * `data` is an array of numbers; renders a polyline scaled to the box.
 */
export default function LineChart({ data = [], color = '#3b82f6', height = 80, label = '', unit = '' }) {
  const w = 300
  const h = height
  const pad = 4
  const vals = data.length ? data : [0]
  const max = Math.max(...vals, 1)
  const min = Math.min(...vals, 0)
  const range = max - min || 1
  const step = vals.length > 1 ? (w - pad * 2) / (vals.length - 1) : 0

  const points = vals.map((v, i) => {
    const x = pad + i * step
    const y = h - pad - ((v - min) / range) * (h - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')

  const latest = vals[vals.length - 1] ?? 0

  return (
    <div className="metric-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span className="metric-label">{label}</span>
        <span style={{ color, fontWeight: 700 }}>{Number(latest).toFixed(1)} <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{unit}</span></span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none" style={{ marginTop: '0.5rem' }}>
        <polyline fill="none" stroke={color} strokeWidth="1.5" points={points} />
      </svg>
    </div>
  )
}
