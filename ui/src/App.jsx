import React, { useEffect, useMemo, useState } from 'react'
import { useStore } from './store'
import { TitleBar, Sidebar, Toasts } from './components/shell'
import { serviceAction } from './shared/service'
import Wizard from './components/Wizard'
import Dashboard from './pages/Dashboard'
import Devices from './pages/Devices'
import Zones from './pages/Zones'
import Profiles from './pages/Profiles'
import Effects from './pages/Effects'
import Notifications from './pages/Notifications'
import Settings from './pages/Settings'
import Logs from './pages/Logs'
import Diagnostics from './pages/Diagnostics'

const PAGES = {
  dashboard: Dashboard, devices: Devices, zones: Zones, profiles: Profiles, effects: Effects,
  notifications: Notifications, settings: Settings, logs: Logs, diagnostics: Diagnostics,
}

// metrics.color → "#rrggbb"
const liveHexOf = (c) => {
  if (!Array.isArray(c)) return '#3a3f4a'
  return '#' + c.map((x) => Math.max(0, Math.min(255, x | 0)).toString(16).padStart(2, '0')).join('')
}

export default function App() {
  const { status, metrics, settings, ui, setUiPref, toasts, setStatus, setMetrics, fetchSettings } = useStore()
  const [tab, setTab] = useState('dashboard')
  const [wizardOpen, setWizardOpen] = useState(false)

  useEffect(() => {
    window.api.onboarding?.get().then((done) => setWizardOpen(!done)).catch(() => {})
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

  const online = status === 'connected'
  const isOff = metrics.mode === 'off'
  const liveHex = useMemo(() => liveHexOf(metrics.color), [metrics.color])

  // Effective accent: echo the live LED when enabled & syncing, else the saved accent.
  const accent = (ui.accentFollowsLive && !isOff && status !== 'disconnected') ? liveHex : ui.accent
  const rootStyle = {
    '--accent': accent,
    '--live': (isOff || status === 'disconnected') ? '#3a3f4a' : liveHex,
  }

  const setMode = useStore.getState().setMode
  const Page = PAGES[tab] || Dashboard

  return (
    <div className="ambi-root"
      data-theme={ui.theme}
      data-density={ui.density === 'compact' ? 'compact' : 'comfortable'}
      data-glass="1"
      data-side={ui.sidebarCollapsed ? 'collapsed' : 'expanded'}
      style={rootStyle}>
      <div className="app">
        <TitleBar
          online={online}
          ip={settings?.device?.ip}
          theme={ui.theme}
          onToggleTheme={() => setUiPref('theme', ui.theme === 'dark' ? 'light' : 'dark')}
          onMin={() => window.api.window?.minimize?.()}
          onMax={() => window.api.window?.maximize?.()}
          onClose={() => window.api.window?.close?.()}
        />
        <div className="body">
          <Sidebar
            tab={tab} setTab={setTab}
            online={online}
            managedCount={settings?.devices?.length || 0}
            mode={metrics.mode}
            setMode={setMode}
            settings={settings}
            onStart={() => serviceAction('start')}
            onStop={() => serviceAction('stop')}
            onRestart={() => serviceAction('restart')}
            onOpenWizard={() => setWizardOpen(true)}
            collapsed={ui.sidebarCollapsed}
            setCollapsed={(v) => setUiPref('sidebarCollapsed', v)}
          />
          <Page />
        </div>
      </div>

      {wizardOpen && <Wizard onClose={() => setWizardOpen(false)} />}
      <Toasts toasts={toasts} />
    </div>
  )
}
