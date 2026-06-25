"""
Cross-instance device ownership
===============================
Cooperative exclusivity so two Ambilight instances on the same LAN never fight
over the same controller (which would produce last-packet-wins flicker — the
hardware accepts commands from any client and cannot arbitrate).

Each instance announces the devices it wants to drive; a deterministic rule
(priority → earliest claim → lowest instance id) decides the single owner of
each device, and a heartbeat/TTL frees a crashed owner's claim so another
instance can take over. Coordination travels over MQTT when a broker is
configured, else a LAN UDP broadcast.

The :class:`OwnershipCoordinator` lives in the main service process (lifecycle
mirrors ``MqttBridge``) and publishes an ``OWNERSHIP_UPDATE`` event whenever the
owned-device set changes; the pipeline controller relays that to the capture
process, which gates its LED output on it.
"""

from .coordinator import OwnershipCoordinator

__all__ = ["OwnershipCoordinator"]
