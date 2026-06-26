import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Icon, PageHead, Section, Empty, Toggle, Stepper } from '../components/shell'

const protoLabel = (p) => (p === 'wled' ? 'WLED' : 'MagicHome')

export default function Devices() {
  const { devices, scanning, fetchDevices, scanDevices, testDevice, settings, updateSettings, monitors, fetchMonitors, toast } = useStore()
  const [manualIp, setManualIp] = useState('')
  const [manualMac, setManualMac] = useState('')
  const [manualProto, setManualProto] = useState('magichome')
  const [testingIp, setTestingIp] = useState(null)
  const [err, setErr] = useState(false)

  useEffect(() => { fetchDevices(); fetchMonitors() }, [])

  const managed = settings?.devices || []
  const monitorChoices = monitors.length
    ? monitors
    : [0, 1, 2, 3].map((i) => ({ index: i, name: `Display ${i + 1}`, width: 0, height: 0 }))
  const monitorLabel = (mc) => `${mc.index} — ${mc.name || `Display ${mc.index + 1}`}`

  const saveManaged = (list) => updateSettings({ devices: list })
  const addManaged = (d) => {
    if (managed.some((mm) => mm.ip === d.ip)) return
    saveManaged([...managed, {
      ip: d.ip, mac: d.mac || '', monitor_index: 0, monitor_id: '',
      led_count: d.led_count || 30, name: d.name || d.ip,
      protocol: d.protocol || 'magichome', enabled: true,
    }])
    toast('Device added')
  }
  const updateManaged = (i, key, val) => saveManaged(managed.map((mm, idx) => (idx === i ? { ...mm, [key]: val } : mm)))
  const updateManagedMonitor = (i, index) => {
    const mc = monitorChoices.find((c) => c.index === index)
    saveManaged(managed.map((mm, idx) => (idx === i ? { ...mm, monitor_index: index, monitor_id: mc?.id || '' } : mm)))
  }
  const removeManaged = (i) => { saveManaged(managed.filter((_, idx) => idx !== i)); toast('Device removed') }
  const handleTest = async (ip, port, protocol) => { setTestingIp(ip); await testDevice(ip, port, protocol); setTestingIp(null) }
  const addManual = (e) => {
    e.preventDefault()
    if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(manualIp)) { setErr(true); return }
    setErr(false)
    addManaged({ ip: manualIp, mac: manualMac, name: manualIp, protocol: manualProto })
    setManualIp(''); setManualMac(''); setManualProto('magichome')
  }

  return (
    <div className="main">
      <PageHead crumb="Network" title="Devices" sub="Discover and configure your LED controllers">
        <button className="btn btn-primary" onClick={scanDevices} disabled={scanning}>
          <Icon n="refresh-cw" {...(scanning ? { className: 'spin' } : {})} />{scanning ? 'Scanning…' : 'Scan network'}
        </button>
      </PageHead>

      <div className="content content-narrow page-enter">
        <Section title="Discovered" />
        {scanning && devices.length === 0 ? (
          <div className="stack">{[0, 1].map((i) => (
            <div key={i} className="card card-pad" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}><div className="skel" style={{ width: 150, height: 18 }} /><div className="skel" style={{ width: 220, height: 11 }} /></div>
              <div className="skel" style={{ width: 120, height: 34, borderRadius: 10 }} />
            </div>
          ))}</div>
        ) : devices.length === 0 ? (
          <div className="card"><Empty icon="radar" title="No devices discovered yet">Run a network scan to find MagicHome and WLED controllers on your subnet.</Empty></div>
        ) : (
          <div className="tile-grid wide">
            {devices.map((d) => {
              const added = managed.some((mm) => mm.ip === d.ip)
              return (
                <div key={d.mac || d.ip} className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div style={{ minWidth: 0 }}>
                    <div className="mono" style={{ fontSize: 16, fontWeight: 500 }}>{d.ip}</div>
                    <div className="lbl" style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <span>{d.mac || 'unknown'}</span><span style={{ color: 'var(--accent)' }}>{protoLabel(d.protocol)}</span>
                      <span>{d.supports_addressable ? `${d.led_count} LED · addressable` : 'single-RGB'}</span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-sm" style={{ flex: 1 }} onClick={() => handleTest(d.ip, d.port, d.protocol)} disabled={testingIp === d.ip}><Icon n="lightbulb" />{testingIp === d.ip ? 'Testing…' : 'Test'}</button>
                    <button className="btn btn-sm btn-primary" style={{ flex: 1 }} onClick={() => addManaged(d)} disabled={added}>{added ? <><Icon n="check" />Added</> : <><Icon n="plus" />Add</>}</button>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        <Section title="Active setup" count={managed.length} />
        {managed.length === 0 ? (
          <div className="card"><Empty icon="wifi-off" title="No active devices">Add a controller from the discovered list above, or enter one manually below. With none here, the single legacy device + primary monitor is used.</Empty></div>
        ) : (
          <div className="stack">
            {managed.map((mm, i) => (
              <div key={`${mm.ip}-${i}`} className="card card-pad">
                <div className="dev-head">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                    <span className="dev-status" style={{ background: mm.enabled !== false ? 'var(--good)' : 'var(--faint)', color: mm.enabled !== false ? 'var(--good)' : 'var(--faint)' }} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 15, fontWeight: 600 }}>{mm.name || mm.ip}</div>
                      <div className="lbl" style={{ marginTop: 3 }}>{mm.enabled !== false ? 'Active' : 'Disabled'} · {protoLabel(mm.protocol)} · {mm.ip}</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-sm" onClick={() => handleTest(mm.ip, mm.port, mm.protocol)}><Icon n="lightbulb" />Test</button>
                    <button className="btn btn-sm btn-danger icon-btn" onClick={() => removeManaged(i)} title="Remove"><Icon n="trash-2" /></button>
                  </div>
                </div>
                <div className="dev-grid">
                  <label className="field-row"><span className="fr-l">Name</span><input className="field" style={{ maxWidth: 180 }} value={mm.name || ''} placeholder={mm.ip} onChange={(e) => updateManaged(i, 'name', e.target.value)} /></label>
                  <div className="field-row"><span className="fr-l">Enabled</span><Toggle checked={mm.enabled !== false} onChange={(v) => updateManaged(i, 'enabled', v)} /></div>
                  <label className="field-row"><span className="fr-l">Protocol</span>
                    <select className="field" style={{ maxWidth: 180 }} value={mm.protocol || 'magichome'} onChange={(e) => updateManaged(i, 'protocol', e.target.value)}><option value="magichome">MagicHome</option><option value="wled">WLED</option></select></label>
                  <label className="field-row"><span className="fr-l">Target monitor</span>
                    <select className="field" style={{ maxWidth: 200 }} value={mm.monitor_index ?? 0} onChange={(e) => updateManagedMonitor(i, Number(e.target.value))}>
                      {monitorChoices.map((mc) => <option key={mc.index} value={mc.index}>{monitorLabel(mc)}</option>)}</select></label>
                  <div className="field-row"><span className="fr-l">LED count</span><Stepper value={mm.led_count ?? 30} onChange={(v) => updateManaged(i, 'led_count', v)} min={1} max={300} /></div>
                </div>
              </div>
            ))}
          </div>
        )}

        <form onSubmit={addManual} className="card card-pad" style={{ marginTop: 'var(--gap)', display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div style={{ flex: '2 1 200px' }}>
            <input className={`field mono ${err ? 'err' : ''}`} placeholder="IP address (e.g. 192.168.1.29)" value={manualIp} onChange={(e) => { setManualIp(e.target.value); setErr(false) }} />
            {err && <div style={{ color: 'var(--bad)', fontSize: 11, marginTop: 5 }}>Enter a valid IPv4 address.</div>}
          </div>
          <input className="field mono" style={{ flex: '1 1 140px' }} placeholder="MAC (optional)" value={manualMac} onChange={(e) => setManualMac(e.target.value)} />
          <select className="field" style={{ flex: '0 0 auto', width: 140 }} value={manualProto} onChange={(e) => setManualProto(e.target.value)}><option value="magichome">MagicHome</option><option value="wled">WLED</option></select>
          <button type="submit" className="btn btn-primary"><Icon n="plus" />Add device</button>
        </form>
      </div>
    </div>
  )
}
