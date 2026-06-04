import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { RefreshCw, Lightbulb, Plus, Wifi, Trash2, Check } from 'lucide-react'
import Toggle from '../components/Toggle'

function SectionHeader({ children }) {
  return (
    <div className="flex items-center gap-3 mb-6">
      <h3 className="text-xs font-bold text-slate-500 uppercase tracking-[0.2em]">{children}</h3>
      <div className="h-px flex-grow bg-white/5" />
    </div>
  )
}

export default function Devices() {
  const { devices, scanning, fetchDevices, scanDevices, testDevice, settings, updateSettings } = useStore()
  const [manualIp, setManualIp] = useState('')
  const [manualMac, setManualMac] = useState('')
  const [testingIp, setTestingIp] = useState(null)
  const [monitors, setMonitors] = useState([])

  useEffect(() => {
    fetchDevices()
    window.api.diagnostics?.get().then((d) => setMonitors(d.monitors || [])).catch(() => {})
  }, [])

  const managed = settings?.devices || []
  const monitorChoices = monitors.length
    ? monitors
    : [0, 1, 2, 3].map((i) => ({ index: i, name: `Display ${i + 1}`, width: 0, height: 0 }))
  const monitorLabel = (m) => `${m.index} — ${m.name}${m.width ? ` (${m.width}×${m.height})` : ''}${m.primary ? ' • primary' : ''}`
  const saveManaged = (list) => updateSettings({ devices: list })
  const addManaged = (d) => {
    if (managed.some((m) => m.ip === d.ip)) return
    saveManaged([...managed, { ip: d.ip, mac: d.mac || '', monitor_index: 0, led_count: d.led_count || 30, name: d.name || d.ip, enabled: true }])
  }
  const updateManaged = (i, key, val) => saveManaged(managed.map((m, idx) => (idx === i ? { ...m, [key]: val } : m)))
  const removeManaged = (i) => saveManaged(managed.filter((_, idx) => idx !== i))
  const handleTest = async (ip, port) => { setTestingIp(ip); await testDevice(ip, port); setTestingIp(null) }
  const handleManualAdd = async (e) => {
    e.preventDefault()
    if (!manualIp) return
    addManaged({ ip: manualIp, mac: manualMac, name: manualIp })
    setManualIp(''); setManualMac('')
  }

  return (
    <div className="animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap mb-10">
        <div className="flex items-center gap-4 min-w-0">
          <div className="p-2.5 rounded-xl bg-white/5 border border-white/10 text-indigo-400"><Wifi className="h-7 w-7" /></div>
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-white">Devices</h2>
            <p className="text-sm text-slate-500 mt-0.5">Manage and configure your Ambilight network</p>
          </div>
        </div>
        <button onClick={scanDevices} disabled={scanning}
          className="btn-neon-blue flex items-center gap-2.5 px-6 py-3 rounded-xl font-bold text-sm tracking-wide">
          <RefreshCw className={`h-5 w-5 ${scanning ? 'spin' : ''}`} /> {scanning ? 'SCANNING…' : 'SCAN NETWORK'}
        </button>
      </div>

      {/* Discovered */}
      <section className="mb-12">
        <SectionHeader>Discovered Devices</SectionHeader>
        {scanning && devices.length === 0 ? (
          <div className="glass-panel rounded-3xl p-10 relative overflow-hidden flex items-center justify-center min-h-[180px]">
            <div className="scan-line" />
            <span className="font-mono text-slate-500">Scanning subnet…</span>
          </div>
        ) : devices.length === 0 ? (
          <div className="glass-panel rounded-3xl p-10 text-center text-slate-500 min-h-[120px] flex items-center justify-center">
            No devices cached. Click <span className="text-slate-300 font-semibold mx-1">Scan Network</span> to discover controllers.
          </div>
        ) : (
          <div className="relative space-y-3">
            {scanning && <div className="scan-line" />}
            {devices.map((d) => (
              <div key={d.mac || d.ip} className="glass-panel rounded-2xl p-6 flex items-center justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <p className="text-2xl font-mono font-medium text-white tracking-tight">{d.ip}</p>
                  <p className="text-[11px] font-mono text-slate-500 uppercase tracking-wider mt-1">
                    MAC: <span className="text-slate-400">{d.mac || 'unknown'}</span> · {d.supports_addressable ? 'ADDRESSABLE' : 'SINGLE-RGB'}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <button onClick={() => handleTest(d.ip, d.port)} disabled={testingIp === d.ip}
                    className="px-6 py-2.5 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 font-semibold text-sm transition-all flex items-center gap-2 disabled:opacity-40">
                    <Lightbulb className="h-4 w-4 text-indigo-400" /> {testingIp === d.ip ? 'Testing…' : 'Test'}
                  </button>
                  <button onClick={() => addManaged(d)} disabled={managed.some((m) => m.ip === d.ip)}
                    className="btn-neon-blue px-8 py-2.5 rounded-xl font-bold text-sm tracking-wide disabled:opacity-40">+ ADD DEVICE</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Active setup */}
      <section className="mb-10">
        <SectionHeader>Active Setup ({managed.length})</SectionHeader>
        {managed.length === 0 ? (
          <div className="glass-panel rounded-3xl p-8 text-center text-slate-500">
            No devices added — add one from Discovered (or below). With none here, the single legacy device + primary monitor is used.
          </div>
        ) : (
          <div className="space-y-5">
            {managed.map((m, i) => (
              <div key={`${m.ip}-${i}`} className="glass-panel p-8 rounded-3xl relative overflow-hidden active-device-pulse">
                <div className="absolute -top-12 -right-12 w-56 h-56 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none" />
                <div className="flex flex-col items-center justify-center gap-6 relative z-10">
                  <div className="relative">
                    <div className={`absolute -inset-5 blur-2xl rounded-full ${m.enabled !== false ? 'bg-emerald-500/20 animate-pulse' : 'bg-slate-500/10'}`} />
                    <div className={`relative rounded-full p-2.5 shadow-lg ${m.enabled !== false ? 'bg-emerald-500 text-white shadow-emerald-500/40' : 'bg-slate-600 text-slate-300'}`}>
                      <Check className="h-6 w-6" />
                    </div>
                  </div>
                  <div className="text-center">
                    <h4 className="text-3xl font-mono font-bold text-white tracking-tight">{m.name || m.ip}</h4>
                    <p className="text-[10px] font-mono text-slate-500 uppercase tracking-[0.3em] mt-2">
                      {m.enabled !== false ? 'Active' : 'Disabled'} · Controller
                    </p>
                  </div>

                  <div className="w-full max-w-sm space-y-4 bg-white/5 p-6 rounded-2xl border border-white/5">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-slate-400 text-xs font-bold uppercase tracking-wider">Name</span>
                      <input type="text" className="custom-input rounded-xl text-sm w-48 py-2 px-3" placeholder={m.ip}
                        value={m.name || ''} onChange={(e) => updateManaged(i, 'name', e.target.value)} />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400 text-xs font-bold uppercase tracking-wider">Enabled</span>
                      <Toggle checked={m.enabled !== false} onChange={(v) => updateManaged(i, 'enabled', v)} />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400 text-xs font-bold uppercase tracking-wider">Target Monitor</span>
                      <select className="custom-input rounded-xl text-sm font-semibold w-56 py-2 px-3" value={m.monitor_index ?? 0}
                        onChange={(e) => updateManaged(i, 'monitor_index', Number(e.target.value))}>
                        {monitorChoices.map((mc) => <option key={mc.index} value={mc.index}>{monitorLabel(mc)}</option>)}
                      </select>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400 text-xs font-bold uppercase tracking-wider">LED Count</span>
                      <input type="number" min="1" className="custom-input rounded-xl text-sm font-bold w-24 py-2 text-center" value={m.led_count ?? 30}
                        onChange={(e) => updateManaged(i, 'led_count', Number(e.target.value) || 1)} />
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <button onClick={() => removeManaged(i)} title="Remove device" className="btn-neon-red p-4 rounded-2xl"><Trash2 className="h-5 w-5" /></button>
                    <button onClick={() => handleTest(m.ip, m.port)}
                      className="px-8 py-4 rounded-2xl bg-white/5 border border-white/10 text-slate-400 hover:text-white transition-all flex items-center gap-3">
                      <Lightbulb className="h-5 w-5" /><span className="font-bold text-sm uppercase tracking-wider">Test Hardware</span>
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Manual add */}
        <form onSubmit={handleManualAdd} className="mt-8 flex gap-4">
          <input className="flex-grow custom-input rounded-2xl px-6 py-4 text-sm font-mono placeholder:font-sans placeholder:italic"
            placeholder="IP address (e.g. 192.168.1.29)" value={manualIp} onChange={(e) => setManualIp(e.target.value)} />
          <input className="w-1/3 custom-input rounded-2xl px-6 py-4 text-sm font-mono placeholder:font-sans placeholder:italic"
            placeholder="MAC (optional)" value={manualMac} onChange={(e) => setManualMac(e.target.value)} />
          <button type="submit" className="btn-neon-blue px-10 py-4 rounded-2xl font-bold text-sm tracking-widest flex items-center gap-2"><Plus className="h-4 w-4" /> ADD</button>
        </form>
      </section>
    </div>
  )
}
