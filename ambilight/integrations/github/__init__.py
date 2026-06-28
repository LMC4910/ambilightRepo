"""
GitHub integration ("Ambient GitHub Awareness")
===============================================
Turns GitHub activity into ambient lighting. The integration polls GitHub
(works behind NAT — no public endpoint needed), normalises every event into one
model, resolves a user-configured colour/effect via a rule hierarchy
(workflow → repo → org → global), and hands the flash to the pipeline.

It sits on top of the same substrate as the other integrations: the event bus,
the typed config, the OS-keyring secret store, and ``PipelineController.flash``.
The whole thing is **off by default** and degrades to a no-op when the optional
``httpx`` dependency is absent, mirroring the MQTT bridge / notification flash.

Public surface: :class:`GithubIntegration` (constructed in ``api_server`` at
startup, refreshed on ``CONFIG_UPDATE``).
"""

from __future__ import annotations

from .service import GithubIntegration

__all__ = ["GithubIntegration"]
