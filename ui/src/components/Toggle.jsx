import React from 'react'

/**
 * Modern pill toggle switch. Drop-in replacement for native checkboxes.
 *
 * Props:
 *   checked   – boolean state
 *   onChange  – (nextChecked: boolean) => void
 *   disabled  – optional
 *   label     – optional text rendered to the right of the switch
 *   size      – 'sm' | 'md' (default 'md')
 */
export default function Toggle({ checked, onChange, disabled = false, label, size = 'md' }) {
  const dims = size === 'sm'
    ? { track: 'w-9 h-5', knob: 'w-3.5 h-3.5', on: 'translate-x-4', off: 'translate-x-1' }
    : { track: 'w-11 h-6', knob: 'w-4 h-4', on: 'translate-x-5', off: 'translate-x-1' }

  const sw = (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={`relative inline-flex ${dims.track} shrink-0 items-center rounded-full transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 disabled:opacity-40 disabled:cursor-not-allowed ${
        checked ? 'bg-indigo-600 shadow-[0_0_12px_-2px] shadow-indigo-500/60' : 'bg-white/15'}`}
    >
      <span className={`inline-block ${dims.knob} transform rounded-full bg-white shadow transition-transform duration-200 ${checked ? dims.on : dims.off}`} />
    </button>
  )

  if (!label) return sw
  return (
    <label className={`flex items-center gap-2.5 ${disabled ? 'opacity-60' : 'cursor-pointer'}`}>
      {sw}
      <span className="text-sm text-slate-300 select-none">{label}</span>
    </label>
  )
}
