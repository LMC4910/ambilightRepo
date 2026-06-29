import React, { useEffect, useState, useRef, useCallback } from 'react'
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
// Fallback actions used only if the backend taxonomy (/api/github/meta) can't be
// reached; normally the per-event action list comes from the server.
const COMMON_ACTIONS = ['success', 'failure', 'cancelled', 'opened', 'merged', 'closed',
  'published', 'review_requested', 'assigned', 'mentioned', 'created']

// Mirror of config.py DEFAULT_GITHUB_RULES — used by the "Restore defaults" button
// to merge any missing defaults into the current rule list (skipping duplicates).
const DEFAULT_RULES = [
  { scope: 'global', event_type: 'workflow_run', action: 'failure', color: [220, 38, 38], blink_count: 4 },
  { scope: 'global', event_type: 'workflow_run', action: 'success', color: [34, 197, 94] },
  { scope: 'global', event_type: 'workflow_run', action: 'cancelled', color: [148, 163, 184] },
  { scope: 'global', event_type: 'workflow_run', action: 'in_progress', color: [234, 179, 8] },
  { scope: 'global', event_type: 'workflow_job', action: 'in_progress', color: [234, 179, 8] },
  { scope: 'global', event_type: 'workflow_job', action: 'completed', color: [148, 163, 184] },
  { scope: 'global', event_type: 'check_run', action: 'created', color: [56, 189, 248] },
  { scope: 'global', event_type: 'check_run', action: 'completed', color: [148, 163, 184] },
  { scope: 'global', event_type: 'pull_request', action: 'opened', color: [59, 130, 246] },
  { scope: 'global', event_type: 'pull_request', action: 'merged', color: [168, 85, 247] },
  { scope: 'global', event_type: 'pull_request', action: 'closed', color: [148, 163, 184] },
  { scope: 'global', event_type: 'pull_request', action: 'review_requested', color: [192, 132, 252] },
  { scope: 'global', event_type: 'pull_request_review', action: '', color: [192, 132, 252] },
  { scope: 'global', event_type: 'review_comment', action: '', color: [129, 140, 248] },
  { scope: 'global', event_type: 'issue', action: 'opened', color: [6, 182, 212] },
  { scope: 'global', event_type: 'issue', action: 'assigned', color: [14, 165, 233] },
  { scope: 'global', event_type: 'issue', action: 'closed', color: [22, 101, 52] },
  { scope: 'global', event_type: 'issue_comment', action: '', color: [56, 189, 248] },
  { scope: 'global', event_type: '', action: 'mentioned', color: [249, 115, 22], blink_count: 3 },
  { scope: 'global', event_type: '', action: 'review_requested', color: [192, 132, 252] },
  { scope: 'global', event_type: '', action: 'assigned', color: [14, 165, 233] },
  { scope: 'global', event_type: 'release', action: '', color: [250, 204, 21] },
  { scope: 'global', event_type: 'push', action: '', color: [100, 116, 139] },
  { scope: 'global', event_type: 'branch', action: 'created', color: [52, 211, 153] },
  { scope: 'global', event_type: 'branch', action: 'deleted', color: [148, 163, 184] },
  { scope: 'global', event_type: 'star', action: '', color: [250, 204, 21] },
  { scope: 'global', event_type: 'fork', action: '', color: [125, 211, 252] },
  { scope: 'global', event_type: 'discussion', action: '', color: [45, 212, 191] },
  { scope: 'global', event_type: 'discussion_comment', action: '', color: [20, 184, 166] },
  { scope: 'global', event_type: 'commit_comment', action: '', color: [14, 165, 233] },
  { scope: 'global', event_type: 'deployment', action: '', color: [99, 102, 241] },
  { scope: 'global', event_type: 'deployment_status', action: '', color: [79, 70, 229] },
  { scope: 'global', event_type: 'repository_invitation', action: '', color: [251, 191, 36], blink_count: 3 },
  { scope: 'global', event_type: 'security_alert', action: '', color: [239, 68, 68], blink_count: 6, on_ms: 120, off_ms: 80 },
]

// Stable identity of a rule's match target (mirrors the backend dedup signature).
const ruleSig = (r) => [r.scope || 'global', r.event_type || '', (r.action || '').trim(),
  r.repo || '', r.org || '', r.workflow || ''].map((s) => String(s).toLowerCase()).join('|')

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
    ...(r.on_ms != null ? { on_ms: r.on_ms } : {}),
    ...(r.off_ms != null ? { off_ms: r.off_ms } : {}),
    ...(r.brightness != null ? { brightness: r.brightness } : {}),
  })),
  // NB: webhook_enabled / webhook_secret_set are intentionally omitted — the live
  // webhook state is owned by the enable/disable endpoints (WebhookPanel), and
  // the config is deep-merged on save, so leaving them out preserves that state.
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

/* ---------------- Webhooks (event-driven delivery) ----------------
   Webhooks make GitHub push activity instantly instead of polling. Because the
   app is loopback-only, enabling opens a cloudflared tunnel and auto-registers a
   hook on each repo the user administers; those repos then stop being polled.
   The notifications inbox and non-admin repos keep polling. */
const HOOK_BADGE = {
  registered: { cls: 'ok', icon: 'check', text: 'Webhook' },
  'needs-admin': { cls: 'warn', icon: 'alert-triangle', text: 'No admin · polling' },
  'polling-fallback': { cls: 'subtle', icon: 'rotate-ccw', text: 'Polling' },
  error: { cls: 'danger', icon: 'x', text: 'Error · polling' },
}

function HookBadge({ name, state }) {
  const b = HOOK_BADGE[state] || HOOK_BADGE['polling-fallback']
  const color = b.cls === 'ok' ? 'var(--ok,#22c55e)' : b.cls === 'warn' ? 'var(--warn,#f5a623)'
    : b.cls === 'danger' ? 'var(--err,#e5484d)' : 'var(--muted,#94a3b8)'
  return (
    <div className="card card-pad" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span className="mono" style={{ flex: 1, fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5, color }}>
        <Icon n={b.icon} />{b.text}
      </span>
    </div>
  )
}

function WebhookPanel({ status, connected, watchedRepos, watchedOrgs }) {
  const { githubWebhookEnable, githubWebhookDisable } = useStore()
  const [busy, setBusy] = useState(false)
  // `running` = tunnel up (so we show its URL + hook badges even if no repo is
  // covered yet, e.g. all need admin); `active` = at least one hook registered.
  const running = !!status?.tunnel_running
  const active = !!status?.webhook_active
  const url = status?.tunnel_public_url || ''
  const err = status?.tunnel_error || ''
  const hookStatus = status?.hook_status || {}

  const toggle = async (on) => {
    setBusy(true)
    if (on) await githubWebhookEnable()
    else await githubWebhookDisable()
    setBusy(false)
  }

  if (!connected) {
    return <div className="hint"><Icon n="info" />Connect your GitHub account to enable instant webhook delivery.</div>
  }

  return (
    <div className="stack">
      <div className="card card-pad" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div className="feat-ic"><Icon n="zap" /></div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>Instant delivery (webhooks)<span className="subtle" style={{ fontSize: 11, fontWeight: 500, marginLeft: 8 }}>beta</span></div>
            <div className="subtle" style={{ fontSize: 12.5 }}>
              {busy ? (running ? 'Disabling…' : 'Opening tunnel & registering hooks…')
                : active ? 'GitHub pushes events instantly — covered repos stop being polled.'
                : running ? 'Tunnel is up, but no watched repo could be hooked yet (admin needed) — still polling.'
                : 'Replace polling with push for repos you admin. Opens a local cloudflared tunnel.'}
            </div>
          </div>
        </div>
        <Toggle checked={running || (busy && !running)} disabled={busy} onChange={(v) => toggle(v)} />
      </div>

      {err && (
        <div className="card card-pad" style={{ borderColor: 'color-mix(in srgb,var(--warn) 28%,transparent)', background: 'var(--warn-bg)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon n="alert-triangle" style={{ color: 'var(--warn)' }} />
            <span style={{ fontSize: 12.5, color: 'var(--warn)' }}>{err} — staying on polling.</span>
          </div>
        </div>
      )}

      {running && url && (
        <div className="card card-pad" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Icon n="link" />
          <span className="subtle" style={{ fontSize: 12 }}>Public endpoint</span>
          <span className="mono" style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{url}/api/github/webhook</span>
          {status?.last_delivery_ts > 0 && <span className="subtle" style={{ fontSize: 11.5 }}>last delivery {relTime(status.last_delivery_ts)}</span>}
        </div>
      )}

      {running && (watchedRepos.length > 0 || watchedOrgs.length > 0) && (
        <div className="tile-grid">
          {watchedRepos.map((r) => <HookBadge key={r} name={r} state={hookStatus[r]} />)}
          {watchedOrgs.map((o) => <HookBadge key={`org:${o}`} name={o} state={hookStatus[`org:${o}`]} />)}
        </div>
      )}

      <div className="hint" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Icon n="info" />Org-wide webhooks need re-authorising with the <span className="mono">admin:org_hook</span> scope. Repos you don't administer keep polling. The notifications inbox always polls.
      </div>
    </div>
  )
}

/* ---------------- Select-or-type combo box ----------------
   Renders a <select> populated from `options`; an "Other…" entry (when
   allowCustom) flips it to a free-text input so private/uncached values still
   work. Options are strings or [value, label] pairs. */
function Combo({ value, onChange, options, emptyLabel, placeholder, style, mono, allowCustom = true }) {
  const opts = (options || []).map((o) => (Array.isArray(o) ? o : [String(o), String(o)])).filter(([v]) => v !== '')
  const v = value || ''
  const known = v === '' || opts.some(([ov]) => ov === v)
  const [typing, setTyping] = useState(allowCustom && !!v && !known)
  // If the value becomes a custom one externally, drop into typing mode.
  useEffect(() => { if (allowCustom && v && !opts.some(([ov]) => ov === v)) setTyping(true) }, [v]) // eslint-disable-line

  if (typing) {
    return (
      <span style={{ display: 'flex', gap: 4, alignItems: 'center', ...style }}>
        <input className={`field ${mono ? 'mono' : ''}`} style={{ flex: 1, minWidth: 0 }} placeholder={placeholder}
          value={v} onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="btn btn-sm icon-btn" title="Pick from list" onClick={() => setTyping(false)}><Icon n="list" /></button>
      </span>
    )
  }
  return (
    <select className="field" style={style} value={known ? v : ''}
      onChange={(e) => (e.target.value === '__custom__' ? setTyping(true) : onChange(e.target.value))}>
      <option value="">{emptyLabel || '— select —'}</option>
      {opts.map(([ov, ol]) => <option key={ov} value={ov}>{ol}</option>)}
      {allowCustom && <option value="__custom__">Other…</option>}
    </select>
  )
}

/* ---------------- Watched repo/org picker ----------------
   Adds entries by selecting from the account's repos/orgs; an edit toggle
   exposes a manual fallback for items not in the fetched list. */
function WatchedPicker({ items, onChange, options, placeholder = 'owner/repo', mono = true, label = 'item' }) {
  const [sel, setSel] = useState('')
  const [manual, setManual] = useState('')
  const [typing, setTyping] = useState(false)
  const available = (options || []).filter((n) => !items.includes(n))
  const add = (val) => { const t = String(val || '').trim(); if (t && !items.includes(t)) onChange([...items, t]); setSel(''); setManual('') }
  const cls = `field ${mono ? 'mono' : ''}`
  return (
    <div className="stack">
      {items.length > 0 && (
        <div className="tile-grid">
          {items.map((it, i) => (
            <div key={i} className="card card-pad" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span className={mono ? 'mono' : ''} style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis' }}>{it}</span>
              <button className="btn btn-sm btn-danger icon-btn" onClick={() => onChange(items.filter((_, idx) => idx !== i))}><Icon n="trash-2" /></button>
            </div>
          ))}
        </div>
      )}
      {typing ? (
        <div style={{ display: 'flex', gap: 10 }}>
          <input className={cls} style={{ flex: 1 }} placeholder={placeholder} value={manual}
            onChange={(e) => setManual(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add(manual)} />
          <button className="btn btn-primary" onClick={() => add(manual)}><Icon n="plus" />Add</button>
          <button className="btn btn-sm icon-btn" title="Pick from list" onClick={() => { setTyping(false); setManual('') }}><Icon n="list" /></button>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 10 }}>
          <select className={cls} style={{ flex: 1 }} value={sel} onChange={(e) => setSel(e.target.value)}>
            <option value="">{available.length ? `Select a ${label}…` : (options && options.length ? `All loaded ${label}s added` : 'Connect GitHub to load')}</option>
            {available.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <button className="btn btn-primary" disabled={!sel} onClick={() => add(sel)}><Icon n="plus" />Add</button>
          <button className="btn btn-sm icon-btn" title="Type manually" onClick={() => setTyping(true)}><Icon n="edit-3" /></button>
        </div>
      )}
    </div>
  )
}

/* ---------------- Rule editor row ---------------- */
function RuleRow({ rule, onChange, onDelete, eventTypes, actionsByEvent, repos, orgs, workflows, onNeedWorkflows }) {
  const scope = rule.scope || 'global'
  const repoOpts = (repos || []).map((r) => r.full_name || r)
  const orgOpts = (orgs || []).map((o) => o.login || o)
  const wfOpts = (workflows || []).map((w) => w.name || w)
  const evtPairs = (eventTypes && eventTypes.length ? eventTypes : EVENT_TYPES).filter(([v]) => v !== '')
  const actsForEvent = (actionsByEvent && actionsByEvent[rule.event_type || '']) || COMMON_ACTIONS

  // Lazily load the workflow names for whichever repo this rule targets.
  useEffect(() => {
    if (scope === 'workflow' && rule.repo) onNeedWorkflows?.(rule.repo)
  }, [scope, rule.repo]) // eslint-disable-line

  return (
    <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Swatch rgb={rule.color || [88, 166, 255]} onChange={(c) => onChange({ ...rule, color: c })} />
        <select className="field" style={{ maxWidth: 130 }} value={scope} onChange={(e) => {
          // Clear fields the new scope doesn't use so buildPayload()/ruleSig()
          // don't persist or dedupe on stale repo/org/workflow values.
          const nextScope = e.target.value
          onChange({
            ...rule,
            scope: nextScope,
            org: nextScope === 'org' ? rule.org : '',
            repo: (nextScope === 'repo' || nextScope === 'workflow') ? rule.repo : '',
            workflow: nextScope === 'workflow' ? rule.workflow : '',
          })
        }}>
          <option value="global">Global</option><option value="org">Organisation</option>
          <option value="repo">Repository</option><option value="workflow">Workflow</option>
        </select>
        <Combo style={{ maxWidth: 175 }} value={rule.event_type || ''} emptyLabel="Any event" allowCustom={false}
          options={evtPairs} onChange={(v) => onChange({ ...rule, event_type: v })} />
        <Combo style={{ maxWidth: 165 }} value={rule.action || ''} emptyLabel="Any action"
          options={actsForEvent} placeholder="action" onChange={(v) => onChange({ ...rule, action: v })} />
        <button className="btn btn-sm btn-danger icon-btn" style={{ marginLeft: 'auto' }} onClick={onDelete}><Icon n="trash-2" /></button>
      </div>
      {(scope === 'repo' || scope === 'workflow') && (
        <div style={{ display: 'flex', gap: 8 }}>
          <Combo style={{ flex: 1 }} mono value={rule.repo || ''} emptyLabel="Select repository…"
            options={repoOpts} placeholder="owner/repo" onChange={(v) => onChange({ ...rule, repo: v, workflow: '' })} />
          {scope === 'workflow' && (
            <Combo style={{ flex: 1 }} value={rule.workflow || ''}
              emptyLabel={rule.repo ? 'Any workflow' : 'Pick a repository first'}
              options={wfOpts} placeholder="workflow name" onChange={(v) => onChange({ ...rule, workflow: v })} />
          )}
        </div>
      )}
      {scope === 'org' && (
        <Combo value={rule.org || ''} emptyLabel="Select organisation…" options={orgOpts}
          placeholder="organisation login" onChange={(v) => onChange({ ...rule, org: v })} />
      )}
    </div>
  )
}

/* ============================ PAGE ============================ */
export default function Github({ onBack }) {
  const { settings, updateSettings, saving, toast, githubTest, githubStatus, fetchGithubStatus,
    githubRepos, githubOrgs, githubMeta, githubWorkflows } = useStore()
  const [draft, setDraft] = useState(null)
  const [repos, setRepos] = useState([])
  const [orgs, setOrgs] = useState([])
  const [meta, setMeta] = useState(null)
  const [wfByRepo, setWfByRepo] = useState({})
  const wfRequested = useRef(new Set())

  const connected = githubStatus?.auth_state === 'connected'

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

  // The rule taxonomy is static — fetch it once so the dropdowns work even
  // before a connection (and independent of GitHub auth).
  useEffect(() => { githubMeta().then((m) => m && setMeta(m)).catch(() => {}) }, [])

  // Repos + orgs need an authenticated connection; (re)load when it comes up.
  // On disconnect, drop the previous account's catalogs so the editor never
  // shows its private repo/org/workflow names after logout or an account switch.
  useEffect(() => {
    if (!connected) {
      setRepos([])
      setOrgs([])
      setWfByRepo({})
      wfRequested.current.clear()
      return
    }
    let alive = true
    githubRepos().then((r) => { if (alive) setRepos(r || []) }).catch(() => {})
    githubOrgs().then((o) => { if (alive) setOrgs(o || []) }).catch(() => {})
    return () => { alive = false }
  }, [connected])

  // Lazily load a repo's workflow names the first time a rule targets it. Mark
  // the repo as requested only after a successful fetch, so a transient failure
  // isn't cached as "no workflows" and the repo can be retried later.
  const ensureWorkflows = useCallback((repo) => {
    if (!repo || !connected || wfRequested.current.has(repo)) return
    githubWorkflows(repo)
      .then((list) => {
        wfRequested.current.add(repo)
        setWfByRepo((m) => ({ ...m, [repo]: list || [] }))
      })
      .catch(() => {})
  }, [connected, githubWorkflows])

  const evtPairs = (meta?.event_types?.length ? meta.event_types.map((e) => [e.value, e.label]) : EVENT_TYPES)
  const actionsByEvent = meta?.actions_by_event || null
  const repoNames = repos.map((r) => r.full_name || r)
  const orgNames = orgs.map((o) => o.login || o)

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
            <div className="hint">CI workflow runs and the activity feed are polled for each repo you pick{connected ? '' : ' (connect to load your repositories)'}.</div>
            <WatchedPicker items={g.watched_repos} onChange={(v) => set({ watched_repos: v })} options={repoNames} placeholder="owner/repo" mono label="repository" />

            <Section title="Watched organisations" count={g.watched_orgs.length} />
            <WatchedPicker items={g.watched_orgs} onChange={(v) => set({ watched_orgs: v })} options={orgNames} placeholder="organisation login" mono={false} label="organisation" />

            {/* webhooks (event-driven delivery) */}
            <Section title="Delivery" />
            {/* Hooks/polling act on the *saved* config, so the panel reflects the
                persisted watches — not the unsaved draft (which may differ). */}
            <WebhookPanel status={githubStatus} connected={connected}
              watchedRepos={settings?.github?.watched_repos || []}
              watchedOrgs={settings?.github?.watched_orgs || []} />

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
            <div className="hint">Rules are matched most-specific first: <strong>workflow → repository → organisation → global</strong>. A blank action matches any. Pick the event and action from the menus — for a CI failure choose <span className="mono">workflow_run</span> + <span className="mono">failure</span>.</div>
            {g.rules.length === 0
              ? <div className="card"><Empty icon="palette" title="No colour rules">Add rules to paint specific events, or restore the built-in defaults. Unmatched events use the default colour above.</Empty></div>
              : <div className="stack">{g.rules.map((r, i) => (
                  <RuleRow key={r._id} rule={r}
                    eventTypes={evtPairs} actionsByEvent={actionsByEvent}
                    repos={repos} orgs={orgs} workflows={wfByRepo[r.repo] || []} onNeedWorkflows={ensureWorkflows}
                    onChange={(nr) => set({ rules: g.rules.map((x, idx) => (idx === i ? { ...nr, _id: x._id } : x)) })}
                    onDelete={() => set({ rules: g.rules.filter((_, idx) => idx !== i) })} />
                ))}</div>}
            <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
              <button className="btn btn-primary"
                onClick={() => set({ rules: [...g.rules, { _id: gid(), scope: 'global', event_type: 'workflow_run', action: 'failure', color: [220, 40, 40] }] })}>
                <Icon n="plus" />Add rule
              </button>
              <button className="btn" title="Add any built-in default rules you're missing (your custom rules are kept)"
                onClick={() => {
                  const seen = new Set(g.rules.map(ruleSig))
                  const added = DEFAULT_RULES.filter((r) => !seen.has(ruleSig(r))).map((r) => ({ _id: gid(), ...r }))
                  if (!added.length) { toast('All default rules are already present'); return }
                  set({ rules: [...g.rules, ...added] })
                  toast(`Added ${added.length} default rule${added.length === 1 ? '' : 's'}`)
                }}>
                <Icon n="rotate-ccw" />Restore defaults
              </button>
            </div>

            {/* recent */}
            <Section title="Recent events" />
            <RecentEvents />
          </div>
        </div>
      </div>
    </div>
  )
}
