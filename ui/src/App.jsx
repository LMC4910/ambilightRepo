import React, { useEffect, useState } from 'react'
import { useStore } from './store'
import {
  Activity, Cpu, MonitorPlay, Zap, ServerCrash, Play, Square, RotateCw, Clock, Power,
} from 'lucide-react'
import Devices from './pages/Devices'
import Settings from './pages/Settings'
import Profiles from './pages/Profiles'
import Effects from './pages/Effects'
import Logs from './pages/Logs'
import Diagnostics from './pages/Diagnostics'
import Onboarding from './pages/Onboarding'
import ZonePreview from './components/ZonePreview'
import ZoneEditor from './components/ZoneEditor'
import UpdateBanner from './components/UpdateBanner'

const TABS = ['dashboard', 'devices', 'zones', 'profiles', 'effects', 'settings', 'logs', 'diagnostics']

// [label, mode, params]
const MODES = [
  ['Screen Sync', 'screen_sync', undefined],
  ['Rainbow', 'rainbow', { speed: 1.0 }],
  ['Candle', 'candle', undefined],
  ['Audio', 'audio', { mode: 'level' }],
  ['Sunrise', 'sunrise', { duration: 300 }],
  ['Sunset', 'sunset', { duration: 300 }],
  ['Ocean', 'ocean', undefined],
  ['Ambient', 'ambient', undefined],
]

const STATUS_STYLES = {
  connected: { wrap: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400', dot: 'bg-emerald-500', ping: 'bg-emerald-400', label: 'Service Online' },
  connecting: { wrap: 'bg-blue-500/10 border-blue-500/20 text-blue-400', dot: 'bg-blue-500', ping: 'bg-blue-400', label: 'Connecting…' },
  disconnected: { wrap: 'bg-red-500/10 border-red-500/20 text-red-400', dot: 'bg-red-500', ping: '', label: 'Service Offline' },
}

function MetricCard({ title, value, unit, icon: Icon, delay }) {
  return (
    <div className="glass-panel p-5 rounded-2xl flex flex-col justify-between min-h-[120px] transition-transform hover:scale-[1.02] metric-card-animate animate-fade-up" style={{ animationDelay: delay }}>
      <div className="flex justify-between items-start">
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{title}</span>
        {Icon && <Icon className="w-4 h-4 text-slate-500" />}
      </div>
      <div className="flex items-baseline space-x-1">
        <span className="text-2xl font-bold text-blue-400">{value}</span>
        <span className="text-xs font-semibold text-slate-500">{unit}</span>
      </div>
    </div>
  )
}

function App() {
  const { status, metrics, settings, setStatus, setMetrics, fetchSettings } = useStore()
  const [activeTab, setActiveTab] = useState('dashboard')
  const [showOnboarding, setShowOnboarding] = useState(false)

  useEffect(() => {
    window.api.onboarding?.get().then((done) => setShowOnboarding(!done)).catch(() => {})
    fetchSettings()
    const checkStatus = async () => {
      try { setStatus(await window.api.service.status()) } catch (e) { setStatus('disconnected') }
    }
    const unsubStatus = window.api.service.onStatus((s) => setStatus(s))

    // Pause the metrics stream + status polling + animations while the window is
    // hidden to tray — a 24/7 minimised app should cost ~no renderer CPU.
    let statusTimer = null
    const startLive = () => {
      if (statusTimer) return
      document.body.classList.remove('app-hidden')
      checkStatus()
      statusTimer = setInterval(checkStatus, 3000)
      window.api.metrics.subscribe((m) => setMetrics(m))
    }
    const stopLive = () => {
      document.body.classList.add('app-hidden')
      if (statusTimer) { clearInterval(statusTimer); statusTimer = null }
      window.api.metrics.unsubscribe()
    }
    startLive()
    const unsubVis = window.api.window?.onVisibility?.((visible) => (visible ? startLive() : stopLive()))

    return () => {
      stopLive()
      if (unsubStatus) unsubStatus()
      if (unsubVis) unsubVis()
    }
  }, [])

  const handleService = async (action) => {
    try { setStatus('connecting'); await window.api.service[action]() } catch (e) { console.error(`service ${action} failed`, e) }
  }
  const setMode = (mode, params) => useStore.getState().setMode(mode, params)

  const st = STATUS_STYLES[status] || STATUS_STYLES.disconnected
  const isOff = metrics.mode === 'off'
  const online = status === 'connected'

  return (
    <div className="flex h-screen w-full overflow-hidden antialiased">
      {showOnboarding && <Onboarding onDone={() => setShowOnboarding(false)} />}

      {/* Sidebar */}
      <aside className="w-64 xl:w-72 glass-panel border-r border-white/10 flex flex-col p-5 xl:p-6 gap-5 xl:gap-6 shrink-0 overflow-y-auto z-10">
        {/* Brand */}
        <div className="flex items-center space-x-3 px-2">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center shadow-lg shadow-indigo-500/30"
            style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)' }}>
            <Zap className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-white">Ambient</h1>
        </div>

        {/* Status */}
        <div className={`flex items-center space-x-2 border px-3 py-2 rounded-lg ${st.wrap}`}>
          <span className="relative flex h-2 w-2">
            {st.ping && <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${st.ping}`} />}
            <span className={`relative inline-flex rounded-full h-2 w-2 ${st.dot}`} />
          </span>
          <span className="text-[10px] font-bold uppercase tracking-widest">{st.label}</span>
        </div>

        {/* Power toggle */}
        <button onClick={() => setMode(isOff ? 'screen_sync' : 'off')} disabled={!online}
          className={`flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
            isOff ? 'bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10'
                  : 'text-white'} ${isOff ? '' : 'nav-item-active'}`}>
          <Power className="w-4 h-4" /> {isOff ? 'Lights Off — Turn On' : 'Turn Lights Off'}
        </button>

        {/* Quick controls */}
        <div className="grid grid-cols-3 gap-2">
          <button title="Start" onClick={() => handleService('start')} disabled={online}
            className="glass-panel hover:bg-white/10 transition-colors p-2 rounded-lg flex justify-center items-center disabled:opacity-40">
            <Play className="w-4 h-4 text-emerald-400" />
          </button>
          <button title="Stop" onClick={() => handleService('stop')} disabled={status === 'disconnected'}
            className="glass-panel bg-red-500/10 hover:bg-red-500/20 transition-colors p-2 rounded-lg flex justify-center items-center border border-red-500/30 disabled:opacity-40">
            <Square className="w-4 h-4 text-red-400" />
          </button>
          <button title="Restart" onClick={() => handleService('restart')}
            className="glass-panel hover:bg-white/10 transition-colors p-2 rounded-lg flex justify-center items-center">
            <RotateCw className="w-4 h-4 text-blue-400" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-1">
          {TABS.map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`w-full text-left flex items-center px-4 py-2.5 text-sm rounded-xl transition-all capitalize ${
                activeTab === tab ? 'nav-item-active font-semibold' : 'text-slate-400 hover:bg-white/5 hover:text-white font-medium'}`}>
              {tab}
            </button>
          ))}
        </nav>

        {/* Modes */}
        <div className="mt-auto pt-6 border-t border-white/5">
          <h2 className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 mb-4">Modes</h2>
          <div className="grid grid-cols-2 gap-2 mb-4">
            {MODES.map(([label, mode, params]) => (
              <button key={label} onClick={() => setMode(mode, { ...(params || {}), ...(settings?.effects?.params?.[mode] || {}) })}
                className={`text-[11px] py-2 px-1 rounded-lg border transition-colors ${
                  metrics.mode === mode ? 'nav-item-active border-transparent font-semibold'
                                        : 'bg-white/5 hover:bg-white/10 border-white/5 text-slate-300'}`}>
                {label}
              </button>
            ))}
          </div>
          <button onClick={() => setShowOnboarding(true)}
            className="w-full bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-400 text-[11px] py-2.5 rounded-xl border border-indigo-500/30 transition-all font-bold uppercase tracking-wider">
            Setup wizard
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 overflow-y-auto p-5 xl:p-8 relative">
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-indigo-600/10 rounded-full blur-[120px] -z-10 pointer-events-none" />
        <div className="max-w-6xl mx-auto space-y-8 min-w-0">
          <UpdateBanner />

          {activeTab === 'dashboard' && (
            <>
              <header className="animate-fade-up">
                <h2 className="text-2xl font-semibold text-white tracking-tight mb-6">Performance Metrics</h2>
                {status === 'disconnected' ? (
                  <div className="glass-panel rounded-2xl p-12 text-center text-slate-400">
                    <ServerCrash className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p>Waiting for the background service…</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
                    <MetricCard title="Capture Rate" value={metrics.fps.toFixed(1)} unit="FPS" icon={MonitorPlay} delay="0s" />
                    <MetricCard title="Latency" value={metrics.latency_ms.toFixed(1)} unit="ms" icon={Activity} delay="0.1s" />
                    <MetricCard title="Processing" value={(metrics.process_time_ms || 0).toFixed(1)} unit="ms" icon={Cpu} delay="0.2s" />
                    <MetricCard title="LED TX" value={(metrics.led_transmit_ms || 0).toFixed(1)} unit="ms" icon={Zap} delay="0.3s" />
                    <MetricCard title="Uptime" value={Math.floor((metrics.uptime_s || 0) / 60)} unit="min" icon={Clock} delay="0.4s" />
                  </div>
                )}
              </header>

              {status !== 'disconnected' && (
                <>
                  <section className="animate-fade-up" style={{ animationDelay: '0.2s' }}>
                    <ZonePreview zones={metrics.zones || []} color={metrics.color || [0, 0, 0]} />
                  </section>

                  <section className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-fade-up" style={{ animationDelay: '0.3s' }}>
                    <div className="glass-panel p-6 rounded-2xl">
                      <h4 className="text-sm font-semibold text-white mb-4">Device Connection</h4>
                      <div className="space-y-4">
                        <div className="flex justify-between items-center">
                          <span className="text-xs text-slate-400">Controllers</span>
                          <span className="text-xs font-mono text-emerald-400 px-2 py-1 bg-emerald-400/10 rounded">
                            {metrics.devices_connected ?? 0}/{metrics.devices ?? 0} connected
                          </span>
                        </div>
                        <div className="w-full bg-white/5 h-1 rounded-full overflow-hidden">
                          <div className="bg-indigo-500 h-full transition-all"
                            style={{ width: `${metrics.devices ? Math.round(100 * (metrics.devices_connected || 0) / metrics.devices) : 0}%` }} />
                        </div>
                      </div>
                    </div>
                    <div className="glass-panel p-6 rounded-2xl">
                      <h4 className="text-sm font-semibold text-white mb-4">Quick Toggle</h4>
                      <div className="flex items-center justify-between p-3 bg-white/5 rounded-xl">
                        <span className="text-xs text-slate-300">Lights {isOff ? 'off' : 'on'}</span>
                        <button onClick={() => setMode(isOff ? 'screen_sync' : 'off')} disabled={!online}
                          className={`w-10 h-5 rounded-full relative transition-colors disabled:opacity-40 ${isOff ? 'bg-white/15' : 'bg-indigo-600'}`}>
                          <div className={`absolute top-1 w-3 h-3 bg-white rounded-full transition-all ${isOff ? 'left-1' : 'right-1'}`} />
                        </button>
                      </div>
                    </div>
                  </section>
                </>
              )}
            </>
          )}

          {activeTab === 'devices' && <Devices />}
          {activeTab === 'zones' && <ZoneEditor />}
          {activeTab === 'profiles' && <Profiles />}
          {activeTab === 'effects' && <Effects />}
          {activeTab === 'settings' && <Settings />}
          {activeTab === 'logs' && <Logs />}
          {activeTab === 'diagnostics' && <Diagnostics />}
        </div>
      </main>
    </div>
  )
}

export default App
