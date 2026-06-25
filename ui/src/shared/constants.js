// Navigation + mode tables shared by the shell and pages. Kept out of the
// component files so react-refresh's "only export components" rule stays happy.

export const NAV = [
  ['dashboard', 'Dashboard', 'layout-dashboard'],
  ['devices', 'Devices', 'wifi'],
  ['zones', 'Zones', 'layout-grid'],
  ['profiles', 'Profiles', 'layers'],
  ['effects', 'Effects', 'wand-2'],
  ['notifications', 'Notifications', 'bell'],
  ['settings', 'Settings', 'sliders-horizontal'],
  ['logs', 'Logs', 'terminal'],
  ['diagnostics', 'Diagnostics', 'activity'],
]

// [label, mode, abbr, defaultParams] — params mirror the legacy App.jsx MODES.
export const MODES = [
  ['Screen Sync', 'screen_sync', 'SS', undefined],
  ['Rainbow', 'rainbow', 'RB', { speed: 1.0 }],
  ['Candle', 'candle', 'CD', undefined],
  ['Audio', 'audio', 'AU', { mode: 'level' }],
  ['Sunrise', 'sunrise', 'SR', { duration: 300 }],
  ['Sunset', 'sunset', 'ST', { duration: 300 }],
  ['Ocean', 'ocean', 'OC', undefined],
  ['Ambient', 'ambient', 'AM', undefined],
]
