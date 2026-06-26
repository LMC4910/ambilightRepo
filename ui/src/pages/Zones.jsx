import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Icon, PageHead, Stepper } from '../components/shell'

const EDGES = ['top', 'bottom', 'left', 'right']
const DEFAULT_ZONES = { top: 7, bottom: 7, left: 4, right: 4, edge_fraction: 0.25 }
const rgb = (c) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`

export default function Zones() {
  const { settings, fetchSettings, updateSettings, saving, toast } = useStore()
  const metrics = useStore((s) => s.metrics)
  const [draft, setDraft] = useState(null)

  useEffect(() => { if (!settings) fetchSettings() }, [])
  useEffect(() => { if (settings?.zones) setDraft({ ...DEFAULT_ZONES, ...settings.zones }) }, [settings])

  if (!draft) {
    return (
      <div className="main">
        <PageHead crumb="Configuration" title="Zone layout" sub="LED distribution around the screen edges" />
        <div className="content content-narrow"><div className="card card-pad subtle">Loading zones…</div></div>
      </div>
    )
  }

  const applied = { ...DEFAULT_ZONES, ...(settings?.zones || {}) }
  const dirty = EDGES.some((e) => draft[e] !== applied[e]) || draft.edge_fraction !== applied.edge_fraction
  const total = EDGES.reduce((s, e) => s + draft[e], 0)
  const thick = `${Math.round(draft.edge_fraction * 100)}%`

  // Live colours only line up with the saved layout — show them when not dirty
  // and the metrics frame has exactly the applied LED count.
  const live = Array.isArray(metrics.zones) ? metrics.zones : []
  const appliedTotal = EDGES.reduce((s, e) => s + applied[e], 0)
  const liveOk = !dirty && live.length === appliedTotal && metrics.mode === 'screen_sync'
  const slices = (() => {
    if (!liveOk) return null
    let i = 0
    const take = (n) => { const s = live.slice(i, i + n); i += n; return s }
    return { top: take(draft.top), bottom: take(draft.bottom), left: take(draft.left), right: take(draft.right) }
  })()

  const set = (e, v) => setDraft((d) => ({ ...d, [e]: Math.max(1, Math.min(100, Math.round(v) || 1)) }))
  const save = () => { updateSettings({ zones: draft }); toast('Zone layout saved') }
  const reset = () => setDraft({ ...applied })

  const band = (edge) => Array.from({ length: draft[edge] }, (_, i) => {
    const col = slices ? rgb(slices[edge][i] || [0, 0, 0]) : 'var(--accent-22)'
    return <div key={i} style={{ flex: 1, margin: 1.5, borderRadius: 2, background: col, transition: 'background .5s' }} />
  })

  return (
    <div className="main">
      <PageHead crumb="Configuration" title="Zone layout" sub="LED distribution around the screen edges">
        <button className="btn btn-sm" onClick={reset} disabled={!dirty}><Icon n="rotate-ccw" />Reset</button>
        <button className="btn btn-primary" onClick={save} disabled={!dirty || saving}><Icon n="save" />{dirty ? 'Save layout' : 'Saved'}</button>
      </PageHead>

      <div className="content content-narrow page-enter">
        <div className="zone-layout">
          <div className="card card-pad">
            <div className="zone-screen" style={{ aspectRatio: '16/9' }}>
              <div className="zb" style={{ left: 0, right: 0, top: 0, height: thick, flexDirection: 'row' }}>{band('top')}</div>
              <div className="zb" style={{ left: 0, right: 0, bottom: 0, height: thick, flexDirection: 'row' }}>{band('bottom')}</div>
              <div className="zb" style={{ left: 0, top: thick, bottom: thick, width: thick, flexDirection: 'column' }}>{band('left')}</div>
              <div className="zb" style={{ right: 0, top: thick, bottom: thick, width: thick, flexDirection: 'column' }}>{band('right')}</div>
              <div className="zone-core" style={{ inset: thick, background: liveOk && metrics.color ? rgb(metrics.color) : 'var(--s3)' }}>
                {!liveOk && <span className="subtle" style={{ fontSize: 12 }}>Live colours show after saving (start screen sync)</span>}
              </div>
            </div>
          </div>

          <div className="stack">
            <div className="zone-edges">
              {EDGES.map((e) => (
                <div key={e} className="card card-pad">
                  <div className="lbl" style={{ marginBottom: 10 }}>{e} LEDs</div>
                  <Stepper value={draft[e]} onChange={(v) => set(e, v)} min={1} max={100} />
                </div>
              ))}
            </div>

            <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <span className="subtle" style={{ whiteSpace: 'nowrap' }}>Edge thickness</span>
                <input type="range" className="rng" style={{ flex: 1 }} min="0.05" max="0.5" step="0.01" value={draft.edge_fraction} onChange={(e) => setDraft((d) => ({ ...d, edge_fraction: +e.target.value }))} />
                <span className="mono" style={{ fontSize: 12, width: 40 }}>{thick}</span>
              </label>
              <div style={{ fontSize: 13.5, borderTop: '1px solid var(--hair)', paddingTop: 14 }}>Total <strong className="mono">{total}</strong> LEDs <span className="subtle">· corners shared</span></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
