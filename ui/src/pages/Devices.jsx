import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { RefreshCw, Lightbulb, Plus, Wifi, Trash2, MonitorSmartphone } from 'lucide-react'

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

  // The multi-device "setup" list lives in config.devices.
  const managed = settings?.devices || []
  const monitorOptions = monitors.length ? monitors.map((m) => m.index) : [0, 1, 2, 3]

  const saveManaged = (list) => updateSettings({ devices: list })

  const addManaged = (d) => {
    if (managed.some((m) => m.ip === d.ip)) return
    saveManaged([...managed, {
      ip: d.ip, mac: d.mac || '', monitor_index: 0,
      led_count: d.led_count || 30, name: d.name || d.ip, enabled: true,
    }])
  }
  const updateManaged = (i, key, val) =>
    saveManaged(managed.map((m, idx) => (idx === i ? { ...m, [key]: val } : m)))
  const removeManaged = (i) => saveManaged(managed.filter((_, idx) => idx !== i))

  const handleTest = async (ip, port) => {
    setTestingIp(ip); await testDevice(ip, port); setTestingIp(null)
  }

  const handleManualAdd = async (e) => {
    e.preventDefault()
    if (!manualIp) return
    addManaged({ ip: manualIp, mac: manualMac, name: manualIp })
    setManualIp(''); setManualMac('')
  }

  return (
    <section className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Wifi size={20} /> Devices</h3>
        <button className="button" style={{ width: 'auto', padding: '0.5rem 1rem' }} disabled={scanning} onClick={scanDevices}>
          <RefreshCw size={16} className={scanning ? 'spin' : ''} /> {scanning ? 'Scanning…' : 'Scan Network'}
        </button>
      </div>

      {/* Discovered / cached devices */}
      <h4 style={{ margin: '0.25rem 0', color: 'var(--text-muted)' }}>Discovered</h4>
      {devices.length === 0 ? (
        <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          No devices cached. Click <strong>Scan Network</strong> to discover controllers.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {devices.map((d) => (
            <div key={d.mac || d.ip} className="metric-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600 }}>{d.ip}</div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                  MAC: {d.mac || 'unknown'} · {d.supports_addressable ? 'Addressable' : 'Single-RGB'}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.4rem' }}>
                <button className="button" style={{ width: 'auto', padding: '0.4rem 0.7rem', background: 'rgba(255,255,255,0.1)' }}
                  disabled={testingIp === d.ip} onClick={() => handleTest(d.ip, d.port)}>
                  <Lightbulb size={15} /> {testingIp === d.ip ? 'Testing…' : 'Test'}
                </button>
                <button className="button" style={{ width: 'auto', padding: '0.4rem 0.7rem' }}
                  disabled={managed.some((m) => m.ip === d.ip)} onClick={() => addManaged(d)}>
                  <Plus size={15} /> Add
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Active multi-device setup */}
      <h4 style={{ margin: '0.75rem 0 0.25rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <MonitorSmartphone size={16} /> Active setup ({managed.length})
      </h4>
      {managed.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          No devices added. Add one above (or below) to drive it. With none here, the single
          legacy device + primary monitor is used.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {managed.map((m, i) => (
            <div key={`${m.ip}-${i}`} className="metric-card" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <input type="checkbox" checked={m.enabled !== false} onChange={(e) => updateManaged(i, 'enabled', e.target.checked)} />
              </label>
              <span style={{ fontWeight: 600, minWidth: '120px' }}>{m.name || m.ip}</span>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Monitor
                <select className="input" style={{ width: 'auto' }} value={m.monitor_index ?? 0}
                  onChange={(e) => updateManaged(i, 'monitor_index', Number(e.target.value))}>
                  {monitorOptions.map((mi) => <option key={mi} value={mi}>{mi}</option>)}
                </select>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                LEDs
                <input className="input" type="number" min="1" style={{ width: '80px' }} value={m.led_count ?? 30}
                  onChange={(e) => updateManaged(i, 'led_count', Number(e.target.value) || 1)} />
              </label>
              <button className="button" style={{ width: 'auto', padding: '0.4rem 0.7rem', background: 'rgba(255,255,255,0.1)', marginLeft: 'auto' }}
                onClick={() => handleTest(m.ip, m.port)} title="Flash"><Lightbulb size={14} /></button>
              <button className="button" style={{ width: 'auto', padding: '0.4rem 0.7rem', background: 'rgba(239,68,68,0.2)', color: 'var(--accent-red)' }}
                onClick={() => removeManaged(i)} title="Remove"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleManualAdd} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.5rem' }}>
        <input className="input" placeholder="IP address (e.g. 192.168.1.29)" value={manualIp}
          onChange={(e) => setManualIp(e.target.value)} style={{ flex: 2 }} />
        <input className="input" placeholder="MAC (optional)" value={manualMac}
          onChange={(e) => setManualMac(e.target.value)} style={{ flex: 2 }} />
        <button type="submit" className="button" style={{ width: 'auto', padding: '0.5rem 1rem' }}><Plus size={16} /> Add</button>
      </form>
    </section>
  )
}
