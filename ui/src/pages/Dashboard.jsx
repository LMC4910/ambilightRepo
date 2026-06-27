import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Icon, PageHead, ServiceStatus, Transport, Toggle } from '../components/shell'
import { MODES } from '../shared/constants'
import { serviceAction } from '../shared/service'
import UpdateBanner from '../components/UpdateBanner'

const fmtRGB = (c) => `rgb(${c?.[0] ?? 0}, ${c?.[1] ?? 0}, ${c?.[2] ?? 0})`

/* live screen preview */
function LivePreview({ color, off }) {
  const lc = fmtRGB(color)
  return (
    <div className="screen" style={{ height: '100%', '--gc': lc }}>
      {!off && <div className="screen-glow" />}
      {!off && <div className="screen-beam" />}
      <div className="screen-core">
        {off ? <span className="subtle">Lights are off</span> :
          <span className="mono" style={{ color: 'rgba(255,255,255,.85)', textShadow: '0 1px 5px rgba(0,0,0,.7)' }}>{lc}</span>}
      </div>
    </div>
  )
}

// Translate the pipeline's capture-health metrics into a human banner — the strip
// can be silently dark even while "online" (fullscreen game on MSS, DRM content).
function captureHealth(m) {
  const backend = (m.capture_backend || '').toUpperCase()
  const reason = m.capture_reason || 'ok'
  const captureOk = m.capture_ok !== false
  if (!captureOk && reason === 'black')
    return { tone: 'bad', icon: 'alert-triangle', text: 'Not syncing — capture is black. A fullscreen game on the MSS backend renders black; install the WGC backend (windows-capture) for proper capture.' }
  if (!captureOk && reason === 'drm_suspected')
    return { tone: 'warn', icon: 'shield-alert', text: 'Not syncing — the screen is black. DRM-protected content (Netflix, Disney+, etc.) is blocked by Windows and can’t be captured.' }
  if (!captureOk && reason === 'no_frames')
    return { tone: 'bad', icon: 'alert-triangle', text: 'Not syncing — capture is producing no frames. Check the selected monitor in Devices, or that a capture backend is available.' }
  if (!captureOk)
    return { tone: 'bad', icon: 'alert-triangle', text: 'Not syncing — capture is unavailable.' }
  if (m.degraded || m.capture_degraded)
    return { tone: 'warn', icon: 'alert-triangle', text: 'Capture fell back to MSS — fullscreen games and overlay video may appear black. Install windows-capture for the WGC backend.' }
  return { tone: 'good', icon: 'check-circle-2', text: `Syncing${backend ? ` · ${backend} backend` : ''}` }
}

// At-a-glance capture source: WGC/DXGI good (emerald), MSS degraded (amber), else neutral.
function captureSource(m) {
  const raw = (m.capture_backend || '').toLowerCase()
  const syncing = m.mode === 'screen_sync'
  if (!syncing) return { label: 'Idle', color: 'var(--faint)', sub: 'not syncing' }
  if (!raw) return { label: '—', color: 'var(--faint)', sub: 'starting…' }
  if (raw === 'mss') return { label: 'MSS', color: 'var(--warn)', sub: 'fallback · may be black' }
  if (raw === 'wgc') return { label: 'WGC', color: 'var(--good)', sub: 'full capture' }
  if (raw === 'dxgi') return { label: 'DXGI', color: 'var(--good)', sub: 'GPU capture' }
  return { label: raw.toUpperCase(), color: 'var(--faint)', sub: 'unknown backend' }
}

// Game-capture (hook) status for the dashboard indicator. The capture manager
// only makes "hook" the active backend when a game is actually being captured,
// so capture_backend === "hook" == injection working; otherwise it's searching.
function gameCapture(m) {
  const backend = (m.capture_backend || '').toLowerCase()
  if (!m.hook_enabled)
    return { tone: 'faint', label: 'Off',
      sub: 'Game capture is off. Enter a game .exe (or leave blank for any fullscreen game) and Re-inject to enable it.' }
  if (backend === 'hook')
    return { tone: 'good', label: 'Capturing',
      sub: `Injection working${m.hook_target ? ` · ${m.hook_target}` : ' · auto-detecting fullscreen games'}.` }
  return { tone: 'warn', label: 'Searching',
    sub: `Waiting for a fullscreen game${m.hook_target ? ` matching “${m.hook_target}”` : ''}. Launch it (DirectX 9/10/11/12), or set its .exe and Re-inject.` }
}

function MCard({ lbl, icon, children, foot, spark }) {
  return (
    <div className="card mcard">
      <div className="mcard-top"><span className="lbl">{lbl}</span><Icon n={icon} /></div>
      <div className="mcard-val">{children}</div>
      {foot}
      {spark}
    </div>
  )
}

export default function Dashboard() {
  const { status, metrics: m, settings } = useStore()
  const online = status === 'connected'
  const syncing = m.mode === 'screen_sync'
  const isOff = m.mode === 'off'

  const [hist, setHist] = useState(() => ({ fps: Array(24).fill(0), lat: Array(24).fill(0) }))
  useEffect(() => {
    setHist((h) => ({ fps: [...h.fps.slice(-23), m.fps || 0], lat: [...h.lat.slice(-23), m.latency_ms || 0] }))
  }, [m.fps, m.latency_ms])

  const spark = (arr, color) => {
    const min = Math.min(...arr), max = Math.max(...arr), r = max - min || 1
    const pts = arr.map((v, i) => `${(i / (arr.length - 1)) * 200},${30 - ((v - min) / r) * 26 - 2}`).join(' ')
    return <svg className="spark" viewBox="0 0 200 30" preserveAspectRatio="none"><polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" /></svg>
  }

  const togglePower = () => useStore.getState().setMode(isOff ? 'screen_sync' : 'off')
  const setNotifEnabled = (v) => useStore.getState().updateSettings({ notifications: { enabled: v } })

  // Game-capture re-inject control. Seed the exe field from the live status and
  // re-sync only when the applied target actually changes (so typing isn't lost).
  const [exe, setExe] = useState(m.hook_target || '')
  useEffect(() => { setExe(m.hook_target || '') }, [m.hook_target])
  const onReinject = () => useStore.getState().retargetCapture(exe.trim())

  const health = captureHealth(m)
  const src = captureSource(m)
  const gc = gameCapture(m)
  const modeLabel = MODES.find((x) => x[1] === m.mode)?.[0] || 'Off'

  return (
    <div className="main">
      <PageHead crumb="Overview" title="Dashboard" sub="Live capture & LED pipeline">
        <ServiceStatus status={status} />
        <Transport online={online} onStart={() => serviceAction('start')} onStop={() => serviceAction('stop')} onRestart={() => serviceAction('restart')} />
        <button className="btn" onClick={togglePower} disabled={!online}><Icon n="power" />{isOff ? 'Turn lights on' : 'Turn lights off'}</button>
      </PageHead>

      <div className="content page-enter">
        <div className="stack">
          <UpdateBanner />

          {status === 'disconnected' ? (
            <div className="card card-pad">
              <div className="empty"><div className="ei"><Icon n="server-crash" /></div><h4>Waiting for the background service…</h4>
                <p>Start the service from the sidebar to see live metrics.</p></div>
            </div>
          ) : (
            <>
              {/* capture health banner */}
              {online && !isOff && syncing && (
                <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px',
                  borderColor: `color-mix(in srgb,var(--${health.tone}) 24%,transparent)`, background: `var(--${health.tone}-bg)` }}>
                  <Icon n={health.icon} style={{ color: `var(--${health.tone})` }} />
                  <span style={{ fontSize: 12.5, fontWeight: 500, color: `var(--${health.tone})` }}>{health.text}</span>
                  {m.hdr_active && (
                    <span className="tag" style={{ marginLeft: 'auto', color: '#c98ad6', background: 'color-mix(in srgb,#c98ad6 14%,transparent)' }}>
                      <span className="d" style={{ background: 'currentColor' }} />HDR
                    </span>
                  )}
                </div>
              )}

              {/* metric grid */}
              <div className="grid-3">
                <MCard lbl="Capture rate" icon="gauge" spark={spark(hist.fps, 'var(--accent)')}>
                  <span className="num">{syncing ? (m.fps || 0).toFixed(1) : '0.0'}</span><span className="unit">fps</span>
                </MCard>
                <MCard lbl="Capture source" icon="monitor"
                  foot={src.color === 'var(--good)' ? <span className="tag good"><span className="d" />{src.sub}</span> : <span className="subtle" style={{ fontSize: 11 }}>{src.sub}</span>}>
                  <span className="num" style={{ color: src.color }}>{src.label}</span>
                </MCard>
                <MCard lbl="Latency" icon="activity" spark={spark(hist.lat, '#7d9be8')}>
                  <span className="num">{(m.latency_ms || 0).toFixed(1)}</span><span className="unit">ms</span>
                </MCard>
                <MCard lbl="Processing" icon="cpu"><span className="num">{(m.process_time_ms || 0).toFixed(1)}</span><span className="unit">ms</span></MCard>
                <MCard lbl="LED transmit" icon="zap"><span className="num">{(m.led_transmit_ms || 0).toFixed(1)}</span><span className="unit">ms</span></MCard>
                <MCard lbl="Uptime" icon="clock"><span className="num">{Math.floor((m.uptime_s || 0) / 60)}</span><span className="unit">min {(m.uptime_s || 0) % 60}s</span></MCard>
              </div>

              {/* preview + control rail */}
              <div className="dash-split">
                <div className="card" style={{ padding: 'var(--pad)', display: 'flex', flexDirection: 'column', gap: 14, minHeight: 340 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span className="lbl">Live zone preview</span>
                    <span className="chip live"><span className="dot" />{modeLabel}</span>
                  </div>
                  <div style={{ flex: 1, minHeight: 0 }}><LivePreview color={m.color} off={isOff} /></div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap)' }}>
                  <div className="card card-pad">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                      <span className="card-title">Device connection</span>
                      <span className="tag good"><span className="d" />{m.devices_connected ?? 0}/{m.devices ?? 0}</span>
                    </div>
                    <div className="bar"><i style={{ width: `${m.devices ? (100 * (m.devices_connected || 0)) / m.devices : 0}%` }} /></div>
                    <div className="subtle" style={{ marginTop: 12, fontSize: 12 }}>
                      {settings?.devices?.[0]?.name || settings?.device?.name || '—'}
                    </div>
                  </div>
                  <div className="card card-pad">
                    <div className="card-title" style={{ marginBottom: 14 }}>Quick toggle</div>
                    <div className="quick-row"><span>Lights {isOff ? 'off' : 'on'}</span><Toggle checked={!isOff} onChange={togglePower} disabled={!online} /></div>
                    <div className="quick-row" style={{ marginTop: 10 }}>
                      <span>Notification flash</span>
                      <Toggle checked={!!settings?.notifications?.enabled} onChange={setNotifEnabled} disabled={!settings} />
                    </div>
                  </div>

                  {/* Game capture (hook): status indicator + re-inject control */}
                  <div className="card card-pad" style={{ flex: 1 }}>
                    <div className="quick-row" style={{ marginBottom: 10 }}>
                      <span className="card-title">Game capture</span>
                      <span className="tag" style={{ color: `var(--${gc.tone})`, background: `color-mix(in srgb,var(--${gc.tone}) 14%,transparent)` }}>
                        <span className="d" style={{ background: 'currentColor' }} />{gc.label}
                      </span>
                    </div>
                    <div className="subtle" style={{ fontSize: 11.5, lineHeight: 1.45, marginBottom: 10 }}>{gc.sub}</div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <input className="field mono" style={{ flex: 1, minWidth: 0 }} placeholder="auto (any fullscreen game)"
                        value={exe} onChange={(e) => setExe(e.target.value)} disabled={!online}
                        onKeyDown={(e) => { if (e.key === 'Enter') onReinject() }} />
                      <button className="btn" onClick={onReinject} disabled={!online}><Icon n="syringe" />Re-inject</button>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
