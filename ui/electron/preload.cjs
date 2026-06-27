const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('api', {
  settings: {
    get: () => ipcRenderer.invoke('api:settings:get'),
    update: (settings) => ipcRenderer.invoke('api:settings:update', settings),
    reload: () => ipcRenderer.invoke('api:settings:reload')
  },
  profiles: {
    list: () => ipcRenderer.invoke('api:profiles:list'),
    save: (name) => ipcRenderer.invoke('api:profiles:save', name),
    apply: (name) => ipcRenderer.invoke('api:profiles:apply', name),
    delete: (name) => ipcRenderer.invoke('api:profiles:delete', name),
    export: (name) => ipcRenderer.invoke('api:profiles:export', name),
    import: () => ipcRenderer.invoke('api:profiles:import')
  },
  autostart: {
    get: () => ipcRenderer.invoke('api:autostart:get'),
    enable: () => ipcRenderer.invoke('api:autostart:enable'),
    disable: () => ipcRenderer.invoke('api:autostart:disable')
  },
  foreground: {
    get: () => ipcRenderer.invoke('api:foreground:get')
  },
  notifications: {
    permission: () => ipcRenderer.invoke('api:notifications:permission'),
    test: (color) => ipcRenderer.invoke('api:notifications:test', color)
  },
  system: {
    // Only known OS settings deep-links are honoured; the main process enforces
    // an allowlist (see app:openExternal) and ignores anything else.
    openExternal: (url) => ipcRenderer.invoke('app:openExternal', url)
  },
  window: {
    onVisibility: (callback) => {
      const listener = (_, visible) => callback(visible)
      ipcRenderer.on('window:visibility', listener)
      return () => ipcRenderer.removeListener('window:visibility', listener)
    },
    // Custom title-bar controls for the frameless window.
    minimize: () => ipcRenderer.send('window:minimize'),
    maximize: () => ipcRenderer.send('window:maximize'),
    close: () => ipcRenderer.send('window:close')
  },
  onboarding: {
    get: () => ipcRenderer.invoke('app:onboarding:get'),
    complete: () => ipcRenderer.invoke('app:onboarding:complete')
  },
  effects: {
    setMode: (mode, params) => ipcRenderer.invoke('api:effects:setMode', mode, params),
    list: () => ipcRenderer.invoke('api:effects:list')
  },
  diagnostics: {
    get: () => ipcRenderer.invoke('api:diagnostics:get')
  },
  devices: {
    list: () => ipcRenderer.invoke('api:devices:list'),
    scan: () => ipcRenderer.invoke('api:devices:scan'),
    test: (ip, port, protocol) => ipcRenderer.invoke('api:devices:test', ip, port, protocol)
  },
  metrics: {
    subscribe: (callback) => {
      ipcRenderer.on('metrics:update', (_, metrics) => callback(metrics))
      ipcRenderer.send('metrics:subscribe')
    },
    unsubscribe: () => {
      ipcRenderer.removeAllListeners('metrics:update')
      ipcRenderer.send('metrics:unsubscribe')
    }
  },
  service: {
    status: () => ipcRenderer.invoke('api:service:status'),
    start: () => ipcRenderer.invoke('api:service:start'),
    stop: () => ipcRenderer.invoke('api:service:stop'),
    restart: () => ipcRenderer.invoke('api:service:restart'),
    onStatus: (callback) => {
      const listener = (_, status) => callback(status)
      ipcRenderer.on('service:status', listener)
      return () => ipcRenderer.removeListener('service:status', listener)
    }
  },
  logs: {
    read: () => ipcRenderer.invoke('api:logs:read'),
    openFolder: () => ipcRenderer.invoke('api:logs:openFolder'),
    clear: () => ipcRenderer.invoke('api:logs:clear')
  },
  capture: {
    // Point game capture at a specific .exe (or "" for auto) and (re)inject now.
    retarget: (target, enabled) => ipcRenderer.invoke('api:capture:retarget', { target, enabled })
  },
  updater: {
    check: () => ipcRenderer.invoke('app:update:check'),
    install: () => ipcRenderer.invoke('app:update:install'),
    status: () => ipcRenderer.invoke('app:update:status'),
    onStatus: (callback) => {
      const listener = (_, status) => callback(status)
      ipcRenderer.on('updater:status', listener)
      return () => ipcRenderer.removeListener('updater:status', listener)
    }
  }
})
