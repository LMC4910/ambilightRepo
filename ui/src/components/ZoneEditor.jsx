import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { LayoutGrid, Plus, Minus, Save, RotateCcw } from 'lucide-react'

const EDGES = ['top', 'bottom', 'left', 'right']
const DEFAULT_ZONES = { top: 7, bottom: 7, left: 4, right: 4, edge_fraction: 0.25 }
const clampCount = (n) => Math.max(1, Math.min(100, Math.round(Number(n) || 1)))
const rgb = (c) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`
const NEUTRAL = 'rgba(99, 102, 241, 0.35)'

export default function ZoneEditor() {
  const { settings, fetchSettings, updateSettings, saving } = useStore()
  const metrics = useStore((s) => s.metrics)
  const [draft, setDraft] = useState(null)

  useEffect(() => { if (!settings) fetchSettings() }, [])
  useEffect(() => { if (settings?.zones) setDraft({ ...DEFAULT_ZONES, ...settings.zones }) }, [settings])

  if (!draft) return <section className="glass-panel rounded-3xl p-8 text-slate-400 animate-fade-up">Loading zones…</section>

  const applied = { ...DEFAULT_ZONES, ...(settings?.zones || {}) }
  const dirty = EDGES.some((e) => draft[e] !== applied[e]) || draft.edge_fraction !== applied.edge_fraction
  const total = EDGES.reduce((s, e) => s + draft[e], 0)
  const live = Array.isArray(metrics.zones) ? metrics.zones : []
  const appliedTotal = EDGES.reduce((s, e) => s + applied[e], 0)
  const liveOk = !dirty && live.length === appliedTotal
  const slices = (() => {
    if (!liveOk) return null
    let i = 0
    const take = (n) => { const s = live.slice(i, i + n); i += n; return s }
    return { top: take(draft.top), bottom: take(draft.bottom), left: take(draft.left), right: take(draft.right) }
  })()
  const colorFor = (edge, idx) => (slices ? rgb(slices[edge][idx]) : NEUTRAL)

  const setCount = (edge, val) => setDraft((d) => ({ ...d, [edge]: clampCount(val) }))
  const bump = (edge, delta) => setCount(edge, draft[edge] + delta)
  const reset = () => setDraft({ ...DEFAULT_ZONES, ...applied })
  const thickPct = `${Math.round(draft.edge_fraction * 100)}%`

  const band = (edge) =>
    Array.from({ length: draft[edge] }, (_, i) => (
      <div key={`${edge}${i}`} className="zone-block" style={{ flex: 1, margin: 1, borderRadius: 2, background: colorFor(edge, i) }} />
    ))

  return (
    <section className="glass-panel rounded-3xl p-8 flex flex-col gap-5 animate-fade-up">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2"><LayoutGrid className="w-5 h-5 text-indigo-400" /> Zone Layout</h3>
        <div className="flex gap-2">
          <button onClick={reset} disabled={!dirty} className="px-4 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-sm flex items-center gap-2 disabled:opacity-40"><RotateCcw className="w-4 h-4" /> Reset</button>
          <button onClick={() => updateSettings({ zones: draft })} disabled={!dirty || saving} className="btn-neon-blue px-5 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 disabled:opacity-40">
            <Save className="w-4 h-4" /> {saving ? 'Saving…' : dirty ? 'Save layout' : 'Saved'}
          </button>
        </div>
      </div>

      {/* Preview */}
      <div className="relative w-full rounded-2xl overflow-hidden border border-white/5" style={{ aspectRatio: '16 / 9', background: '#0a0c1a' }}>
        <div className="absolute left-0 right-0 top-0 flex" style={{ height: thickPct }}>{band('top')}</div>
        <div className="absolute left-0 right-0 bottom-0 flex" style={{ height: thickPct }}>{band('bottom')}</div>
        <div className="absolute left-0 flex flex-col" style={{ top: thickPct, bottom: thickPct, width: thickPct }}>{band('left')}</div>
        <div className="absolute right-0 flex flex-col" style={{ top: thickPct, bottom: thickPct, width: thickPct }}>{band('right')}</div>
        <div className="absolute flex items-center justify-center text-xs text-slate-500"
          style={{ inset: thickPct, borderRadius: 6, background: liveOk && metrics.color ? rgb(metrics.color) : 'rgba(255,255,255,0.04)' }}>
          {liveOk ? '' : 'Live colours show after saving (start screen sync)'}
        </div>
      </div>

      {/* Counts */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {EDGES.map((edge) => (
          <div key={edge} className="glass-panel rounded-2xl p-4">
            <div className="capitalize text-slate-400 text-xs mb-2">{edge} LEDs</div>
            <div className="flex items-center gap-2">
              <button onClick={() => bump(edge, -1)} className="px-2 py-1.5 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300"><Minus className="w-3.5 h-3.5" /></button>
              <input type="number" min="1" max="100" className="custom-input rounded-lg w-16 py-1.5 text-center text-sm font-mono" value={draft[edge]} onChange={(e) => setCount(edge, e.target.value)} />
              <button onClick={() => bump(edge, 1)} className="px-2 py-1.5 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300"><Plus className="w-3.5 h-3.5" /></button>
            </div>
          </div>
        ))}
      </div>

      {/* Thickness + total */}
      <div className="glass-panel rounded-2xl p-4 flex items-center gap-4 flex-wrap">
        <label className="flex items-center gap-3 flex-1 min-w-[220px]">
          <span className="text-slate-400 text-xs whitespace-nowrap">Edge thickness</span>
          <input type="range" min="0.05" max="0.5" step="0.05" className="flex-1" value={draft.edge_fraction} onChange={(e) => setDraft((d) => ({ ...d, edge_fraction: Number(e.target.value) }))} />
          <span className="font-mono text-xs text-slate-300">{thickPct}</span>
        </label>
        <div className="text-sm">Total: <strong>{total}</strong> LEDs <span className="text-slate-500">(corners shared)</span></div>
      </div>
    </section>
  )
}
