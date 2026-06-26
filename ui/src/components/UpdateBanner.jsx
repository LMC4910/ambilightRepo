import React, { useEffect, useState } from 'react'
import { Icon } from './shell'

/** Thin banner surfacing electron-updater state pushed from the main process. */
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
  if (dismissed || !['available', 'downloading', 'downloaded'].includes(state)) return null
  const ready = state === 'downloaded'

  return (
    <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', borderLeft: '3px solid var(--accent)' }}>
      <Icon n="download" style={{ color: 'var(--accent)' }} />
      <span style={{ flex: 1, fontSize: 12.5, color: 'var(--tx-2)' }}>
        {ready ? `Update ${version ? `v${version} ` : ''}ready to install.`
          : state === 'downloading' ? `Downloading update… ${percent ?? 0}%`
            : `Update ${version ? `v${version} ` : ''}available — downloading…`}
      </span>
      {ready && (
        <button className="btn btn-sm btn-primary" onClick={() => window.api.updater.install()}>
          <Icon n="rotate-cw" />Restart to update
        </button>
      )}
      <button className="btn btn-sm icon-btn" onClick={() => setDismissed(true)} title="Dismiss"><Icon n="x" /></button>
    </div>
  )
}
