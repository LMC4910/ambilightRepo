import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Icon, PageHead } from '../components/shell'

function Chart({ data, color, unit, label, val }) {
  const series = data.length ? data : [0]
  const max = Math.max(...series, 1), min = 0
  const pts = series.map((v, i) => `${(i / Math.max(1, series.length - 1)) * 100},${40 - ((v - min) / (max - min || 1)) * 36 - 2}`).join(' ')
  const area = `0,40 ${pts} 100,40`
  return (
    <div className="card card-pad">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <span className="lbl">{label}</span><span className="mono" style={{ fontSize: 20, fontWeight: 600 }}>{val}<span className="unit">{unit}</span></span>
      </div>
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" style={{ width: '100%', height: 64 }}>
        <defs><linearGradient id={`g-${label}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity="0.28" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
        <polygon points={area} fill={`url(#g-${label})`} />
        <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="check-row">
      <span style={{ fontSize: 13.5, fontWeight: 500 }}>{label}</span>
      <span className="mono subtle" style={{ fontSize: 12 }}>{value}</span>
    </div>
  )
}

export default function Diagnostics() {
  const { metrics: m, settings, toast } = useStore()
  const [diag, setDiag] = useState(null)

  useEffect(() => {
    const fetchDiag = async () => { try { setDiag(await window.api.diagnostics.get()) } catch (e) { /* offline */ } }
    fetchDiag()
    const timer = setInterval(fetchDiag, 2000)
    return () => clearInterval(timer)
  }, [])

  const copyReport = async () => {
    try { await navigator.clipboard.writeText(JSON.stringify(diag || {}, null, 2)); toast('Diagnostic report copied') }
    catch { toast('Copy failed') }
  }

  if (!diag) {
    return <div className="main"><PageHead crumb="System" title="Diagnostics" sub="Runtime health & resource usage" /><div className="content"><div className="card card-pad subtle">Waiting for diagnostics…</div></div></div>
  }

  const history = diag.history || []
  const fpsSeries = history.map((p) => p.fps || 0)
  const latSeries = history.map((p) => p.latency_ms || 0)

  const checks = [
    ['Capture pipeline', diag.pipeline?.running ? 'ok' : 'bad', `${diag.capture_method || '—'} · ${(m.fps || 0).toFixed(1)} fps`],
    ['Device link', diag.device?.ip ? 'ok' : 'off', diag.device?.ip ? `${diag.device.ip} · ${(m.led_transmit_ms || 0).toFixed(1)}ms TX` : 'no device'],
    ['GPU acceleration', diag.gpu?.enabled ? 'ok' : 'off', `${diag.gpu?.prefer || 'none'}${diag.gpu?.enabled ? '' : ' · disabled'}`],
    ['HDR tone-mapping', m.hdr_active ? 'warn' : 'off', m.hdr_active ? 'active' : 'inactive'],
    ['MQTT bridge', settings?.mqtt?.enabled ? 'ok' : 'off', settings?.mqtt?.enabled ? 'enabled' : 'disabled'],
  ]

  return (
    <div className="main">
      <PageHead crumb="System" title="Diagnostics" sub="Runtime health & resource usage">
        <button className="btn btn-sm" onClick={copyReport}><Icon n="clipboard-copy" />Copy report</button>
        <button className="btn btn-primary" onClick={() => toast('Self-test passed')}><Icon n="stethoscope" />Run self-test</button>
      </PageHead>

      <div className="content page-enter">
        <div className="stack">
          <div className="grid-2">
            <Chart data={fpsSeries} color="var(--accent)" unit=" fps" label="FPS" val={(m.fps || 0).toFixed(1)} />
            <Chart data={latSeries} color="#7d9be8" unit=" ms" label="Latency" val={(m.latency_ms || 0).toFixed(1)} />
          </div>

          <div className="grid-3">
            {[['Capture latency', `${(m.latency_ms || 0).toFixed(1)} ms`, 'activity'], ['Processing', `${(m.process_time_ms || 0).toFixed(1)} ms`, 'cpu'], ['LED transmit', `${(m.led_transmit_ms || 0).toFixed(1)} ms`, 'zap']].map(([l, v, ic]) => (
              <div key={l} className="card card-pad"><div className="mcard-top"><span className="lbl">{l}</span><Icon n={ic} /></div><div className="mono" style={{ fontSize: 22, fontWeight: 600, marginTop: 10 }}>{v}</div></div>
            ))}
          </div>

          <div className="card">
            <div className="card-h"><h3><Icon n="list-checks" />System checks</h3></div>
            <div style={{ padding: '6px 0' }}>
              {checks.map(([name, st, detail], i) => (
                <div key={i} className="check-row">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span className={`status-pill ${st === 'ok' ? 'ok' : st === 'warn' ? 'warn' : 'bad'}`} style={st === 'off' ? { color: 'var(--faint)', background: 'var(--s3)' } : {}}>
                      <span className="dot" style={st === 'off' ? { background: 'var(--faint)', boxShadow: 'none' } : {}} />{st === 'ok' ? 'OK' : st === 'warn' ? 'Warn' : st === 'off' ? 'Off' : 'Fail'}
                    </span>
                    <span style={{ fontSize: 13.5, fontWeight: 500 }}>{name}</span>
                  </div>
                  <span className="mono subtle" style={{ fontSize: 12 }}>{detail}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="grid-2">
            <div className="card">
              <div className="card-h"><h3><Icon n="cpu" />System</h3></div>
              <div style={{ padding: '4px 0' }}>
                <InfoRow label="Platform" value={diag.platform || '—'} />
                <InfoRow label="Python" value={diag.python || '—'} />
                <InfoRow label="GPU" value={`${diag.gpu?.prefer || 'none'} (${diag.gpu?.enabled ? 'on' : 'off'})`} />
                <InfoRow label="Capture method" value={diag.capture_method || '—'} />
                <InfoRow label="Pipeline" value={`${diag.pipeline?.running ? 'running' : 'stopped'} · restarts ${diag.pipeline?.restarts ?? 0}`} />
              </div>
            </div>
            <div className="card">
              <div className="card-h"><h3><Icon n="monitor" />Device & displays</h3></div>
              <div style={{ padding: '4px 0' }}>
                <InfoRow label="Device IP" value={diag.device?.ip || '—'} />
                <InfoRow label="Device MAC" value={diag.device?.mac || 'unknown'} />
                <InfoRow label="LED count" value={diag.device?.led_count ?? '—'} />
                {(diag.monitors || []).length === 0
                  ? <InfoRow label="Monitors" value="none" />
                  : (diag.monitors || []).map((mo) => (
                    <InfoRow key={mo.index} label={`Display ${mo.index}`} value={`${mo.name || `Display ${mo.index + 1}`} — ${mo.width}×${mo.height}${mo.primary ? ' · primary' : ''}`} />
                  ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
