"""Notification Flash — listen for OS notifications and flash the LEDs.

Public surface re-exported for convenience; see :mod:`.service` for the
orchestrator wired up in the API server.
"""

from .base import (
    NotificationEvent,
    NotificationListener,
    get_notification_listener,
)
from .icon_color import icon_dominant_color
from .service import NotificationFlashService

__all__ = [
    "NotificationEvent",
    "NotificationListener",
    "get_notification_listener",
    "icon_dominant_color",
    "NotificationFlashService",
]
