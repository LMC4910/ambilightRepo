import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Icon, PageHead, ServiceStatus, Section, Empty, Toggle, Stepper, Swatch } from '../components/shell'

const G_DEFAULTS = {
  enabled: false, client_id: '', scopes: ['notifications', 'read:org', 'repo'],
  poll_interval_s: 60, watch_notifications: true, watched_repos: [], watched_orgs: [],
  default_color: [88, 166, 255], brightness: 1.0, blink_count: 2, on_ms: 180, off_ms: 120,
  rules: [], webhook_enabled: false, webhook_secret_set: false,
}

// Event types the rule editor offers (''/any first). Mirrors the normaliser's taxonomy.
const EVENT_TYPES = [
  ['', 'Any event'], ['workflow_run', 'Workflow run (CI)'], ['pull_request', 'Pull request'],
  ['pull_request_review', 'Pull request review'], ['review_comment', 'Review comment'],
  ['issue', 'Issue'], ['issue_comment', 'Issue comment'], ['release', 'Release'],
  ['push', 'Push'], ['branch', 'Branch create/delete'], ['fork', 'Fork'], ['star', 'Star'],
  ['discussion', 'Discussion'], ['discussion_comment', 'Discussion comment'],
  ['commit_comment', 'Commit comment'], ['deployment', 'Deployment'],
  ['deployment_status', 'Deployment status'], ['workflow_job', 'Workflow job'],
  ['check_run', 'Check run'], ['repository_invitation', 'Repository invitation'],
  ['security_alert', 'Security alert'],
]
// Common actions, surfaced as a datalist hint (the field is free-text).
const COMMON_ACTIONS = ['success', 'failure', 'cancelled', 'opened', 'merged', 'closed',
  'published', 'review_requested', 'assigned', 'mentioned', 'created']

let _gid = 0
const gid = () => (_gid += 1)

const toDraft = (g) => {
  const s = { ...G_DEFAULTS, ...(g || {}) }
  return {
    enabled: !!s.enabled,
    client_id: s.client_id || '',
    scopes: s.scopes || G_DEFAULTS.scopes,
    poll_interval_s: Number(s.poll_interval_s ?? 60),
    watch_notifications: s.watch_notifications !== false,
    watched_repos: [...(s.watched_repos || [])],
    watched_orgs: [...(s.watched_orgs || [])],
    default_color: s.default_color || [88, 166, 255],
    brightness: Number(s.brightness ?? 1),
    blink_count: Number(s.blink_count ?? 2),
    on_ms: Number(s.on_ms ?? 180),
    off_ms: Number(s.off_ms ?? 120),
    rules: (s.rules || []).map((r) => ({ _id: gid(), ...r })),
    webhook_enabled: !!s.webhook_enabled,
    webhook_secret_set: !!s.webhook_secret_set,
  }
}

const buildPayload = (d) => ({
  enabled: d.enabled, client_id: d.client_id.trim(), scopes: d.scopes,
  poll_interval_s: d.poll_interval_s, watch_notifications: d.watch_notifications,
  watched_repos: d.watched_repos.map((r) => r.trim()).filter(Boolean),
  watched_orgs: d.watched_orgs.map((o) => o.trim()).filter(Boolean),
  default_color: d.default_color, brightness: d.brightness,
  blink_count: d.blink_count, on_ms: d.on_ms, off_ms: d.off_ms,
  rules: d.rules.map(({ _id, ...r }) => ({
    scope: r.scope || 'global', repo: r.repo || '', org: r.org || '', workflow: r.workflow || '',
    event_type: r.event_type || '', action: (r.action || '').trim(), color: r.color || d.default_color,
    ...(r.blink_count != null ? { blink_count: r.blink_count } : {}),
  })),
  webhook_enabled: d.webhook_enabled, webhook_secret_set: d.webhook_secret_set,
})

const relTime = (ts) => {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - (ts || 0)))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

/* ---------------- Connect panel (OAuth device flow) ---------------- */
function ConnectPanel({ status, onChanged }) {
  const { githubAuthStart, githubLogout } = useStore()
  const [prompt, setPrompt] = useState(null)
  const [busy, setBusy] = useState(false)

  const connected = status?.auth_state === 'connected'
  const pending = status?.auth_state === 'pending'

  // While pending, the backend exposes the live code in /status; prefer it.
  useEffect(() => {
    if (pending && status?.user_code) {
      setPrompt({ user_code: status.user_code, verification_uri: status.verification_uri })
    }
    if (connected) setPrompt(null)
  }, [pending, connected, status?.user_code])

  const start = async () => {
    setBusy(true)
    const r = await githubAuthStart()
    setBusy(false)
    if (r) setPrompt(r)
  }

  if (connected) {
    return (
      <div className="card card-pad" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div className="feat-ic"><Icon n="github" /></div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>Connected{status.account ? ` as ${status.account}` : ''}</div>
            <div className="subtle" style={{ fontSize: 12.5 }}>
              {status.rate_remaining >= 0 ? `API budget ${status.rate_remaining}/${status.rate_limit} · ` : ''}
              {status.watched_repos} repo{status.watched_repos === 1 ? '' : 's'} watched
            </div>
          </div>
        </div>
        <button className="btn btn-sm btn-danger" onClick={async () => { await githubLogout(); onChanged?.() }}>
          <Icon n="log-out" />Disconnect
        </button>
      </div>
    )
  }

  if (!status?.httpx_available) {
    return (
      <div className="card card-pad" style={{ borderColor: 'color-mix(in srgb,var(--warn) 28%,transparent)', background: 'var(--warn-bg)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Icon n="alert-triangle" style={{ color: 'var(--warn)' }} />
          <span style={{ fontSize: 12.5, color: 'var(--warn)' }}>
            The GitHub integration needs the <span className="mono">httpx</span> package. Install it (<span className="mono">pip install httpx</span>) and restart the service.
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div className="feat-ic"><Icon n="github" /></div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>Connect your GitHub account</div>
          <div className="subtle" style={{ fontSize: 12.5 }}>Sign in with the device flow — no password leaves your machine.</div>
        </div>
        {!prompt && <button className="btn btn-primary" disabled={busy} onClick={start}><Icon n="github" />{busy ? 'Starting…' : 'Connect'}</button>}
      </div>

      {!status?.client_id_configured && (
        <div className="hint" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Icon n="info" />No OAuth client id configured. Set <span className="mono">github.client_id</span> (or the <span className="mono">AMBILIGHT_GITHUB_CLIENT_ID</span> env var) to your GitHub OAuth App.
        </div>
      )}

      {prompt && (
        <div className="card card-pad" style={{ background: 'var(--bg-2,rgba(127,127,127,.08))', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="subtle" style={{ fontSize: 12.5 }}>1 · Copy this code, then 2 · open GitHub and paste it:</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span className="mono" style={{ fontSize: 22, letterSpacing: 3, fontWeight: 700 }}>{prompt.user_code}</span>
            <button className="btn btn-sm" onClick={() => navigator.clipboard?.writeText(prompt.user_code)}><Icon n="copy" />Copy</button>
            <button className="btn btn-sm btn-primary" onClick={() => window.api.system?.openExternal(prompt.verification_uri || 'https://github.com/login/device')}>
              <Icon n="external-link" />Open GitHub
            </button>
          </div>
          <div className="subtle" style={{ fontSize: 12 }}>Waiting for authorisation… this page updates automatically once you approve.</div>
        </div>
      )}
    </div>
  )
}

/* ---------------- Recent events ---------------- */
function RecentEvents() {
  const { githubEvents } = useStore()
  const [events, setEvents] = useState([])
  useEffect(() => {
    let alive = true
    const tick = () => githubEvents(25).then((e) => { if (alive) setEvents(e || []) }).catch(() => {})
    tick()
    const id = setInterval(tick, 5000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  if (!events.length) return <div className="card"><Empty icon="inbox" title="No events yet">Activity from your watched repos will appear here.</Empty></div>
  return (
    <div className="stack">
      {events.map((e) => (
        <div key={e.id} className="card card-pad" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, flex: '0 0 auto', background: e.priority === 'critical' ? '#e5484d' : e.priority === 'high' ? '#f5a623' : 'var(--accent)' }} />
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.title}</div>
            <div className="subtle" style={{ fontSize: 11.5 }}>{e.repository || e.account} · {e.event_type}/{e.action}</div>
          </div>
          <span className="subtle" style={{ fontSize: 11.5, flex: '0 0 auto' }}>{relTime(e.timestamp)}</span>
        </div>
      ))}
    </div>
  )
}

/* ---------------- Rule editor row ---------------- */
function RuleRow({ rule, onChange, onDelete }) {
  const scope = rule.scope || 'global'
  return (
    <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Swatch rgb={rule.color || [88, 166, 255]} onChange={(c) => onChange({ ...rule, color: c })} />
        <select className="field" style={{ maxWidth: 130 }} value={scope} onChange={(e) => onChange({ ...rule, scope: e.target.value })}>
          <option value="global">Global</option><option value="org">Organisation</option>
          <option value="repo">Repository</option><option value="workflow">Workflow</option>
        </select>
        <select className="field" style={{ maxWidth: 170 }} value={rule.event_type || ''} onChange={(e) => onChange({ ...rule, event_type: e.target.value })}>
          {EVENT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <input className="field" style={{ maxWidth: 150 }} list="gh-actions" placeholder="action (any)" value={rule.action || ''} onChange={(e) => onChange({ ...rule, action: e.target.value })} />
        <button className="btn btn-sm btn-danger icon-btn" style={{ marginLeft: 'auto' }} onClick={onDelete}><Icon n="trash-2" /></button>
      </div>
      {(scope === 'repo' || scope === 'workflow') && (
        <div style={{ display: 'flex', gap: 8 }}>
          <input className="field mono" style={{ flex: 1 }} placeholder="owner/repo" value={rule.repo || ''} onChange={(e) => onChange({ ...rule, repo: e.target.value })} />
          {scope === 'workflow' && <input className="field" style={{ flex: 1 }} placeholder="workflow name (e.g. Deploy)" value={rule.workflow || ''} onChange={(e) => onChange({ ...rule, workflow: e.target.value })} />}
        </div>
      )}
      {scope === 'org' && (
        <input className="field" placeholder="organisation login" value={rule.org || ''} onChange={(e) => onChange({ ...rule, org: e.target.value })} />
      )}
    </div>
  )
}

/* ---------------- String-list editor (watched repos / orgs) ---------------- */
function ListEditor({ items, onChange, placeholder, mono }) {
  const [val, setVal] = useState('')
  const add = () => { const v = val.trim(); if (!v) return; onChange([...items, v]); setVal('') }
  return (
    <div className="stack">
      {items.length > 0 && (
        <div className="tile-grid">
          {items.map((it, i) => (
            <div key={i} className="card card-pad" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <input className={`field ${mono ? 'mono' : ''}`} style={{ flex: 1 }} value={it} onChange={(e) => onChange(items.map((x, idx) => (idx === i ? e.target.value : x)))} />
              <button className="btn btn-sm btn-danger icon-btn" onClick={() => onChange(items.filter((_, idx) => idx !== i))}><Icon n="trash-2" /></button>
            </div>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', gap: 10 }}>
        <input className={`field ${mono ? 'mono' : ''}`} placeholder={placeholder} value={val} onChange={(e) => setVal(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()} />
        <button className="btn btn-primary" onClick={add}><Icon n="plus" />Add</button>
      </div>
    </div>
  )
}

/* ============================ PAGE ============================ */
export default function Github({ onBack }) {
  const { settings, updateSettings, saving, toast, githubTest, githubStatus, fetchGithubStatus } = useStore()
  const [draft, setDraft] = useState(null)

  useEffect(() => { if (!settings) useStore.getState().fetchSettings() }, [])
  useEffect(() => { if (settings) setDraft(toDraft(settings.github)) }, [settings])

  // Poll connection status (so the device flow flips to "connected" live).
  useEffect(() => {
    let alive = true
    const tick = () => { if (alive) fetchGithubStatus() }
    tick()
    const id = setInterval(tick, 3000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  if (!draft) {
    return (
      <div className="main">
        <PageHead crumb="Integrations" title="GitHub" />
        <div className="content content-narrow"><div className="card card-pad subtle">Loading…</div></div>
      </div>
    )
  }

  const set = (patch) => setDraft((d) => ({ ...d, ...patch }))
  const payload = buildPayload(draft)
  const dirty = JSON.stringify(payload) !== JSON.stringify(buildPayload(toDraft(settings?.github)))
  const g = draft

  return (
    <div className="main">
      <PageHead crumb="Integrations" title="GitHub" sub="Light up on GitHub activity">
        <button className="btn btn-sm" onClick={onBack}><Icon n="arrow-left" />Integrations</button>
        <ServiceStatus status={useStore.getState().status} />
        <button className={`btn ${dirty ? 'btn-primary' : ''}`} disabled={!dirty || saving}
          onClick={() => { updateSettings({ github: payload }); toast('GitHub settings saved') }}>
          <Icon n={dirty ? 'save' : 'check'} />{saving ? 'Saving…' : dirty ? 'Save' : 'Saved'}
        </button>
      </PageHead>

      <datalist id="gh-actions">{COMMON_ACTIONS.map((a) => <option key={a} value={a} />)}</datalist>

      <div className="content content-narrow page-enter">
        <div className="stack">
          <ConnectPanel status={githubStatus} onChanged={fetchGithubStatus} />

          {/* master enable */}
          <div className="card card-pad" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div className="feat-ic"><Icon n="zap" /></div>
              <div><div style={{ fontSize: 15, fontWeight: 600 }}>Ambient GitHub awareness</div><div className="subtle" style={{ fontSize: 12.5 }}>Flash the strip when GitHub activity arrives</div></div>
            </div>
            <Toggle checked={g.enabled} onChange={(v) => set({ enabled: v })} />
          </div>

          <div style={g.enabled ? {} : { opacity: 0.5, pointerEvents: 'none' }}>
            {/* watched */}
            <Section title="What to watch" />
            <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column' }}>
              <div className="field-row"><span className="fr-l">Notifications inbox<small>Mentions, review requests, assignments, CI you follow</small></span><Toggle checked={g.watch_notifications} onChange={(v) => set({ watch_notifications: v })} /></div>
              <div className="hairline" />
              <div className="field-row"><span className="fr-l">Poll interval<small>How often to check (honours GitHub's pacing)</small></span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Stepper value={g.poll_interval_s} onChange={(v) => set({ poll_interval_s: v })} min={15} max={3600} /><span className="subtle">s</span></span></div>
            </div>

            <Section title="Watched repositories" count={g.watched_repos.length} />
            <div className="hint">CI workflow runs and the activity feed are polled for each repo you list (e.g. <span className="mono">octocat/hello-world</span>).</div>
            <ListEditor items={g.watched_repos} onChange={(v) => set({ watched_repos: v })} placeholder="owner/repo" mono />

            <Section title="Watched organisations" count={g.watched_orgs.length} />
            <ListEditor items={g.watched_orgs} onChange={(v) => set({ watched_orgs: v })} placeholder="organisation login" />

            {/* appearance */}
            <Section title="Default light" />
            <div className="grid-2">
              <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div className="card-title" style={{ marginBottom: 8 }}>Colour</div>
                <div className="field-row"><span className="fr-l">Default colour<small>Used when no rule matches</small></span><Swatch rgb={g.default_color} onChange={(c) => set({ default_color: c })} /></div>
                <label className="field-row"><span className="fr-l">Brightness</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, maxWidth: 200 }}><input type="range" className="rng" style={{ flex: 1 }} min="0.1" max="1" step="0.05" value={g.brightness} onChange={(e) => set({ brightness: +e.target.value })} /><span className="mono" style={{ fontSize: 12, width: 34 }}>{Math.round(g.brightness * 100)}%</span></span></label>
              </div>
              <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div className="card-title" style={{ marginBottom: 8 }}>Timing</div>
                <div className="field-row"><span className="fr-l">Blink count</span><Stepper value={g.blink_count} onChange={(v) => set({ blink_count: v })} min={1} max={10} /></div>
                <label className="field-row"><span className="fr-l">On <small>{g.on_ms}ms</small></span><input type="range" className="rng" style={{ flex: 1, maxWidth: 170 }} min="50" max="600" step="10" value={g.on_ms} onChange={(e) => set({ on_ms: +e.target.value })} /></label>
                <label className="field-row"><span className="fr-l">Off <small>{g.off_ms}ms</small></span><input type="range" className="rng" style={{ flex: 1, maxWidth: 170 }} min="50" max="600" step="10" value={g.off_ms} onChange={(e) => set({ off_ms: +e.target.value })} /></label>
                <button className="btn btn-sm" style={{ alignSelf: 'flex-start', marginTop: 4 }} onClick={() => githubTest(g.default_color)}><Icon n="zap" />Test flash</button>
              </div>
            </div>

            {/* rules */}
            <Section title="Colour rules" count={g.rules.length} />
            <div className="hint">Rules are matched most-specific first: <strong>workflow → repository → organisation → global</strong>. A blank action matches any. Example: a <em>repository</em> rule for <span className="mono">workflow_run</span> + <span className="mono">failure</span> → red.</div>
            {g.rules.length === 0
              ? <div className="card"><Empty icon="palette" title="No colour rules">Add rules to paint specific events. Unmatched events use the default colour above.</Empty></div>
              : <div className="stack">{g.rules.map((r, i) => (
                  <RuleRow key={r._id} rule={r}
                    onChange={(nr) => set({ rules: g.rules.map((x, idx) => (idx === i ? { ...nr, _id: x._id } : x)) })}
                    onDelete={() => set({ rules: g.rules.filter((_, idx) => idx !== i) })} />
                ))}</div>}
            <button className="btn btn-primary" style={{ marginTop: 10 }}
              onClick={() => set({ rules: [...g.rules, { _id: gid(), scope: 'global', event_type: 'workflow_run', action: 'failure', color: [220, 40, 40] }] })}>
              <Icon n="plus" />Add rule
            </button>

            {/* recent */}
            <Section title="Recent events" />
            <RecentEvents />
          </div>
        </div>
      </div>
    </div>
  )
}
