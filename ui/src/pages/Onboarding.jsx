import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Monitor, Wifi, Lightbulb, Layers, Power, ChevronRight, ChevronLeft, Check } from 'lucide-react'

const STEPS = ['Monitor', 'Device', 'Test', 'Profile', 'Auto-start']

export default function Onboarding({ onDone }) {
  const { updateSettings, devices, scanning, scanDevices, testDevice, profiles, fetchProfiles, applyProfile } = useStore()
  const [step, setStep] = useState(0)
  const [monitors, setMonitors] = useState([])
  const [monitorIdx, setMonitorIdx] = useState(0)
  const [selectedIp, setSelectedIp] = useState(null)
  const [tested, setTested] = useState(false)
  const [autostart, setAutostart] = useState(false)

  useEffect(() => {
    window.api.diagnostics.get().then((d) => setMonitors(d.monitors || [])).catch(() => {})
    fetchProfiles()
  }, [])

  const next = () => setStep((s) => Math.min(STEPS.length - 1, s + 1))
  const back = () => setStep((s) => Math.max(0, s - 1))

  const finish = async () => {
    try { await window.api.onboarding.complete() } catch (e) { /* ignore */ }
    onDone()
  }

  const chooseMonitor = async (i) => {
    setMonitorIdx(i)
    await updateSettings({ capture: { monitor_index: i } })
  }

  const chooseDevice = async (d) => {
    setSelectedIp(d.ip)
    await updateSettings({ device: { ip: d.ip, ...(d.mac ? { mac: d.mac } : {}) } })
  }

  const doTest = async () => {
    if (selectedIp) { await testDevice(selectedIp); setTested(true) }
  }

  const toggleAutostart = async () => {
    try {
      const r = autostart ? await window.api.autostart.disable() : await window.api.autostart.enable()
      setAutostart(!!r?.enabled)
    } catch (e) { console.error(e) }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div className="glass-panel" style={{ width: 'min(560px, 92vw)', maxHeight: '88vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0 }}>Welcome to Ambilight</h2>
          <button className="button" style={{ width: 'auto', padding: '0.3rem 0.7rem', background: 'rgba(255,255,255,0.1)' }} onClick={finish}>Skip</button>
        </div>

        {/* Stepper */}
        <div style={{ display: 'flex', gap: '0.4rem', margin: '1rem 0' }}>
          {STEPS.map((s, i) => (
            <div key={s} style={{ flex: 1, height: '4px', borderRadius: '2px', background: i <= step ? 'var(--accent-purple)' : 'rgba(255,255,255,0.15)' }} />
          ))}
        </div>

        <div style={{ minHeight: '220px' }}>
          {step === 0 && (
            <div>
              <h3 style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}><Monitor size={18} /> Choose a monitor</h3>
              <p style={{ color: 'var(--text-muted)' }}>Which display should drive the LEDs?</p>
              {monitors.length === 0 ? <p style={{ color: 'var(--text-muted)' }}>Detecting monitors…</p> :
                monitors.map((m, i) => (
                  <label key={i} className="metric-card" style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', cursor: 'pointer' }}>
                    <input type="radio" name="mon" checked={monitorIdx === i} onChange={() => chooseMonitor(i)} />
                    <span>Monitor {i} — {m.width}×{m.height}</span>
                  </label>
                ))}
            </div>
          )}

          {step === 1 && (
            <div>
              <h3 style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}><Wifi size={18} /> Find your controller</h3>
              <button className="button" style={{ width: 'auto', padding: '0.5rem 1rem' }} disabled={scanning} onClick={scanDevices}>
                {scanning ? 'Scanning…' : 'Scan network'}
              </button>
              <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {devices.map((d) => (
                  <label key={d.mac || d.ip} className="metric-card" style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', cursor: 'pointer' }}>
                    <input type="radio" name="dev" checked={selectedIp === d.ip} onChange={() => chooseDevice(d)} />
                    <span>{d.ip} <span style={{ color: 'var(--text-muted)' }}>({d.mac || 'no mac'})</span></span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {step === 2 && (
            <div>
              <h3 style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}><Lightbulb size={18} /> Test the strip</h3>
              <p style={{ color: 'var(--text-muted)' }}>Flash the LEDs white to confirm the right device.</p>
              <button className="button" style={{ width: 'auto', padding: '0.5rem 1rem' }} disabled={!selectedIp} onClick={doTest}>
                {tested ? 'Flash again' : 'Flash LEDs'}
              </button>
              {!selectedIp && <p style={{ color: 'var(--accent-red)' }}>Pick a device first (step 2).</p>}
            </div>
          )}

          {step === 3 && (
            <div>
              <h3 style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}><Layers size={18} /> Pick a profile</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {profiles.map((name) => (
                  <button key={name} className="button" style={{ background: 'rgba(255,255,255,0.1)', textTransform: 'capitalize' }} onClick={() => applyProfile(name)}>{name}</button>
                ))}
                {profiles.length === 0 && <p style={{ color: 'var(--text-muted)' }}>No profiles found.</p>}
              </div>
            </div>
          )}

          {step === 4 && (
            <div>
              <h3 style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}><Power size={18} /> Start on login</h3>
              <p style={{ color: 'var(--text-muted)' }}>Launch Ambilight automatically when you log in?</p>
              <label className="metric-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}>
                <span>Enable auto-start</span>
                <input type="checkbox" checked={autostart} onChange={toggleAutostart} />
              </label>
            </div>
          )}
        </div>

        {/* Nav */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem' }}>
          <button className="button" style={{ width: 'auto', padding: '0.5rem 1rem', background: 'rgba(255,255,255,0.1)' }} disabled={step === 0} onClick={back}>
            <ChevronLeft size={16} /> Back
          </button>
          {step < STEPS.length - 1 ? (
            <button className="button" style={{ width: 'auto', padding: '0.5rem 1rem' }} onClick={next}>Next <ChevronRight size={16} /></button>
          ) : (
            <button className="button" style={{ width: 'auto', padding: '0.5rem 1rem' }} onClick={finish}><Check size={16} /> Finish</button>
          )}
        </div>
      </div>
    </div>
  )
}
