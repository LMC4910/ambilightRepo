/* ============================================================================
   AMBI LIGHT — shell + shared primitives (ported from the design's app/shell.jsx,
   converted to lucide-react and wired to the real store via props).
   ========================================================================== */
import React from 'react'
import * as Lucide from 'lucide-react'
import { NAV, MODES } from '../shared/constants'

// --- Icon: map a kebab-case lucide name to the lucide-react component, kept
// inside a span.ic so the design's `.xxx .ic svg` selectors still apply. ------
const _pascalCache = {}
function pascal(n) {
  if (_pascalCache[n]) return _pascalCache[n]
  const v = String(n).split(/[-_]/).map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  _pascalCache[n] = v
  return v
}
export function Icon({ n, className, style, ...p }) {
  const Cmp = Lucide[pascal(n)] || Lucide.Circle
  return (
    <span className={'ic' + (className ? ' ' + className : '')} style={{ display: 'inline-flex', ...style }} {...p}>
      <Cmp />
    </span>
  )
}

/* ---------------- form primitives ---------------- */
export function Toggle({ checked, onChange, disabled }) {
  return (
    <button type="button" role="switch" aria-checked={!!checked} disabled={disabled}
      className={`toggle ${checked ? 'on' : ''}`} onClick={() => !disabled && onChange(!checked)} />
  )
}

export function Stepper({ value, onChange, min = 1, max = 999 }) {
  const clamp = (n) => Math.max(min, Math.min(max, Math.round(n) || min))
  return (
    <div className="stepper">
      <button onClick={() => onChange(clamp(value - 1))} aria-label="decrease"><Icon n="minus" /></button>
      <input className="mono" value={value} onChange={(e) => onChange(clamp(+e.target.value))} />
      <button onClick={() => onChange(clamp(value + 1))} aria-label="increase"><Icon n="plus" /></button>
    </div>
  )
}

export function Swatch({ rgb, onChange }) {
  const hex = '#' + rgb.map((c) => Math.max(0, Math.min(255, c | 0)).toString(16).padStart(2, '0')).join('')
  const fromHex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
  return (
    <label className="swatch" style={{ background: hex }}>
      <input type="color" value={hex} onChange={(e) => onChange(fromHex(e.target.value))} />
    </label>
  )
}

export function Empty({ icon, title, children, action }) {
  return (
    <div className="empty">
      <div className="ei"><Icon n={icon} /></div>
      <h4>{title}</h4>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

export function Section({ title, count, children }) {
  return (
    <div className="sect">
      <h2>{title}</h2>
      {count != null && <span className="count">{count}</span>}
      <span className="line" />
      {children}
    </div>
  )
}

/* ---------------- TITLEBAR ---------------- */
export function TitleBar({ online, ip, theme, onToggleTheme, onMin, onMax, onClose }) {
  const dark = theme === 'dark'
  return (
    <div className="titlebar">
      <div className="tb-left">
        <div className="tb-logo"><Icon n="zap" /></div>
        <span className="tb-brand">Ambi&nbsp;Light</span>
        <span className="tb-meta">
          <span className="mdot" style={{ background: online ? 'var(--good)' : 'var(--faint)', boxShadow: online ? '0 0 7px var(--good)' : 'none' }} />
          {online ? `Connected${ip ? ` · ${ip}` : ''}` : 'Offline'}
        </span>
      </div>
      <div className="tb-right">
        <button className="theme-toggle" onClick={onToggleTheme} title={dark ? 'Switch to light theme' : 'Switch to dark theme'} aria-label="Toggle theme">
          <Icon n={dark ? 'sun' : 'moon'} />
        </button>
        <div className="wctl">
          <button className="wbtn" onClick={onMin} aria-label="Minimize"><Icon n="minus" /></button>
          <button className="wbtn" onClick={onMax} aria-label="Maximize"><Icon n="square" /></button>
          <button className="wbtn close" onClick={onClose} aria-label="Close"><Icon n="x" /></button>
        </div>
      </div>
    </div>
  )
}

/* ---------------- SIDEBAR ---------------- */
export function Sidebar({ tab, setTab, online, managedCount, mode, setMode, settings, onStart, onStop, onRestart, onOpenWizard, collapsed, setCollapsed }) {
  const pick = (m, params) => setMode(m, { ...(params || {}), ...(settings?.effects?.params?.[m] || {}) })
  return (
    <aside className="side">
      <div className="side-scroll">
        <div className="side-head">
          <span className="side-head-label">Menu</span>
          <button className="collapse-btn" onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            <Icon n="panel-left-close" />
          </button>
        </div>
        <nav className="nav">
          {NAV.map(([id, label, icon]) => (
            <button key={id} className={`nav-item ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)} title={label}>
              <Icon n={icon} /><span className="nlabel">{label}</span>
              {id === 'devices' && managedCount > 0 && <span className="nav-badge">{managedCount}</span>}
            </button>
          ))}
        </nav>

        <div className="side-sect">Service</div>
        <div className="transport">
          <button className="tp-btn play" onClick={onStart} disabled={online} title="Start"><Icon n="play" /><span className="nlabel">Start</span></button>
          <button className="tp-btn stop" onClick={onStop} disabled={!online} title="Stop"><Icon n="square" /></button>
          <button className="tp-btn re" onClick={onRestart} title="Restart"><Icon n="rotate-cw" /></button>
        </div>

        <div className="side-sect">Modes</div>
        <div className="modes">
          {MODES.map(([label, m, abbr, params]) => (
            <button key={m} data-abbr={abbr} className={`mode ${mode === m ? 'on' : ''}`} onClick={() => pick(m, params)}>{label}</button>
          ))}
        </div>
      </div>
      <div className="side-foot">
        <button className="wizard-btn" onClick={onOpenWizard}>
          <Icon n="sparkles" /><span className="nlabel">Setup wizard</span>
        </button>
      </div>
    </aside>
  )
}

/* ---------------- PAGE HEADER ---------------- */
export function PageHead({ crumb, title, sub, children }) {
  return (
    <header className="phead">
      <div className="phead-l">
        <div className="crumb"><Icon n="zap" style={{ opacity: 0.6 }} />{crumb}</div>
        <h1>{title}</h1>
        {sub && <div className="phead-sub">{sub}</div>}
      </div>
      <div className="phead-r">{children}</div>
    </header>
  )
}

export function ServiceStatus({ status }) {
  const map = { connected: ['ok', 'Service online'], connecting: ['warn', 'Connecting…'], disconnected: ['bad', 'Service offline'] }
  const [cls, label] = map[status] || map.disconnected
  return <span className={`status-pill ${cls}`}><span className="dot" />{label}</span>
}

export function Transport({ online, onStart, onStop, onRestart }) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      <button className="btn btn-sm icon-btn" onClick={onStart} disabled={online} title="Start"><Icon n="play" /></button>
      <button className="btn btn-sm icon-btn" onClick={onStop} disabled={!online} title="Stop"><Icon n="square" /></button>
      <button className="btn btn-sm icon-btn" onClick={onRestart} title="Restart"><Icon n="rotate-cw" /></button>
    </div>
  )
}

export function Toasts({ toasts }) {
  return (
    <div className="toast-wrap">
      {toasts.map((t) => (
        <div className="toast" key={t.id}><Icon n="check-circle-2" />{t.msg}</div>
      ))}
    </div>
  )
}
