import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Icon, PageHead, ServiceStatus, Section, Empty, Toggle, Stepper, Swatch } from '../components/shell'

const N_DEFAULTS = {
  enabled: false, default_color: [255, 255, 255], brightness: 1.0, blink_count: 2, on_ms: 180, off_ms: 120,
  color_mode: 'icon', suppress_during_dnd: false, flash_when_locked: true, dedup_window_s: 5.0,
  min_flash_interval_s: 1.5, app_overrides: {}, keyword_rules: [],
}

let _rowId = 0
const nextId = () => (_rowId += 1)

// Brand-colour matching — mirrors ambilight/notifications/brand_colors.py so the UI
// suggests the same colour the flash will use. Returns [r,g,b] or null.
const BRAND_PREFIXES = ['microsoft', 'google', 'apple', 'amazon', 'meta']
const normName = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '')
const matchBrand = (name, map) => {
  if (!map) return null
  const n = normName(name)
  if (!n) return null
  if (map[n]) return map[n]
  for (const p of BRAND_PREFIXES) {
    if (n.startsWith(p) && n.length > p.length + 2) {
      const s = n.slice(p.length)
      if (map[s]) return map[s]
    }
  }
  return null
}
const sameRgb = (a, b) => Array.isArray(a) && Array.isArray(b) && a[0] === b[0] && a[1] === b[1] && a[2] === b[2]
const dotStyle = (rgb) => ({ width: 12, height: 12, borderRadius: 3, flex: '0 0 auto', background: `rgb(${rgb.join(',')})`, boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.25)' })

// Convert the persisted config shape ↔ an editable draft (app_overrides dict ↔ rows).
const toDraft = (n) => {
  const src = { ...N_DEFAULTS, ...(n || {}) }
  return {
    enabled: !!src.enabled,
    default_color: src.default_color || [255, 255, 255],
    brightness: Number(src.brightness ?? 1),
    blink_count: Number(src.blink_count ?? 2),
    on_ms: Number(src.on_ms ?? 180),
    off_ms: Number(src.off_ms ?? 120),
    color_mode: src.color_mode || 'icon',
    suppress_during_dnd: !!src.suppress_during_dnd,
    flash_when_locked: src.flash_when_locked !== false,
    dedup_window_s: Number(src.dedup_window_s ?? 5),
    min_flash_interval_s: Number(src.min_flash_interval_s ?? 1.5),
    overrides: Object.entries(src.app_overrides || {}).map(([app, color]) => ({ _id: nextId(), app, color })),
    keyword_rules: (src.keyword_rules || []).map((r) => ({ _id: nextId(), keyword: r.keyword || '', color: r.color || [255, 255, 255] })),
  }
}

const buildPayload = (d) => ({
  enabled: d.enabled, default_color: d.default_color, brightness: d.brightness, blink_count: d.blink_count,
  on_ms: d.on_ms, off_ms: d.off_ms, color_mode: d.color_mode, suppress_during_dnd: d.suppress_during_dnd,
  flash_when_locked: d.flash_when_locked, dedup_window_s: d.dedup_window_s, min_flash_interval_s: d.min_flash_interval_s,
  app_overrides: Object.fromEntries(d.overrides.filter((o) => o.app.trim()).map((o) => [o.app.trim(), o.color])),
  keyword_rules: d.keyword_rules.filter((r) => r.keyword.trim()).map((r) => ({ keyword: r.keyword.trim(), color: r.color })),
})

function PermissionBanner() {
  const [info, setInfo] = useState(null)
  useEffect(() => {
    let alive = true
    const tick = () => useStore.getState().notifPermission().then((r) => { if (alive) setInfo(r) }).catch(() => {})
    tick()
    const id = setInterval(tick, 4000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  if (!info) return null
  const status = info.status
  const platform = info.platform || ''
  if (status === 'granted') {
    return (
      <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px', borderColor: 'color-mix(in srgb,var(--good) 24%,transparent)', background: 'var(--good-bg)' }}>
        <Icon n="check-circle-2" style={{ color: 'var(--good)' }} /><span style={{ fontSize: 12.5, color: 'var(--good)', fontWeight: 500 }}>Notification access granted.</span>
      </div>
    )
  }
  const grantUrl = platform === 'darwin'
    ? 'x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles'
    : 'ms-settings:privacy-notifications'
  let text = 'Notification access is not granted — the flash won’t fire until it is.'
  if (status === 'unavailable') {
    text = platform === 'darwin'
      ? 'macOS notification reading needs Full Disk Access (best-effort; may break on OS updates).'
      : 'Notification listening is unavailable on this system (needs Windows 10+ with the winsdk component).'
  } else if (platform === 'darwin') {
    text = 'Grant Full Disk Access so notifications can be read (best-effort; may break on macOS updates).'
  }
  return (
    <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px', borderColor: 'color-mix(in srgb,var(--warn) 28%,transparent)', background: 'var(--warn-bg)' }}>
      <Icon n="alert-triangle" style={{ color: 'var(--warn)' }} />
      <span style={{ fontSize: 12.5, color: 'var(--warn)', minWidth: 0 }}>{text}</span>
      <button className="btn btn-sm" style={{ marginLeft: 'auto' }} onClick={() => window.api.system?.openExternal(grantUrl)}>Grant access</button>
    </div>
  )
}

export default function Notifications() {
  const { settings, updateSettings, saving, testFlash, toast, fetchBrandColors } = useStore()
  const brands = useStore((s) => s.brandColors)
  const [draft, setDraft] = useState(null)
  const [newApp, setNewApp] = useState('')
  const [newKw, setNewKw] = useState('')

  useEffect(() => { if (!settings) useStore.getState().fetchSettings() }, [])
  useEffect(() => { fetchBrandColors() }, [])
  useEffect(() => { if (settings) setDraft(toDraft(settings.notifications)) }, [settings])

  if (!draft) return <div className="main"><PageHead crumb="Configuration" title="Notifications" sub="Flash your lights on desktop alerts" /><div className="content content-narrow"><div className="card card-pad subtle">Loading…</div></div></div>

  const set = (patch) => setDraft((d) => ({ ...d, ...patch }))
  const payload = buildPayload(draft)
  const dirty = JSON.stringify(payload) !== JSON.stringify(buildPayload(toDraft(settings?.notifications)))
  const n = draft

  const newAppBrand = matchBrand(newApp, brands)
  const commitApp = () => { if (!newApp.trim()) return; set({ overrides: [...n.overrides, { _id: nextId(), app: newApp.trim(), color: newAppBrand || [120, 140, 255] }] }); setNewApp('') }
  const commitKw = () => { if (!newKw.trim()) return; set({ keyword_rules: [...n.keyword_rules, { _id: nextId(), keyword: newKw.trim(), color: [225, 48, 108] }] }); setNewKw('') }

  return (
    <div className="main">
      <PageHead crumb="Configuration" title="Notifications" sub="Flash your lights on desktop alerts">
        <ServiceStatus status={useStore.getState().status} />
        <button className={`btn ${dirty ? 'btn-primary' : ''}`} disabled={!dirty || saving} onClick={() => { updateSettings({ notifications: payload }); toast('Notification settings saved') }}><Icon n={dirty ? 'save' : 'check'} />{saving ? 'Saving…' : dirty ? 'Save' : 'Saved'}</button>
      </PageHead>

      <div className="content content-narrow page-enter">
        <div className="stack">
          <PermissionBanner />

          {/* master */}
          <div className="card card-pad" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div className="feat-ic"><Icon n="bell" /></div>
              <div><div style={{ fontSize: 15, fontWeight: 600 }}>Notification flash</div><div className="subtle" style={{ fontSize: 12.5 }}>Briefly flash the strip when a desktop notification arrives</div></div>
            </div>
            <Toggle checked={n.enabled} onChange={(v) => set({ enabled: v })} />
          </div>

          <div style={n.enabled ? {} : { opacity: 0.5, pointerEvents: 'none' }}>
            <div className="grid-2">
              <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div className="card-title" style={{ marginBottom: 8 }}>Flash appearance</div>
                <label className="field-row"><span className="fr-l">Colour mode</span>
                  <select className="field" style={{ maxWidth: 200 }} value={n.color_mode} onChange={(e) => set({ color_mode: e.target.value })}>
                    <option value="icon">Match app icon</option><option value="fixed">Fixed colour</option></select></label>
                <div className="field-row"><span className="fr-l">Default colour</span><Swatch rgb={n.default_color} onChange={(c) => set({ default_color: c })} /></div>
                <label className="field-row"><span className="fr-l">Brightness</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, maxWidth: 200 }}><input type="range" className="rng" style={{ flex: 1 }} min="0.1" max="1" step="0.05" value={n.brightness} onChange={(e) => set({ brightness: +e.target.value })} /><span className="mono" style={{ fontSize: 12, width: 34 }}>{Math.round(n.brightness * 100)}%</span></span></label>
              </div>
              <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div className="card-title" style={{ marginBottom: 8 }}>Timing</div>
                <div className="field-row"><span className="fr-l">Blink count</span><Stepper value={n.blink_count} onChange={(v) => set({ blink_count: v })} min={1} max={10} /></div>
                <label className="field-row"><span className="fr-l">On duration <small>{n.on_ms}ms</small></span>
                  <input type="range" className="rng" style={{ flex: 1, maxWidth: 170 }} min="50" max="600" step="10" value={n.on_ms} onChange={(e) => set({ on_ms: +e.target.value })} /></label>
                <label className="field-row"><span className="fr-l">Off duration <small>{n.off_ms}ms</small></span>
                  <input type="range" className="rng" style={{ flex: 1, maxWidth: 170 }} min="50" max="600" step="10" value={n.off_ms} onChange={(e) => set({ off_ms: +e.target.value })} /></label>
                <button className="btn btn-sm" style={{ alignSelf: 'flex-start', marginTop: 4 }} onClick={() => testFlash(n.default_color)}><Icon n="zap" />Test flash</button>
              </div>
            </div>

            <Section title="Behaviour" />
            <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column' }}>
              <div className="field-row"><span className="fr-l">Suppress during Do Not Disturb<small>Stay dark while Windows DND / Focus Assist is on</small></span><Toggle checked={n.suppress_during_dnd} onChange={(v) => set({ suppress_during_dnd: v })} /></div>
              <div className="hairline" />
              <div className="field-row"><span className="fr-l">Flash when screen locked<small>Allow flashes on the lock screen / while asleep</small></span><Toggle checked={n.flash_when_locked} onChange={(v) => set({ flash_when_locked: v })} /></div>
              <div className="hairline" />
              <div className="field-row"><span className="fr-l">De-dup window<small>Ignore repeat notifications within this window</small></span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Stepper value={n.dedup_window_s} onChange={(v) => set({ dedup_window_s: v })} min={0} max={60} /><span className="subtle">s</span></span></div>
              <div className="hairline" />
              <div className="field-row"><span className="fr-l">Min interval between flashes<small>Rate-limit bursts of alerts</small></span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Stepper value={n.min_flash_interval_s} onChange={(v) => set({ min_flash_interval_s: v })} min={0} max={30} /><span className="subtle">s</span></span></div>
            </div>

            <Section title="Per-app colours" count={n.overrides.length} />
            <div className="stack">
              <div className="hint">Known apps already flash in their official brand colour automatically — no need to add them. Add an app here only to <em>override</em> its colour. When you type a recognised app below, its brand colour is pre-filled.</div>
              {n.overrides.length === 0 ? <div className="card"><Empty icon="app-window" title="No app overrides">Add a custom colour for specific apps to override their automatic brand colour.</Empty></div> :
                <div className="tile-grid">
                  {n.overrides.map((o, i) => {
                    const rowBrand = matchBrand(o.app, brands)
                    const applied = rowBrand && sameRgb(o.color, rowBrand)
                    return (
                    <div key={o._id} className="card card-pad" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0, flex: 1 }}>
                        <Swatch rgb={o.color} onChange={(c) => set({ overrides: n.overrides.map((x, idx) => (idx === i ? { ...x, color: c } : x)) })} />
                        <input className="field" style={{ flex: 1 }} placeholder="app name or id" value={o.app} onChange={(e) => set({ overrides: n.overrides.map((x, idx) => (idx === i ? { ...x, app: e.target.value } : x)) })} />
                      </div>
                      {rowBrand && (applied
                        ? <span className="badge" title="Matches this app’s official brand colour" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11.5, padding: '3px 8px', borderRadius: 999, background: 'var(--bg-2,rgba(127,127,127,.12))', color: 'var(--tx-2)' }}><span style={dotStyle(rowBrand)} />Brand</span>
                        : <button type="button" className="btn btn-sm" title="Use this app’s official brand colour" onClick={() => set({ overrides: n.overrides.map((x, idx) => (idx === i ? { ...x, color: rowBrand } : x)) })} style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={dotStyle(rowBrand)} />Use brand</button>)}
                      <button className="btn btn-sm btn-danger icon-btn" onClick={() => set({ overrides: n.overrides.filter((_, idx) => idx !== i) })}><Icon n="trash-2" /></button>
                    </div>
                  )})}
                </div>}
              <div style={{ display: 'flex', gap: 10 }}><input className="field" placeholder="App name (e.g. Discord)" value={newApp} onChange={(e) => setNewApp(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && commitApp()} /><button className="btn btn-primary" onClick={commitApp}><Icon n="plus" />Add app</button></div>
              {newAppBrand && <div className="hint" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={dotStyle(newAppBrand)} />Brand colour found — it’ll be applied when you add “{newApp.trim()}”.</div>}
            </div>

            <Section title="Keyword rules" count={n.keyword_rules.length} />
            <div className="stack">
              <div className="hint">Phone notifications forwarded by Phone Link / Link to Windows appear as “Phone Link”. Recognised apps named in the alert (e.g. Instagram, WhatsApp) now flash in their brand colour automatically. Add a rule only for apps that aren’t recognised, or to override one: match a word in the text (e.g. <span className="mono" style={{ color: 'var(--tx-2)' }}>instagram</span>) — checked against app name, title and body.</div>
              {n.keyword_rules.length > 0 && (
                <div className="tile-grid">
                  {n.keyword_rules.map((k, i) => (
                    <div key={k._id} className="card card-pad" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
                        <Swatch rgb={k.color} onChange={(c) => set({ keyword_rules: n.keyword_rules.map((x, idx) => (idx === i ? { ...x, color: c } : x)) })} />
                        <input className="field mono" style={{ flex: 1 }} placeholder="text contains…" value={k.keyword} onChange={(e) => set({ keyword_rules: n.keyword_rules.map((x, idx) => (idx === i ? { ...x, keyword: e.target.value } : x)) })} />
                      </div>
                      <button className="btn btn-sm btn-danger icon-btn" onClick={() => set({ keyword_rules: n.keyword_rules.filter((_, idx) => idx !== i) })}><Icon n="trash-2" /></button>
                    </div>
                  ))}
                </div>
              )}
              <div style={{ display: 'flex', gap: 10 }}><input className="field" placeholder="Keyword (e.g. urgent)" value={newKw} onChange={(e) => setNewKw(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && commitKw()} /><button className="btn btn-primary" onClick={commitKw}><Icon n="plus" />Add rule</button></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
