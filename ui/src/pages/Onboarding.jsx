import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Monitor, Wifi, Lightbulb, Layers, Power, ChevronRight, ChevronLeft, Check } from 'lucide-react'
import Toggle from '../components/Toggle'

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
  const finish = async () => { try { await window.api.onboarding.complete() } catch (e) { /* ignore */ } onDone() }
  const chooseMonitor = async (i) => { setMonitorIdx(i); await updateSettings({ capture: { monitor_index: i } }) }
  const chooseDevice = async (d) => { setSelectedIp(d.ip); await updateSettings({ device: { ip: d.ip, ...(d.mac ? { mac: d.mac } : {}) } }) }
  const doTest = async () => { if (selectedIp) { await testDevice(selectedIp); setTested(true) } }
  const toggleAutostart = async () => {
    try { const r = autostart ? await window.api.autostart.disable() : await window.api.autostart.enable(); setAutostart(!!r?.enabled) } catch (e) { console.error(e) }
  }

  const radioCard = 'glass-panel rounded-xl p-3 flex items-center gap-3 cursor-pointer hover:bg-white/5 transition-colors'

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 backdrop-blur-md">
      <div className="glass-panel rounded-3xl p-8 w-[min(560px,92vw)] max-h-[88vh] overflow-y-auto animate-fade-up">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-bold text-white">Welcome to Ambient</h2>
          <button onClick={finish} className="px-3 py-1.5 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-sm">Skip</button>
        </div>

        <div className="flex gap-1.5 my-5">
          {STEPS.map((s, i) => (
            <div key={s} className="flex-1 h-1 rounded-full transition-all" style={{ background: i <= step ? 'linear-gradient(90deg,#6366f1,#a855f7)' : 'rgba(255,255,255,0.12)' }} />
          ))}
        </div>

        <div className="min-h-[220px]">
          {step === 0 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-white font-semibold"><Monitor className="w-5 h-5 text-indigo-400" /> Choose a monitor</h3>
              <p className="text-slate-400 text-sm">Which display should drive the LEDs?</p>
              {monitors.length === 0 ? <p className="text-slate-500 text-sm">Detecting monitors…</p> :
                monitors.map((m, i) => (
                  <label key={i} className={radioCard}>
                    <input type="radio" name="mon" checked={monitorIdx === i} onChange={() => chooseMonitor(i)} className="text-indigo-500" />
                    <span className="text-sm">{i} — {m.name || `Display ${i + 1}`} <span className="font-mono text-slate-400">({m.width}×{m.height}{m.primary ? ', primary' : ''})</span></span>
                  </label>
                ))}
            </div>
          )}
          {step === 1 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-white font-semibold"><Wifi className="w-5 h-5 text-indigo-400" /> Find your controller</h3>
              <button onClick={scanDevices} disabled={scanning} className="btn-neon-blue px-4 py-2 rounded-xl text-sm font-semibold disabled:opacity-40">{scanning ? 'Scanning…' : 'Scan network'}</button>
              <div className="flex flex-col gap-2">
                {devices.map((d) => (
                  <label key={d.mac || d.ip} className={radioCard}>
                    <input type="radio" name="dev" checked={selectedIp === d.ip} onChange={() => chooseDevice(d)} className="text-indigo-500" />
                    <span className="text-sm font-mono">{d.ip} <span className="text-slate-500">({d.mac || 'no mac'})</span></span>
                  </label>
                ))}
              </div>
            </div>
          )}
          {step === 2 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-white font-semibold"><Lightbulb className="w-5 h-5 text-indigo-400" /> Test the strip</h3>
              <p className="text-slate-400 text-sm">Flash the LEDs white to confirm the right device.</p>
              <button onClick={doTest} disabled={!selectedIp} className="btn-neon-blue px-4 py-2 rounded-xl text-sm font-semibold disabled:opacity-40">{tested ? 'Flash again' : 'Flash LEDs'}</button>
              {!selectedIp && <p className="text-red-400 text-sm">Pick a device first (step 2).</p>}
            </div>
          )}
          {step === 3 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-white font-semibold"><Layers className="w-5 h-5 text-indigo-400" /> Pick a profile</h3>
              <div className="flex flex-col gap-2">
                {profiles.map((name) => (
                  <button key={name} onClick={() => applyProfile(name)} className="px-4 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-200 text-sm capitalize text-left">{name}</button>
                ))}
                {profiles.length === 0 && <p className="text-slate-500 text-sm">No profiles found.</p>}
              </div>
            </div>
          )}
          {step === 4 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-white font-semibold"><Power className="w-5 h-5 text-indigo-400" /> Start on login</h3>
              <p className="text-slate-400 text-sm">Launch Ambient automatically when you log in?</p>
              <div className="glass-panel rounded-xl p-3 flex justify-between items-center">
                <span className="text-sm">Enable auto-start</span>
                <Toggle checked={autostart} onChange={toggleAutostart} />
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-between mt-5">
          <button onClick={back} disabled={step === 0} className="px-4 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-sm flex items-center gap-1 disabled:opacity-40"><ChevronLeft className="w-4 h-4" /> Back</button>
          {step < STEPS.length - 1 ? (
            <button onClick={next} className="btn-neon-blue px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-1">Next <ChevronRight className="w-4 h-4" /></button>
          ) : (
            <button onClick={finish} className="btn-neon-blue px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-1"><Check className="w-4 h-4" /> Finish</button>
          )}
        </div>
      </div>
    </div>
  )
}
