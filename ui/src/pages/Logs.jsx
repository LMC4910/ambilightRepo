import React, { useEffect, useRef, useState } from 'react'
import { Icon, PageHead, Empty } from '../components/shell'

const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
const LEVEL_STYLE = {
  DEBUG: ['#7d8597', 'var(--s3)'], INFO: ['#5fa8d8', 'rgba(95,168,216,.12)'],
  WARNING: ['var(--warn)', 'var(--warn-bg)'], ERROR: ['var(--bad)', 'var(--bad-bg)'], CRITICAL: ['var(--bad)', 'var(--bad-bg)'],
}

// The service writes a plain-text log file; we tail it and best-effort split each
// line into time / level / message for the styled view (raw fallback otherwise).
function parseLine(line) {
  const lvl = (line.match(/\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b/) || [])[1] || null
  const ts = (line.match(/^\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)/) || [])[1] || ''
  const msg = ts ? line.slice(line.indexOf(ts) + ts.length).replace(/^[\s,|-]+/, '') : line
  return { raw: line, lvl, ts, msg }
}

export default function Logs() {
  const [raw, setRaw] = useState('')
  const [level, setLevel] = useState('ALL')
  const [query, setQuery] = useState('')
  const [autoscroll, setAuto] = useState(true)
  const boxRef = useRef(null)

  useEffect(() => {
    const fetchLogs = async () => { try { setRaw(await window.api.logs.read()) } catch (e) { /* offline */ } }
    fetchLogs()
    const timer = setInterval(fetchLogs, 2000)
    return () => clearInterval(timer)
  }, [])

  const lines = raw.split('\n').filter((ln) => {
    if (!ln) return false
    if (level !== 'ALL' && !ln.includes(level)) return false
    if (query && !ln.toLowerCase().includes(query.toLowerCase())) return false
    return true
  })

  useEffect(() => { if (autoscroll && boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight }, [raw, autoscroll, lines.length])

  const handleClear = async () => { await window.api.logs.clear(); setRaw('') }

  return (
    <div className="main">
      <PageHead crumb="System" title="Logs" sub="Live service output">
        <button className="btn btn-sm" onClick={() => window.api.logs.openFolder()}><Icon n="folder-open" />Open folder</button>
        <button className="btn btn-sm btn-danger" onClick={handleClear}><Icon n="trash-2" />Clear</button>
      </PageHead>

      <div className="content page-enter" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexShrink: 0 }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Icon n="search" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--faint)', pointerEvents: 'none' }} />
            <input className="field" style={{ paddingLeft: 36 }} placeholder="Filter logs…" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <select className="field" style={{ width: 140 }} value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="ALL">All levels</option>{LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <button className={`btn ${autoscroll ? 'btn-primary' : ''}`} onClick={() => setAuto((a) => !a)}><Icon n="arrow-down-to-line" />Auto-scroll</button>
        </div>

        <div ref={boxRef} className="card logbox">
          {lines.length === 0 ? <Empty icon="terminal" title="No matching log lines">Adjust your filter or level to see output.</Empty> :
            lines.map((ln, i) => {
              const p = parseLine(ln)
              const [c, bg] = LEVEL_STYLE[p.lvl] || LEVEL_STYLE.INFO
              return (
                <div key={i} className="logline">
                  {p.ts && <span className="lt">{p.ts}</span>}
                  {p.lvl ? <span className="ll" style={{ color: c, background: bg }}>{p.lvl}</span> : null}
                  <span className="lm">{p.lvl || p.ts ? p.msg : ln}</span>
                </div>
              )
            })}
        </div>
      </div>
    </div>
  )
}
