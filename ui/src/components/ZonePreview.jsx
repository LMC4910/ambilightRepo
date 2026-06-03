import React from 'react'

/**
 * Live zone-colour preview (FR-UI-03). Renders the streamed per-zone colours as
 * a ring of swatches around a screen outline. `zones` is an array of [r,g,b].
 * Pipeline emits zones in order: top, bottom, left, right.
 */
export default function ZonePreview({ zones = [], color = [0, 0, 0] }) {
  const rgb = (c) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`
  // Best-effort split back into edges for placement; if counts are unknown we
  // just lay the swatches along the top as a fallback strip.
  const swatch = (c, key, style) => (
    <div key={key} style={{ flex: 1, background: rgb(c), ...style }} />
  )

  return (
    <div className="metric-card" style={{ gridColumn: '1 / -1' }}>
      <span className="metric-label">Live zone preview</span>
      <div style={{
        position: 'relative', marginTop: '0.75rem', height: '160px',
        borderRadius: '10px', overflow: 'hidden',
        background: zones.length ? '#000' : 'rgba(255,255,255,0.04)',
        boxShadow: zones.length ? `0 0 40px ${rgb(color)}` : 'none',
      }}>
        {/* Outer ring of zone swatches */}
        <div style={{ position: 'absolute', inset: 0, display: 'flex' }}>
          {zones.length
            ? zones.map((c, i) => swatch(c, i, {}))
            : <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>No signal — start screen sync</div>}
        </div>
        {/* Inner "screen" tinted by the combined colour */}
        {zones.length > 0 && (
          <div style={{
            position: 'absolute', inset: '18px', borderRadius: '6px',
            background: rgb(color), opacity: 0.85,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontFamily: 'monospace', fontSize: '0.8rem', textShadow: '0 1px 3px #000',
          }}>
            {rgb(color)}
          </div>
        )}
      </div>
    </div>
  )
}
