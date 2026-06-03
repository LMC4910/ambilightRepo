"""
Authentication Module
=====================
Secures the internal API. The Electron UI and the Python Service run on the
same machine, but binding to localhost isn't enough to prevent other local
applications or malicious scripts from accessing the API.

This module generates a secure Bearer token on startup, writes it to a file
with strict 0600 permissions, and forces all incoming REST and WebSocket
connections to authenticate using it.
"""

import logging
import os
import secrets
import stat
from typing import Optional

from fastapi import HTTPException, Security, Request, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# Store the token in the per-user data directory (NFR-S-04) so the service and
# the Electron UI agree on its location regardless of the service's working
# directory. The UI reads ~/.ambilight/auth_token.
AMBILIGHT_DIR = os.path.join(os.path.expanduser("~"), ".ambilight")
AUTH_TOKEN_PATH = os.path.join(AMBILIGHT_DIR, "auth_token")
_current_token: Optional[str] = None

def generate_and_save_token() -> str:
    """Generate a high-entropy token and save it to disk with strict permissions."""
    global _current_token
    _current_token = secrets.token_hex(32)

    # Secure file writing: 0600 permissions (read/write by owner only)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    mode = stat.S_IRUSR | stat.S_IWUSR

    try:
        os.makedirs(AMBILIGHT_DIR, exist_ok=True)
        if os.path.exists(AUTH_TOKEN_PATH):
            # Attempt to enforce permissions if it already exists, just in case
            os.chmod(AUTH_TOKEN_PATH, mode)
            
        fd = os.open(AUTH_TOKEN_PATH, flags, mode)
        with os.fdopen(fd, 'w') as f:
            f.write(_current_token)
        logger.info("[Auth] Generated secure authentication token.")
    except Exception as exc:
        logger.error("[Auth] Failed to write auth token securely: %s", exc)
        
    return _current_token


bearer_scheme = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)) -> str:
    """Dependency for REST endpoints to verify Bearer token."""
    if not _current_token:
        raise HTTPException(status_code=500, detail="Authentication not initialized.")
        
    if credentials.credentials != _current_token:
        logger.warning("[Auth] Unauthorized REST access attempt.")
        raise HTTPException(status_code=403, detail="Invalid token.")
        
    return credentials.credentials


async def verify_ws_token(websocket: WebSocket) -> str:
    """Helper to verify WebSocket connections via query parameter `?token=...`"""
    if not _current_token:
        raise HTTPException(status_code=500, detail="Authentication not initialized.")
        
    token = websocket.query_params.get("token")
    if token != _current_token:
        logger.warning("[Auth] Unauthorized WebSocket access attempt.")
        # FastAPI's WebSocket endpoint doesn't catch HTTPExceptions cleanly before accept,
        # but we can return False or handle it in the endpoint.
        raise HTTPException(status_code=403, detail="Invalid token")
        
    return token
