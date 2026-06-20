"""
Device Discovery Module
=======================
Discovers MagicHome LED controllers on the local network, identifies them by
MAC address (stable across IP changes after router restarts), caches results
to disk, and verifies connectivity before use.

Discovery strategy
------------------
1. **Cache hit** — load the saved ``device_cache.json`` and verify each entry
   is still reachable on TCP port 5577.
2. **Active scan** — parallel TCP port scan of the configured subnet.
3. **Interrogation** — send the MagicHome ``0x81 0x8a 0x8b`` status request
   and parse the response to confirm the device is a compatible LED controller
   and to extract the firmware version.

The results are cached to ``device_cache.json`` for fast start-up next time.

MAC-based identification
------------------------
MagicHome controllers expose their MAC address in the status response.  When
a ``mac`` is configured, the discovery module ignores IP changes and searches
for the device with the matching MAC on every scan — making the system robust
to DHCP address changes.
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
_STATUS_RESPONSE_LEN = 14


# ---------------------------------------------------------------------------
# Device info
# ---------------------------------------------------------------------------

@dataclass
class DeviceInfo:
    """Discovered MagicHome device."""
    ip: str
    port: int = _MAGIC_PORT
    mac: str = ""
    model: str = "MagicHome"
    firmware: str = ""
    device_type: int = 0
    supports_addressable: bool = False
    supports_rgbw: bool = False
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

                mac, firmware, device_type = self._parse_status(data)
                if not mac:
                    return None

                info = DeviceInfo(
                    ip=ip,
                    mac=mac,
                    firmware=firmware,
                    device_type=device_type,
                    supports_addressable=device_type in (0x04, 0x35),
                    supports_rgbw=device_type in (0x44, 0x35),
                    last_seen=time.time(),
                )
                logger.debug("[Scanner] Found device at %s (MAC=%s, Type=0x%02x).", ip, mac or "?", device_type)
                return info

        except (OSError, ConnectionRefusedError, socket.timeout):
            return None

    @staticmethod
    def _parse_status(data: bytes) -> tuple[str, str, int]:
        """
        Parse MagicHome status response.

        The 14-byte response encodes device state; bytes 6-11 contain the
        6-byte MAC address in many firmware revisions. Byte 1 is device type.
        If parsing fails we return empty strings and 0.
        """
        mac = ""
        firmware = ""
        device_type = 0
        if len(data) >= _STATUS_RESPONSE_LEN:
            try:
                device_type = data[1]
                mac_bytes = data[6:12]
                mac = ":".join(f"{b:02x}" for b in mac_bytes)
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
                    data = b""
            if not data:
                logger.debug("[CapabilityProbe] %s connected but returned no data.", ip)
                return None
            mac, firmware, device_type = DeviceScanner._parse_status(data)
            return DeviceInfo(
                ip=ip,
                port=port,
                mac=mac,
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
        self._scanner = DeviceScanner(subnet=subnet, connect_timeout=discovery_timeout)
        self._cache = DeviceCache(path=cache_file)

    def find_device(self) -> Optional[DeviceInfo]:
        """
        Locate the best MagicHome device.

        Strategy:

        1. If *preferred_ip* is set, verify it first.
        2. Check the cache for a matching MAC.
        3. Fall back to an active subnet scan.

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
                    "[Discovery] Configured IP %s unreachable; scanning network.",
                    self._preferred_ip,
                )

        # 2. Cache lookup by MAC
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

        # 3. Full subnet scan
        found = self._scanner.scan()
        if not found:
            logger.error("[Discovery] No MagicHome devices found on subnet.")
            return None

        # Prefer MAC match
        if self._preferred_mac:
            for dev in found:
                if dev.mac.lower() == self._preferred_mac:
                    logger.info(
                        "[Discovery] MAC match after scan: %s.", dev.ip
                    )
                    self._cache.save(found)
                    return dev

        # Return first responsive device
        self._cache.save(found)
        return found[0]

    def _verify(self, ip: str) -> bool:
        """Return True if *ip* responds on port 5577 within timeout."""
        try:
            with socket.create_connection((ip, _MAGIC_PORT), timeout=self._connect_timeout):
                return True
        except (OSError, socket.timeout):
            return False
