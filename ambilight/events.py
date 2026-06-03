"""
Event Bus Module
================
Provides an asyncio-based internal publish/subscribe Event Bus.
This decoupled architecture allows components (like the Display Monitor,
Config Manager, and API Server) to communicate without direct dependencies.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List

logger = logging.getLogger(__name__)

# Type alias for async event callbacks
EventCallback = Callable[..., Awaitable[None]]


class EventBus:
    """
    Asynchronous Publish/Subscribe Event Bus.
    """
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventCallback]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """Register a callback for an event type."""
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
            logger.debug("[EventBus] Subscribed to %s", event_type)

    async def unsubscribe(self, event_type: str, callback: EventCallback) -> None:
        """Remove a callback for an event type."""
        async with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                    logger.debug("[EventBus] Unsubscribed from %s", event_type)
                except ValueError:
                    pass

    async def publish(self, event_type: str, *args: Any, **kwargs: Any) -> None:
        """
        Publish an event to all subscribers asynchronously.
        Handlers are executed concurrently. Exceptions in handlers are caught and logged.
        """
        async with self._lock:
            if event_type not in self._subscribers:
                return
            callbacks = list(self._subscribers[event_type])

        if not callbacks:
            return

        logger.debug("[EventBus] Publishing event: %s", event_type)
        
        # Fire-and-forget execution of handlers
        tasks = []
        for cb in callbacks:
            task = asyncio.create_task(self._safe_execute(cb, event_type, *args, **kwargs))
            tasks.append(task)
            
    async def _safe_execute(self, cb: EventCallback, event_type: str, *args: Any, **kwargs: Any) -> None:
        try:
            await cb(*args, **kwargs)
        except Exception as exc:
            logger.exception("[EventBus] Error in handler for event '%s': %s", event_type, exc)

# Global singleton instance for the service
bus = EventBus()
