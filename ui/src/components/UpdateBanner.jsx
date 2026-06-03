import React, { useEffect, useState } from 'react'
import { Download, RefreshCw, X } from 'lucide-react'

/**
 * Thin banner that surfaces electron-updater state pushed from the main process.
 * Stays hidden while idle / in dev (no update feed). Shows download progress and,
 * once an update is downloaded, a "Restart to update" action.
 */
export default function UpdateBanner() {
  const [st, setSt] = useState({ state: 'idle' })
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    if (!window.api?.updater) return undefined
    window.api.updater.status().then(setSt).catch(() => {})
    const unsub = window.api.updater.onStatus((s) => { setSt(s); setDismissed(false) })
    return unsub
  }, [])

  const { state, version, percent } = st
  // Only the actionable / in-flight states are worth a banner.
  if (dismissed || !['available', 'downloading', 'downloaded'].includes(state)) return null

  const ready = state === 'downloaded'
  return (
    <div className="glass-panel" style={{
      display: 'flex', alignItems: 'center', gap: '0.75rem',
      padding: '0.6rem 1rem', borderLeft: '3px solid var(--accent-purple, #863bff)',
    }}>
      <Download size={16} color="var(--accent-purple, #863bff)" />
      <span style={{ flex: 1, fontSize: '0.9rem' }}>
        {ready
          ? `Update ${version ? `v${version} ` : ''}ready to install.`
          : state === 'downloading'
            ? `Downloading update… ${percent ?? 0}%`
            : `Update ${version ? `v${version} ` : ''}available — downloading…`}
      </span>
      {ready && (
        <button className="button" style={{ width: 'auto', padding: '0.4rem 0.8rem' }}
          onClick={() => window.api.updater.install()}>
          <RefreshCw size={14} /> Restart to update
        </button>
      )}
      <button className="button" title="Dismiss"
        style={{ width: 'auto', padding: '0.4rem', background: 'rgba(255,255,255,0.1)' }}
        onClick={() => setDismissed(true)}><X size={14} /></button>
    </div>
  )
}
