import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Layers, Check, Trash2, Plus, Download, Upload, Repeat, Save } from 'lucide-react'
import Toggle from '../components/Toggle'

const AP_DEFAULTS = { enabled: false, poll_interval: 2.0, default_profile: '', rules: [] }

function AutoSwitchPanel({ profiles }) {
  const { settings, fetchSettings, updateSettings, saving } = useStore()
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
    <div className="glass-panel rounded-2xl p-5 flex flex-col gap-3">
      <div className="flex justify-between items-center">
        <h4 className="text-sm font-semibold text-white flex items-center gap-2"><Repeat className="w-4 h-4 text-indigo-400" /> Auto-switch by app</h4>
        <Toggle checked={!!draft.enabled} onChange={(v) => setDraft((d) => ({ ...d, enabled: v }))} label="Enabled" />
      </div>

      <div className="text-xs text-slate-500">
        Foreground app: <span className="text-slate-200 font-mono">{current || 'unknown'}</span>
        {current && (
          <button onClick={() => addRule(current)} className="ml-2 px-2 py-0.5 rounded bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-xs inline-flex items-center gap-1">
            <Plus className="w-3 h-3" /> rule for this app
          </button>
        )}
      </div>

      <label className="flex items-center gap-3 text-sm">
        <span className="text-slate-400 min-w-[110px]">Default profile</span>
        <select className="custom-input rounded-lg px-2 py-1.5 text-sm" value={draft.default_profile} onChange={(e) => setDraft((d) => ({ ...d, default_profile: e.target.value }))}>
          <option value="">(leave unchanged)</option>
          {profiles.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>

      <div className="flex flex-col gap-2">
        {draft.rules.length === 0 && <div className="text-xs text-slate-500">No rules — add one to map an app to a profile.</div>}
        {draft.rules.map((r, i) => (
          <div key={i} className="flex gap-2 items-center">
            <input className="custom-input rounded-lg px-2 py-1.5 text-sm flex-[2]" placeholder="app contains… (e.g. game.exe)" value={r.match} onChange={(e) => setRule(i, 'match', e.target.value)} />
            <span className="text-slate-500">→</span>
            <select className="custom-input rounded-lg px-2 py-1.5 text-sm flex-1" value={r.profile} onChange={(e) => setRule(i, 'profile', e.target.value)}>
              <option value="">(select profile)</option>
              {profiles.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <button onClick={() => removeRule(i)} className="btn-neon-red px-2.5 py-1.5 rounded-lg"><Trash2 className="w-4 h-4" /></button>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <button onClick={() => addRule()} className="px-4 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-sm flex items-center gap-2"><Plus className="w-4 h-4" /> Add rule</button>
        <button onClick={() => updateSettings({ auto_profile: draft })} disabled={!dirty || saving}
          className="btn-neon-blue px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 ml-auto disabled:opacity-40">
          <Save className="w-4 h-4" /> {saving ? 'Saving…' : dirty ? 'Save rules' : 'Saved'}
        </button>
      </div>
    </div>
  )
}

export default function Profiles() {
  const { profiles, activeProfile, fetchProfiles, applyProfile, saveProfile, deleteProfile } = useStore()
  const [newName, setNewName] = useState('')

  useEffect(() => {
    fetchProfiles()
    const t = setInterval(fetchProfiles, 4000)  // reflect auto-switch changes
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
    <section className="glass-panel rounded-3xl p-8 flex flex-col gap-4 animate-fade-up">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2"><Layers className="w-5 h-5 text-indigo-400" /> Profiles</h3>
        <button onClick={handleImport} title="Import profile from file"
          className="px-4 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 text-sm flex items-center gap-2"><Upload className="w-4 h-4" /> Import</button>
      </div>

      {profiles.length === 0 ? (
        <div className="glass-panel rounded-2xl p-6 text-center text-slate-500">No saved profiles yet.</div>
      ) : (
        <div className="flex flex-col gap-2">
          {profiles.map((name) => {
            const active = name === activeProfile
            return (
            <div key={name} className={`glass-panel rounded-2xl p-4 flex justify-between items-center ${active ? 'ring-1 ring-indigo-500/60 active-device-pulse' : ''}`}>
              <span className="font-semibold capitalize flex items-center gap-2">
                {name}
                {active && <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-2 py-0.5 rounded">Active</span>}
              </span>
              <div className="flex gap-2">
                <button onClick={() => applyProfile(name)} className={`px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 ${active ? 'nav-item-active' : 'btn-neon-blue'}`}><Check className="w-4 h-4" /> {active ? 'Active' : 'Apply'}</button>
                <button onClick={() => window.api.profiles.export(name)} title="Export" className="px-3 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300"><Download className="w-4 h-4" /></button>
                <button onClick={() => deleteProfile(name)} title="Delete" className="btn-neon-red px-3 py-2 rounded-xl"><Trash2 className="w-4 h-4" /></button>
              </div>
            </div>
            )
          })}
        </div>
      )}

      <form onSubmit={handleSave} className="flex gap-2 items-center">
        <input className="custom-input rounded-xl px-3 py-2.5 text-sm flex-1" placeholder="Save current settings as…" value={newName} onChange={(e) => setNewName(e.target.value)} />
        <button type="submit" className="btn-neon-blue px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2"><Plus className="w-4 h-4" /> Save</button>
      </form>

      <AutoSwitchPanel profiles={profiles} />
    </section>
  )
}
