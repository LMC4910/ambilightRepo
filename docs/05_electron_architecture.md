# Electron Architecture Document
## Ambilight Desktop — Frontend Application Design

**Version:** 1.0  
**Framework:** Electron 30 + React 18 + TypeScript 5 + Vite 5

---

## 1. Design Principles

1. **The Electron app is a control panel, not a processing engine.** All LED and capture logic lives in the Python service. Electron's job is to present state and accept commands.
2. **The service must survive UI closure.** The app can be closed; LEDs keep running.
3. **Zero business logic in the renderer.** Renderer processes display what the store tells them. Business logic lives in Zustand actions or the Python service.
4. **Context isolation is non-negotiable.** `nodeIntegration: false`, `contextIsolation: true`, `sandbox: true` — always.

---

## 2. Process Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    ELECTRON APPLICATION                          │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   MAIN PROCESS (Node.js)                 │   │
│  │                                                          │   │
│  │  ┌─────────────┐  ┌────────────┐  ┌──────────────────┐  │   │
│  │  │ App Lifecycle│  │ ServiceCtrl│  │  Auto Updater    │  │   │
│  │  │ (app events) │  │            │  │ (electron-updater│  │   │
│  │  └─────────────┘  └────────────┘  └──────────────────┘  │   │
│  │                                                          │   │
│  │  ┌─────────────┐  ┌────────────┐  ┌──────────────────┐  │   │
│  │  │  Tray Icon  │  │  WS Bridge │  │  IPC Handlers    │  │   │
│  │  │             │  │            │  │                  │  │   │
│  │  └─────────────┘  └────────────┘  └──────────────────┘  │   │
│  └────────────────────────┬─────────────────────────────────┘   │
│                           │  ipcMain / ipcRenderer              │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │                 PRELOAD SCRIPT                            │   │
│  │    contextBridge.exposeInMainWorld('ambilightAPI', ...)   │   │
│  └────────────────────────┬─────────────────────────────────┘   │
│                           │  window.ambilightAPI.*              │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │              RENDERER PROCESS (Chromium)                  │   │
│  │                                                           │   │
│  │  React 18 + TypeScript                                   │   │
│  │  ┌──────────────────────────────────────────────────┐    │   │
│  │  │                Zustand Store                      │    │   │
│  │  │  serviceStatus | metrics | config | devices | ... │    │   │
│  │  └────────────────────┬─────────────────────────────┘    │   │
│  │                       │                                   │   │
│  │  ┌────────────────────▼─────────────────────────────┐    │   │
│  │  │              React Component Tree                 │    │   │
│  │  │  Dashboard | Devices | Settings | Profiles | Logs│    │   │
│  │  └───────────────────────────────────────────────────┘   │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Main Process Design

### 3.1 Application Lifecycle

```typescript
// src/main/index.ts
import { app, BrowserWindow, nativeTheme } from 'electron';
import { ServiceController } from './service-controller';
import { TrayManager } from './tray';
import { AutoUpdater } from './updater';
import { WSBridge } from './ws-bridge';
import { registerIPCHandlers } from './ipc-handlers';

let mainWindow: BrowserWindow | null = null;
let serviceController: ServiceController;
let wsbridge: WSBridge;

app.on('ready', async () => {
  serviceController = new ServiceController();
  wsbridge = new WSBridge(serviceController);
  
  await serviceController.ensureRunning();
  
  mainWindow = createWindow();
  await wsbridge.connect(mainWindow);
  
  registerIPCHandlers(serviceController);
  TrayManager.create(mainWindow, serviceController);
  AutoUpdater.initialize();
});

// Quit only main window; service keeps running
app.on('window-all-closed', (e: Event) => {
  if (process.platform !== 'darwin') {
    e.preventDefault(); // don't quit app — tray is still active
  }
});

app.on('before-quit', async () => {
  // Only kill service if user explicitly quit (not just closed window)
  if (serviceController.shouldStopOnExit()) {
    await serviceController.stop();
  }
});

function createWindow(): BrowserWindow {
  return new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#121212',
    titleBarStyle: 'hiddenInset',  // macOS: native title bar integration
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: path.join(__dirname, '../preload/index.js'),
    },
  });
}
```

### 3.2 Service Controller

```typescript
// src/main/service-controller.ts
import { spawn, ChildProcess } from 'child_process';
import { readFileSync, existsSync } from 'fs';
import path from 'path';
import net from 'net';

export class ServiceController {
  private process: ChildProcess | null = null;
  private healthCheckInterval: NodeJS.Timeout | null = null;
  private authToken: string = '';
  private readonly REST_URL = 'http://127.0.0.1:7826/api/v1';
  private readonly HEALTH_INTERVAL_MS = 5_000;
  private readonly SERVICE_EXECUTABLE: string;
  
  constructor() {
    // In production, use bundled service binary
    // In development, use Python directly
    this.SERVICE_EXECUTABLE = app.isPackaged
      ? path.join(process.resourcesPath, 'service', 'ambilight-service')
      : 'python';
  }

  async ensureRunning(): Promise<void> {
    if (await this.isHealthy()) return;
    await this.start();
  }
  
  async start(): Promise<void> {
    const args = app.isPackaged ? [] : ['-m', 'ambilight.service'];
    
    this.process = spawn(this.SERVICE_EXECUTABLE, args, {
      detached: true,      // Service outlives Electron if app closes
      stdio: 'ignore',     // Service writes its own logs
      env: {
        ...process.env,
        AMBILIGHT_DATA_DIR: this.getDataDir(),
      },
    });
    
    this.process.unref();  // Don't hold event loop
    
    // Wait for service to become responsive
    await this.waitForHealth(10_000);
    this.authToken = this.readAuthToken();
    this.startHealthChecks();
  }
  
  async stop(): Promise<void> {
    await fetch(`${this.REST_URL}/service/stop`, {
      method: 'POST',
      headers: this.authHeaders(),
    });
  }
  
  async restart(): Promise<void> {
    await fetch(`${this.REST_URL}/service/restart`, {
      method: 'POST',
      headers: this.authHeaders(),
    });
  }
  
  async isHealthy(): Promise<boolean> {
    try {
      const resp = await fetch(`${this.REST_URL}/health`, {
        signal: AbortSignal.timeout(2_000),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }
  
  private startHealthChecks(): void {
    this.healthCheckInterval = setInterval(async () => {
      if (!(await this.isHealthy())) {
        // Service died unexpectedly — restart it
        await this.start();
      }
    }, this.HEALTH_INTERVAL_MS);
  }
  
  authHeaders(): Record<string, string> {
    return { Authorization: `Bearer ${this.authToken}` };
  }
  
  private readAuthToken(): string {
    const tokenPath = path.join(this.getDataDir(), 'auth_token');
    return existsSync(tokenPath) ? readFileSync(tokenPath, 'utf8').trim() : '';
  }
  
  private getDataDir(): string {
    return path.join(app.getPath('home'), '.ambilight');
  }
  
  private async waitForHealth(timeoutMs: number): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (await this.isHealthy()) return;
      await new Promise(r => setTimeout(r, 500));
    }
    throw new Error('Service failed to start within timeout');
  }
}
```

### 3.3 WebSocket Bridge

```typescript
// src/main/ws-bridge.ts
import WebSocket from 'ws';
import { BrowserWindow } from 'electron';

export class WSBridge {
  private ws: WebSocket | null = null;
  private window: BrowserWindow | null = null;
  private readonly WS_URL = 'ws://127.0.0.1:7825';
  private reconnectTimer: NodeJS.Timeout | null = null;

  async connect(window: BrowserWindow): Promise<void> {
    this.window = window;
    this.tryConnect();
  }
  
  private tryConnect(): void {
    const token = this.serviceController.authHeaders().Authorization.split(' ')[1];
    this.ws = new WebSocket(`${this.WS_URL}?token=${token}`);
    
    this.ws.on('message', (data: Buffer) => {
      try {
        const msg = JSON.parse(data.toString());
        // Forward typed messages to renderer via IPC
        this.window?.webContents.send(`ws:${msg.type}`, msg.payload);
      } catch { /* drop malformed messages */ }
    });
    
    this.ws.on('close', () => {
      // Reconnect after 2 s
      this.reconnectTimer = setTimeout(() => this.tryConnect(), 2_000);
    });
    
    this.ws.on('error', () => {
      // Error is followed by close event; handled there
    });
  }
}
```

### 3.4 IPC Handlers

```typescript
// src/main/ipc-handlers.ts
import { ipcMain } from 'electron';
import { ServiceController } from './service-controller';

export function registerIPCHandlers(svc: ServiceController): void {
  // Service control
  ipcMain.handle('service:start', () => svc.start());
  ipcMain.handle('service:stop', () => svc.stop());
  ipcMain.handle('service:restart', () => svc.restart());
  ipcMain.handle('service:status', () => svc.isHealthy());

  // Proxy REST calls to Python service
  // The renderer calls invoke('api:get', '/config')
  // Main process adds auth header and makes the actual HTTP request
  ipcMain.handle('api:get', async (_, endpoint: string) => {
    const resp = await fetch(
      `http://127.0.0.1:7826/api/v1${endpoint}`,
      { headers: svc.authHeaders() }
    );
    return resp.json();
  });
  
  ipcMain.handle('api:put', async (_, endpoint: string, body: unknown) => {
    const resp = await fetch(
      `http://127.0.0.1:7826/api/v1${endpoint}`,
      {
        method: 'PUT',
        headers: { ...svc.authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }
    );
    return resp.json();
  });
  
  ipcMain.handle('api:post', async (_, endpoint: string, body?: unknown) => {
    const resp = await fetch(
      `http://127.0.0.1:7826/api/v1${endpoint}`,
      {
        method: 'POST',
        headers: { ...svc.authHeaders(), 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      }
    );
    return resp.json();
  });
}
```

---

## 4. Preload Script

```typescript
// src/preload/index.ts
import { contextBridge, ipcRenderer } from 'electron';

// Everything exposed here is available in renderer as window.ambilightAPI
// Nothing in this list grants Node.js access to renderer code
contextBridge.exposeInMainWorld('ambilightAPI', {

  // Service control
  service: {
    start:   () => ipcRenderer.invoke('service:start'),
    stop:    () => ipcRenderer.invoke('service:stop'),
    restart: () => ipcRenderer.invoke('service:restart'),
    status:  () => ipcRenderer.invoke('service:status'),
  },

  // REST API proxy (auth handled in main)
  api: {
    get:    (endpoint: string) => ipcRenderer.invoke('api:get', endpoint),
    put:    (endpoint: string, body: unknown) => ipcRenderer.invoke('api:put', endpoint, body),
    post:   (endpoint: string, body?: unknown) => ipcRenderer.invoke('api:post', endpoint, body),
    delete: (endpoint: string) => ipcRenderer.invoke('api:delete', endpoint),
  },

  // Real-time event subscriptions
  // Each returns an unsubscribe function
  on: {
    metrics: (cb: (data: MetricsPayload) => void) => {
      const handler = (_: unknown, data: MetricsPayload) => cb(data);
      ipcRenderer.on('ws:metrics', handler);
      return () => ipcRenderer.off('ws:metrics', handler);
    },
    deviceEvent: (cb: (data: DeviceEventPayload) => void) => {
      const handler = (_: unknown, data: DeviceEventPayload) => cb(data);
      ipcRenderer.on('ws:device_event', handler);
      return () => ipcRenderer.off('ws:device_event', handler);
    },
    log: (cb: (data: LogEntry) => void) => {
      const handler = (_: unknown, data: LogEntry) => cb(data);
      ipcRenderer.on('ws:log', handler);
      return () => ipcRenderer.off('ws:log', handler);
    },
    stateChange: (cb: (data: StateChangePayload) => void) => {
      const handler = (_: unknown, data: StateChangePayload) => cb(data);
      ipcRenderer.on('ws:state_change', handler);
      return () => ipcRenderer.off('ws:state_change', handler);
    },
  },
});
```

---

## 5. Renderer Process Design

### 5.1 State Management (Zustand)

```typescript
// src/renderer/store/index.ts
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';

interface AppState {
  // Service
  serviceStatus: 'running' | 'stopped' | 'starting' | 'stopping' | 'unknown';
  
  // Live metrics
  metrics: MetricsPayload | null;
  
  // Configuration
  config: AppConfig | null;
  configDirty: boolean;
  configSchema: JsonSchema | null;
  
  // Devices
  devices: DeviceInfo[];
  
  // Profiles
  profiles: Profile[];
  activeProfileId: string | null;
  
  // Effects
  activeEffect: string;
  availableEffects: EffectDefinition[];
  
  // Logs
  logs: LogEntry[];
  
  // Actions
  actions: {
    startService: () => Promise<void>;
    stopService: () => Promise<void>;
    restartService: () => Promise<void>;
    loadConfig: () => Promise<void>;
    saveConfig: (config: AppConfig) => Promise<void>;
    loadProfiles: () => Promise<void>;
    activateProfile: (id: string) => Promise<void>;
    scanDevices: () => Promise<void>;
    activateEffect: (name: string) => Promise<void>;
    appendLog: (entry: LogEntry) => void;
    updateMetrics: (metrics: MetricsPayload) => void;
  };
}

export const useAppStore = create<AppState>()(
  immer((set, get) => ({
    serviceStatus: 'unknown',
    metrics: null,
    config: null,
    configDirty: false,
    configSchema: null,
    devices: [],
    profiles: [],
    activeProfileId: null,
    activeEffect: 'screen_sync',
    availableEffects: [],
    logs: [],
    
    actions: {
      startService: async () => {
        set(s => { s.serviceStatus = 'starting'; });
        await window.ambilightAPI.service.start();
        set(s => { s.serviceStatus = 'running'; });
      },
      
      saveConfig: async (config) => {
        await window.ambilightAPI.api.put('/config', config);
        set(s => {
          s.config = config;
          s.configDirty = false;
        });
      },
      
      appendLog: (entry) => {
        set(s => {
          s.logs.unshift(entry);
          if (s.logs.length > 500) s.logs.length = 500;  // cap at 500 entries
        });
      },
      
      updateMetrics: (metrics) => {
        set(s => { s.metrics = metrics; });
      },
      
      // ... other actions
    }
  }))
);
```

### 5.2 App Layout

```typescript
// src/renderer/App.tsx
import { Suspense, lazy, useEffect } from 'react';
import { HashRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { AppShell } from './components/AppShell';
import { useAppStore } from './store';
import { theme } from './theme';

// Lazy-load pages to minimise initial render time
const Dashboard  = lazy(() => import('./pages/Dashboard'));
const Devices    = lazy(() => import('./pages/Devices'));
const Settings   = lazy(() => import('./pages/Settings'));
const Profiles   = lazy(() => import('./pages/Profiles'));
const Effects    = lazy(() => import('./pages/Effects'));
const Logs       = lazy(() => import('./pages/Logs'));
const Diagnostics= lazy(() => import('./pages/Diagnostics'));

export function App() {
  const { actions } = useAppStore();
  
  // Subscribe to real-time events on mount
  useEffect(() => {
    const unsubs = [
      window.ambilightAPI.on.metrics(actions.updateMetrics),
      window.ambilightAPI.on.log(actions.appendLog),
      window.ambilightAPI.on.deviceEvent((e) => {
        if (e.event === 'discovered') actions.scanDevices();
      }),
    ];
    
    // Initial data load
    actions.loadConfig();
    actions.loadProfiles();
    
    return () => unsubs.forEach(fn => fn());
  }, []);
  
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <HashRouter>
        <AppShell>
          <Suspense fallback={<PageSkeleton />}>
            <Routes>
              <Route path="/"           element={<Dashboard />} />
              <Route path="/devices"    element={<Devices />} />
              <Route path="/effects"    element={<Effects />} />
              <Route path="/profiles"   element={<Profiles />} />
              <Route path="/settings"   element={<Settings />} />
              <Route path="/logs"       element={<Logs />} />
              <Route path="/diagnostics"element={<Diagnostics />} />
            </Routes>
          </Suspense>
        </AppShell>
      </HashRouter>
    </ThemeProvider>
  );
}
```

### 5.3 Schema-Driven Settings Page

The Settings page renders configuration fields dynamically from the JSON Schema served by `/api/v1/config/schema`. This means adding a new config field to Python automatically appears in the UI without any front-end changes.

```typescript
// src/renderer/pages/Settings.tsx
import { useEffect, useState } from 'react';
import Form from '@rjsf/mui';          // react-jsonschema-form Material UI theme
import validator from '@rjsf/validator-ajv8';
import { useAppStore } from '../store';

export default function Settings() {
  const { config, configSchema, actions } = useAppStore();
  const [draft, setDraft] = useState(config);
  
  useEffect(() => { setDraft(config); }, [config]);
  
  const handleSubmit = async ({ formData }) => {
    await actions.saveConfig(formData);
  };
  
  if (!configSchema || !draft) return <LoadingSpinner />;
  
  return (
    <Form
      schema={configSchema}
      formData={draft}
      validator={validator}
      onChange={({ formData }) => setDraft(formData)}
      onSubmit={handleSubmit}
      uiSchema={uiSchemaOverrides}  // field-level UI hints
    />
  );
}
```

---

## 6. Auto Update Design

```typescript
// src/main/updater.ts
import { autoUpdater } from 'electron-updater';
import { dialog } from 'electron';
import log from 'electron-log';

export class AutoUpdater {
  static initialize(): void {
    autoUpdater.logger = log;
    autoUpdater.autoDownload = false;      // ask user first
    autoUpdater.autoInstallOnAppQuit = true;
    
    // Check on launch, then every 24 hours
    autoUpdater.checkForUpdates();
    setInterval(() => autoUpdater.checkForUpdates(), 24 * 60 * 60 * 1_000);
    
    autoUpdater.on('update-available', (info) => {
      dialog.showMessageBox({
        type: 'info',
        title: 'Update Available',
        message: `Version ${info.version} is available.`,
        detail: info.releaseNotes as string,
        buttons: ['Download', 'Later'],
      }).then(({ response }) => {
        if (response === 0) autoUpdater.downloadUpdate();
      });
    });
    
    autoUpdater.on('update-downloaded', () => {
      dialog.showMessageBox({
        type: 'info',
        title: 'Update Ready',
        message: 'Restart to apply update?',
        buttons: ['Restart Now', 'Later'],
      }).then(({ response }) => {
        if (response === 0) autoUpdater.quitAndInstall();
      });
    });
  }
}
```

---

## 7. Packaging Configuration

```yaml
# electron-builder.yml
appId: com.ambilight.desktop
productName: Ambilight Desktop
copyright: Copyright © 2026

directories:
  output: dist-packages
  buildResources: build

files:
  - dist/renderer/**
  - dist/main/**
  - dist/preload/**

extraResources:
  - from: dist/service/
    to: service/
    filter: ['**/*']

win:
  target:
    - target: nsis
      arch: [x64, arm64]
    - target: msi
      arch: [x64]
  icon: build/icon.ico
  signingHashAlgorithms: [sha256]

nsis:
  oneClick: false
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: always
  runAfterFinish: true

msi:
  runAfterFinish: false

mac:
  target:
    - target: dmg
      arch: [x64, arm64]
  icon: build/icon.icns
  hardenedRuntime: true
  gatekeeperAssess: false
  entitlements: build/entitlements.mac.plist
  entitlementsInherit: build/entitlements.mac.plist
  notarize:
    teamId: YOUR_TEAM_ID

linux:
  target:
    - target: AppImage
      arch: [x64, arm64]
    - target: deb
      arch: [x64]
    - target: rpm
      arch: [x64]
  icon: build/icons/
  category: Utility
  synopsis: Ambient LED lighting control

publish:
  provider: github
  owner: your-org
  repo: ambilight-desktop
```

---

## 8. Development Workflow

```bash
# Start Python service in dev mode
python -m ambilight.service --dev

# Start Electron in dev mode (hot reload via Vite)
cd electron
npm run dev

# Build production packages
npm run build               # Vite build
npm run electron:build      # PyInstaller + electron-builder

# Type check
npm run typecheck

# Lint
npm run lint
```

---

## 9. Security Checklist

| Control | Status | Implementation |
|---|---|---|
| `nodeIntegration: false` | Required | Set in BrowserWindow options |
| `contextIsolation: true` | Required | Set in BrowserWindow options |
| `sandbox: true` | Required | Set in BrowserWindow options |
| API auth token | Required | Bearer token in all main→service calls |
| Token not exposed to renderer | Required | Token only in main process; renderer calls IPC |
| Content Security Policy | Required | `meta http-equiv` in renderer HTML |
| No `eval()` in renderer | Required | ESLint `no-eval` rule |
| HTTPS for update checks | Required | electron-updater uses HTTPS |
| Code signing | Required | All platforms before public release |
