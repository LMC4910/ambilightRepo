import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Save, Sliders, RefreshCw } from 'lucide-react'

const SECTIONS = [
  ['capture', 'Capture'], ['device', 'Device'], ['zones', 'Zones'], ['color', 'Color'],
  ['smoothing', 'Smoothing'], ['gpu', 'GPU'], ['logging', 'Logging'],
]
const ENUMS = {
  'capture.method': ['wgc', 'dxgi', 'mss'],
  'color.mode': ['average', 'edges', 'dominant', 'kmeans', 'saturation_weighted'],
  'gpu.prefer': ['cupy', 'opencv_cuda', 'torch', 'none'],
}

function Field({ section, name, value, onChange }) {
  const key = `${section}.${name}`
  const label = name.replace(/_/g, ' ')
  let control
  if (typeof value === 'boolean') {
    control = <input type="checkbox" checked={value} onChange={(e) => onChange(name, e.target.checked)} className="rounded text-indigo-500" />
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
  return (
    <label className="flex justify-between items-center gap-4 py-1.5">
      <span className="text-slate-400 capitalize text-sm">{label}</span>
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
  const change = (section, name, val) => setDraft((d) => ({ ...d, [section]: { ...d[section], [name]: val } }))

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
        <input type="checkbox" checked={autostart} onChange={toggleAutostart} className="rounded text-indigo-500" />
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
            <Field key={name} section={section} name={name} value={value} onChange={(n, v) => change(section, n, v)} />
          ))}
        </div>
      ))}
    </section>
  )
}
