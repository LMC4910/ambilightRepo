import { create } from 'zustand'

// --- Persisted UI preferences (theme / density / sidebar / accent) ---------
// These are renderer-only look-and-feel prefs; kept in localStorage so they
// survive relaunches without touching the service config.
const UI_PREFS_KEY = 'ambi.ui'
const DEFAULT_UI = {
  theme: 'dark',            // 'dark' | 'light'
  density: 'comfortable',   // 'comfortable' | 'compact'
  sidebarCollapsed: false,
  accentFollowsLive: true,  // echo the live LED colour as the accent
  accent: '#6f74e6',
}
function loadUiPrefs() {
  try { return { ...DEFAULT_UI, ...(JSON.parse(localStorage.getItem(UI_PREFS_KEY)) || {}) } }
  catch { return { ...DEFAULT_UI } }
}

export const useStore = create((set, get) => ({
  status: 'disconnected', // 'disconnected', 'connecting', 'connected'
  metrics: {
    fps: 0,
    latency_ms: 0,
    capture_time_ms: 0,
    process_time_ms: 0,
    led_transmit_ms: 0,
    dropped_frames: 0,
    cpu_usage: 0,
    memory_usage_mb: 0,
    uptime_s: 0
  },
  settings: null,
  profiles: [],
  activeProfile: null,
  devices: [],
  monitors: [],
  scanning: false,
  saving: false,

  // --- UI preferences ---
  ui: loadUiPrefs(),
  setUiPref: (key, value) => set((s) => {
    const ui = { ...s.ui, [key]: value }
    try { localStorage.setItem(UI_PREFS_KEY, JSON.stringify(ui)) } catch { /* ignore */ }
    return { ui }
  }),

  // --- Transient toasts (consumed by <Toasts/>) ---
  toasts: [],
  toast: (msg) => {
    const id = Math.random().toString(36).slice(2)
    set((s) => ({ toasts: [...s.toasts, { id, msg }] }))
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 2200)
  },

  setStatus: (status) => set({ status }),
  setMetrics: (metrics) => set({ metrics }),
  setSettings: (settings) => set({ settings }),
  setProfiles: (profiles) => set({ profiles }),
  setDevices: (devices) => set({ devices }),

  // Fetch the connected displays (name + resolution). The setup wizard opens
  // the instant the app launches — often before the background service has
  // finished booting — so a single attempt frequently fails and the UI would
  // otherwise fall back to generic "Display N" placeholders. Retry until the
  // service answers with a real list so proper monitor names always appear.
  fetchMonitors: async (retries = 8, delayMs = 750) => {
    for (let attempt = 0; attempt < retries; attempt++) {
      try {
        const d = await window.api.diagnostics?.get();
        const mons = d?.monitors || [];
        if (mons.length) {
          set({ monitors: mons });
          return mons;
        }
      } catch (e) {
        // Service may still be starting; fall through to retry.
      }
      await new Promise((r) => setTimeout(r, delayMs));
    }
    return get().monitors;
  },

  fetchSettings: async () => {
    try {
      const data = await window.api.settings.get();
      set({ settings: data });
    } catch (e) {
      console.error(e);
    }
  },

  updateSettings: async (newSettings) => {
    set({ saving: true });
    try {
      await window.api.settings.update(newSettings);
      await get().fetchSettings();
    } catch (e) {
      console.error(e);
    } finally {
      set({ saving: false });
    }
  },

  fetchDevices: async () => {
    try {
      const data = await window.api.devices.list();
      set({ devices: data.devices || [] });
    } catch (e) {
      console.error(e);
    }
  },

  scanDevices: async () => {
    set({ scanning: true });
    try {
      const data = await window.api.devices.scan();
      set({ devices: data.devices || [] });
      get().toast(`Scan complete · ${(data.devices || []).length} device${(data.devices || []).length === 1 ? '' : 's'}`);
    } catch (e) {
      console.error(e);
    } finally {
      set({ scanning: false });
    }
  },

  testDevice: async (ip, port, protocol) => {
    try {
      await window.api.devices.test(ip, port, protocol);
      get().toast('LEDs flashed white');
      return true;
    } catch (e) {
      console.error(e);
      // The service explains why (offline / wrong IP / wrong protocol) in the
      // error message — show it instead of leaving the click with no feedback.
      // Electron wraps IPC rejections as "Error invoking remote method '…': Error: <msg>";
      // strip that wrapper so the toast shows just the real reason.
      const reason = (e?.message || '').replace(/^Error invoking remote method '[^']*':\s*(Error:\s*)?/, '');
      get().toast(reason || `Could not reach device at ${ip}`);
      return false;
    }
  },

  fetchProfiles: async () => {
    try {
      const data = await window.api.profiles.list();
      set({ profiles: data.profiles || [], activeProfile: data.active || null });
    } catch (e) {
      console.error(e);
    }
  },

  applyProfile: async (name) => {
    try {
      await window.api.profiles.apply(name);
      set({ activeProfile: name });
      get().fetchSettings();
      get().fetchProfiles();
      get().toast(`Profile "${name}" applied`);
    } catch (e) {
      console.error(e);
    }
  },

  saveProfile: async (name) => {
    try {
      await window.api.profiles.save(name);
      await get().fetchProfiles();
      get().toast(`Saved "${name}"`);
    } catch (e) {
      console.error(e);
    }
  },

  deleteProfile: async (name) => {
    try {
      await window.api.profiles.delete(name);
      await get().fetchProfiles();
      get().toast(`Deleted "${name}"`);
    } catch (e) {
      console.error(e);
    }
  },

  setMode: async (mode, params = {}) => {
    try {
      await window.api.effects.setMode(mode, params);
      get().fetchSettings();
    } catch (e) {
      console.error(e);
    }
  },

  // --- Game capture (hook) re-inject ---
  retargetCapture: async (target) => {
    try {
      await window.api.capture.retarget(target, true);
      await get().fetchSettings();
      get().toast(target ? `Injecting into ${target}…` : 'Re-injecting game capture…');
      return true;
    } catch (e) {
      console.error(e);
      const reason = (e?.message || '').replace(/^Error invoking remote method '[^']*':\s*(Error:\s*)?/, '');
      get().toast(reason || 'Could not re-trigger game capture');
      return false;
    }
  },

  // --- Notification flash ---
  notifPermission: async () => {
    try {
      return await window.api.notifications.permission();
    } catch (e) {
      return null;
    }
  },

  testFlash: async (color) => {
    try {
      await window.api.notifications.test(color);
      get().toast('Test flash sent');
      return true;
    } catch (e) {
      console.error(e);
      return false;
    }
  },

  // Curated brand→RGB map (normalised app name → [r,g,b]). Static, so fetch once
  // and cache; used to suggest a colour when adding a per-app override.
  brandColors: null,
  fetchBrandColors: async () => {
    if (get().brandColors) return get().brandColors;
    try {
      const map = await window.api.notifications.brandColors();
      const safe = map && typeof map === 'object' ? map : {};
      set({ brandColors: safe });
      return safe;
    } catch (e) {
      set({ brandColors: {} });
      return {};
    }
  },

  // --- GitHub integration ---
  githubStatus: null,
  fetchGithubStatus: async () => {
    try {
      const s = await window.api.github.status();
      set({ githubStatus: s });
      return s;
    } catch (e) {
      set({ githubStatus: null });
      return null;
    }
  },
  githubAuthStart: async () => {
    try {
      const r = await window.api.github.authStart();
      get().fetchGithubStatus();
      return r;
    } catch (e) {
      const reason = (e?.message || '').replace(/^Error invoking remote method '[^']*':\s*(Error:\s*)?/, '');
      get().toast(reason || 'Could not start GitHub sign-in');
      return null;
    }
  },
  githubLogout: async () => {
    try {
      await window.api.github.logout();
      await get().fetchGithubStatus();
      get().toast('Disconnected from GitHub');
    } catch (e) {
      console.error(e);
    }
  },
  githubOrgs: async () => {
    try { return await window.api.github.orgs(); } catch (e) { return []; }
  },
  githubRepos: async () => {
    try { return await window.api.github.repos(); } catch (e) { return []; }
  },
  githubEvents: async (limit = 50) => {
    try { return await window.api.github.events(limit); } catch (e) { return []; }
  },
  githubTest: async (color) => {
    try {
      await window.api.github.test(color);
      get().toast('Test flash sent');
      return true;
    } catch (e) {
      console.error(e);
      return false;
    }
  }
}))
