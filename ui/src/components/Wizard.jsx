import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Icon, Stepper } from './shell'

const protoLabel = (p) => (p === 'wled' ? 'WLED' : 'MagicHome')
const EDGES = ['top', 'bottom', 'left', 'right']

const STEPS = [
  { key: 'welcome', title: 'Welcome to Ambi Light', icon: 'sparkles' },
  { key: 'monitor', title: 'Choose your display', icon: 'monitor' },
  { key: 'device', title: 'Connect your lights', icon: 'wifi' },
  { key: 'zones', title: 'Map the LEDs', icon: 'layout-grid' },
  { key: 'done', title: 'You’re all set', icon: 'party-popper' },
]

// 5-step onboarding journey wired to the real store/IPC (replaces the legacy
// Onboarding modal). Opens on first run and on demand from the sidebar.
export default function Wizard({ onClose }) {
  const { monitors, fetchMonitors, scanDevices, devices, scanning, settings, fetchSettings, updateSettings, setMode, toast } = useStore()
  const [step, setStep] = useState(0)
  const [monitor, setMonitor] = useState(0)
  const [picked, setPicked] = useState(null)
  const [ledCount, setLedCount] = useState(60)
  const [zones, setZones] = useState({ top: 18, bottom: 18, left: 10, right: 10 })

  useEffect(() => { fetchMonitors(); if (!settings) fetchSettings() }, [])

  // Reflect the monitor already saved in config (default to primary, else 0).
  useEffect(() => {
    const saved = settings?.capture?.monitor_index
    if (typeof saved === 'number') setMonitor(saved)
    else if (monitors.length) setMonitor((monitors.find((m) => m.primary) || monitors[0]).index)
  }, [settings, monitors])

  // Seed zone counts from the saved layout when available.
  useEffect(() => {
    if (settings?.zones) setZones((z) => ({ ...z, ...Object.fromEntries(EDGES.map((e) => [e, settings.zones[e] ?? z[e]])) }))
  }, [settings])

  // Kick off a real network scan the first time we hit the device step.
  useEffect(() => { if (STEPS[step].key === 'device' && devices.length === 0 && !scanning) scanDevices() }, [step])

  const cur = STEPS[step]
  const total = zones.top + zones.bottom + zones.left + zones.right
  const monId = monitors.find((m) => m.index === monitor)?.id || ''

  const finish = async () => {
    const managed = settings?.devices || []
    let nextDevices = managed
    if (picked && !managed.some((m) => m.ip === picked.ip)) {
      nextDevices = [...managed, {
        ip: picked.ip, mac: picked.mac || '', monitor_index: monitor, monitor_id: monId,
        led_count: ledCount, name: picked.ip, protocol: picked.protocol || 'magichome', enabled: true,
      }]
    }
    const patch = {
      capture: { monitor_index: monitor, monitor_id: monId },
      zones: { ...(settings?.zones || {}), ...zones },
    }
    if (picked) patch.device = { ip: picked.ip, protocol: picked.protocol || 'magichome', ...(picked.mac ? { mac: picked.mac } : {}) }
    if (nextDevices !== managed) patch.devices = nextDevices
    try { await updateSettings(patch) } catch (e) { console.error(e) }
    setMode('screen_sync')
    try { await window.api.onboarding.complete() } catch (e) { /* ignore */ }
    onClose()
    toast('Setup complete — enjoy the show ✨')
  }

  return (
    <div className="wiz-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="wiz" role="dialog" aria-modal="true">
        {/* rail */}
        <aside className="wiz-rail">
          <div className="wiz-brand"><div className="tb-logo" style={{ width: 30, height: 30 }}><Icon n="zap" /></div><b>Ambi Light</b></div>
          <div className="wiz-steps">
            {STEPS.map((s, i) => (
              <div key={s.key} className={`wiz-step ${i === step ? 'cur' : ''} ${i < step ? 'done' : ''}`}>
                <span className="ws-dot">{i < step ? <Icon n="check" /> : <Icon n={s.icon} />}</span>
                <span className="ws-label">{s.title}</span>
              </div>
            ))}
          </div>
          <div className="wiz-rail-foot subtle">Step {step + 1} of {STEPS.length}</div>
        </aside>

        {/* body */}
        <div className="wiz-body">
          <button className="wiz-x" onClick={onClose} aria-label="Close"><Icon n="x" /></button>
          <div className="wiz-content" key={step}>
            {cur.key === 'welcome' && (
              <div className="wiz-welcome">
                <div className="wiz-hero-ic"><Icon n="zap" /></div>
                <h2>Let’s light up your setup</h2>
                <p className="subtle">In four quick steps we’ll pick your screen, find your LED controller, and map the strip around your display. Takes about a minute.</p>
                <div className="wiz-feats">
                  {[['monitor', 'Screen sync', 'GPU-accelerated capture'], ['wifi', 'Auto-discovery', 'Finds MagicHome & WLED'], ['layout-grid', 'Zone mapping', 'Per-edge LED control']].map(([ic, t, d]) => (
                    <div key={t} className="wiz-feat"><div className="feat-ic"><Icon n={ic} /></div><div><div style={{ fontWeight: 600, fontSize: 13.5 }}>{t}</div><div className="subtle" style={{ fontSize: 12 }}>{d}</div></div></div>
                  ))}
                </div>
              </div>
            )}

            {cur.key === 'monitor' && (
              <div>
                <h2>{cur.title}</h2><p className="subtle wiz-sub">Ambi will mirror the colours from this display onto your lights.</p>
                {monitors.length === 0 ? <p className="subtle">Detecting displays…</p> : (
                  <div className="wiz-monitors">
                    {monitors.map((m) => (
                      <button key={m.index} className={`wiz-mon ${monitor === m.index ? 'sel' : ''}`} onClick={() => setMonitor(m.index)}>
                        <div className="wiz-mon-screen"><Icon n="monitor" /></div>
                        <div style={{ fontWeight: 600, fontSize: 13.5 }}>{m.name || `Display ${m.index + 1}`}</div>
                        <div className="subtle" style={{ fontSize: 11.5 }}>{m.width}×{m.height}{m.primary ? ' · primary' : ''}</div>
                        {monitor === m.index && <span className="wiz-check"><Icon n="check" /></span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {cur.key === 'device' && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div><h2>{cur.title}</h2><p className="subtle wiz-sub">Pick the controller driving your LED strip.</p></div>
                  <button className="btn btn-sm" onClick={scanDevices} disabled={scanning}><Icon n="refresh-cw" {...(scanning ? { className: 'spin' } : {})} />{scanning ? 'Scanning…' : 'Rescan'}</button>
                </div>
                <div className="wiz-devices">
                  {scanning && devices.length === 0 ? [0, 1].map((i) => (
                    <div key={i} className="wiz-dev"><div className="skel" style={{ width: 38, height: 38, borderRadius: 10 }} /><div style={{ flex: 1 }}><div className="skel" style={{ width: 120, height: 15, marginBottom: 7 }} /><div className="skel" style={{ width: 200, height: 10 }} /></div></div>
                  )) : devices.map((d) => (
                    <button key={d.mac || d.ip} className={`wiz-dev ${picked?.ip === d.ip ? 'sel' : ''}`} onClick={() => { setPicked(d); setLedCount(d.led_count || 60) }}>
                      <div className="feat-ic"><Icon n="lightbulb" /></div>
                      <div style={{ flex: 1, textAlign: 'left', minWidth: 0 }}>
                        <div className="mono" style={{ fontWeight: 500, fontSize: 14 }}>{d.ip}</div>
                        <div className="lbl" style={{ marginTop: 3 }}>{protoLabel(d.protocol)} · {d.led_count ?? '—'} LEDs · {d.mac || 'no mac'}</div>
                      </div>
                      {picked?.ip === d.ip && <span className="wiz-check" style={{ position: 'static' }}><Icon n="check" /></span>}
                    </button>
                  ))}
                  {!scanning && devices.length === 0 && <div className="hint">No devices found yet. Make sure the controller is powered and on the same Wi-Fi, then rescan — or add it manually later from Devices.</div>}
                </div>
                {picked && (
                  <div className="card card-pad" style={{ marginTop: 14, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span className="fr-l">LED count on this strip</span><Stepper value={ledCount} onChange={setLedCount} min={1} max={300} />
                  </div>
                )}
              </div>
            )}

            {cur.key === 'zones' && (
              <div>
                <h2>{cur.title}</h2><p className="subtle wiz-sub">How many LEDs run along each edge of your screen? You can fine-tune this later.</p>
                <div className="wiz-zone-wrap">
                  <div className="zone-screen" style={{ aspectRatio: '16/9', flex: 1 }}>
                    {EDGES.map((edge) => {
                      const vert = edge === 'left' || edge === 'right'
                      const pos = edge === 'top' ? { left: 0, right: 0, top: 0, height: '16%' }
                        : edge === 'bottom' ? { left: 0, right: 0, bottom: 0, height: '16%' }
                          : edge === 'left' ? { left: 0, top: '16%', bottom: '16%', width: '10%' }
                            : { right: 0, top: '16%', bottom: '16%', width: '10%' }
                      return <div key={edge} className="zb" style={{ ...pos, flexDirection: vert ? 'column' : 'row' }}>
                        {Array.from({ length: Math.min(zones[edge], 30) }).map((_, i) => <div key={i} style={{ flex: 1, margin: 1.5, borderRadius: 2, background: 'var(--accent-22)' }} />)}
                      </div>
                    })}
                    <div className="zone-core" style={{ inset: '16%', background: 'var(--s3)' }} />
                  </div>
                  <div className="wiz-zone-controls">
                    {EDGES.map((e) => (
                      <div key={e} className="field-row" style={{ padding: 0 }}><span className="fr-l" style={{ textTransform: 'capitalize' }}>{e}</span><Stepper value={zones[e]} onChange={(v) => setZones((z) => ({ ...z, [e]: v }))} min={1} max={100} /></div>
                    ))}
                    <div className="hairline" />
                    <div className="field-row" style={{ padding: 0 }}><span className="fr-l">Total LEDs</span><span className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{total}</span></div>
                  </div>
                </div>
              </div>
            )}

            {cur.key === 'done' && (
              <div className="wiz-welcome">
                <div className="wiz-hero-ic" style={{ background: 'var(--good-bg)', color: 'var(--good)', boxShadow: 'none' }}><Icon n="check" /></div>
                <h2>You’re all set</h2>
                <p className="subtle">Screen Sync is ready to roll. Here’s your configuration:</p>
                <div className="wiz-summary">
                  {[['monitor', 'Display', monitors.find((m) => m.index === monitor)?.name || `Display ${monitor + 1}`], ['wifi', 'Device', picked ? `${picked.ip} · ${protoLabel(picked.protocol)}` : 'Skipped'], ['layout-grid', 'LED layout', `${total} LEDs${picked ? ` · ${ledCount} on strip` : ''}`]].map(([ic, k, v]) => (
                    <div key={k} className="wiz-sum-row"><Icon n={ic} /><span className="fr-l" style={{ flex: 1 }}>{k}</span><span className="mono subtle" style={{ fontSize: 12.5 }}>{v}</span></div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* footer */}
          <div className="wiz-foot">
            <button className="btn btn-ghost" onClick={() => (step === 0 ? onClose() : setStep(step - 1))}>{step === 0 ? 'Cancel' : <><Icon n="arrow-left" />Back</>}</button>
            <div className="wiz-dots">{STEPS.map((_, i) => <span key={i} className={`wd ${i === step ? 'on' : ''}`} />)}</div>
            {step < STEPS.length - 1
              ? <button className="btn btn-primary" onClick={() => setStep(step + 1)}>{step === 2 && !picked ? 'Skip for now' : 'Continue'}<Icon n="arrow-right" /></button>
              : <button className="btn btn-primary" onClick={finish}><Icon n="check" />Finish setup</button>}
          </div>
        </div>
      </div>
    </div>
  )
}
