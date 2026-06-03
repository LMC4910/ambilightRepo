"""
build_windows.py  (compatibility shim)
======================================
Superseded by the cross-platform ``build.py``. This shim is kept so existing
docs/commands (``python build_windows.py --service``) keep working; it simply
forwards to ``build.py``.

    python build_windows.py            # service + UI for the current OS
    python build_windows.py --service  # service only
    python build_windows.py --ui       # UI only
"""

from build import main

if __name__ == "__main__":
    print("[note] build_windows.py is deprecated; use build.py (cross-platform).")
    main()
