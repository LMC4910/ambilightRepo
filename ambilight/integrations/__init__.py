"""
Smart-home integrations
========================
Optional outward integrations that sit on top of the service's event bus and
control surface — currently the MQTT bridge + Home Assistant auto-discovery
(Phase C). Each integration degrades gracefully when its optional dependency
(e.g. ``paho-mqtt``) is absent and is off by default.
"""
