# WLED support

Ambilight Desktop drives [WLED](https://kno.wled.ge) controllers alongside
MagicHome. WLED is always **addressable**, so screen-sync renders a per-pixel
gradient across the strip.

## How it works

- **Per-pixel colour** is streamed over **realtime UDP** (port `21324`) using
  WLED's DRGB protocol (or chunked DNRGB for strips longer than 490 LEDs). This
  is the low-latency hot path — the same approach Hyperion/Prismatik use.
- **Power / brightness** uses the **JSON API over HTTP** (`POST /json/state`),
  and the live LED count is read from `GET /json/info` on connect.

No realtime mode needs to be pre-selected in WLED — incoming UDP realtime
packets temporarily take over and WLED reverts to its normal effect a couple of
seconds after the stream stops.

## Adding a WLED device

1. Make sure the WLED device is on the same network and reachable over HTTP.
2. In **Devices → Scan Network**, WLED nodes appear with a **WLED** badge
   (discovered via mDNS when available, otherwise an HTTP subnet probe). You can
   also add one manually: enter its IP and pick **WLED** in the protocol
   selector.
3. **Add** it, choose the target monitor and confirm the LED count (auto-filled
   from the device), then **Test** to flash it.

### Optional: mDNS auto-discovery

Auto-discovery via `_wled._tcp` mDNS requires the optional `zeroconf` package
(`pip install zeroconf`). Without it, the HTTP subnet probe and manual IP entry
still find and add WLED devices.

## Config example

WLED devices live in the same `devices:` list as MagicHome — just set
`protocol: wled`:

```yaml
devices:
  - protocol: wled
    ip: 192.168.1.50
    monitor_index: 0
    led_count: 120
    name: Desk WLED
    enabled: true
  - protocol: magichome      # the default when omitted
    ip: 192.168.1.29
    monitor_index: 1
    led_count: 30
    enabled: true
```

`port` is optional: for WLED it is the HTTP API port (default `80`); the
realtime UDP port is fixed at `21324`.
