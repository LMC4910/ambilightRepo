import React from 'react'

/** Dependency-free SVG sparkline with a gradient area fill. */
export default function LineChart({ data = [], color = '#3b82f6', height = 80, label = '', unit = '' }) {
  const w = 300
  const h = height
  const pad = 4
  const vals = data.length ? data : [0]
  const max = Math.max(...vals, 1)
  const min = Math.min(...vals, 0)
  const range = max - min || 1
  const step = vals.length > 1 ? (w - pad * 2) / (vals.length - 1) : 0

  const coords = vals.map((v, i) => [pad + i * step, h - pad - ((v - min) / range) * (h - pad * 2)])
  const points = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = coords.length ? `${pad},${h - pad} ${points} ${(pad + (coords.length - 1) * step).toFixed(1)},${h - pad}` : ''
  const gid = `lc-${label.replace(/\W/g, '')}`
  const latest = vals[vals.length - 1] ?? 0

  return (
    <div className="glass-panel rounded-2xl p-5">
      <div className="flex justify-between items-baseline">
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{label}</span>
        <span className="font-mono font-bold" style={{ color }}>{Number(latest).toFixed(1)} <span className="text-slate-500 text-xs">{unit}</span></span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none" className="mt-2">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.35" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {area && <polygon fill={`url(#${gid})`} points={area} />}
        <polyline fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" points={points} />
      </svg>
    </div>
  )
}
