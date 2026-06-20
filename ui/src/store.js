import { create } from 'zustand'

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
    } catch (e) {
      console.error(e);
    } finally {
      set({ scanning: false });
    }
  },

  testDevice: async (ip, port) => {
    try {
      await window.api.devices.test(ip, port);
      return true;
    } catch (e) {
      console.error(e);
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
    } catch (e) {
      console.error(e);
    }
  },

  saveProfile: async (name) => {
    try {
      await window.api.profiles.save(name);
      await get().fetchProfiles();
    } catch (e) {
      console.error(e);
    }
  },

  deleteProfile: async (name) => {
    try {
      await window.api.profiles.delete(name);
      await get().fetchProfiles();
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
  }
}))
