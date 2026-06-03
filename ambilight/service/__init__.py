"""
Ambilight Service Package
=========================
Runnable as a module::

    python -m ambilight.service

This is the dedicated, supervisable entry point for the background service
(distinct from the legacy ``main.py`` CLI, which is preserved for rollback).
It loads configuration, applies environment overrides, and launches the
FastAPI application (REST + WebSocket) via uvicorn.
"""
