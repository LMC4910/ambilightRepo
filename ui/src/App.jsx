import React, { useEffect, useState } from 'react'
import { useStore } from './store'
import { Activity, Cpu, MonitorPlay, Zap, ServerCrash, Play, Square, RotateCw } from 'lucide-react'
import Devices from './pages/Devices'
import Settings from './pages/Settings'
import Profiles from './pages/Profiles'
import Logs from './pages/Logs'
import Diagnostics from './pages/Diagnostics'
import Onboarding from './pages/Onboarding'
import ZonePreview from './components/ZonePreview'
import UpdateBanner from './components/UpdateBanner'

const TABS = ['dashboard', 'devices', 'profiles', 'settings', 'logs', 'diagnostics']

function MetricCard({ title, value, unit, icon: Icon }) {
  return (
    <div className="metric-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="metric-label">{title}</span>
        {Icon && <Icon size={16} color="var(--text-muted)" />}
      </div>
      <div className="metric-value">
        {value} <span style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>{unit}</span>
      </div>
    </div>
  )
}

function App() {
  const { status, metrics, setStatus, setMetrics, fetchSettings } = useStore()
  const [activeTab, setActiveTab] = useState('dashboard')
  const [showOnboarding, setShowOnboarding] = useState(false)

  useEffect(() => {
    // Show the first-run wizard unless the onboarding marker exists.
    window.api.onboarding?.get().then((done) => setShowOnboarding(!done)).catch(() => {})
    fetchSettings()

    const checkStatus = async () => {
      try {
        setStatus(await window.api.service.status())
      } catch (e) {
        setStatus('disconnected')
      }
    }
    const unsubStatus = window.api.service.onStatus((s) => setStatus(s))
    const timer = setInterval(checkStatus, 3000)
    checkStatus()

    window.api.metrics.subscribe((newMetrics) => setMetrics(newMetrics))

    return () => {
      clearInterval(timer)
      if (unsubStatus) unsubStatus()
      window.api.metrics.unsubscribe()
    }
  }, [])

  const handleService = async (action) => {
    try {
      setStatus('connecting')
      await window.api.service[action]()
    } catch (e) {
      console.error(`service ${action} failed`, e)
    }
  }

  return (
    <div className="app-container">
      {showOnboarding && <Onboarding onDone={() => setShowOnboarding(false)} />}
      <aside className="sidebar glass-panel">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Zap color="var(--accent-purple)" /> Ambilight
        </h2>

        <div className={`status-badge status-${status}`}>
          <div className="status-dot"></div>
          {status === 'connected' ? 'Service Online' : status === 'connecting' ? 'Connecting...' : 'Service Offline'}
        </div>

        <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.75rem' }}>
          <button className="button" title="Start service"
            style={{ flex: 1, padding: '0.4rem', background: 'rgba(163,190,140,0.2)', color: 'var(--accent-green, #a3be8c)' }}
            disabled={status === 'connected'}
            onClick={() => handleService('start')}><Play size={14} /></button>
          <button className="button" title="Stop service"
            style={{ flex: 1, padding: '0.4rem', background: 'rgba(239,68,68,0.2)', color: 'var(--accent-red, #ef4444)' }}
            disabled={status === 'disconnected'}
            onClick={() => handleService('stop')}><Square size={14} /></button>
          <button className="button" title="Restart service"
            style={{ flex: 1, padding: '0.4rem', background: 'rgba(255,255,255,0.1)' }}
            onClick={() => handleService('restart')}><RotateCw size={14} /></button>
        </div>

        <nav style={{ marginTop: '2rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {TABS.map((tab) => (
            <button key={tab}
              className={`button ${activeTab === tab ? '' : 'inactive'}`}
              style={{ background: activeTab === tab ? undefined : 'rgba(255,255,255,0.1)', textTransform: 'capitalize' }}
              onClick={() => setActiveTab(tab)}>{tab}</button>
          ))}
        </nav>

        <div style={{ marginTop: 'auto' }}>
          <h4 style={{ color: 'var(--text-muted)', marginBottom: '0.5rem', fontSize: '0.875rem' }}>Modes</h4>
          <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <button className="button" style={{ background: 'rgba(255,255,255,0.1)', padding: '0.5rem' }} onClick={() => useStore.getState().setMode('screen_sync')}>Screen Sync</button>
            <button className="button" style={{ background: 'rgba(255,255,255,0.1)', padding: '0.5rem' }} onClick={() => useStore.getState().setMode('rainbow', { speed: 1.0 })}>Rainbow Effect</button>
            <button className="button" style={{ background: 'rgba(255,255,255,0.1)', padding: '0.5rem' }} onClick={() => useStore.getState().setMode('candle')}>Candle</button>
          </nav>
          <button className="button" style={{ marginTop: '0.75rem', padding: '0.5rem', background: 'rgba(255,255,255,0.06)', fontSize: '0.8rem' }} onClick={() => setShowOnboarding(true)}>Setup wizard</button>
        </div>
      </aside>

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1.5rem', overflow: 'auto' }}>
        <UpdateBanner />
        {activeTab === 'dashboard' && (
          <section className="glass-panel">
            <h3>Performance Metrics</h3>
            {status === 'disconnected' ? (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                <ServerCrash size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
                <p>Waiting for background service...</p>
              </div>
            ) : (
              <div className="metrics-grid">
                <MetricCard title="Capture Rate" value={metrics.fps.toFixed(1)} unit="FPS" icon={MonitorPlay} />
                <MetricCard title="Latency" value={metrics.latency_ms.toFixed(1)} unit="ms" icon={Activity} />
                <MetricCard title="Processing" value={metrics.process_time_ms?.toFixed(1) || 0} unit="ms" icon={Cpu} />
                <MetricCard title="LED Tx" value={metrics.led_transmit_ms?.toFixed(1) || 0} unit="ms" icon={Zap} />
                <MetricCard title="Uptime" value={Math.floor((metrics.uptime_s || 0) / 60)} unit="min" />
                <ZonePreview zones={metrics.zones || []} color={metrics.color || [0, 0, 0]} />
              </div>
            )}
          </section>
        )}

        {activeTab === 'devices' && <Devices />}
        {activeTab === 'profiles' && <Profiles />}
        {activeTab === 'settings' && <Settings />}
        {activeTab === 'logs' && <Logs />}
        {activeTab === 'diagnostics' && <Diagnostics />}
      </main>
    </div>
  )
}

export default App
