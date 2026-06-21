import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Save, Sliders, RefreshCw } from 'lucide-react'
import Toggle from '../components/Toggle'

const SECTIONS = [
  ['capture', 'Capture'], ['device', 'Device'], ['zones', 'Zones'], ['color', 'Color'],
  ['smoothing', 'Smoothing'], ['gpu', 'GPU'], ['logging', 'Logging'],
]
const ENUMS = {
  'capture.method': ['wgc', 'dxgi', 'mss'],
  'capture.hdr.mode': ['auto', 'on', 'off'],
  'color.mode': ['average', 'edges', 'dominant', 'kmeans', 'saturation_weighted'],
  'gpu.prefer': ['cupy', 'opencv_cuda', 'torch', 'none'],
}

// Short hints for the non-obvious game-quality knobs.
const HINTS = {
  'capture.hdr.mode': 'auto = tone-map only HDR displays; on = always; off = never',
  'color.vibrance': '1.0 = off; higher makes game colors more vivid',
}

function Field({ section, name, value, onChange }) {
  const key = `${section}.${name}`
  const label = name.replace(/_/g, ' ')
  let control
  if (typeof value === 'boolean') {
    control = <Toggle checked={value} onChange={(v) => onChange(name, v)} />
  } else if (ENUMS[key]) {
    control = (
      <select className="custom-input rounded-lg px-2 py-1.5 text-sm" value={value} onChange={(e) => onChange(name, e.target.value)}>
        {ENUMS[key].map((opt) => <option key={opt} value={opt}>{opt}</option>)}
      </select>
    )
  } else if (typeof value === 'number') {
    control = <input className="custom-input rounded-lg px-2 py-1.5 text-sm w-28 text-right font-mono" type="number" step="any" value={value}
      onChange={(e) => onChange(name, e.target.value === '' ? '' : Number(e.target.value))} />
  } else {
    control = <input className="custom-input rounded-lg px-2 py-1.5 text-sm w-44" type="text" value={value ?? ''} onChange={(e) => onChange(name, e.target.value)} />
  }
  const hint = HINTS[key]
  return (
    <label className="flex justify-between items-center gap-4 py-1.5">
      <span className="text-slate-400 capitalize text-sm">
        {label}
        {hint && <span className="block text-[10px] text-slate-500 normal-case">{hint}</span>}
      </span>
      <span className="min-w-[120px] text-right">{control}</span>
    </label>
  )
}

export default function Settings() {
  const { settings, fetchSettings, updateSettings, saving } = useStore()
  const [draft, setDraft] = useState(null)
  const [autostart, setAutostart] = useState(false)
  const [update, setUpdate] = useState({ state: 'idle' })

  useEffect(() => { if (!settings) fetchSettings() }, [])
  useEffect(() => { if (settings) setDraft(structuredClone(settings)) }, [settings])
  useEffect(() => { window.api.autostart?.get().then((r) => setAutostart(!!r?.enabled)).catch(() => {}) }, [])
  useEffect(() => {
    if (!window.api?.updater) return undefined
    window.api.updater.status().then(setUpdate).catch(() => {})
    return window.api.updater.onStatus(setUpdate)
  }, [])

  const updateLabel = {
    idle: 'Up to date', checking: 'Checking…', available: 'Update available',
    downloading: `Downloading… ${update.percent ?? 0}%`, downloaded: 'Update ready', error: 'Check failed',
  }[update.state] || 'Up to date'

  const toggleAutostart = async () => {
    try {
      const r = autostart ? await window.api.autostart.disable() : await window.api.autostart.enable()
      setAutostart(!!r?.enabled)
    } catch (e) { console.error(e) }
  }

  if (!draft) return <section className="glass-panel rounded-3xl p-8 text-slate-400 animate-fade-up">Loading settings…</section>

  const dirty = JSON.stringify(draft) !== JSON.stringify(settings)
  // Immutable set at an arbitrary depth so nested config (e.g. capture.hdr.mode)
  // edits without clobbering siblings.
  const changePath = (path, val) => setDraft((d) => {
    const next = structuredClone(d)
    let o = next
    for (let i = 0; i < path.length - 1; i++) o = o[path[i]]
    o[path[path.length - 1]] = val
    return next
  })

  return (
    <section className="glass-panel rounded-3xl p-8 flex flex-col gap-4 animate-fade-up">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2"><Sliders className="w-5 h-5 text-indigo-400" /> Settings</h3>
        <button onClick={() => updateSettings(draft)} disabled={!dirty || saving}
          className="btn-neon-blue px-5 py-2.5 rounded-xl font-semibold text-sm flex items-center gap-2 disabled:opacity-40">
          <Save className="w-4 h-4" /> {saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
        </button>
      </div>

      <div className="glass-panel rounded-2xl p-4 flex justify-between items-center">
        <span className="text-slate-400 text-sm">Start on login</span>
        <Toggle checked={autostart} onChange={toggleAutostart} />
      </div>

      <div className="glass-panel rounded-2xl p-4 flex justify-between items-center">
        <span className="text-slate-400 text-sm">Software updates — {updateLabel}</span>
        {update.state === 'downloaded' ? (
          <button onClick={() => window.api.updater.install()} className="btn-neon-blue px-4 py-2 rounded-xl text-sm font-semibold">Restart to update</button>
        ) : (
          <button onClick={() => window.api.updater.check()} disabled={update.state === 'checking' || update.state === 'downloading'}
            className="px-4 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-sm flex items-center gap-2 disabled:opacity-40">
            <RefreshCw className={`w-4 h-4 ${update.state === 'checking' ? 'spin' : ''}`} /> Check for updates
          </button>
        )}
      </div>

      {SECTIONS.filter(([s]) => draft[s]).map(([section, title]) => (
        <div key={section} className="glass-panel rounded-2xl p-5">
          <h4 className="text-sm font-semibold text-white mb-2">{title}</h4>
          {Object.entries(draft[section]).map(([name, value]) => (
            (value && typeof value === 'object' && !Array.isArray(value)) ? (
              <div key={name} className="mt-2 pl-3 border-l border-white/10">
                <h5 className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider mb-1">{name.replace(/_/g, ' ')}</h5>
                {Object.entries(value).map(([sub, sv]) => (
                  <Field key={sub} section={`${section}.${name}`} name={sub} value={sv}
                    onChange={(n, v) => changePath([section, name, n], v)} />
                ))}
              </div>
            ) : (
              <Field key={name} section={section} name={name} value={value}
                onChange={(n, v) => changePath([section, n], v)} />
            )
          ))}
        </div>
      ))}
    </section>
  )
}
