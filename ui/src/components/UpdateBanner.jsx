import React, { useEffect, useState } from 'react'
import { Download, RefreshCw, X } from 'lucide-react'

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
    <div className="glass-panel rounded-2xl flex items-center gap-3 px-4 py-3 animate-fade-up" style={{ borderLeft: '3px solid #6366f1' }}>
      <Download className="w-4 h-4 text-indigo-400 shrink-0" />
      <span className="flex-1 text-sm text-slate-300">
        {ready ? `Update ${version ? `v${version} ` : ''}ready to install.`
          : state === 'downloading' ? `Downloading update… ${percent ?? 0}%`
          : `Update ${version ? `v${version} ` : ''}available — downloading…`}
      </span>
      {ready && (
        <button onClick={() => window.api.updater.install()}
          className="btn-neon-blue px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2">
          <RefreshCw className="w-4 h-4" /> Restart to update
        </button>
      )}
      <button onClick={() => setDismissed(true)} title="Dismiss"
        className="p-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-400"><X className="w-4 h-4" /></button>
    </div>
  )
}
