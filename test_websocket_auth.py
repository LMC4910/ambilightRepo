#!/usr/bin/env python3
"""
Simple test to verify WebSocket authentication fix
"""
import sys
import asyncio
import subprocess
import time
import os
import signal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_websocket_auth():
    """Test WebSocket connection with valid token"""
    try:
        # Import required libraries
        import websockets
        from websockets.exceptions import InvalidStatusException
    except ImportError:
        logger.error("websockets library not found. Install with: pip install websockets")
        return False
    
    # Start the API server in a subprocess
    logger.info("[TEST] Starting API server...")
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    try:
        # Wait for server to start and generate token
        time.sleep(5)
        
        # Read the token from file
        token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_token")
        if not os.path.exists(token_file):
            logger.error("[TEST] auth_token file not found")
            return False
        
        with open(token_file, 'r') as f:
            token = f.read().strip()
        
        logger.info(f"[TEST] Read token from file: {token[:16]}...")
        
        # Test WebSocket connection with valid token
        try:
            async with websockets.connect(f"ws://127.0.0.1:7826/ws?token={token}", ping_interval=None) as ws:
                logger.info("[TEST] ✅ WebSocket connection SUCCESSFUL with valid token (101 Switching Protocols)")
                return True
        except InvalidStatusException as e:
            if "403" in str(e):
                logger.error("[TEST] ❌ WebSocket connection REJECTED with 403 Forbidden")
                logger.error(f"Error: {e}")
                return False
            else:
                logger.error(f"[TEST] ❌ Unexpected status error: {e}")
                return False
        except Exception as e:
            logger.error(f"[TEST] ❌ WebSocket connection failed: {e}")
            return False
            
    finally:
        # Stop the server
        logger.info("[TEST] Stopping API server...")
        try:
            os.kill(proc.pid, signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception as e:
            logger.warning(f"Failed to stop server gracefully: {e}")
            try:
                proc.kill()
            except:
                pass


if __name__ == "__main__":
    try:
        result = asyncio.run(test_websocket_auth())
        if result:
            logger.info("[TEST] ✅ TEST PASSED: WebSocket authentication is working correctly!")
            sys.exit(0)
        else:
            logger.error("[TEST] ❌ TEST FAILED: WebSocket authentication is not working!")
            sys.exit(1)
    except Exception as e:
        logger.error(f"[TEST] Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
