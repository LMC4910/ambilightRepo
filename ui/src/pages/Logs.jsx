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
    <section className="glass-panel" style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', gap: '0.5rem' }}>
        <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Terminal size={20} /> Logs</h3>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <select className="input" value={level} onChange={(e) => setLevel(e.target.value)} style={{ width: 'auto' }}>
            {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: 8, top: 9, color: 'var(--text-muted)' }} />
            <input className="input" placeholder="Search…" value={query} onChange={(e) => setQuery(e.target.value)} style={{ paddingLeft: '1.6rem', width: '160px' }} />
          </div>
          <button onClick={() => window.api.logs.openFolder()} className="button" style={{ padding: '0.4rem 0.7rem', background: 'rgba(255,255,255,0.1)', width: 'auto' }} title="Open log folder"><FolderOpen size={16} /></button>
          <button onClick={handleClear} className="button" style={{ padding: '0.4rem 0.7rem', background: 'rgba(239,68,68,0.2)', color: 'var(--accent-red)', width: 'auto' }} title="Clear logs"><Trash2 size={16} /></button>
        </div>
      </div>
      <div style={{ flex: 1, background: '#000', borderRadius: '8px', padding: '1rem', overflowY: 'auto', fontFamily: 'monospace', fontSize: '0.78rem', whiteSpace: 'pre-wrap', color: '#a3be8c' }}>
        {lines.length ? lines.join('\n') : 'No matching log lines.'}
        <div ref={endRef} />
      </div>
    </section>
  )
}
