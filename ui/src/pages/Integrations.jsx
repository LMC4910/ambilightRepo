import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Icon, PageHead } from '../components/shell'
import Github from './Github'

// Integration registry. GitHub is live; the rest are placeholders for the
// roadmap (Gmail, Outlook, Discord, …) so the hub communicates where this goes.
const INTEGRATIONS = [
  { id: 'github', name: 'GitHub', icon: 'github', available: true,
    desc: 'Light up on CI runs, pull requests, issues, releases & security alerts.' },
  { id: 'gmail', name: 'Gmail', icon: 'mail', available: false, desc: 'Flash on new important mail. Coming soon.' },
  { id: 'outlook', name: 'Outlook', icon: 'mail', available: false, desc: 'Flash on new important mail. Coming soon.' },
  { id: 'discord', name: 'Discord', icon: 'message-circle', available: false, desc: 'Mentions & DMs. Coming soon.' },
]

export default function Integrations() {
  const { githubStatus, fetchGithubStatus } = useStore()
  const [view, setView] = useState('hub')

  useEffect(() => { fetchGithubStatus() }, [])

  if (view === 'github') return <Github onBack={() => setView('hub')} />

  const statusFor = (id) => {
    if (id !== 'github' || !githubStatus) return null
    if (githubStatus.auth_state === 'connected') {
      return { cls: 'ok', label: githubStatus.account ? `Connected · ${githubStatus.account}` : 'Connected' }
    }
    if (githubStatus.enabled) return { cls: 'warn', label: 'Enabled · not connected' }
    return null
  }

  return (
    <div className="main">
      <PageHead crumb="Configuration" title="Integrations" sub="Turn activity from your tools into ambient light" />
      <div className="content page-enter">
        <div className="tile-grid">
          {INTEGRATIONS.map((it) => {
            const st = statusFor(it.id)
            return (
              <button key={it.id} className="card card-pad" disabled={!it.available}
                onClick={() => it.available && setView(it.id)}
                style={{ textAlign: 'left', width: '100%', opacity: it.available ? 1 : 0.55, cursor: it.available ? 'pointer' : 'default' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div className="feat-ic"><Icon n={it.icon} /></div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', minWidth: 0 }}>
                      <span style={{ fontWeight: 600 }}>{it.name}</span>
                      {st && (
                        <span className={`status-pill ${st.cls}`} title={st.label}
                          style={{ fontSize: 11, minWidth: 0, maxWidth: '100%' }}>
                          <span className="dot" style={{ flex: '0 0 auto' }} />
                          <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{st.label}</span>
                        </span>
                      )}
                    </div>
                    <div className="subtle" style={{ fontSize: 12.5 }}>{it.desc}</div>
                  </div>
                  {it.available
                    ? <Icon n="chevron-right" style={{ opacity: 0.5 }} />
                    : <span className="badge" style={{ fontSize: 11, padding: '3px 8px', borderRadius: 999 }}>Soon</span>}
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
