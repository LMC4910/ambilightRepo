import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Icon, PageHead, Section, Empty, Toggle } from '../components/shell'

const AP_DEFAULTS = { enabled: false, poll_interval: 2.0, default_profile: '', rules: [] }

function AutoSwitchPanel({ profiles }) {
  const { settings, fetchSettings, updateSettings, saving, toast } = useStore()
  const [draft, setDraft] = useState(null)
  const [current, setCurrent] = useState(null)

  useEffect(() => { if (!settings) fetchSettings() }, [])
  useEffect(() => { if (settings) setDraft({ ...AP_DEFAULTS, ...(settings.auto_profile || {}) }) }, [settings])
  useEffect(() => {
    let alive = true
    const tick = () => window.api.foreground?.get().then((r) => { if (alive) setCurrent(r?.app || null) }).catch(() => {})
    tick()
    const id = setInterval(tick, 2000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  if (!draft) return null
  const applied = { ...AP_DEFAULTS, ...(settings?.auto_profile || {}) }
  const dirty = draft.enabled !== applied.enabled || draft.default_profile !== applied.default_profile
    || JSON.stringify(draft.rules) !== JSON.stringify(applied.rules)
  const setRule = (i, key, val) => setDraft((d) => ({ ...d, rules: d.rules.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)) }))
  const addRule = (match = '') => setDraft((d) => ({ ...d, rules: [...d.rules, { match, profile: profiles[0] || '' }] }))
  const removeRule = (i) => setDraft((d) => ({ ...d, rules: d.rules.filter((_, idx) => idx !== i) }))

  return (
    <div className="card" style={{ marginTop: 'var(--gap)' }}>
      <div className="card-h"><h3><Icon n="repeat" />Auto-switch by app</h3><Toggle checked={!!draft.enabled} onChange={(v) => setDraft((d) => ({ ...d, enabled: v }))} /></div>
      <div className="card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div className="hint">
          Foreground app: <span className="mono" style={{ color: 'var(--tx-2)' }}>{current || 'unknown'}</span>
          {current && <button className="btn btn-sm" style={{ marginLeft: 10 }} onClick={() => addRule(current)}><Icon n="plus" />rule for this app</button>}
        </div>
        <label className="field-row" style={{ padding: 0 }}><span className="fr-l">Default profile</span>
          <select className="field" style={{ maxWidth: 220 }} value={draft.default_profile} onChange={(e) => setDraft((d) => ({ ...d, default_profile: e.target.value }))}>
            <option value="">(leave unchanged)</option>{profiles.map((p) => <option key={p} value={p}>{p}</option>)}</select></label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {draft.rules.length === 0 && <div className="hint">No rules — add one to map an app to a profile.</div>}
          {draft.rules.map((r, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input className="field mono" style={{ flex: 2 }} placeholder="app contains… (e.g. game.exe)" value={r.match} onChange={(e) => setRule(i, 'match', e.target.value)} />
              <Icon n="arrow-right" style={{ color: 'var(--faint)' }} />
              <select className="field" style={{ flex: 1 }} value={r.profile} onChange={(e) => setRule(i, 'profile', e.target.value)}>
                <option value="">(select profile)</option>{profiles.map((p) => <option key={p} value={p}>{p}</option>)}</select>
              <button className="btn btn-sm btn-danger icon-btn" onClick={() => removeRule(i)}><Icon n="trash-2" /></button>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <button className="btn btn-sm" onClick={() => addRule()}><Icon n="plus" />Add rule</button>
          <button className="btn btn-sm btn-primary" onClick={() => { updateSettings({ auto_profile: draft }); toast('Auto-switch rules saved') }} disabled={!dirty || saving}><Icon n="save" />{dirty ? 'Save rules' : 'Saved'}</button>
        </div>
      </div>
    </div>
  )
}

export default function Profiles() {
  const { profiles, activeProfile, fetchProfiles, applyProfile, saveProfile, deleteProfile } = useStore()
  const [newName, setNewName] = useState('')

  useEffect(() => {
    fetchProfiles()
    const t = setInterval(fetchProfiles, 4000) // reflect auto-switch changes
    return () => clearInterval(t)
  }, [])

  const handleSave = async (e) => {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    await saveProfile(name)
    setNewName('')
  }
  const handleImport = async () => {
    try { const r = await window.api.profiles.import(); if (r?.ok) await fetchProfiles() } catch (e) { console.error(e) }
  }

  return (
    <div className="main">
      <PageHead crumb="Configuration" title="Profiles" sub="Saved configurations & automatic switching">
        <button className="btn btn-sm" onClick={handleImport}><Icon n="upload" />Import</button>
      </PageHead>

      <div className="content content-narrow page-enter">
        <div className="stack">
          <Section title="Saved profiles" count={profiles.length} />
          {profiles.length === 0 ? (
            <div className="card"><Empty icon="layers" title="No profiles yet">Save your current settings as a profile to switch between setups instantly.</Empty></div>
          ) : (
            <div className="tile-grid">
              {profiles.map((name) => {
                const active = name === activeProfile
                return (
                  <div key={name} className={`card prof-tile ${active ? 'active' : ''}`} style={active ? { borderColor: 'var(--accent-22)' } : {}}>
                    <div className="prof-tile-top">
                      <span className="prof-tile-ic"><Icon n="layers" /></span>
                      <span className="prof-tile-name">{name}</span>
                      {active && <span className="tag good" style={{ marginLeft: 'auto' }}><span className="d" />Active</span>}
                    </div>
                    <div className="prof-tile-foot">
                      <button className={`btn btn-sm ${active ? '' : 'btn-primary'}`} onClick={() => applyProfile(name)} disabled={active}><Icon n="check" />{active ? 'Active' : 'Apply'}</button>
                      <button className="btn btn-sm icon-btn" title="Export" onClick={() => window.api.profiles.export(name)}><Icon n="download" /></button>
                      <button className="btn btn-sm btn-danger icon-btn" title="Delete" onClick={() => deleteProfile(name)}><Icon n="trash-2" /></button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
          <form onSubmit={handleSave} style={{ display: 'flex', gap: 10 }}>
            <input className="field" placeholder="Save current settings as…" value={newName} onChange={(e) => setNewName(e.target.value)} />
            <button type="submit" className="btn btn-primary"><Icon n="plus" />Save</button>
          </form>

          <AutoSwitchPanel profiles={profiles} />
        </div>
      </div>
    </div>
  )
}
