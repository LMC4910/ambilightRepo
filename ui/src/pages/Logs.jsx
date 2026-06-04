import React, { useEffect, useState, useRef } from 'react'
import { Terminal, FolderOpen, Trash2, Search } from 'lucide-react'

const LEVELS = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR']

export default function Logs() {
  const [raw, setRaw] = useState('')
  const [level, setLevel] = useState('ALL')
  const [query, setQuery] = useState('')
  const endRef = useRef(null)

  useEffect(() => {
    const fetchLogs = async () => setRaw(await window.api.logs.read())
    fetchLogs()
    const timer = setInterval(fetchLogs, 2000)
    return () => clearInterval(timer)
  }, [])

  const lines = raw.split('\n').filter((ln) => {
    if (level !== 'ALL' && !ln.includes(level)) return false
    if (query && !ln.toLowerCase().includes(query.toLowerCase())) return false
    return true
  })

  useEffect(() => { if (endRef.current) endRef.current.scrollIntoView() }, [raw])
  const handleClear = async () => { await window.api.logs.clear(); setRaw('') }

  return (
    <section className="glass-panel rounded-3xl p-8 flex flex-col animate-fade-up" style={{ height: 'calc(100vh - 8rem)' }}>
      <div className="flex justify-between items-center mb-5 gap-3 flex-wrap">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2"><Terminal className="w-5 h-5 text-indigo-400" /> Logs</h3>
        <div className="flex gap-2 items-center">
          <select className="custom-input rounded-xl px-3 py-2 text-sm" value={level} onChange={(e) => setLevel(e.target.value)}>
            {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input className="custom-input rounded-xl pl-9 pr-3 py-2 text-sm w-44" placeholder="Search…" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <button onClick={() => window.api.logs.openFolder()} title="Open log folder"
            className="px-3 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300"><FolderOpen className="w-4 h-4" /></button>
          <button onClick={handleClear} title="Clear logs" className="btn-neon-red px-3 py-2 rounded-xl"><Trash2 className="w-4 h-4" /></button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto rounded-xl border border-white/5 bg-black/40 p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap text-emerald-300/90">
        {lines.length ? lines.join('\n') : 'No matching log lines.'}
        <div ref={endRef} />
      </div>
    </section>
  )
}
