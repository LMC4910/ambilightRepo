import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Icon, PageHead, Swatch, Stepper } from '../components/shell'

const fmtRGB = (c) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`

// Which controls each mode exposes + defaults (mirrors the legacy Effects page).
const FIELDS = {
  static: ['color'], breathing: ['color', 'speed'], rainbow: ['speed'], candle: ['speed'],
  ocean: ['speed'], ambient: ['speed'], sunrise: ['duration'], sunset: ['duration'], custom: ['sequence', 'speed'],
}
const DEFAULTS = {
  static: { r: 255, g: 60, b: 0 }, breathing: { r: 0, g: 120, b: 255, speed: 1.0 },
  rainbow: { speed: 1.0 }, candle: { speed: 1.0 }, ocean: { speed: 1.0 }, ambient: { speed: 1.0 },
  sunrise: { duration: 300 }, sunset: { duration: 300 },
  custom: { colors: [[255, 0, 0], [0, 255, 0], [0, 0, 255]], speed: 1.0 },
}

const PREVIEW = {
  rainbow: 'linear-gradient(90deg,#ef4444,#f59e0b,#22c55e,#06b6d4,#6366f1,#a855f7)',
  candle: 'linear-gradient(90deg,#7a3a0a,#f0902a,#ffcb6b,#f0902a)',
  ocean: 'linear-gradient(90deg,#063a6b,#2a86d6,#5fc9e8,#2a86d6)',
  ambient: 'linear-gradient(90deg,#5a3fa6,#7a7fe6,#c98ad6)',
  sunrise: 'linear-gradient(90deg,#1a1f3a,#7a4fa0,#f0902a,#f5b53a)',
  sunset: 'linear-gradient(90deg,#f5b53a,#ef6a52,#7a4fa0,#1a1f3a)',
}
const ICONS = { static: 'square', breathing: 'activity', rainbow: 'rainbow', candle: 'flame', ocean: 'waves', ambient: 'cloud', sunrise: 'sunrise', sunset: 'sunset' }
const TITLES = { static: 'Static colour', breathing: 'Breathing', rainbow: 'Rainbow', candle: 'Candle', ocean: 'Ocean', ambient: 'Ambient', sunrise: 'Sunrise', sunset: 'Sunset' }

function EffectCard({ id, onApply, colorPreview, children }) {
  return (
    <div className="card">
      <div className="card-h"><h3><Icon n={ICONS[id]} />{TITLES[id]}</h3>
        <button className="btn btn-sm" onClick={onApply}><Icon n="play" />Apply</button></div>
      <div className="card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {colorPreview && <div className="effect-prev" style={{ background: colorPreview }} />}
        {children}
      </div>
    </div>
  )
}

function SpeedRow({ value, onChange }) {
  const v = value ?? 1
  return (
    <label className="field-row" style={{ padding: 0, gap: 14 }}>
      <span className="fr-l" style={{ whiteSpace: 'nowrap' }}>Speed</span>
      <input type="range" className="rng" style={{ flex: 1 }} min="0.1" max="3" step="0.1" value={v} onChange={(ev) => onChange(+ev.target.value)} />
      <span className="mono" style={{ fontSize: 12, width: 34 }}>{v.toFixed(1)}×</span>
    </label>
  )
}

export default function Effects() {
  const { settings, fetchSettings, updateSettings, saving, setMode, toast } = useStore()
  const [draft, setDraft] = useState(null)

  useEffect(() => { if (!settings) fetchSettings() }, [])
  useEffect(() => {
    if (!settings) return
    const saved = settings.effects?.params || {}
    const merged = {}
    for (const k of Object.keys(FIELDS)) merged[k] = { ...DEFAULTS[k], ...(saved[k] || {}) }
    setDraft(merged)
  }, [settings])

  if (!draft) {
    return (
      <div className="main">
        <PageHead crumb="Configuration" title="Effects" sub="Tune the look of each lighting mode" />
        <div className="content"><div className="card card-pad subtle">Loading effects…</div></div>
      </div>
    )
  }

  const applied = settings?.effects?.params || {}
  const dirty = JSON.stringify(draft) !== JSON.stringify(
    Object.fromEntries(Object.keys(FIELDS).map((k) => [k, { ...DEFAULTS[k], ...(applied[k] || {}) }])))

  const upd = (k, patch) => setDraft((d) => ({ ...d, [k]: { ...d[k], ...patch } }))
  const apply = (k) => { setMode(k, draft[k]); toast(`Applied ${TITLES[k] || k}`) }
  const save = () => { updateSettings({ effects: { ...(settings.effects || {}), params: draft } }); toast('Effect settings saved') }
  const e = draft

  return (
    <div className="main">
      <PageHead crumb="Configuration" title="Effects" sub="Tune the look of each lighting mode">
        <button className={`btn ${dirty ? 'btn-primary' : ''}`} onClick={save} disabled={!dirty || saving}><Icon n={dirty ? 'save' : 'check'} />{saving ? 'Saving…' : dirty ? 'Save effects' : 'Saved'}</button>
      </PageHead>

      <div className="content page-enter">
        <div className="grid-2">
          <EffectCard id="static" onApply={() => apply('static')} colorPreview={fmtRGB([e.static.r, e.static.g, e.static.b])}>
            <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
              <Swatch rgb={[e.static.r, e.static.g, e.static.b]} onChange={([r, g, b]) => upd('static', { r, g, b })} />
              <div className="mono subtle" style={{ fontSize: 12.5 }}>{fmtRGB([e.static.r, e.static.g, e.static.b])}</div>
            </div>
          </EffectCard>

          <EffectCard id="breathing" onApply={() => apply('breathing')} colorPreview={fmtRGB([e.breathing.r, e.breathing.g, e.breathing.b])}>
            <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
              <Swatch rgb={[e.breathing.r, e.breathing.g, e.breathing.b]} onChange={([r, g, b]) => upd('breathing', { r, g, b })} />
              <div className="mono subtle" style={{ fontSize: 12.5, flex: 1 }}>{fmtRGB([e.breathing.r, e.breathing.g, e.breathing.b])}</div>
            </div>
            <SpeedRow value={e.breathing.speed} onChange={(v) => upd('breathing', { speed: v })} />
          </EffectCard>

          <EffectCard id="rainbow" onApply={() => apply('rainbow')} colorPreview={PREVIEW.rainbow}><SpeedRow value={e.rainbow.speed} onChange={(v) => upd('rainbow', { speed: v })} /></EffectCard>
          <EffectCard id="candle" onApply={() => apply('candle')} colorPreview={PREVIEW.candle}><SpeedRow value={e.candle.speed} onChange={(v) => upd('candle', { speed: v })} /></EffectCard>
          <EffectCard id="ocean" onApply={() => apply('ocean')} colorPreview={PREVIEW.ocean}><SpeedRow value={e.ocean.speed} onChange={(v) => upd('ocean', { speed: v })} /></EffectCard>
          <EffectCard id="ambient" onApply={() => apply('ambient')} colorPreview={PREVIEW.ambient}><SpeedRow value={e.ambient.speed} onChange={(v) => upd('ambient', { speed: v })} /></EffectCard>

          <EffectCard id="sunrise" onApply={() => apply('sunrise')} colorPreview={PREVIEW.sunrise}>
            <label className="field-row" style={{ padding: 0 }}><span className="fr-l">Duration</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Stepper value={Math.round((e.sunrise.duration ?? 300) / 60)} onChange={(v) => upd('sunrise', { duration: v * 60 })} min={1} max={60} /><span className="subtle">min</span></div></label>
          </EffectCard>
          <EffectCard id="sunset" onApply={() => apply('sunset')} colorPreview={PREVIEW.sunset}>
            <label className="field-row" style={{ padding: 0 }}><span className="fr-l">Duration</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Stepper value={Math.round((e.sunset.duration ?? 300) / 60)} onChange={(v) => upd('sunset', { duration: v * 60 })} min={1} max={60} /><span className="subtle">min</span></div></label>
          </EffectCard>
        </div>

        {/* custom palette */}
        <div className="card" style={{ marginTop: 'var(--gap)' }}>
          <div className="card-h"><h3><Icon n="palette" />Custom palette</h3>
            <button className="btn btn-sm" onClick={() => apply('custom')}><Icon n="play" />Apply</button></div>
          <div className="card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="effect-prev" style={{ background: `linear-gradient(90deg,${e.custom.colors.map(fmtRGB).join(',')})` }} />
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              {e.custom.colors.map((c, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Swatch rgb={c} onChange={(nc) => upd('custom', { colors: e.custom.colors.map((x, idx) => (idx === i ? nc : x)) })} />
                  {e.custom.colors.length > 1 && <button className="btn btn-sm icon-btn btn-ghost" onClick={() => upd('custom', { colors: e.custom.colors.filter((_, idx) => idx !== i) })}><Icon n="x" /></button>}
                </div>
              ))}
              <button className="btn btn-sm" onClick={() => upd('custom', { colors: [...e.custom.colors, [255, 255, 255]] })}><Icon n="plus" />Add stop</button>
            </div>
            <SpeedRow value={e.custom.speed} onChange={(v) => upd('custom', { speed: v })} />
          </div>
        </div>
      </div>
    </div>
  )
}
