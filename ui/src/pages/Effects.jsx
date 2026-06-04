import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Wand2, Save, Play, Plus, Trash2, ArrowUp, ArrowDown } from 'lucide-react'

const hex = (c) => '#' + [c[0], c[1], c[2]].map((v) => Math.max(0, Math.min(255, v | 0)).toString(16).padStart(2, '0')).join('')
const fromHex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))

// Which controls each mode exposes.
const FIELDS = {
  static: ['color'], breathing: ['color', 'speed'], rainbow: ['speed'], candle: ['speed'],
  ocean: ['speed'], ambient: ['speed'], sunrise: ['duration'], sunset: ['duration'], custom: ['sequence', 'speed'],
}
const DEFAULTS = {
  static: { r: 255, g: 60, b: 0 }, breathing: { r: 0, g: 120, b: 255, speed: 1.0 },
  rainbow: { speed: 1.0 }, candle: { speed: 1.0 }, ocean: { speed: 1.0 }, ambient: { speed: 1.0 },
  sunrise: { duration: 300 }, sunset: { duration: 300 },
  custom: { colors: [[255, 0, 0], [0, 255, 0], [0, 0, 255]], speed: 1.0 },
}

function Speed({ value, onChange }) {
  return (
    <label className="flex items-center gap-3 text-sm">
      <span className="text-slate-400 w-16">Speed</span>
      <input type="range" min="0.1" max="3" step="0.1" className="flex-1" value={value ?? 1}
        onChange={(e) => onChange(Number(e.target.value))} />
      <span className="font-mono text-xs text-slate-300 w-8">{(value ?? 1).toFixed(1)}×</span>
    </label>
  )
}
function ColorPick({ rgb, onChange }) {
  return (
    <label className="flex items-center gap-3 text-sm">
      <span className="text-slate-400 w-16">Colour</span>
      <input type="color" className="h-8 w-14 bg-transparent rounded cursor-pointer"
        value={hex(rgb)} onChange={(e) => onChange(fromHex(e.target.value))} />
    </label>
  )
}
function Duration({ value, onChange }) {
  return (
    <label className="flex items-center gap-3 text-sm">
      <span className="text-slate-400 w-16">Duration</span>
      <input type="number" min="5" className="custom-input rounded-lg px-2 py-1.5 text-sm w-24 font-mono"
        value={value ?? 300} onChange={(e) => onChange(Number(e.target.value) || 5)} />
      <span className="text-slate-500 text-xs">sec</span>
    </label>
  )
}

export default function Effects() {
  const { settings, fetchSettings, updateSettings, saving, setMode } = useStore()
  const [draft, setDraft] = useState(null)

  useEffect(() => { if (!settings) fetchSettings() }, [])
  useEffect(() => {
    if (!settings) return
    const saved = settings.effects?.params || {}
    const merged = {}
    for (const m of Object.keys(FIELDS)) merged[m] = { ...DEFAULTS[m], ...(saved[m] || {}) }
    setDraft(merged)
  }, [settings])

  if (!draft) return <section className="glass-panel rounded-3xl p-8 text-slate-400 animate-fade-up">Loading effects…</section>

  const applied = settings?.effects?.params || {}
  const dirty = JSON.stringify(draft) !== JSON.stringify(
    Object.fromEntries(Object.keys(FIELDS).map((m) => [m, { ...DEFAULTS[m], ...(applied[m] || {}) }])))

  const set = (mode, patch) => setDraft((d) => ({ ...d, [mode]: { ...d[mode], ...patch } }))
  const save = () => updateSettings({ effects: { ...(settings.effects || {}), params: draft } })
  const apply = (mode) => setMode(mode, draft[mode])

  // Custom sequence helpers
  const cust = draft.custom
  const setColors = (colors) => set('custom', { colors })
  const addColor = () => setColors([...cust.colors, [255, 255, 255]])
  const removeColor = (i) => setColors(cust.colors.filter((_, idx) => idx !== i))
  const moveColor = (i, d) => {
    const j = i + d
    if (j < 0 || j >= cust.colors.length) return
    const next = cust.colors.slice()
    ;[next[i], next[j]] = [next[j], next[i]]
    setColors(next)
  }
  const setColorAt = (i, rgb) => setColors(cust.colors.map((c, idx) => (idx === i ? rgb : c)))

  return (
    <section className="glass-panel rounded-3xl p-8 flex flex-col gap-4 animate-fade-up">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2"><Wand2 className="w-5 h-5 text-indigo-400" /> Effects</h3>
        <button onClick={save} disabled={!dirty || saving} className="btn-neon-blue px-5 py-2.5 rounded-xl font-semibold text-sm flex items-center gap-2 disabled:opacity-40">
          <Save className="w-4 h-4" /> {saving ? 'Saving…' : dirty ? 'Save effects' : 'Saved'}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.keys(FIELDS).filter((m) => m !== 'custom').map((mode) => (
          <div key={mode} className="glass-panel rounded-2xl p-5 flex flex-col gap-3">
            <div className="flex justify-between items-center">
              <h4 className="text-sm font-semibold text-white capitalize">{mode}</h4>
              <button onClick={() => apply(mode)} className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-xs flex items-center gap-1"><Play className="w-3.5 h-3.5" /> Apply</button>
            </div>
            {FIELDS[mode].includes('color') && <ColorPick rgb={[draft[mode].r, draft[mode].g, draft[mode].b]} onChange={([r, g, b]) => set(mode, { r, g, b })} />}
            {FIELDS[mode].includes('speed') && <Speed value={draft[mode].speed} onChange={(v) => set(mode, { speed: v })} />}
            {FIELDS[mode].includes('duration') && <Duration value={draft[mode].duration} onChange={(v) => set(mode, { duration: v })} />}
          </div>
        ))}
      </div>

      {/* Custom sequence */}
      <div className="glass-panel rounded-2xl p-5 flex flex-col gap-3">
        <div className="flex justify-between items-center">
          <h4 className="text-sm font-semibold text-white">Custom sequence</h4>
          <button onClick={() => apply('custom')} className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-xs flex items-center gap-1"><Play className="w-3.5 h-3.5" /> Apply</button>
        </div>
        <p className="text-xs text-slate-500">The LEDs cycle through these colours in order.</p>
        <div className="flex flex-col gap-2">
          {cust.colors.map((c, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-slate-500 text-xs w-5">{i + 1}</span>
              <input type="color" className="h-8 w-12 bg-transparent rounded cursor-pointer" value={hex(c)}
                onChange={(e) => setColorAt(i, fromHex(e.target.value))} />
              <span className="font-mono text-xs text-slate-400 flex-1">{hex(c)}</span>
              <button onClick={() => moveColor(i, -1)} className="p-1.5 rounded bg-white/5 hover:bg-white/10 text-slate-300"><ArrowUp className="w-3.5 h-3.5" /></button>
              <button onClick={() => moveColor(i, 1)} className="p-1.5 rounded bg-white/5 hover:bg-white/10 text-slate-300"><ArrowDown className="w-3.5 h-3.5" /></button>
              <button onClick={() => removeColor(i)} className="btn-neon-red p-1.5 rounded"><Trash2 className="w-3.5 h-3.5" /></button>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <button onClick={addColor} className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-xs flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Add colour</button>
          <Speed value={cust.speed} onChange={(v) => set('custom', { speed: v })} />
        </div>
      </div>
    </section>
  )
}
