"""
Device Discovery Module
=======================
Discovers MagicHome LED controllers on the local network, identifies them by
MAC address (stable across IP changes after router restarts), caches results
to disk, and verifies connectivity before use.

Discovery strategy
------------------
1. **Direct IP** — verify the configured IP first (fastest, no scanning).
2. **UDP broadcast** — send ``HF-A11ASSISTHREAD`` to 255.255.255.255:48899.
   Every MagicHome controller replies with ``{ip},{mac},{model}``, giving the
   real hardware MAC and current IP in 1–2 s regardless of subnet changes.
3. **Cache hit** — if a matching MAC is cached, verify that IP still answers.
4. **TCP scan** — parallel TCP port 5577 scan of the auto-detected local /24
   subnet (falls back to the configured subnet prefix).

The results are cached to ``device_cache.json`` for fast start-up next time.

MAC-based identification
------------------------
The MAC address is obtained from the UDP discovery response — **not** from
the TCP status response.  Bytes 6–11 of the ``0x81 0x8A 0x8B`` reply contain
RGB/W colour data, not the hardware MAC.  Using colour bytes as a MAC would
give a fake ``00:00:00:00:00:00`` for an off device and wrong values otherwise.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# MagicHome TCP port
_MAGIC_PORT = 5577

# Status query command (0x81 0x8a 0x8b) — standard for flux_led protocol
_STATUS_QUERY = bytes([0x81, 0x8A, 0x8B])

# UDP broadcast discovery — standard MagicHome LAN discovery protocol
_UDP_DISCOVERY_MSG = b"HF-A11ASSISTHREAD"
_UDP_DISCOVERY_PORT = 48899


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _local_subnets() -> list[str]:
    """
    Return ``/24`` subnet prefixes for active local interfaces.

    Uses a UDP routing trick: create a socket and call ``connect()`` toward a
    public address; the OS fills in the source IP via the routing table without
    sending any packets.  No extra dependencies, no admin rights required.
    """
    subnets: set[str] = set()
    for target in ("8.8.8.8", "1.1.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            s.close()
            prefix = ".".join(ip.split(".")[:3]) + "."
            subnets.add(prefix)
            break
        except OSError:
            pass
    return list(subnets) if subnets else ["192.168.1."]


def _udp_discover(timeout: float = 2.0) -> "list[DeviceInfo]":
    """
    Broadcast the MagicHome discovery message and parse device responses.

    Each MagicHome controller replies on UDP port 48899 with::

        {ip},{mac_no_colons},{model}

    e.g. ``192.168.1.29,0B0D23000C00,HF-LPB100-ZJ200``

    Returns one :class:`DeviceInfo` per responding device with the real
    hardware MAC.  ``device_type`` is left at 0 — call
    :meth:`CapabilityProbe.probe` afterwards to classify the device.
    """
    found: dict[str, "DeviceInfo"] = {}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.1)          # short per-recv timeout; loop checks deadline
        sock.bind(("", 0))
        sock.sendto(_UDP_DISCOVERY_MSG, ("255.255.255.255", _UDP_DISCOVERY_PORT))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, _ = sock.recvfrom(1024)
                text = data.decode("ascii", errors="replace").strip()
                parts = text.split(",")
                if len(parts) >= 2:
                    ip = parts[0].strip()
                    mac_raw = parts[1].strip().replace(":", "").replace("-", "")
                    model = parts[2].strip() if len(parts) >= 3 else "MagicHome"
                    if len(ip.split(".")) == 4 and len(mac_raw) == 12:
                        mac = ":".join(mac_raw[i:i + 2].lower() for i in range(0, 12, 2))
                        found[ip] = DeviceInfo(ip=ip, mac=mac, model=model, last_seen=time.time())
                        logger.debug("[UDP] Found %s  MAC=%s  model=%s", ip, mac, model)
            except socket.timeout:
                continue
        sock.close()
    except OSError as exc:
        logger.debug("[UDP Discovery] Error: %s", exc)
    if found:
        logger.info("[UDP Discovery] %d device(s) found.", len(found))
    return list(found.values())


def full_scan(
    configured_subnet: str = "192.168.1.",
    discovery_timeout: float = 0.5,
    udp_timeout: float = 2.0,
) -> "list[DeviceInfo]":
    """
    Full discovery: UDP broadcast first, TCP scan fallback.

    Designed for the ``POST /api/devices/scan`` endpoint so the UI always
    gets real MACs and doesn't depend on the configured subnet being correct.

    Steps
    -----
    1. UDP broadcast → collect all respondents (real IP + MAC).
    2. If UDP returns nothing, TCP-scan the auto-detected subnet(s) plus the
       configured subnet.
    3. Enrich every discovered device with ``device_type`` via a parallel
       :class:`CapabilityProbe` pass (needed for addressable vs single-RGB UI).
    """
    by_ip: dict[str, DeviceInfo] = {}

    # 1. UDP broadcast
    for dev in _udp_discover(timeout=udp_timeout):
        by_ip[dev.ip] = dev

    # 2. TCP scan fallback when UDP finds nothing
    if not by_ip:
        subnets_to_scan = list({configured_subnet} | set(_local_subnets()))
        logger.info("[Scan] UDP returned nothing; TCP-scanning %s", subnets_to_scan)
        for subnet in subnets_to_scan:
            scanner = DeviceScanner(subnet=subnet, connect_timeout=discovery_timeout)
            for dev in scanner.scan():
                if dev.ip not in by_ip:
                    by_ip[dev.ip] = dev

    # 3. Enrich device_type via parallel TCP capability probe
    if by_ip:
        cap = CapabilityProbe(connect_timeout=max(discovery_timeout, 0.8))
        with ThreadPoolExecutor(max_workers=min(len(by_ip), 20)) as pool:
            futures = {pool.submit(cap.probe, ip): ip for ip in list(by_ip.keys())}
            for fut in as_completed(futures):
                ip = futures[fut]
                try:
                    info = fut.result()
                    if info and ip in by_ip:
                        by_ip[ip].device_type = info.device_type
                        by_ip[ip].supports_addressable = info.supports_addressable
                        by_ip[ip].supports_rgbw = info.supports_rgbw
                except Exception:
                    pass

    results = list(by_ip.values())

    # Merge WLED devices (mDNS when zeroconf is available, else HTTP subnet
    # probe). Best-effort: a discovery error must never break the MagicHome scan.
    try:
        for w in discover_wled(configured_subnet, discovery_timeout):
            if w.ip not in by_ip:
                results.append(w)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("[Scan] WLED discovery error: %s", exc)

    return results


# ---------------------------------------------------------------------------
# WLED discovery (mDNS with HTTP-probe fallback)
# ---------------------------------------------------------------------------

def _wled_probe(ip: str, timeout: float = 0.5) -> "Optional[DeviceInfo]":
    """Return a WLED :class:`DeviceInfo` if *ip* answers ``GET /json/info``."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://{ip}/json/info", timeout=timeout) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(info, dict) or "leds" not in info:
        return None
    leds = info.get("leds") or {}
    try:
        led_count = int(leds.get("count", 0) or 0)
    except (TypeError, ValueError):
        led_count = 0   # malformed count must not break the None-on-failure contract
    raw = str(info.get("mac", "")).strip()
    mac = ":".join(raw[i:i + 2] for i in range(0, 12, 2)).lower() if len(raw) == 12 else raw.lower()
    return DeviceInfo(
        ip=ip, port=80, mac=mac,
        model=str(info.get("name") or "WLED"),
        firmware=str(info.get("ver", "")),
        supports_addressable=True, protocol="wled",
        led_count=led_count,
        last_seen=time.time(),
    )


def _wled_http_scan(subnets: "list[str]", timeout: float = 0.5, max_workers: int = 64) -> "list[DeviceInfo]":
    """Probe every host on *subnets* with ``GET /json/info`` to find WLED nodes."""
    candidates = [f"{s}{i}" for s in subnets for i in range(1, 255)]
    found: dict[str, DeviceInfo] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_wled_probe, ip, timeout): ip for ip in candidates}
        for fut in as_completed(futures):
            try:
                info = fut.result()
            except Exception:
                info = None
            if info:
                found[info.ip] = info
    return list(found.values())


def _wled_mdns(timeout: float = 2.0) -> "list[DeviceInfo]":
    """Browse ``_wled._tcp.local.`` via zeroconf. Returns [] if zeroconf is absent."""
    try:
        from zeroconf import Zeroconf, ServiceBrowser  # optional dependency
    except Exception:
        return []

    addrs: dict[str, str] = {}

    class _Listener:
        def add_service(self, zc, type_, name):  # noqa: ANN001
            try:
                info = zc.get_service_info(type_, name, timeout=int(timeout * 1000))
                if info and info.parsed_addresses():
                    addrs[info.parsed_addresses()[0]] = name
            except Exception:
                pass

        def update_service(self, *a):  # noqa: ANN001, D401
            pass

        def remove_service(self, *a):  # noqa: ANN001
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, "_wled._tcp.local.", _Listener())
        time.sleep(timeout)
    finally:
        try:
            zc.close()
        except Exception:
            pass

    out: list[DeviceInfo] = []
    for ip in addrs:
        out.append(_wled_probe(ip) or DeviceInfo(
            ip=ip, port=80, supports_addressable=True, protocol="wled",
            model="WLED", last_seen=time.time(),
        ))
    return out


def discover_wled(configured_subnet: str = "192.168.1.", timeout: float = 0.5) -> "list[DeviceInfo]":
    """Discover WLED devices: mDNS first (when zeroconf is present), else an
    HTTP subnet probe across the auto-detected + configured subnets."""
    devices = _wled_mdns(timeout=2.0)
    if devices:
        return devices
    subnets = list({configured_subnet} | set(_local_subnets()))
    return _wled_http_scan(subnets, timeout=max(timeout, 0.4))


# ---------------------------------------------------------------------------
# Device info
# ---------------------------------------------------------------------------

@dataclass
class DeviceInfo:
    """A discovered LED device (MagicHome or WLED)."""
    ip: str
    port: int = _MAGIC_PORT
    mac: str = ""
    model: str = "MagicHome"
    firmware: str = ""
    device_type: int = 0
    supports_addressable: bool = False
    supports_rgbw: bool = False
    protocol: str = "magichome"   # magichome | wled
    led_count: int = 0            # known LED count (WLED reports it; 0 = unknown)
    last_seen: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class DeviceScanner:
    """
    Scans the local subnet for MagicHome LED controllers.

    Parameters
    ----------
    subnet:
        Network prefix, e.g. ``"192.168.1."``.
    connect_timeout:
        TCP connect timeout per host in seconds.
    max_workers:
        Thread pool size for parallel scanning.
    """

    def __init__(
        self,
        subnet: str = "192.168.1.",
        connect_timeout: float = 0.5,
        max_workers: int = 120,
    ) -> None:
        self._subnet = subnet
        self._timeout = connect_timeout
        self._max_workers = max_workers

    def scan(self) -> list[DeviceInfo]:
        """
        Perform a full subnet scan and return all discovered devices.

        Returns
        -------
        list[DeviceInfo]
            All responsive MagicHome devices found on the subnet.
        """
        logger.info(
            "[Scanner] Starting subnet scan on %s1-254 (port %d).",
            self._subnet, _MAGIC_PORT,
        )
        t0 = time.monotonic()
        candidates: list[str] = [f"{self._subnet}{i}" for i in range(1, 255)]
        devices: list[DeviceInfo] = []
        lock = threading.Lock()

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(self._probe, ip): ip for ip in candidates}
            for fut in as_completed(futures):
                result = fut.result()
                if result is not None:
                    with lock:
                        devices.append(result)

        elapsed = time.monotonic() - t0
        logger.info(
            "[Scanner] Scan complete in %.1f s — %d device(s) found.",
            elapsed, len(devices),
        )
        return devices

    def _probe(self, ip: str) -> Optional[DeviceInfo]:
        """
        Connect to *ip*:5577, send a status query, and parse the response.

        Returns *None* if the host is unreachable or not a MagicHome device.

        Validation: a valid MagicHome status reply always has ``byte[0] == 0x81``
        and is at least 2 bytes long.  MAC address is **not** extracted here —
        bytes 6–11 of the response are RGB/W colour data, not the hardware MAC.
        Use :func:`_udp_discover` to obtain real MACs.
        """
        try:
            with socket.create_connection((ip, _MAGIC_PORT), timeout=self._timeout) as sock:
                sock.settimeout(self._timeout)
                sock.sendall(_STATUS_QUERY)
                try:
                    data = sock.recv(128)
                except socket.timeout:
                    return None

                if not data:
                    return None

                # byte 0 of a genuine MagicHome status reply is always 0x81
                if len(data) < 2 or data[0] != 0x81:
                    return None

                _, firmware, device_type = self._parse_status(data)
                info = DeviceInfo(
                    ip=ip,
                    device_type=device_type,
                    supports_addressable=device_type in (0x04, 0x35),
                    supports_rgbw=device_type in (0x44, 0x35),
                    last_seen=time.time(),
                )
                logger.debug("[Scanner] Found device at %s (Type=0x%02x).", ip, device_type)
                return info

        except (OSError, ConnectionRefusedError, socket.timeout):
            return None

    @staticmethod
    def _parse_status(data: bytes) -> tuple[str, str, int]:
        """
        Parse MagicHome TCP status response.

        Response layout (``0x81 0x8A 0x8B`` query, 11–14 bytes):

        ======  =====================================================
        Byte    Meaning
        ======  =====================================================
        0       ``0x81``  (response header — always this value)
        1       device_type  (``0x44``=RGB, ``0x04``=addressable, …)
        2       power state  (``0x23``=on, ``0x24``=off)
        3       mode  (``0x61``=static, …)
        4       speed
        5       Red
        6       Green   **← colour data, NOT part of MAC**
        7       Blue
        8       White
        9–12    padding
        13      checksum
        ======  =====================================================

        **The MAC address is not carried in this response.**  It is obtained
        from the UDP discovery broadcast (``HF-A11ASSISTHREAD``) instead.
        """
        mac = ""
        firmware = ""
        device_type = 0
        if len(data) >= 2 and data[0] == 0x81:
            try:
                device_type = data[1]
            except Exception:
                pass
        return mac, firmware, device_type


# ---------------------------------------------------------------------------
# Capability probe
# ---------------------------------------------------------------------------

def classify_device(info: DeviceInfo) -> str:
    """Return a coarse capability kind: ``addressable`` | ``rgbw`` | ``single``."""
    if info.supports_addressable:
        return "addressable"
    if info.supports_rgbw:
        return "rgbw"
    return "single"


class CapabilityProbe:
    """
    Live capability detection for a single MagicHome controller (FR-DEV-04).

    Connects to ``ip``:5577, issues the standard status query, and classifies the
    device. Reuses :meth:`DeviceScanner._parse_status` so the byte layout lives in
    exactly one place.
    """

    def __init__(self, connect_timeout: float = 1.0) -> None:
        self._timeout = connect_timeout

    def probe(self, ip: str, port: int = _MAGIC_PORT) -> Optional[DeviceInfo]:
        try:
            with socket.create_connection((ip, port), timeout=self._timeout) as sock:
                sock.settimeout(self._timeout)
                sock.sendall(_STATUS_QUERY)
                try:
                    data = sock.recv(128)
                except socket.timeout:
                    return None
            if not data:
                logger.debug("[CapabilityProbe] %s connected but returned no data.", ip)
                return None
            if len(data) < 2 or data[0] != 0x81:
                logger.debug("[CapabilityProbe] %s returned non-MagicHome response (byte0=0x%02x).", ip, data[0])
                return None
            _, firmware, device_type = DeviceScanner._parse_status(data)
            return DeviceInfo(
                ip=ip,
                port=port,
                firmware=firmware,
                device_type=device_type,
                supports_addressable=device_type in (0x04, 0x35),
                supports_rgbw=device_type in (0x44, 0x35),
                last_seen=time.time(),
            )
        except (OSError, socket.timeout) as exc:
            logger.debug("[CapabilityProbe] %s unreachable: %s", ip, exc)
            return None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class DeviceCache:
    """
    Persists discovered :class:`DeviceInfo` objects to a JSON file.

    Parameters
    ----------
    path:
        File path for the cache JSON.
    """

    def __init__(self, path: str = "device_cache.json") -> None:
        self._path = Path(path)

    def load(self) -> list[DeviceInfo]:
        """Load cached devices, returning an empty list if the file is absent."""
        if not self._path.exists():
            return []
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            
            now = time.time()
            valid_devices = []
            for d in data:
                device = DeviceInfo.from_dict(d)
                # Expire devices older than 7 days (7 * 86400 seconds)
                if now - device.last_seen < 604800:
                    valid_devices.append(device)
            
            devices = valid_devices
            logger.debug("[Cache] Loaded %d valid device(s) from cache (expired %d).", len(devices), len(data) - len(devices))
            return devices
        except Exception as exc:
            logger.warning("[Cache] Failed to load device cache: %s", exc)
            return []

    def save(self, devices: list[DeviceInfo]) -> None:
        """Write *devices* to the cache file."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as fh:
                json.dump([d.to_dict() for d in devices], fh, indent=2)
            logger.debug("[Cache] Saved %d device(s) to cache.", len(devices))
        except Exception as exc:
            logger.warning("[Cache] Failed to save device cache: %s", exc)


# ---------------------------------------------------------------------------
# Discovery manager
# ---------------------------------------------------------------------------

class DeviceDiscovery:
    """
    High-level device discovery service.

    Combines cache look-up, subnet scanning, and connectivity verification
    into a single :meth:`find_device` call.

    Parameters
    ----------
    preferred_ip:
        IP address to try first (from configuration).
    preferred_mac:
        MAC address to prefer.  When set, the discovery will search the
        network for this specific device after a router restart changes IPs.
    subnet:
        Network prefix for active scanning.
    connect_timeout:
        TCP connection timeout in seconds.
    discovery_timeout:
        Per-host probe timeout during scanning.
    cache_file:
        Path to the JSON device cache.
    """

    def __init__(
        self,
        preferred_ip: str = "",
        preferred_mac: str = "",
        subnet: str = "192.168.1.",
        connect_timeout: float = 2.0,
        discovery_timeout: float = 0.5,
        cache_file: str = "device_cache.json",
    ) -> None:
        self._preferred_ip = preferred_ip
        self._preferred_mac = preferred_mac.lower().replace("-", ":").strip()
        self._connect_timeout = connect_timeout
        self._discovery_timeout = discovery_timeout
        self._subnet = subnet
        self._cache = DeviceCache(path=cache_file)

    def find_device(self) -> Optional[DeviceInfo]:
        """
        Locate the best MagicHome device.

        Strategy
        --------
        1. If *preferred_ip* is configured, verify it first (no scanning).
        2. UDP broadcast discovery — fast, gets the real current IP and MAC
           even after a DHCP lease change.
        3. Cache lookup by MAC — avoids a full scan when the IP is known.
        4. TCP subnet scan — parallel probe of the auto-detected local /24.

        Returns
        -------
        DeviceInfo or None
        """
        # 1. Direct IP check
        if self._preferred_ip:
            if self._verify(self._preferred_ip):
                logger.info("[Discovery] Device confirmed at configured IP %s.", self._preferred_ip)
                info = DeviceInfo(ip=self._preferred_ip, mac=self._preferred_mac, last_seen=time.time())
                self._cache.save([info])
                return info
            else:
                logger.warning(
                    "[Discovery] Configured IP %s unreachable; trying UDP discovery.",
                    self._preferred_ip,
                )

        # 2. UDP broadcast discovery (fast, real MACs)
        logger.info("[Discovery] Running UDP broadcast discovery…")
        udp_devices = _udp_discover(timeout=2.0)
        if udp_devices:
            # Prefer MAC match if a preferred MAC is configured
            if self._preferred_mac:
                for dev in udp_devices:
                    if dev.mac.lower() == self._preferred_mac:
                        logger.info("[Discovery] MAC match via UDP: %s (MAC %s).", dev.ip, dev.mac)
                        self._enrich_device_type(dev)
                        self._cache.save(udp_devices)
                        return dev
                logger.warning(
                    "[Discovery] UDP found %d device(s) but none matched MAC %s; "
                    "using first device.",
                    len(udp_devices), self._preferred_mac,
                )
            dev = udp_devices[0]
            self._enrich_device_type(dev)
            self._cache.save(udp_devices)
            return dev

        # 3. Cache lookup by MAC
        cached = self._cache.load()
        if self._preferred_mac:
            for device in cached:
                if device.mac.lower() == self._preferred_mac:
                    if self._verify(device.ip):
                        logger.info(
                            "[Discovery] Device found via cache: %s (MAC %s).",
                            device.ip, device.mac,
                        )
                        device.last_seen = time.time()
                        self._cache.save([device])
                        return device
                    else:
                        logger.debug(
                            "[Discovery] Cached IP %s for MAC %s no longer responds.",
                            device.ip, device.mac,
                        )

        # 4. TCP subnet scan on auto-detected + configured subnet
        subnets = list({self._subnet} | set(_local_subnets()))
        for subnet in subnets:
            found = DeviceScanner(subnet=subnet, connect_timeout=self._discovery_timeout).scan()
            if not found:
                continue
            if self._preferred_mac:
                for dev in found:
                    if dev.mac.lower() == self._preferred_mac:
                        logger.info("[Discovery] MAC match after TCP scan: %s.", dev.ip)
                        self._cache.save(found)
                        return dev
            logger.info("[Discovery] TCP scan found %d device(s) on subnet %s.", len(found), subnet)
            self._cache.save(found)
            return found[0]

        logger.error("[Discovery] No MagicHome devices found after all discovery methods.")
        return None

    def _enrich_device_type(self, dev: DeviceInfo) -> None:
        """Fill device_type / supports_* via a quick TCP capability probe."""
        probe = CapabilityProbe(connect_timeout=self._connect_timeout)
        info = probe.probe(dev.ip, dev.port)
        if info:
            dev.device_type = info.device_type
            dev.supports_addressable = info.supports_addressable
            dev.supports_rgbw = info.supports_rgbw

    def _verify(self, ip: str) -> bool:
        """Return True if *ip* responds on port 5577 within timeout."""
        try:
            with socket.create_connection((ip, _MAGIC_PORT), timeout=self._connect_timeout):
                return True
        except (OSError, socket.timeout):
            return False
