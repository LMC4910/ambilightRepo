import React from 'react'

/**
 * Live zone-colour preview (FR-UI-03) — framed "screen" with a scanning beam,
 * corner accents, and shimmering zone blocks driven by the live metrics
 * (`zones`: array of [r,g,b] in pipeline order; `color`: combined RGB).
 */
export default function ZonePreview({ zones = [], color = [0, 0, 0] }) {
  const rgb = (c) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`
  const hasSignal = zones.length > 0

  return (
    <div className="glass-panel rounded-3xl p-8 border border-white/5">
      <h3 className="text-xs font-bold text-slate-500 uppercase tracking-[0.2em] mb-6">Live Zone Preview</h3>
      <div className="relative">
        <div className="w-full h-48 bg-slate-900/50 rounded-2xl border-4 border-slate-800/80 overflow-hidden flex shadow-2xl relative"
          style={{ boxShadow: hasSignal ? `0 0 60px -10px ${rgb(color)}` : undefined }}>
          {hasSignal && <div className="scanner-beam" />}

          {hasSignal ? (
            zones.map((c, i) => (
              <div key={i} className="zone-block h-full" style={{ flex: 1, background: rgb(c), borderRight: '1px solid rgba(0,0,0,0.25)' }} />
            ))
          ) : (
            <div className="flex-1 flex items-center justify-center text-sm text-slate-500">No signal — start screen sync</div>
          )}

          {hasSignal && (
            <div className="absolute inset-5 rounded-lg flex items-center justify-center"
              style={{ background: rgb(color), opacity: 0.9 }}>
              <span className="font-mono text-xs text-white" style={{ textShadow: '0 1px 4px rgba(0,0,0,0.7)' }}>{rgb(color)}</span>
            </div>
          )}
        </div>
        {/* Corner accents */}
        <div className="absolute -top-2 -left-2 w-6 h-6 border-t-2 border-l-2 border-indigo-500/30 rounded-tl-lg" />
        <div className="absolute -top-2 -right-2 w-6 h-6 border-t-2 border-r-2 border-indigo-500/30 rounded-tr-lg" />
        <div className="absolute -bottom-2 -left-2 w-6 h-6 border-b-2 border-l-2 border-indigo-500/30 rounded-bl-lg" />
        <div className="absolute -bottom-2 -right-2 w-6 h-6 border-b-2 border-r-2 border-indigo-500/30 rounded-br-lg" />
      </div>
    </div>
  )
}
