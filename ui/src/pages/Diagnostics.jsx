import React, { useEffect, useState } from 'react'
import LineChart from '../components/LineChart'
import { Stethoscope, Cpu, Monitor } from 'lucide-react'

function InfoRow({ label, value }) {
  return (
    <div className="flex justify-between py-1.5 text-sm border-b border-white/5 last:border-0">
      <span className="text-slate-400">{label}</span>
      <span className="font-mono text-slate-200">{value}</span>
    </div>
  )
}

export default function Diagnostics() {
  const [diag, setDiag] = useState(null)

  useEffect(() => {
    const fetchDiag = async () => { try { setDiag(await window.api.diagnostics.get()) } catch (e) { /* offline */ } }
    fetchDiag()
    const timer = setInterval(fetchDiag, 2000)
    return () => clearInterval(timer)
  }, [])

  if (!diag) {
    return <section className="glass-panel rounded-3xl p-8 text-slate-400 animate-fade-up">Waiting for diagnostics…</section>
  }

  const history = diag.history || []
  const fpsSeries = history.map((p) => p.fps)
  const latSeries = history.map((p) => p.latency_ms)

  return (
    <section className="glass-panel rounded-3xl p-8 flex flex-col gap-5 animate-fade-up">
      <h3 className="text-lg font-semibold text-white flex items-center gap-2"><Stethoscope className="w-5 h-5 text-indigo-400" /> Diagnostics</h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <LineChart data={fpsSeries} color="#34d399" label="FPS (60 s)" unit="fps" />
        <LineChart data={latSeries} color="#818cf8" label="Latency (60 s)" unit="ms" />
      </div>

      <div className="glass-panel rounded-2xl p-5">
        <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2"><Cpu className="w-4 h-4 text-slate-400" /> System</h4>
        <InfoRow label="Platform" value={diag.platform} />
        <InfoRow label="Python" value={diag.python} />
        <InfoRow label="GPU" value={`${diag.gpu?.prefer} (${diag.gpu?.enabled ? 'on' : 'off'})`} />
        <InfoRow label="Capture method" value={diag.capture_method} />
        <InfoRow label="Pipeline" value={`${diag.pipeline?.running ? 'running' : 'stopped'} · restarts ${diag.pipeline?.restarts ?? 0}`} />
      </div>

      <div className="glass-panel rounded-2xl p-5">
        <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2"><Monitor className="w-4 h-4 text-slate-400" /> Device &amp; Displays</h4>
        <InfoRow label="Device IP" value={diag.device?.ip} />
        <InfoRow label="Device MAC" value={diag.device?.mac || 'unknown'} />
        <InfoRow label="LED count" value={diag.device?.led_count} />
        <InfoRow label="Monitors" value={(diag.monitors || []).map((m) => `${m.width}×${m.height}`).join(', ') || 'none'} />
      </div>
    </section>
  )
}
