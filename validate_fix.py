#!/usr/bin/env python3
"""
Validate that the WebSocket authentication bug fix is in place
"""
import sys
import os

def validate_fix():
    """Check that the api_server.py has the correct import and usage"""
    
    api_server_path = os.path.join(os.path.dirname(__file__), "ambilight", "api_server.py")
    
    with open(api_server_path, 'r') as f:
        content = f.read()
    
    # Check 1: Make sure we're NOT importing _current_token directly
    if "from .auth import generate_and_save_token, verify_token, _current_token" in content:
        print("❌ FAILED: api_server.py is still importing _current_token directly")
        print("   This causes the stale reference bug where the imported value")
        print("   doesn't get updated when generate_and_save_token() is called")
        return False
    
    # Check 2: Make sure we ARE importing the auth module
    if "from . import auth" not in content:
        print("❌ FAILED: api_server.py is not importing the auth module")
        return False
    
    # Check 3: Make sure the WebSocket endpoint uses auth._current_token
    if "token != auth._current_token" not in content:
        print("❌ FAILED: WebSocket endpoint is not using auth._current_token")
        return False
    
    # Check 4: Verify the WebSocket endpoint looks correct
    if "async def websocket_endpoint(websocket: WebSocket)" in content:
        print("✅ WebSocket endpoint function found")
    else:
        print("❌ FAILED: WebSocket endpoint function not found")
        return False
    
    print("✅ All validation checks passed!")
    print("   - auth module is imported correctly")
    print("   - _current_token is accessed dynamically via auth._current_token")
    print("   - WebSocket endpoint will use the current token value")
    return True


if __name__ == "__main__":
    if validate_fix():
        print("\n✅ FIX VALIDATED: The WebSocket authentication bug has been fixed!")
        print("\nExplanation of the fix:")
        print("- The original bug: importing _current_token as a value captured it as None at import time")
        print("- When generate_and_save_token() updates _current_token in the auth module,")
        print("  the imported reference in api_server.py still points to the old None value")
        print("- The fix: import the auth module and access auth._current_token dynamically")
        print("- Now the WebSocket endpoint always compares against the current token value")
        sys.exit(0)
    else:
        print("\n❌ FIX NOT VALIDATED")
        sys.exit(1)
