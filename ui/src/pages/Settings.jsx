import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Save, Sliders, RefreshCw } from 'lucide-react'

// Friendly section ordering + labels.
const SECTIONS = [
  ['capture', 'Capture'],
  ['device', 'Device'],
  ['zones', 'Zones'],
  ['color', 'Color'],
  ['smoothing', 'Smoothing'],
  ['gpu', 'GPU'],
  ['logging', 'Logging'],
]

// Known enum fields rendered as dropdowns.
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
    control = <input type="checkbox" checked={value} onChange={(e) => onChange(name, e.target.checked)} />
  } else if (ENUMS[key]) {
    control = (
      <select className="input" value={value} onChange={(e) => onChange(name, e.target.value)}>
        {ENUMS[key].map((opt) => <option key={opt} value={opt}>{opt}</option>)}
      </select>
    )
  } else if (typeof value === 'number') {
    control = <input className="input" type="number" step="any" value={value}
      onChange={(e) => onChange(name, e.target.value === '' ? '' : Number(e.target.value))} />
  } else {
    control = <input className="input" type="text" value={value ?? ''} onChange={(e) => onChange(name, e.target.value)} />
  }

  return (
    <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', padding: '0.35rem 0' }}>
      <span style={{ color: 'var(--text-muted)', textTransform: 'capitalize', fontSize: '0.85rem' }}>{label}</span>
      <span style={{ minWidth: '180px', textAlign: 'right' }}>{control}</span>
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
  useEffect(() => {
    window.api.autostart?.get().then((r) => setAutostart(!!r?.enabled)).catch(() => {})
  }, [])
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

  if (!draft) {
    return <section className="glass-panel"><p style={{ color: 'var(--text-muted)' }}>Loading settings…</p></section>
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(settings)

  const change = (section, name, val) => {
    setDraft((d) => ({ ...d, [section]: { ...d[section], [name]: val } }))
  }

  const handleSave = async () => {
    await updateSettings(draft)
  }

  return (
    <section className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Sliders size={20} /> Settings</h3>
        <button className="button" style={{ width: 'auto', padding: '0.5rem 1rem' }} disabled={!dirty || saving} onClick={handleSave}>
          <Save size={16} /> {saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
        </button>
      </div>

      <label className="metric-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Start on login</span>
        <input type="checkbox" checked={autostart} onChange={toggleAutostart} />
      </label>

      <div className="metric-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Software updates — {updateLabel}</span>
        {update.state === 'downloaded' ? (
          <button className="button" style={{ width: 'auto', padding: '0.4rem 0.8rem' }}
            onClick={() => window.api.updater.install()}>Restart to update</button>
        ) : (
          <button className="button" style={{ width: 'auto', padding: '0.4rem 0.8rem', background: 'rgba(255,255,255,0.1)' }}
            disabled={update.state === 'checking' || update.state === 'downloading'}
            onClick={() => window.api.updater.check()}>
            <RefreshCw size={14} className={update.state === 'checking' ? 'spin' : ''} /> Check for updates
          </button>
        )}
      </div>

      {SECTIONS.filter(([s]) => draft[s]).map(([section, title]) => (
        <div key={section} className="metric-card">
          <h4 style={{ margin: '0 0 0.5rem' }}>{title}</h4>
          {Object.entries(draft[section]).map(([name, value]) => (
            <Field key={name} section={section} name={name} value={value}
              onChange={(n, v) => change(section, n, v)} />
          ))}
        </div>
      ))}
    </section>
  )
}
