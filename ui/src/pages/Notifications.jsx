import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Bell, Save, Plus, Trash2, Zap, AlertTriangle, CheckCircle2, Smartphone } from 'lucide-react'
import Toggle from '../components/Toggle'

const N_DEFAULTS = {
  enabled: false,
  default_color: [255, 255, 255],
  brightness: 1.0,
  blink_count: 2,
  on_ms: 180,
  off_ms: 120,
  color_mode: 'icon',
  suppress_during_dnd: false,
  flash_when_locked: true,
  dedup_window_s: 5.0,
  min_flash_interval_s: 1.5,
  app_overrides: {},
  keyword_rules: [],
}

// Monotonic id source for stable React keys on editable rows (index keys cause
// input/focus to jump to the wrong row when items are removed).
let _rowId = 0
const nextId = () => (_rowId += 1)

const clamp = (n) => Math.max(0, Math.min(255, Math.round(Number(n) || 0)))
const rgbToHex = (rgb) => '#' + (rgb || [255, 255, 255]).map((c) => clamp(c).toString(16).padStart(2, '0')).join('')
const hexToRgb = (hex) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '')
  if (!m) return [255, 255, 255]
  const n = parseInt(m[1], 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

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
  enabled: d.enabled,
  default_color: d.default_color,
  brightness: d.brightness,
  blink_count: d.blink_count,
  on_ms: d.on_ms,
  off_ms: d.off_ms,
  color_mode: d.color_mode,
  suppress_during_dnd: d.suppress_during_dnd,
  flash_when_locked: d.flash_when_locked,
  dedup_window_s: d.dedup_window_s,
  min_flash_interval_s: d.min_flash_interval_s,
  app_overrides: Object.fromEntries(
    d.overrides.filter((o) => o.app.trim()).map((o) => [o.app.trim(), o.color])
  ),
  keyword_rules: d.keyword_rules.filter((r) => r.keyword.trim()).map((r) => ({ keyword: r.keyword.trim(), color: r.color })),
})

function ColorSwatch({ value, onChange }) {
  return (
    <input type="color" value={rgbToHex(value)} onChange={(e) => onChange(hexToRgb(e.target.value))}
      className="w-9 h-9 rounded-lg bg-transparent border border-white/10 cursor-pointer p-0.5" />
  )
}

function PermissionBanner() {
  const [info, setInfo] = useState(null)

  useEffect(() => {
    let alive = true
    // Access the store method via getState() so it doesn't need to be an effect
    // dependency (Zustand methods are stable; this keeps exhaustive-deps quiet).
    const tick = () => useStore.getState().notifPermission().then((r) => { if (alive) setInfo(r) }).catch(() => {})
    tick()
    const id = setInterval(tick, 4000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  if (!info) return null
  const status = info.status
  const platform = info.platform || ''
  const ok = status === 'granted'
  if (ok) {
    return (
      <div className="flex items-center gap-2 border px-3 py-2 rounded-xl text-xs font-medium bg-emerald-500/10 border-emerald-500/20 text-emerald-300">
        <CheckCircle2 className="w-4 h-4 shrink-0" /> Notification access granted.
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
    <div className="flex items-center gap-2 border px-3 py-2 rounded-xl text-xs font-medium bg-amber-500/10 border-amber-500/30 text-amber-300">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      <span className="min-w-0">{text}</span>
      <button onClick={() => window.api.system?.openExternal(grantUrl)}
        className="ml-auto shrink-0 px-2.5 py-1 rounded bg-white/5 border border-white/10 hover:bg-white/10 text-slate-200">
        Grant access
      </button>
    </div>
  )
}

function NumField({ label, value, onChange, step = 1, min = 0, suffix }) {
  return (
    <label className="flex items-center gap-3 text-sm">
      <span className="text-slate-400 min-w-[150px]">{label}</span>
      <input type="number" step={step} min={min} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="custom-input rounded-lg px-2 py-1.5 text-sm w-28" />
      {suffix && <span className="text-xs text-slate-500">{suffix}</span>}
    </label>
  )
}

export default function Notifications() {
  const { settings, updateSettings, saving, testFlash } = useStore()
  const [draft, setDraft] = useState(null)

  // getState() avoids listing the (stable) store method as an effect dependency.
  useEffect(() => { if (!settings) useStore.getState().fetchSettings() }, [])
  useEffect(() => { if (settings) setDraft(toDraft(settings.notifications)) }, [settings])

  if (!draft) return null
  const set = (patch) => setDraft((d) => ({ ...d, ...patch }))
  const payload = buildPayload(draft)
  const dirty = JSON.stringify(payload) !== JSON.stringify(buildPayload(toDraft(settings?.notifications)))

  // override rows (keyed by stable _id)
  const setOverride = (id, key, val) => set({ overrides: draft.overrides.map((o) => (o._id === id ? { ...o, [key]: val } : o)) })
  const addOverride = () => set({ overrides: [...draft.overrides, { _id: nextId(), app: '', color: [255, 255, 255] }] })
  const removeOverride = (id) => set({ overrides: draft.overrides.filter((o) => o._id !== id) })
  // keyword rules
  const setRule = (id, key, val) => set({ keyword_rules: draft.keyword_rules.map((r) => (r._id === id ? { ...r, [key]: val } : r)) })
  const addRule = () => set({ keyword_rules: [...draft.keyword_rules, { _id: nextId(), keyword: '', color: [255, 105, 180] }] })
  const removeRule = (id) => set({ keyword_rules: draft.keyword_rules.filter((r) => r._id !== id) })

  return (
    <section className="glass-panel rounded-3xl p-8 flex flex-col gap-5 animate-fade-up">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2"><Bell className="w-5 h-5 text-indigo-400" /> Notification Flash</h3>
        <Toggle checked={draft.enabled} onChange={(v) => set({ enabled: v })} label="Enabled" />
      </div>

      <p className="text-xs text-slate-500 -mt-2">
        Briefly flash the lights when an app notification arrives — so you catch it even in fullscreen,
        during Do Not Disturb, or while the screen is locked. Defaults to the app icon’s colour; override per app below.
      </p>

      <PermissionBanner />

      {/* Flash appearance */}
      <div className="glass-panel rounded-2xl p-5 flex flex-col gap-3">
        <h4 className="text-sm font-semibold text-white">Flash appearance</h4>

        <label className="flex items-center gap-3 text-sm">
          <span className="text-slate-400 min-w-[150px]">Colour source</span>
          <select className="custom-input rounded-lg px-2 py-1.5 text-sm" value={draft.color_mode}
            onChange={(e) => set({ color_mode: e.target.value })}>
            <option value="icon">App icon colour</option>
            <option value="fixed">Always the default colour</option>
          </select>
        </label>

        <label className="flex items-center gap-3 text-sm">
          <span className="text-slate-400 min-w-[150px]">Default / fallback colour</span>
          <ColorSwatch value={draft.default_color} onChange={(c) => set({ default_color: c })} />
        </label>

        <label className="flex items-center gap-3 text-sm">
          <span className="text-slate-400 min-w-[150px]">Brightness</span>
          <input type="range" min="0" max="1" step="0.05" value={draft.brightness}
            onChange={(e) => set({ brightness: Number(e.target.value) })} className="flex-1 max-w-[240px]" />
          <span className="text-xs text-slate-500 w-10">{Math.round(draft.brightness * 100)}%</span>
        </label>

        <NumField label="Blinks" value={draft.blink_count} onChange={(v) => set({ blink_count: v })} min={1} />
        <NumField label="On duration" value={draft.on_ms} onChange={(v) => set({ on_ms: v })} step={10} min={20} suffix="ms" />
        <NumField label="Off duration" value={draft.off_ms} onChange={(v) => set({ off_ms: v })} step={10} min={0} suffix="ms" />

        <button onClick={() => testFlash(draft.default_color)}
          className="self-start mt-1 btn-neon-blue px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2">
          <Zap className="w-4 h-4" /> Test flash
        </button>
      </div>

      {/* Behaviour */}
      <div className="glass-panel rounded-2xl p-5 flex flex-col gap-3">
        <h4 className="text-sm font-semibold text-white">Behaviour</h4>
        <Toggle checked={draft.flash_when_locked} onChange={(v) => set({ flash_when_locked: v })}
          label="Flash even when the screen is locked or asleep" />
        <Toggle checked={draft.suppress_during_dnd} onChange={(v) => set({ suppress_during_dnd: v })}
          label="Suppress during Do Not Disturb / Focus Assist" />
        <NumField label="De-dup window" value={draft.dedup_window_s} onChange={(v) => set({ dedup_window_s: v })} step={0.5} suffix="s" />
        <NumField label="Min gap between flashes" value={draft.min_flash_interval_s} onChange={(v) => set({ min_flash_interval_s: v })} step={0.5} suffix="s" />
      </div>

      {/* Per-app overrides */}
      <div className="glass-panel rounded-2xl p-5 flex flex-col gap-3">
        <h4 className="text-sm font-semibold text-white">Per-app colours</h4>
        <p className="text-xs text-slate-500">Pin a colour for a specific app (matched by its name or id).</p>
        {draft.overrides.length === 0 && <div className="text-xs text-slate-500">No overrides — the icon colour is used.</div>}
        {draft.overrides.map((o) => (
          <div key={o._id} className="flex gap-2 items-center">
            <input className="custom-input rounded-lg px-2 py-1.5 text-sm flex-1" placeholder="app name or id (e.g. Discord)"
              value={o.app} onChange={(e) => setOverride(o._id, 'app', e.target.value)} />
            <ColorSwatch value={o.color} onChange={(c) => setOverride(o._id, 'color', c)} />
            <button onClick={() => removeOverride(o._id)} aria-label="Remove app override" title="Remove app override" className="btn-neon-red px-2.5 py-1.5 rounded-lg"><Trash2 className="w-4 h-4" /></button>
          </div>
        ))}
        <button onClick={addOverride} className="self-start px-4 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-sm flex items-center gap-2"><Plus className="w-4 h-4" /> Add app</button>
      </div>

      {/* Keyword rules (Phone Link / forwarded) */}
      <div className="glass-panel rounded-2xl p-5 flex flex-col gap-3">
        <h4 className="text-sm font-semibold text-white flex items-center gap-2"><Smartphone className="w-4 h-4 text-indigo-400" /> Keyword rules (phone / forwarded)</h4>
        <p className="text-xs text-slate-500">
          Phone notifications forwarded by Phone Link appear as “Phone Link”. Match a word in the notification text
          (e.g. <span className="font-mono">instagram</span>) to give it a colour. Matched against the app name, title and body.
        </p>
        {draft.keyword_rules.length === 0 && <div className="text-xs text-slate-500">No keyword rules yet.</div>}
        {draft.keyword_rules.map((r) => (
          <div key={r._id} className="flex gap-2 items-center">
            <input className="custom-input rounded-lg px-2 py-1.5 text-sm flex-1" placeholder="text contains… (e.g. instagram)"
              value={r.keyword} onChange={(e) => setRule(r._id, 'keyword', e.target.value)} />
            <ColorSwatch value={r.color} onChange={(c) => setRule(r._id, 'color', c)} />
            <button onClick={() => removeRule(r._id)} aria-label="Remove keyword rule" title="Remove keyword rule" className="btn-neon-red px-2.5 py-1.5 rounded-lg"><Trash2 className="w-4 h-4" /></button>
          </div>
        ))}
        <button onClick={addRule} className="self-start px-4 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-sm flex items-center gap-2"><Plus className="w-4 h-4" /> Add rule</button>
      </div>

      <button onClick={() => updateSettings({ notifications: payload })} disabled={!dirty || saving}
        className="btn-neon-blue px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 self-end disabled:opacity-40">
        <Save className="w-4 h-4" /> {saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
      </button>
    </section>
  )
}
