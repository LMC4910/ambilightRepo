# MQTT bridge & Home Assistant

Ambilight can connect to an MQTT broker to publish live state and accept
commands, and it auto-creates entities in **Home Assistant** via MQTT discovery.
The integration is **off by default**.

## Requirements

Install the optional integration dependencies into the service's Python
environment:

```bash
pip install paho-mqtt keyring
```

- `paho-mqtt` — the MQTT client. Without it the bridge is a no-op.
- `keyring` — stores the broker password in the OS credential store (Windows
  Credential Manager / macOS Keychain / Linux Secret Service). Without it the
  password falls back to a session-only value (a warning is logged); it is never
  written to `configuration.yaml` either way.

For frozen installers, install both in the PyInstaller build environment (they
are bundled automatically when present — see `build.py`).

## Enable it

In **Settings → MQTT / Home Assistant** (or `configuration.yaml`):

| Field | Meaning |
|---|---|
| `enabled` | Turn the bridge on |
| `broker` | Broker host/IP (blank disables) |
| `port` | Broker port (default `1883`; `8883` for TLS) |
| `username` / `password` | Broker credentials (password → OS keyring) |
| `tls` | Use TLS/SSL |
| `base_topic` | Topic prefix (default `ambilight`) |
| `ha_discovery` | Publish Home Assistant discovery configs |
| `device_id` | Stable HA device id (blank = hostname) |

With `ha_discovery` on, Home Assistant shows one **Ambilight** device with a
light (power / RGB / mode), a **profile** select, and **FPS / syncing / devices**
sensors. Toggling MQTT off removes the entities.

## Topics (base `ambilight`)

| Topic | Direction | Payload |
|---|---|---|
| `ambilight/availability` | state (retained) | `online` / `offline` (LWT) |
| `ambilight/light/state` | state (retained) | JSON `{state, color, effect}` |
| `ambilight/light/set` | command | JSON `{state, color:{r,g,b}, effect}` |
| `ambilight/profile/state` | state (retained) | active profile name |
| `ambilight/profile/set` | command | profile name |
| `ambilight/sensor/fps` | state (retained) | frames/sec |
| `ambilight/sensor/syncing` | state (retained) | `ON` / `OFF` |
| `ambilight/sensor/devices` | state (retained) | connected device count |

Command mapping: `state: OFF` powers off; an `effect` selects a mode
(`screen_sync`, `rainbow`, …); a `color` sets a static colour; `state: ON` alone
resumes screen-sync.

## Security

The bridge binds nothing new — it only connects out to your broker. Use a broker
account with a strong password and enable `tls` for connections that leave the
host. The broker password lives in the OS keyring, not in the config file.
