import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { Layers, Check, Trash2, Plus, Download, Upload } from 'lucide-react'

export default function Profiles() {
  const { profiles, fetchProfiles, applyProfile, saveProfile, deleteProfile } = useStore()
  const [newName, setNewName] = useState('')

  useEffect(() => { fetchProfiles() }, [])

  const handleSave = async (e) => {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    await saveProfile(name)
    setNewName('')
  }

  const handleImport = async () => {
    try {
      const r = await window.api.profiles.import()
      if (r?.ok) await fetchProfiles()
    } catch (e) { console.error(e) }
  }

  return (
    <section className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Layers size={20} /> Profiles</h3>
        <button className="button" style={{ width: 'auto', padding: '0.4rem 0.8rem', background: 'rgba(255,255,255,0.1)' }}
          onClick={handleImport} title="Import profile from file"><Upload size={15} /> Import</button>
      </div>

      {profiles.length === 0 ? (
        <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)' }}>No saved profiles yet.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {profiles.map((name) => (
            <div key={name} className="metric-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{name}</span>
              <div style={{ display: 'flex', gap: '0.4rem' }}>
                <button className="button" style={{ width: 'auto', padding: '0.4rem 0.8rem' }}
                  onClick={() => applyProfile(name)} title="Apply profile"><Check size={15} /> Apply</button>
                <button className="button" style={{ width: 'auto', padding: '0.4rem 0.7rem', background: 'rgba(255,255,255,0.1)' }}
                  onClick={() => window.api.profiles.export(name)} title="Export profile to file"><Download size={15} /></button>
                <button className="button" style={{ width: 'auto', padding: '0.4rem 0.7rem', background: 'rgba(239,68,68,0.2)', color: 'var(--accent-red)' }}
                  onClick={() => deleteProfile(name)} title="Delete profile"><Trash2 size={15} /></button>
              </div>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleSave} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.5rem' }}>
        <input className="input" placeholder="Save current settings as…" value={newName}
          onChange={(e) => setNewName(e.target.value)} style={{ flex: 1 }} />
        <button type="submit" className="button" style={{ width: 'auto', padding: '0.5rem 1rem' }}><Plus size={16} /> Save</button>
      </form>
    </section>
  )
}
