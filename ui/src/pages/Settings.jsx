import React, { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'
import { Icon, PageHead, Toggle } from '../components/shell'

// Section nav (id, label, icon). "general" is hand-built; the rest are rendered
// generically from whatever the backend config actually contains.
const SETTINGS_TABS = [
  ['general', 'General', 'sliders-horizontal'],
  ['capture', 'Capture', 'monitor'],
  ['device', 'Device', 'wifi'],
  ['zones', 'Zones', 'layout-grid'],
  ['color', 'Colour', 'palette'],
  ['smoothing', 'Smoothing', 'wind'],
  ['gpu', 'Performance', 'cpu'],
  ['logging', 'Logging', 'file-text'],
  ['mqtt', 'Integrations', 'plug'],
]

const ENUMS = {
  'capture.method': ['wgc', 'dxgi', 'mss', 'hook'],
  'capture.hdr.mode': ['auto', 'on', 'off'],
  'color.mode': ['average', 'edges', 'dominant', 'kmeans', 'saturation_weighted'],
  'gpu.prefer': ['cupy', 'opencv_cuda', 'torch', 'none'],
}
const HINTS = {
  'capture.hdr.mode': 'auto = tone-map only HDR displays; on = always; off = never',
  'color.vibrance': '1.0 = off; higher makes game colours more vivid',
  'mqtt.enabled': 'Connect to an MQTT broker (off by default)',
  'mqtt.broker': 'Broker host/IP; leave blank to disable',
  'mqtt.password': 'Stored in the OS keyring, never written to the config file',
  'mqtt.tls': 'Use TLS/SSL for the broker connection',
  'mqtt.base_topic': 'Topic prefix for state + commands',
  'mqtt.ha_discovery': 'Auto-create Home Assistant entities via MQTT discovery',
  'mqtt.device_id': 'Stable Home Assistant device id (blank = hostname)',
}

function SettingsField({ section, name, value, onChange }) {
  const key = `${section}.${name}`
  const label = name.replace(/_/g, ' ')
  const hint = HINTS[key]
  let control
  if (typeof value === 'boolean') {
    control = <Toggle checked={value} onChange={(v) => onChange(name, v)} />
  } else if (ENUMS[key]) {
    control = (
      <select className="field set-val" style={{ width: 150 }} value={value} onChange={(e) => onChange(name, e.target.value)}>
        {ENUMS[key].map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    )
  } else if (typeof value === 'number') {
    control = <input className="field set-val mono" style={{ width: 120 }} type="number" step="any" value={value}
      onChange={(e) => onChange(name, e.target.value === '' ? '' : Number(e.target.value))} />
  } else if (name === 'password') {
    control = <input className="field set-val mono" style={{ width: 200 }} type="password" autoComplete="new-password"
      placeholder="•••• (stored)" value={value ?? ''} onChange={(e) => onChange(name, e.target.value)} />
  } else {
    control = <input className="field set-val mono" style={{ width: 200 }} type="text" value={value ?? ''} onChange={(e) => onChange(name, e.target.value)} />
  }
  return (
    <div className="set-row">
      <div className="set-row-l"><span style={{ textTransform: 'capitalize' }}>{label}</span>{hint && <small>{hint}</small>}</div>
      <div className="set-row-r">{control}</div>
    </div>
  )
}

function SectionCard({ id, title, icon, sec, onField }) {
  const hasEnabled = typeof sec.enabled === 'boolean'
  const dimmed = hasEnabled && !sec.enabled
  return (
    <div className="set-card-wrap" id={`setsec-${id}`}>
      <div className="card set-card">
        <div className="set-card-h">
          <h3><Icon n={icon} />{title}</h3>
          {hasEnabled && <Toggle checked={sec.enabled} onChange={(v) => onField([id, 'enabled'], v)} />}
        </div>
        <div className="set-card-body" style={dimmed ? { opacity: 0.42, pointerEvents: 'none' } : {}}>
          {Object.entries(sec).map(([name, value]) => {
            if (name === 'enabled' && hasEnabled) return null
            if (value && typeof value === 'object' && !Array.isArray(value)) {
              return (
                <div key={name} className="set-sub">
                  <div className="set-sub-h">{name.replace(/_/g, ' ')}</div>
                  {Object.entries(value).map(([sub, sv]) => (
                    <SettingsField key={sub} section={`${id}.${name}`} name={sub} value={sv} onChange={(n, v) => onField([id, name, n], v)} />
                  ))}
                </div>
              )
            }
            return <SettingsField key={name} section={id} name={name} value={value} onChange={(n, v) => onField([id, n], v)} />
          })}
        </div>
      </div>
    </div>
  )
}

export default function Settings() {
  const { settings, fetchSettings, updateSettings, saving, toast } = useStore()
  const [draft, setDraft] = useState(null)
  const [autostart, setAutostart] = useState(false)
  const [update, setUpdate] = useState({ state: 'idle' })
  const [active, setActive] = useState('general')
  const scrollRef = useRef(null)

  useEffect(() => { if (!settings) fetchSettings() }, [])
  useEffect(() => { if (settings) setDraft(structuredClone(settings)) }, [settings])
  useEffect(() => { window.api.autostart?.get().then((r) => setAutostart(!!r?.enabled)).catch(() => {}) }, [])
  useEffect(() => {
    if (!window.api?.updater) return undefined
    window.api.updater.status().then(setUpdate).catch(() => {})
    return window.api.updater.onStatus(setUpdate)
  }, [])

  const updateLabel = {
    idle: 'Automatic · up to date', checking: 'Checking…', available: 'Update available',
    downloading: `Downloading… ${update.percent ?? 0}%`, downloaded: 'Update ready', error: 'Check failed',
  }[update.state] || 'Automatic · up to date'

  const toggleAutostart = async () => {
    try {
      const r = autostart ? await window.api.autostart.disable() : await window.api.autostart.enable()
      setAutostart(!!r?.enabled)
    } catch (e) { console.error(e) }
  }

  if (!draft) {
    return <div className="main"><PageHead crumb="Configuration" title="Settings" sub="Capture, colour science & system" /><div className="content"><div className="card card-pad subtle">Loading settings…</div></div></div>
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(settings)
  // Only show tabs whose card actually renders (general + existing config sections).
  const tabs = SETTINGS_TABS.filter(([id]) => id === 'general' || draft[id])
  const changePath = (path, val) => setDraft((d) => {
    const next = structuredClone(d)
    let o = next
    for (let i = 0; i < path.length - 1; i++) o = o[path[i]]
    o[path[path.length - 1]] = val
    return next
  })

  const offsetOf = (el) => {
    const sc = scrollRef.current
    return el.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop
  }
  const jump = (id) => {
    const el = document.getElementById(`setsec-${id}`), sc = scrollRef.current
    setActive(id)
    if (!el || !sc) return
    const target = Math.max(0, offsetOf(el) - 8)
    const start = sc.scrollTop, dist = target - start, dur = 360
    const ease = (p) => 1 - Math.pow(1 - p, 3)
    // Use the rAF timestamp as the time base (no impure performance.now()).
    let t0 = null
    const stepFn = (now) => {
      if (t0 === null) t0 = now
      const p = Math.min(1, (now - t0) / dur)
      sc.scrollTop = start + dist * ease(p)
      if (p < 1) requestAnimationFrame(stepFn)
    }
    requestAnimationFrame(stepFn)
  }
  const onScroll = () => {
    const sc = scrollRef.current; if (!sc) return
    const y = sc.scrollTop + 70; let cur = tabs[0][0]
    for (const [id] of tabs) { const el = document.getElementById(`setsec-${id}`); if (el && offsetOf(el) <= y) cur = id }
    setActive(cur)
  }

  return (
    <div className="main">
      <PageHead crumb="Configuration" title="Settings" sub="Capture, colour science & system">
        <button className="btn btn-sm" onClick={() => { setDraft(structuredClone(settings)); toast('Reverted unsaved changes') }} disabled={!dirty}><Icon n="rotate-ccw" />Revert</button>
        <button className={`btn ${dirty ? 'btn-primary' : ''}`} disabled={!dirty || saving} onClick={() => { updateSettings(draft); toast('Settings saved') }}><Icon n={dirty ? 'save' : 'check'} />{saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}</button>
      </PageHead>

      <div className="content settings-content page-enter" ref={scrollRef} onScroll={onScroll}>
        <div className="settings-nav">
          {tabs.map(([id, label, icon]) => (
            <button key={id} className={`set-tab ${active === id ? 'active' : ''}`} onClick={() => jump(id)}><Icon n={icon} />{label}</button>
          ))}
        </div>

        <div className="settings-grid">
          {/* General — autostart + updates */}
          <div className="set-card-wrap" id="setsec-general">
            <div className="card set-card">
              <div className="set-card-h"><h3><Icon n="sliders-horizontal" />General</h3></div>
              <div className="set-card-body">
                <div className="set-row">
                  <div className="set-row-l"><span>Start on login</span><small>Launch Ambi Light automatically when you log in</small></div>
                  <div className="set-row-r"><Toggle checked={autostart} onChange={toggleAutostart} /></div>
                </div>
                <div className="hairline" />
                <div className="set-row">
                  <div className="set-row-l"><span>Software updates</span><small>{updateLabel}</small></div>
                  <div className="set-row-r">
                    {update.state === 'downloaded'
                      ? <button className="btn btn-sm btn-primary" onClick={() => window.api.updater.install()}>Restart to update</button>
                      : <button className="btn btn-sm" onClick={() => window.api.updater.check()} disabled={update.state === 'checking' || update.state === 'downloading'}><Icon n="refresh-cw" {...(update.state === 'checking' ? { className: 'spin' } : {})} />Check for updates</button>}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Schema-driven sections */}
          {SETTINGS_TABS.filter(([id]) => id !== 'general' && draft[id]).map(([id, title, icon]) => (
            <SectionCard key={id} id={id} title={title} icon={icon} sec={draft[id]} onField={changePath} />
          ))}
        </div>
      </div>
    </div>
  )
}
