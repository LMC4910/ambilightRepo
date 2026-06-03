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
  devices: [],
  scanning: false,
  saving: false,

  setStatus: (status) => set({ status }),
  setMetrics: (metrics) => set({ metrics }),
  setSettings: (settings) => set({ settings }),
  setProfiles: (profiles) => set({ profiles }),
  setDevices: (devices) => set({ devices }),

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
      set({ profiles: data.profiles || [] });
    } catch (e) {
      console.error(e);
    }
  },

  applyProfile: async (name) => {
    try {
      await window.api.profiles.apply(name);
      get().fetchSettings();
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
